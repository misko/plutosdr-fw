"""Radio C association and wire port against the independent Python GLS1 oracle."""
import ctypes as c
import random
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tools.starlink_glrt_schedule_abi import ScheduleBatch, ScheduleSnapshot, ScheduledResult


class Batch(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in ("epoch", "tag")]+[
        (name, c.c_uint64) for name in ("start", "period", "step", "delta", "expires")]+[
        (name, c.c_uint32) for name in ("fraction", "seed", "repeats")]


class Estimate(c.Structure):
    _fields_ = [(name, c.c_double) for name in ("delay", "residual", "cfo", "coherence", "linearized")]+[
        ("rejection", c.c_uint32)]


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("schedule-port")/"port.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
        str(root/"tools/glrt_native_schedule.c"), str(root/"tools/glrt_native_solver.c"),
        "-lm", "-o", str(out)], check=True)
    lib = c.CDLL(str(out))
    u32p = c.POINTER(c.c_uint32)
    lib.glrt_native_batch_valid.argtypes = [c.POINTER(Batch)]
    lib.glrt_native_batch_encode.argtypes = [c.POINTER(Batch), c.c_char_p, c.c_size_t]
    lib.glrt_native_prediction.argtypes = [c.POINTER(Batch), c.c_uint, c.POINTER(c.c_uint64), u32p]
    lib.glrt_native_head_parse.argtypes = [c.c_char_p, c.c_size_t, u32p, u32p]
    lib.glrt_native_snapshot_parse.argtypes = [c.c_char_p, c.c_size_t, u32p]
    lib.glrt_native_snapshot_drained.argtypes = [u32p]
    lib.glrt_native_associated_solve.argtypes = [c.POINTER(Batch), c.c_uint32, c.c_uint32,
        u32p, c.POINTER(Estimate)]
    return lib


def batch():
    return ScheduleBatch(3, 7, 2**60+1000, 0, 80000*65536, 7310173*65536,
        2**48-65536, 17, 64, 2**60+1000+64*80000)


def cbatch(b):
    return Batch(**{name: getattr(b, name) for name, _ in Batch._fields_})


def words(b, repeat=0, sequence=0):
    start, step = b.prediction(repeat)
    w = [0]*32
    w[:9] = [0x474c5331, sequence, b.tag, start % 2**32, start >> 32,
        b.seed, step, 79200, 0]
    w[25:28] = [60000000, 79200, repeat]
    return w


def head_text(b, w):
    return ("GLS1 00010000 "+" ".join(f"{x:08x}" for x in (b.epoch, *w))+"\n").encode()


def test_c_predicts_exact_high_index_and_modulo_carrier_like_fraction_oracle(port):
    rng = random.Random(182)
    for _ in range(500):
        b = replace(batch(), fraction=rng.choice([0, 32767, 32768, 32769, 65535]),
            period=80000*65536+rng.randrange(65536), start=2**60+rng.randrange(100000),
            step=rng.randrange(2**48), delta=rng.randrange(2**48), expires=2**60+6000000)
        native = cbatch(b)
        start, step = c.c_uint64(), c.c_uint32()
        for repeat in (0, 1, 2, 31, 63):
            assert port.glrt_native_prediction(c.byref(native), repeat, c.byref(start), c.byref(step)) == 0
            assert (start.value, step.value) == b.prediction(repeat)
        text = c.create_string_buffer(256)
        n = port.glrt_native_batch_encode(c.byref(native), text, len(text))
        assert n == len(b.encode()) and text.value.decode() == b.encode()


@pytest.mark.parametrize("start,fraction,step", [(1000,32768,2**48-32768),
    (1001,32768,32768), (1000,32768,65536+32768)])
def test_both_ties_round_to_even_and_carrier_wrap_is_exact(port, start, fraction, step):
    b = replace(batch(), start=start, fraction=fraction, step=step)
    native = cbatch(b)
    actual_start, actual_step = c.c_uint64(), c.c_uint32()
    assert port.glrt_native_prediction(c.byref(native), 0, c.byref(actual_start), c.byref(actual_step)) == 0
    assert (actual_start.value, actual_step.value) == b.prediction(0)


@pytest.mark.parametrize("field,value", [("epoch",0), ("tag",0), ("fraction",65536),
    ("repeats",0), ("repeats",65), ("start",511), ("expires",0),
    ("period",79328*65536-1), ("period",81000*65536+1), ("step",2**48), ("delta",2**48)])
def test_invalid_descriptor_never_serializes(port, field, value):
    native = cbatch(batch())
    setattr(native, field, value)
    text = c.create_string_buffer(256)
    assert not port.glrt_native_batch_valid(c.byref(native))
    assert port.glrt_native_batch_encode(c.byref(native), text, len(text)) == -1


@pytest.mark.parametrize("start,fraction,expires,repeat", [
    (2**64-1,32768,2**64-1,0), (2**64-80000,0,2**64-1,1),
    (1000,0,1000+79198,0), (1000,0,10000000,64)])
