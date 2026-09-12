"""GLT1 C/Python association, rejection and full-rate numerical handoff."""
import ctypes as c
import subprocess
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from tools.starlink_glrt_schedule_abi import ScheduledResult
from tools.starlink_glrt_tracking_abi import (
    MAGIC,
    VERSION,
    TrackingBatch,
    TrackingResult,
    bank_id,
)

from . import test_tracking_solver
from .test_native_schedule_port import Batch, Estimate
from .test_native_solver import ROOT, dense_fit
from .test_tracking_schedule import RATES
from .test_tracking_schedule import TrackingBatch as CBatch
from .test_tracking_solver import moments

models = test_tracking_solver.models


@pytest.fixture(scope="module")
def transport(tmp_path_factory):
    output = tmp_path_factory.mktemp("tracking-transport")/"port.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
        *[str(ROOT/"tools"/name) for name in (
            "glrt_tracking_transport.c", "glrt_tracking_schedule.c", "glrt_native_solver.c")],
        "-lm", "-o", str(output)], check=True)
    lib = c.CDLL(str(output))
    u32p = c.POINTER(c.c_uint32)
    lib.glrt_tracking_head_parse.argtypes = [c.c_char_p, c.c_size_t, u32p, u32p]
    lib.glrt_tracking_batch_encode.argtypes = [c.POINTER(CBatch), c.c_char_p, c.c_size_t]
    lib.glrt_tracking_associated_solve.argtypes = [c.POINTER(CBatch), c.c_uint32, c.c_uint32,
        u32p, c.POINTER(Estimate)]
    return lib


def descriptor(rate, **changes):
    b = TrackingBatch(rate, 3, 7, 2**60+1001, 24576, round(Fraction(rate*65536, 750)),
        7310173*65536, 2**48-65537, 17, 64, 2**64-1)
    return replace(b, **changes)


def cbatch(b):
    return CBatch(Batch(**{name: getattr(b, name) for name, _ in Batch._fields_}), b.rate)


def words(b, repeat=0, sequence=0):
    start, step, phase = b.prediction(repeat)
    return [MAGIC, sequence, b.tag, start % 2**32, start >> 32, b.seed, step, b.samples, 0,
            *([0]*16), b.rate, b.samples, repeat, phase, bank_id(b.rate), VERSION, 0]


def envelope(b, w):
    return ("GLT1 00010000 "+" ".join(f"{v:08x}" for v in (b.epoch, *w))+"\n").encode()


def solve(lib, b, w, *, epoch=None, sequence=0):
    out = Estimate(123, 456, 789, 1, 1, 0)
    batch = cbatch(b)
    rc = lib.glrt_tracking_associated_solve(c.byref(batch), b.epoch if epoch is None else epoch,
        sequence, (c.c_uint32*32)(*w), c.byref(out))
    return rc, out


@pytest.mark.parametrize("rate", RATES)
def test_text_and_predictions_match_independent_fraction_oracle(transport, rate):
    for fraction in (0, 8192, 24576, 32768, 57344, 65535):
        b = descriptor(rate, fraction=fraction)
        native = cbatch(b)
        text = c.create_string_buffer(256)
        n = transport.glrt_tracking_batch_encode(c.byref(native), text, len(text))
        assert n == len(b.encode()) and text.value.decode() == b.encode()
        assert transport.glrt_tracking_batch_encode(c.byref(native), text, 10) == -1
        assert text.value == b""
        for repeat in (0, 1, 2, 31, 63):
            w = words(b, repeat)
            payload = envelope(b, w)
            epoch, parsed = c.c_uint32(), (c.c_uint32*32)()
            assert transport.glrt_tracking_head_parse(payload, len(payload), c.byref(epoch), parsed) == 0
            assert epoch.value == b.epoch and list(parsed) == w
            decoded = TrackingResult.from_sysfs(payload.decode())
            decoded.require_association(b, sequence=0)
            decoded.require_complete()
            rc, out = solve(transport, b, w)
            assert rc == 0 and out.rejection == 4  # Complete arithmetic, zero energy, no detection.
            with pytest.raises(ValueError):
                ScheduledResult.from_sysfs(payload.decode())


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fault", ["epoch", "sequence", "tag", "start", "seed", "step", "count",
    "fault", "rate", "samples", "repeat", "phase", "bank", "version", "reserved", "magic",
    "sum_width", "prefix_width", "energy_width", "expiry", "empty"])
