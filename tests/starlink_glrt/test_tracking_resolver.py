"""Radio-portable bootstrap resolver versus an independent NumPy FFT oracle."""
import ctypes as c
from pathlib import Path
import subprocess

import numpy as np
import pytest

N, FFT = 3300, 16384


class Peak(c.Structure):
    _fields_ = [("shift", c.c_int32), ("cfo", c.c_double), ("coherence", c.c_double)]


class Result(c.Structure):
    _fields_ = [("best", Peak), ("hypotheses", Peak*17)]


FFT_PORT = c.CFUNCTYPE(c.c_int, c.c_void_p, c.POINTER(c.c_double), c.c_size_t)


@pytest.fixture(scope="module")
def resolver(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path_factory.mktemp("resolver")/"resolver.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    str(root/"tools/glrt_tracking_resolver.c"), "-lm", "-o", str(path)], check=True)
    library = c.CDLL(str(path))
    fn = library.glrt_tracking_resolve_2500000
    fn.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t,
                   c.c_void_p, c.c_size_t, FFT_PORT, c.c_void_p, c.POINTER(Result)]
    local = library.glrt_tracking_resolve_2500000_local
    local.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t,
                      c.c_void_p, c.c_size_t, c.c_uint32, FFT_PORT, c.c_void_p,
                      c.POINTER(Peak)]
    return fn, local


def call(resolver, reference, iq, starts, *, damage=None):
    resolver = resolver[0]
    workspace = (c.c_double*(FFT*3))()
    starts = np.asarray(starts, dtype=np.uintp)
    result = Result()
    result.best.cfo = 999999
    calls = []

    @FFT_PORT
    def fft(context, data, count):
        calls.append(count)
        values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
        if damage == "fft_fail" and len(calls) == 3:
            return -1
        values[:] = np.fft.fft(values)
        if damage == "fft_nan":
            values[1] = np.nan
        if damage == "fft_inf":
            values[1] = np.inf
        if damage == "fft_square_overflow":
            values[1] = 1e300
        return 0

    rc = resolver(None if damage == "no_workspace" else workspace, reference.ctypes.data,
                  len(reference)-int(damage == "short_reference"), iq.ctypes.data, len(iq),
                  starts.ctypes.data, 3 if damage == "short_starts" else len(starts),
                  fft, None, c.byref(result))
    return rc, result, calls


def oracle(reference, iq, starts):
    ref = reference[:, 0].astype(float)+1j*reference[:, 1]
    z = iq[:, 0].astype(float)+1j*iq[:, 1]
    rows = []
    for shift in range(-8, 9):
        powers = []
        for start in starts:
            cut = z[start+shift:start+shift+N]
            powers.append(abs(np.fft.fft(cut*np.conj(ref), FFT))**2/
                          max(float(np.vdot(cut, cut).real*np.vdot(ref, ref).real), 1))
        power = np.mean(powers, axis=0)
        peak = int(np.argmax(power))
        left, center, right = power[(peak-1)%FFT], power[peak], power[(peak+1)%FFT]
        curvature = left-2*center+right
        fraction = .5*(left-right)/curvature if curvature < 0 else 0
        signed_peak = peak if peak < FFT//2 else peak-FFT
        rows.append((shift, (signed_peak+fraction)*2500000/FFT, center))
    return rows


@pytest.mark.parametrize("kind", ["pilot", "noise", "rails", "zero"])
@pytest.mark.parametrize("shift,cfo", [(-8, -511246), (3, 511246), (8, -1249800)])
def test_all_timing_hypotheses_and_cfo_aliases_match_oracle(resolver, kind, shift, cfo):
    rng = np.random.default_rng(163843300)
    reference = rng.integers(-1200, 1201, (N, 2), dtype=np.int16)
    iq = rng.integers(-500, 501, (13400, 2), dtype=np.int16)
    starts = [8, 3341, 6675, 10008]
    if kind == "pilot":
        ref = reference[:, 0]+1j*reference[:, 1]
        for start in starts:
            signal = 4*ref*np.exp(2j*np.pi*cfo*np.arange(N)/2500000)
            iq[start+shift:start+shift+N] = np.rint(np.column_stack((signal.real, signal.imag)))
    elif kind == "rails":
        iq[:] = (-32768, 32767)
    elif kind == "zero":
        iq[:] = 0
    rc, result, calls = call(resolver, reference, iq, starts)
    expected = oracle(reference, iq, starts)
    assert rc == 0 and calls == [FFT]*68
    np.testing.assert_allclose([(p.shift, p.cfo, p.coherence) for p in result.hypotheses], expected,
                               rtol=2e-12, atol=2e-8)
    best = max(expected, key=lambda row: row[2])
    np.testing.assert_allclose((result.best.shift, result.best.cfo, result.best.coherence), best,
                               rtol=2e-12, atol=2e-8)
    if kind == "pilot":
        assert result.best.shift == shift and abs(result.best.cfo-cfo) < 5
    elif kind == "zero":
        assert result.best.coherence == 0