def test_overflow_expiry_or_missing_repeat_cannot_publish_a_prediction(port, start, fraction, expires, repeat):
    b = replace(batch(), start=start, fraction=fraction, expires=expires)
    native = cbatch(b)
    predicted, step = c.c_uint64(99), c.c_uint32(22)
    assert port.glrt_native_prediction(c.byref(native), repeat, c.byref(predicted), c.byref(step)) == -1
    assert (predicted.value, step.value) == (99,22)


def test_short_descriptor_buffer_is_cleared_instead_of_exposing_partial_command(port):
    native = cbatch(batch())
    text = c.create_string_buffer(8)
    assert port.glrt_native_batch_encode(c.byref(native), text, len(text)) == -1
    assert text.value == b""


@pytest.mark.parametrize("mutation", ["none", "prefix", "version", "epoch", "nul", "hidden",
    "extra", "short", "long", "nonhex", "truncated"])
def test_result_text_port_matches_python_envelope(port, mutation):
    b = batch()
    text = head_text(b, words(b, 63, 51))
    changes = {
        "prefix": text.replace(b"GLS1", b"GLN1", 1),
        "version": text.replace(b"00010000", b"00010001", 1),
        "epoch": text.replace(b"00000003", b"00000000", 1),
        "nul": text+b"\0", "hidden": text+b"\0discard", "extra": text+b"00000000",
        "short": text.replace(b"00000003", b"3", 1),
        "long": text.replace(b"00000003", b"000000003", 1),
        "nonhex": text.replace(b"00000003", b"0000000g", 1), "truncated": text[:-10],
    }
    text = changes.get(mutation, text)
    epoch, result = c.c_uint32(99), (c.c_uint32*32)(*[99]*32)
    rc = port.glrt_native_head_parse(text, len(text), c.byref(epoch), result)
    if mutation == "none":
        decoded = ScheduledResult.from_sysfs(text.decode())
        assert rc == 0 and epoch.value == decoded.epoch and list(result) == words(b,63,51)
    else:
        with pytest.raises(ValueError):
            ScheduledResult.from_sysfs(text.decode())
        assert rc == -1 and epoch.value == 99 and list(result) == [99]*32


@pytest.mark.parametrize("mutation", ["none", "epoch", "sequence", "tag", "startlo", "starthi",
    "seed", "step", "repeat", "count", "magic", "reserved", "fault"])
def test_only_exact_association_reaches_solver_and_faulted_heads_are_drainable(port, mutation):
    b = batch()
    native = cbatch(b)
    w = words(b, 31, 51)
    epoch = b.epoch
    if mutation == "epoch": epoch += 1
    indexes = {"sequence":1,"tag":2,"startlo":3,"starthi":4,"seed":5,"step":6,
               "repeat":27,"count":7,"magic":0,"reserved":31,"fault":8}
    if mutation in indexes: w[indexes[mutation]] ^= 1
    out = Estimate(1,2,3,4,5,0)
    rc = port.glrt_native_associated_solve(c.byref(native), epoch, 51,
        (c.c_uint32*32)(*w), c.byref(out))
    if mutation in ("none", "fault"):
        assert rc == 0 and out.rejection == (4 if mutation == "none" else 1)
    else:
        assert rc == -1 and out.rejection != 0


def snap_text(w):
    return ("GLS1SNAP 00010000 "+" ".join(f"{x:08x}" for x in w)+"\n").encode()


@pytest.mark.parametrize("mutation", ["drained", "live", "source_fault", "reserved", "pending",
    "excess_terminal", "wide_terminal", "commit_ahead", "admit_ahead", "pop_ahead",
    "queue_mismatch", "highwater", "unknown_status", "unknown_fault", "zero_generation"])
def test_snapshot_conservation_and_drained_state_match_python(port, mutation):
    w = [0x474c5331,2,3,1000,0,0x33,0,64,60,1,1,0,2,0,60,60,0,64,0,0]
    if mutation == "live": w[14:17] = [59,30,29]; w[5] |= 4
    elif mutation == "source_fault": w[6] = 8; w[5] &= ~16
    elif mutation == "reserved": w[5] |= 4
    elif mutation == "pending": w[7] += 1
    elif mutation == "excess_terminal": w[9] += 1
    elif mutation == "wide_terminal": w[9:14] = [0xffffffff]*5
    elif mutation == "commit_ahead": w[14] = 61
    elif mutation == "admit_ahead": w[8] = 62; w[7] = 66
    elif mutation == "pop_ahead": w[15] = 61
    elif mutation == "queue_mismatch": w[16] = 1
    elif mutation == "highwater": w[17] = 65
    elif mutation == "unknown_status": w[5] |= 256
    elif mutation == "unknown_fault": w[6] |= 16
    elif mutation == "zero_generation": w[1] = 0
    text = snap_text(w)
    result = (c.c_uint32*20)(*[99]*20)
    rc = port.glrt_native_snapshot_parse(text,len(text),result)
    try:
        decoded = ScheduleSnapshot.from_sysfs(text.decode())
    except ValueError:
        assert rc == -1 and list(result) == [99]*20
    else:
        assert rc == 0 and list(result) == w
        try:
            decoded.require_drained()
            drained = True
        except ValueError:
            drained = False
        assert bool(port.glrt_native_snapshot_drained(result)) == drained
