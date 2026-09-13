"""Software proposals select retained pilots without synthesizing GLA events."""
import ctypes as c
from fractions import Fraction
from pathlib import Path
import subprocess

import numpy as np
import pytest

from . import test_tracking_seed as t


class Peak(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in ("epoch", "frequency", "score")]


class Candidate(c.Structure):
    _fields_ = [("window_start", c.c_uint64), ("epoch", c.c_uint32), ("peak", Peak)]


class Seed(c.Structure):
    _fields_ = [("candidate", Candidate), ("maximum_age", c.c_uint32),
                ("first_repeat", c.c_uint32), ("fraction", c.c_uint32),
                ("first", c.c_uint64), ("start", c.c_uint64), ("starts", c.c_size_t*4),
                ("selected", t.View), ("copied", t.View)]


@pytest.fixture(scope="module")
def cpu(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("cpu-seed")
    wrapper = t.WRAPPER.replace('"glrt_tracking_seed.h"', '"glrt_cpu_seed.h"')
    wrapper = wrapper.replace("struct glrt_tracking_seed_window", "struct glrt_cpu_seed")
    (out/"wrapper.c").write_text(wrapper)
    sources = ["glrt_cpu_seed.c", *t.SOURCES[1:]]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-shared", "-fPIC", "-I", str(root/"tools"), str(out/"wrapper.c"),
                    *(str(root/"tools"/name) for name in sources), "-lm", "-o", str(out/"cpu.so")], check=True)
    lib = c.CDLL(str(out/"cpu.so"))
    lib.glrt_cpu_seed_plan.argtypes = [c.POINTER(Candidate), c.POINTER(t.View), c.c_uint32, c.POINTER(Seed)]
    lib.glrt_cpu_seed_copy.argtypes = [c.c_void_p, c.POINTER(Candidate), c.c_uint32,
                                     c.c_void_p, c.c_size_t, c.POINTER(Seed)]
    lib.glrt_cpu_seed_resolve.argtypes = [c.POINTER(Seed), c.c_void_p, c.c_void_p, c.c_void_p,
                                        t.FFT_PORT, c.c_void_p, c.c_uint64, c.POINTER(t.Result), c.c_void_p]
    lib.seed_owner_new.argtypes = [c.c_size_t, c.c_uint32, c.c_uint64]
    lib.seed_owner_new.restype = c.c_void_p
    lib.seed_owner_free.argtypes = [c.c_void_p]
    lib.glrt_tracking_iq_owner_publish.argtypes = [c.c_void_p, c.c_uint32, c.c_uint64, c.c_void_p,
                                                 c.c_size_t, c.c_uint64, c.c_uint64]
    lib.glrt_tracking_iq_owner_close.argtypes = [c.c_void_p, c.c_int]
    lib.seed_live_size.restype = lib.seed_window_size.restype = c.c_size_t
    lib.seed_live_summary.argtypes = [c.c_void_p, c.c_void_p]
    assert lib.seed_window_size() == c.sizeof(Seed)
    return lib


def proposal(first=1_000_000, epoch_bin=1234):
    return Candidate(first, 3, Peak(epoch_bin, 4, 23000))


def source(candidate, end=None):
    end = candidate.window_start+447851 if end is None else end
    return t.View(candidate.window_start, end, end, 100, 2, candidate.epoch, 1, 0)


def planned(cpu, candidate=None, view=None):
    candidate = proposal() if candidate is None else candidate
    view = source(candidate) if view is None else view
    seed = Seed()
    assert cpu.glrt_cpu_seed_plan(c.byref(candidate), c.byref(view), t.RATE, c.byref(seed)) == 0
    seed.copied = view
    return seed