@pytest.mark.parametrize("damage", ["no_workspace", "short_reference", "short_starts", "left_guard",
                                    "right_guard", "wrapped_start", "empty_reference", "fft_fail", "fft_nan",
                                    "fft_inf", "fft_square_overflow"])
def test_invalid_or_failed_resolver_clears_estimate_and_checks_bounds_before_fft(resolver, damage):
    reference = np.ones((N, 2), dtype=np.int16)
    iq = np.ones((13400, 2), dtype=np.int16)
    starts = [8, 3341, 6675, 10008]
    if damage == "left_guard": starts[0] = 7
    if damage == "right_guard": starts[-1] = len(iq)-N-7
    if damage == "wrapped_start": starts[-1] = np.iinfo(np.uintp).max
    if damage == "empty_reference": reference[:] = 0
    rc, result, calls = call(resolver, reference, iq, starts, damage=damage)
    assert rc == -1 and bytes(result) == bytes(Result())
    assert len(calls) == (3 if damage == "fft_fail" else 1 if damage in
                         ("fft_nan", "fft_inf", "fft_square_overflow") else 0)


def test_local_prior_search_keeps_full_pilot_and_cfo_evidence(resolver):
    full, local = resolver
    rng = np.random.default_rng(2300417)
    reference = rng.integers(-1200, 1201, (N, 2), dtype=np.int16)
    iq = rng.integers(-300, 301, (13400, 2), dtype=np.int16)
    starts = np.asarray([8, 3341, 6675, 10008], dtype=np.uintp)
    ref = reference[:, 0]+1j*reference[:, 1]
    for start in starts:
        signal = 5*ref*np.exp(2j*np.pi*417321*np.arange(N)/2500000)
        iq[start+2:start+2+N] = np.rint(np.column_stack((signal.real, signal.imag)))
    _, unrestricted, unrestricted_calls = call((full, local), reference, iq, starts)
    workspace = (c.c_double*(FFT*3))(); best = Peak(); calls = []

    @FFT_PORT
    def fft(context, data, count):
        calls.append(count)
        values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
        values[:] = np.fft.fft(values)
        return 0

    rc = local(workspace, reference.ctypes.data, len(reference), iq.ctypes.data, len(iq),
               starts.ctypes.data, len(starts), 2, fft, None, c.byref(best))
    assert rc == 0 and unrestricted_calls == [FFT]*68 and calls == [FFT]*20
    assert (best.shift, best.cfo, best.coherence) == pytest.approx(
        (unrestricted.best.shift, unrestricted.best.cfo, unrestricted.best.coherence),
        rel=2e-12, abs=2e-8)


@pytest.mark.parametrize("radius", [9, 2**32-1])
def test_local_prior_search_rejects_unbounded_radius_before_fft(resolver, radius):
    _, local = resolver
    reference = np.ones((N, 2), dtype=np.int16)
    iq = np.ones((13400, 2), dtype=np.int16)
    starts = np.asarray([8, 3341, 6675, 10008], dtype=np.uintp)
    workspace = (c.c_double*(FFT*3))(); best = Peak(7, 1, 1); calls=[]

    @FFT_PORT
    def fft(context, data, count):
        calls.append(count); return 0

    assert local(workspace, reference.ctypes.data, len(reference), iq.ctypes.data, len(iq),
                 starts.ctypes.data, len(starts), radius, fft, None, c.byref(best)) == -1
    assert bytes(best) == bytes(Peak()) and calls == []