def test_bad_heads_never_leave_a_supported_estimate(transport, rate, fault):
    b = descriptor(rate)
    w = words(b)
    epoch = b.epoch
    fields = {"sequence": 1, "tag": 2, "start": 3, "seed": 5, "step": 6, "count": 7,
              "rate": 25, "samples": 26, "phase": 28, "bank": 29, "version": 30,
              "reserved": 31, "magic": 0}
    if fault in fields: w[fields[fault]] ^= 1
    elif fault == "epoch": epoch += 1
    elif fault == "fault": w[8] = 1 << 10
    elif fault == "repeat": w[27] = 64
    elif fault == "sum_width": w[10] = 1 << 31
    elif fault == "prefix_width": w[19] = 1 << 31
    elif fault == "energy_width": w[24] = 1 << 31
    elif fault == "expiry": b = replace(b, expires=b.prediction(0)[0]+b.samples-2)
    elif fault == "empty": w[7] = 0; w[8] = 0x100; w[9] = 1
    rc, out = solve(transport, b, w, epoch=epoch)
    assert rc == -1 and out.rejection == 1
    assert (out.delay, out.residual, out.coherence, out.linearized) == (0, 0, 0, 0)
    with pytest.raises(ValueError):
        result = TrackingResult.from_sysfs(envelope(replace(b, epoch=epoch), w).decode())
        result.require_association(b, sequence=0)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fault", [1, 0x100, 0x200, 0x3ff])
def test_faulted_heads_are_validated_retained_and_rejected_for_fit(transport, rate, fault):
    b = descriptor(rate)
    w = words(b)
    w[7:9] = [17, fault]
    # Canonical negative prefix, including the whole high word at 2.5 MS/s.
    w[17:20] = [0xfffffffb, 0xffffffff, 0xffffffff]
    result = TrackingResult.from_sysfs(envelope(b, w).decode())
    result.require_association(b, sequence=0)
    assert result.reference_prefix_integral == (-5, 0)
    assert result.acknowledgement() == "00000003 00000000\n"
    with pytest.raises(ValueError): result.require_complete()
    rc, out = solve(transport, b, w)
    assert rc == 0 and out.rejection == 3
    w[19] = 0x7fffffff  # Break extension above every profile's actual prefix width.
    assert solve(transport, b, w)[0] == -1


@pytest.mark.parametrize("damage", ["prefix", "version", "epoch", "short", "long", "nul", "trailing"])
def test_text_parse_failure_is_atomic(transport, damage):
    b = descriptor(2500000)
    payload = envelope(b, words(b))
    if damage == "prefix": payload = payload.replace(b"GLT1", b"GLS1")
    elif damage == "version": payload = payload.replace(b"00010000", b"00020000", 1)
    elif damage == "epoch": payload = payload.replace(b"00000003", b"00000000", 1)
    elif damage == "short": payload = payload.replace(b"00000003", b"3", 1)
    elif damage == "long": payload = payload.replace(b"00000003", b"000000003", 1)
    elif damage == "nul": payload += b"\0"
    else: payload += b"junk"
    epoch, parsed = c.c_uint32(91), (c.c_uint32*32)(*([92]*32))
    assert transport.glrt_tracking_head_parse(payload, len(payload), c.byref(epoch), parsed) == -1
    assert epoch.value == 91 and list(parsed) == [92]*32
    with pytest.raises(ValueError): TrackingResult.from_sysfs(payload.decode())


@pytest.mark.parametrize("rate,phase", [(2500000, n) for n in range(4)]+[
    (15000000, 0), (30000000, 0), (60000000, 0)])
def test_associated_pinned_pilot_reaches_solver_with_correct_rate_and_reference(
        transport, models, rate, phase):
    basis, raw = models[rate, phase]
    signal = .3*np.exp(.4j)*(basis @ np.array([1, .07, -.06]))
    iq = np.rint(np.column_stack((signal.real, signal.imag))).astype(np.int64)
    fitted, coherence, improved = dense_fit(basis, iq)
    data = moments(iq, raw)
    b = descriptor(rate, fraction=phase*16384 if rate == 2500000 else 0, step=0)
    w = words(b)
    w[9:25] = data.words
    rc, out = solve(transport, b, w)
    assert rc == 0 and out.rejection == 0
    assert out.delay*1e6 == pytest.approx(fitted[0], abs=2e-12)
    assert out.residual/1000 == pytest.approx(fitted[1], abs=2e-12)
    assert out.cfo == out.residual
    assert out.coherence == pytest.approx(coherence, abs=2e-13)
    assert out.linearized == pytest.approx(improved, abs=2e-13)