@pytest.mark.parametrize("first", [0, 1_000_000, 2**60+17, t.MAX-3_000_000])
@pytest.mark.parametrize("epoch_bin", [0, 1234, 3332])
def test_exact_source_coordinates_match_fraction_oracle(cpu, first, epoch_bin):
    candidate = proposal(first, epoch_bin)
    origin = first+epoch_bin+22
    for repeat in (3, 4, 63, 64, 65, 66, 133, 134, 135, 744):
        for margin in (0, 1, 3325):
            end = origin+round(Fraction(repeat*t.RATE, 750))+t.N+8+margin
            view = source(candidate, end)
            seed = Seed()
            rc = cpu.glrt_cpu_seed_plan(c.byref(candidate), c.byref(view), t.RATE, c.byref(seed))
            if end < max(first+14000, origin+3*t.RATE//750+t.N+8):
                assert rc == -2 and bytes(seed) == bytes(Seed())
                continue
            assert rc == 0 and seed.first_repeat == 0
            exact = Fraction(origin)
            positions = [round(exact+Fraction(n*t.RATE, 750)) for n in range(4)]
            assert seed.first == min(positions)-8
            assert list(seed.starts) == [position-seed.first for position in positions]
            assert seed.start*65536+seed.fraction == round(exact*65536)
            assert seed.first+t.SAMPLES == max(positions)+t.N+8 <= view.end


@pytest.mark.parametrize("damage", ["candidate_epoch", "bin", "frequency", "zero_score", "score",
    "overflow", "epoch", "closed", "invalid", "unobserved", "generation", "reversed",
    "future_iq", "future_proposal", "partial", "expired", "few", "overwritten", "age", "large_age"])
def test_malformed_or_unavailable_proposals_cannot_select_iq(cpu, damage):
    candidate = proposal(); view = source(candidate); age = t.RATE
    if damage == "candidate_epoch": candidate.epoch = 0
    elif damage == "bin": candidate.peak.epoch = 3333
    elif damage == "frequency": candidate.peak.frequency = 11
    elif damage == "zero_score": candidate.peak.score = 0
    elif damage == "score": candidate.peak.score = 65537
    elif damage == "overflow": candidate.window_start = t.MAX-13999
    elif damage == "epoch": view.epoch += 1
    elif damage == "closed": view.closed = 1
    elif damage == "invalid": view.valid = 0
    elif damage == "unobserved": view.observed_ns = 0
    elif damage == "generation": view.generation = 0
    elif damage == "reversed": view.first = view.end+1
    elif damage == "future_iq": view.source_now = view.end-1
    elif damage == "future_proposal": candidate.window_start = view.source_now+1
    elif damage == "partial": view.end = candidate.window_start+13999
    elif damage == "expired": view.source_now = candidate.window_start+t.RATE+1
    elif damage == "few": view.end = candidate.window_start+candidate.peak.epoch+22+13307
    elif damage == "overwritten": view.first = planned(cpu).first+1
    elif damage == "age": age = 0
    elif damage == "large_age": age = t.RATE+1
    out = Seed(); c.memset(c.byref(out), 0x55, c.sizeof(out))
    assert cpu.glrt_cpu_seed_plan(c.byref(candidate), c.byref(view), age, c.byref(out)) < 0
    assert bytes(out) == bytes(Seed())


@pytest.mark.parametrize("mode", ["normal", "wrapped", "closed", "lost", "epoch", "short", "expired"])
def test_copy_uses_owned_ring_and_rejects_unusable_history(cpu, mode):
    candidate = proposal(2**60+17); first = candidate.window_start
    iq = np.arange(447851*2, dtype=np.int64).astype(np.int16).reshape(-1, 2)
    owner = cpu.seed_owner_new(230000 if mode == "wrapped" else 500000, candidate.epoch, first)
    out = np.full((t.SAMPLES, 2), 1234, dtype=np.int16)
    try:
        for offset in range(0, len(iq), 16384):
            block = np.ascontiguousarray(iq[offset:offset+16384]); end = first+offset+len(block)
            assert cpu.glrt_tracking_iq_owner_publish(owner, candidate.epoch, first+offset,
                block.ctypes.data, len(block), end+1000, 100+offset) == 0
        if mode in ("closed", "lost"):
            assert cpu.glrt_tracking_iq_owner_close(owner, int(mode == "lost")) == 0
        if mode == "epoch": candidate.epoch += 1
        seed = Seed()
        rc = cpu.glrt_cpu_seed_copy(owner, c.byref(candidate), 1 if mode == "expired" else t.RATE,
                                    out.ctypes.data, t.SAMPLES-int(mode == "short"), c.byref(seed))
        if mode == "normal":
            assert rc == 0
            np.testing.assert_array_equal(out, iq[seed.first-first:seed.first-first+t.SAMPLES])
            assert seed.copied.source_now == first+len(iq)+1000
        else:
            assert rc < 0 and bytes(seed) == bytes(Seed()) and np.all(out == 1234)
    finally:
        cpu.seed_owner_free(owner)


def resolve(cpu, seed, reference, iq, *, fail=False):
    workspace = (c.c_double*(t.FFT*3))()
    live = c.create_string_buffer(cpu.seed_live_size()); result = t.Result(); calls = []
    c.memset(live, 0x55, len(live)); c.memset(c.byref(result), 0x55, c.sizeof(result))

    @t.FFT_PORT
    def fft(context, data, count):
        calls.append(count)
        if fail and len(calls) == 3: return -1
        values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
        values[:] = np.fft.fft(values)
        return 0

    rc = cpu.glrt_cpu_seed_resolve(c.byref(seed), workspace, reference.ctypes.data,
        iq.ctypes.data, fft, None, seed.selected.source_now+2*t.RATE, c.byref(result), live)
    summary = (c.c_uint64*10)(); cpu.seed_live_summary(live, summary)
    return rc, result, live, list(summary), calls


@pytest.mark.parametrize("repeat", [69, 70, 71])
@pytest.mark.parametrize("shift,cfo", [(-8, -511246), (3, 511246), (8, 399999)])
def test_resolver_agrees_with_fft_oracle_and_initializes_no_supported_history(cpu, repeat, shift, cfo):
    candidate = proposal(2**60+17)
    origin = candidate.window_start+candidate.peak.epoch+22
    view = source(candidate, origin+int(Fraction((repeat+63)*t.RATE, 750))+t.N+9)
    seed = planned(cpu, candidate, view)
    assert seed.first_repeat == 0
    rng = np.random.default_rng(13316)
    reference = rng.integers(-1200, 1201, (t.N, 2), dtype=np.int16)
    iq = rng.integers(-50, 51, (t.SAMPLES, 2), dtype=np.int16)
    signal = (reference[:, 0]+1j*reference[:, 1])*np.exp(2j*np.pi*cfo*np.arange(t.N)/t.RATE)
    for start in seed.starts:
        iq[start+shift:start+shift+t.N] = np.rint(np.column_stack((signal.real, signal.imag)))
    rc, result, _, summary, calls = resolve(cpu, seed, reference, iq)
    assert rc == 0 and calls == [t.FFT]*68
    np.testing.assert_allclose([(p.shift, p.cfo, p.coherence) for p in result.hypotheses],
                              t.oracle(reference, iq, list(seed.starts)), rtol=2e-12, atol=2e-8)
    assert result.best.shift == shift and abs(result.best.cfo-cfo) < 5
    assert summary == [seed.start+shift, seed.fraction, candidate.epoch, 1, 0, 0, 0, 0,
                       view.source_now+2*t.RATE, t.RATE]


@pytest.mark.parametrize("damage", ["first", "start", "fraction", "repeat", "starts", "closed",
    "invalid", "epoch", "overwritten", "short", "future_iq", "source", "clock", "generation",
    "expired", "fft", "empty_reference"])
def test_invalid_or_failed_resolution_leaves_no_bootstrap(cpu, damage):
    seed = planned(cpu)
    if damage in ("first", "start", "fraction"): setattr(seed, damage, getattr(seed, damage)+1)
    elif damage == "repeat": seed.first_repeat += 1
    elif damage == "starts": seed.starts[1] += 1
    elif damage == "closed": seed.copied.closed = 1
    elif damage == "invalid": seed.copied.valid = 0
    elif damage == "epoch": seed.copied.epoch += 1
    elif damage == "overwritten": seed.copied.first = seed.first+1
    elif damage == "short": seed.copied.end = seed.first+t.SAMPLES-1
    elif damage == "future_iq": seed.copied.end = seed.copied.source_now+1
    elif damage == "source": seed.copied.source_now -= 1; seed.copied.end -= 1
    elif damage == "clock": seed.copied.observed_ns -= 1
    elif damage == "generation": seed.copied.generation -= 1
    elif damage == "expired": seed.copied.source_now = seed.candidate.window_start+t.RATE+1
    reference = np.ones((t.N, 2), dtype=np.int16)
    if damage == "empty_reference": reference[:] = 0
    rc, result, live, _, calls = resolve(cpu, seed, reference, np.ones((t.SAMPLES, 2), dtype=np.int16),
                                       fail=damage == "fft")
    assert rc == -1 and bytes(result) == bytes(t.Result()) and bytes(live) == bytes(len(live))
    assert len(calls) == (3 if damage == "fft" else 0)
