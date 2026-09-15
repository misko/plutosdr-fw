"""Causal multirate timing/CFO feedback with phase-aware native coordinates."""
import ctypes as c
from fractions import Fraction

import numpy as np
import pytest

from . import test_native_trend, test_tracking_solver
from .test_native_trend import Estimate, Trend
from .test_tracking_schedule import RATES, Job, TrackingBatch, oracle
from .test_tracking_solver import Moments, moments

native_core = test_native_trend.core
models = test_tracking_solver.models


class TrackingTrend(c.Structure):
    _fields_ = [("history", Trend), ("rate", c.c_uint32)]


@pytest.fixture(scope="module")
def core(native_core):
    lib = native_core
    lib.glrt_tracking_trend_reset.argtypes = [c.POINTER(TrackingTrend), c.c_uint32, c.c_uint32]
    lib.glrt_tracking_trend_observe.argtypes = [c.POINTER(TrackingTrend), c.c_uint32, c.c_uint32,
        c.c_uint64, c.c_uint32, c.POINTER(Estimate)]
    lib.glrt_tracking_trend_batch.argtypes = [c.POINTER(TrackingTrend), c.c_uint32, c.c_uint32,
        c.c_uint32, c.c_uint32, c.POINTER(TrackingBatch), c.POINTER(c.c_double)]
    lib.glrt_tracking_trend_batch_horizon.argtypes = [c.POINTER(TrackingTrend), c.c_uint32,
        c.c_uint32, c.c_uint32, c.c_uint32, c.c_uint32,
        c.POINTER(TrackingBatch), c.POINTER(c.c_double)]
    lib.glrt_tracking_prediction.argtypes = [c.POINTER(TrackingBatch), c.c_uint, c.POINTER(Job)]
    lib.glrt_tracking_solve.argtypes = [c.c_uint32, c.c_uint32, c.POINTER(Moments), c.POINTER(Estimate)]
    lib.glrt_tracking_trend_from_coarse.argtypes = [c.POINTER(TrackingTrend),c.c_uint32,
        c.c_uint32,c.c_uint32,c.POINTER(TrackingTrend)]
    return lib


def fresh(core, rate):
    t = TrackingTrend()
    assert core.glrt_tracking_trend_reset(c.byref(t), 3, rate) == 0
    return t


def observe(core, t, frame, origin, cfo, *, rejection=0):
    phases = 4 if t.rate == 2500000 else 1
    start, phase = divmod(round(origin*phases), phases)
    delay = float(origin-start-Fraction(phase, phases))/t.rate
    e = Estimate(delay, 0, cfo, .9, .91, rejection)
    return core.glrt_tracking_trend_observe(c.byref(t), 3, frame, start, phase, c.byref(e))


def predict(core, t, first, repeats=16):
    b, rate = TrackingBatch(), c.c_double()
    rc = core.glrt_tracking_trend_batch(c.byref(t), first, repeats, 99, 17, c.byref(b), c.byref(rate))
    return rc, b, rate.value


def test_explicit_coast_extends_only_the_bounded_prediction_window(core):
    t = fresh(core, 30000000)
    anchor = 1000000
    for frame in range(0, 64, 9):
        assert observe(core, t, frame, anchor+frame*40000, 1000) == 1
    assert t.history.last_supported == 63
    batch, rate = TrackingBatch(), c.c_double()
    assert predict(core, t, 96, 1)[0] == -1
    assert core.glrt_tracking_trend_batch_horizon(c.byref(t), 96, 1, 99, 17, 96,
        c.byref(batch), c.byref(rate)) == 0
    assert core.glrt_tracking_trend_batch_horizon(c.byref(t), 159, 1, 99, 17, 96,
        c.byref(batch), c.byref(rate)) == 0
    assert core.glrt_tracking_trend_batch_horizon(c.byref(t), 160, 1, 99, 17, 96,
        c.byref(batch), c.byref(rate)) == -1
    for invalid in (0, 31, 33, 64, 65, 97):
        assert core.glrt_tracking_trend_batch_horizon(c.byref(t), 64, 1, 99, 17, invalid,
            c.byref(batch), c.byref(rate)) == -1


@pytest.mark.parametrize("native_rate", [30000000,60000000])
@pytest.mark.parametrize("alias", [False,True])
def test_coarse_handoff_preserves_physical_time_and_cfo_without_filter_delay_added_twice(core, native_rate, alias):
    coarse = fresh(core,2500000)
    anchor = 2**56+3
    period = Fraction(2500000,750)+Fraction(1,400)
    delay = Fraction(37,400)
    for frame in range(128):
        assert observe(core,coarse,frame,anchor+frame*period+delay,-100000+4000*frame/750) == 1
    saved = bytes(coarse)
    native = coarse if alias else TrackingTrend()
    assert core.glrt_tracking_trend_from_coarse(c.byref(coarse),native_rate,128,16,c.byref(native)) == 0
    if not alias: assert bytes(coarse) == saved
    assert native.rate == native_rate
    ratio = native_rate//2500000
    rc,b,slope = predict(core,native,128)
    assert rc == 0
    target = (anchor+128*period+delay)*ratio
    actual = Fraction(b.prediction.start*65536+b.prediction.fraction,65536)
    assert abs(actual-target) <= Fraction(1,65536)
    assert b.prediction.period == round(period*ratio*65536)
    assert slope == pytest.approx(4000*float(Fraction(2500000,750)/period),abs=1e-6)
    job = Job()
    assert core.glrt_tracking_prediction(c.byref(b),0,c.byref(job)) == 0
    assert job.start == round(target)
    signed_step = job.phase_step if job.phase_step<2**31 else job.phase_step-2**32
    assert signed_step*native_rate/2**32 == pytest.approx(-100000+4000*128/750,abs=native_rate/2**33)


@pytest.mark.parametrize("damage", ["few","stale_frame","wrong_source_rate","wrong_target_rate",
                                     "anchor_overflow","nonfinite","fenced"])
def test_invalid_coarse_handoff_cannot_create_native_prediction(core, damage):
    coarse = fresh(core,2500000)
    for frame in range(7 if damage == "few" else 16):
        assert observe(core,coarse,frame,Fraction(100000)+Fraction(frame*2500000,750),1000) == 1
    target_rate,first = 60000000,16
    if damage == "stale_frame": first = 15
    elif damage == "wrong_source_rate": coarse.rate = 5000000
    elif damage == "wrong_target_rate": target_rate = 15000000
    elif damage == "anchor_overflow": coarse.history.anchor = 2**64//24+1
    elif damage == "nonfinite": coarse.history.observations[0].offset = float("nan")
    elif damage == "fenced": coarse.history.valid = 0
    result = TrackingTrend()
    c.memset(c.byref(result),0xa5,c.sizeof(result))
    assert core.glrt_tracking_trend_from_coarse(c.byref(coarse),target_rate,first,16,c.byref(result)) == -1
    assert bytes(result) == bytes(c.sizeof(result))


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("slope", [-4000, 4000])
@pytest.mark.parametrize("timing_slope_ns", [-1, 1])
def test_fractional_origin_and_frequency_ramps_predict_causally_at_each_rate(
        core, rate, slope, timing_slope_ns):
    t = fresh(core, rate)
    anchor = 2**60+3
    period = Fraction(rate, 750)
    drift = Fraction(timing_slope_ns*rate, 10**9)
    delay = Fraction(37*rate, 10**9)
    for frame in range(128):
        origin = anchor+frame*(period+drift)+delay
        assert observe(core, t, frame, origin, -100000+slope*frame/750) == 1
    retained = bytes(t)
    rc, b, fitted = predict(core, t, 128)
    assert rc == 0 and b.rate == rate and bytes(t) == retained
    assert fitted == pytest.approx(slope*float(period/(period+drift)), abs=1e-7)
    predicted_origin = Fraction(b.prediction.start*65536+b.prediction.fraction, 65536)
    truth = anchor+128*(period+drift)+delay
    assert abs(predicted_origin-truth) <= Fraction(1, 65536)
    assert b.prediction.period == round((period+drift)*65536)
    for n in range(16):
        job = Job()
        assert core.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == 0
        assert (job.start, job.phase_step, job.reference_phase) == oracle(b, n)
        signed = job.phase_step if job.phase_step < 2**31 else job.phase_step-2**32
        assert signed*rate/2**32 == pytest.approx(-100000+slope*(128+n)/750, abs=rate/2**33)
    assert b.prediction.expires == oracle(b, 15)[0]+rate*33//25000-1


@pytest.mark.parametrize("rate", RATES)
def test_noisy_trend_matches_independent_fit_and_rejected_points_age_out(core, rate):
    t = fresh(core, rate)
    anchor = 2**60+3
    rng = np.random.default_rng(991)
    rows = []
    for frame in range(160):
        delay = (37+frame*.3+rng.normal(0, 10))*1e-9*rate
        cfo = -100000+frame*4000/750+rng.normal(0, 15)
        reject = frame in (89, 99, 110, 159)
        origin = Fraction(anchor)+Fraction(frame*rate, 750)+Fraction.from_float(delay)
        assert observe(core, t, frame, origin, cfo, rejection=64 if reject else 0) == int(not reject)
        if not reject: rows.append((frame, delay, cfo))
    rc, b, fitted = predict(core, t, 160)
    assert rc == 0
    points = np.array([r for r in rows if r[0] >= 158-95])
    fit = np.linalg.lstsq(np.column_stack((np.ones(len(points)), points[:, 0]-158)),
                          points[:, 1:], rcond=None)[0]
    expected = np.array([1, 2]) @ fit
    actual = Fraction(b.prediction.start*65536+b.prediction.fraction, 65536)-anchor-Fraction(160*rate, 750)
    assert float(actual) == pytest.approx(expected[0], abs=1/65536)
    assert fitted == pytest.approx(fit[1, 1]*rate/(rate/750+fit[1, 0]), abs=1e-7)
    # A lost measurement advances last_seen, but cannot extend prediction life.
    assert predict(core, t, 159)[0] == -1
    assert predict(core, t, 191, 1)[0] == -1


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fault", ["phase", "epoch", "order", "partial", "gap", "nan", "nyquist"])
def test_invalid_phase_or_source_fences_rate_bound_history(core, rate, fault):
    t = fresh(core, rate)
    for frame in range(8):
        assert observe(core, t, frame, Fraction(10000)+Fraction(frame*rate, 750), 100000) == 1
    e = Estimate(0, 0, 100000, .9, .91, 0)
    epoch, frame, phase = 3, 8, 0
    if fault == "phase": phase = 4 if rate == 2500000 else 1
    elif fault == "epoch": epoch = 4
    elif fault == "order": frame = 7
    elif fault == "partial": e.rejection = 2
    elif fault == "gap": e.rejection = 1
    elif fault == "nan": e.delay = float("nan")
    else: e.cfo = rate/2-100
    assert core.glrt_tracking_trend_observe(c.byref(t), epoch, frame,
        10000+round(Fraction(frame*rate, 750)), phase, c.byref(e)) == -1
    assert predict(core, t, 9, 1)[0] == -1
    assert not t.history.valid


@pytest.mark.parametrize("rate", [0, 25000000, 2500001])
def test_unsupported_reset_invalidates_old_history(core, rate):
    t = fresh(core, 2500000)
    assert core.glrt_tracking_trend_reset(c.byref(t), 3, rate) == -1
    assert not t.history.valid and predict(core, t, 8, 1)[0] == -1


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("slope", [-4000, 4000])
def test_quantized_moments_solver_and_future_feedback_follow_local_model(core, models, rate, slope):
    # This is causal component integration, not nonlinear RF qualification.
    # Independent physical/model qualification remains a separate release gate.
    t = fresh(core, rate)
    anchor = 2**60+3
    q16 = round(Fraction(rate*140*65536, 10**9))
    from .test_tracking_schedule import descriptor

    b = descriptor(rate, start=anchor+q16//65536, fraction=q16%65536,
        step=round(100100/rate*2**48), delta=0, repeats=16)
    phases = 4 if rate == 2500000 else 1
    rng = np.random.default_rng(49381)
    supported, errors, controls, fitted = 0, [], 0, None
    for first in range(0, 128, 16):
        if first:
            rc, b, fitted = predict(core, t, first)
            assert rc == 0
        retained = bytes(b)
        for n in range(16):
            frame = first+n
            job = Job()
            assert core.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == 0
            basis, raw = models[rate, job.reference_phase]
            truth = Fraction(anchor)+Fraction(frame*rate, 750)+Fraction((37+frame)*rate, 10**9)
            delay_us = float(truth-job.start-Fraction(job.reference_phase, phases))/rate*1e6
            carrier = (job.phase_step if job.phase_step < 2**31 else job.phase_step-2**32)*rate/2**32
            cfo = 100000+slope*frame/750
            signal = .3*np.exp(1j*rng.uniform(-np.pi, np.pi))*(basis @ np.array([1, delay_us, (cfo-carrier)/1000]))
            control = frame in (32, 33, 34, 88)
            if control: signal[:] = 0
            iq = np.rint(np.column_stack((signal.real, signal.imag))+
                rng.normal(0, 20, (len(raw), 2))).astype(np.int64)
            data = moments(iq, raw)
            data.start, data.step = job.start, job.phase_step
            estimate = Estimate()
            assert core.glrt_tracking_solve(rate, job.reference_phase, c.byref(data), c.byref(estimate)) == 0
            rc = core.glrt_tracking_trend_observe(c.byref(t), 3, frame, job.start,
                job.reference_phase, c.byref(estimate))
            assert rc >= 0
            if control:
                assert rc == 0
                controls += 1
            elif frame >= 8:
                supported += rc
                errors.append((estimate.delay*1e6-delay_us, estimate.cfo-cfo))
        assert bytes(b) == retained
    assert controls == 4 and supported >= .95*len(errors)
    timing_rms_us, cfo_rms_hz = np.sqrt(np.mean(np.square(errors), axis=0))
    assert timing_rms_us < .005 and cfo_rms_hz < .5
    assert fitted is not None and abs(fitted-slope) < 200
    fault = Estimate(0, 0, 0, 0, 0, 3)
    assert core.glrt_tracking_trend_observe(c.byref(t), 3, 128,
        anchor+round(Fraction(128*rate, 750)), 0, c.byref(fault)) == -1
    assert predict(core, t, 129)[0] == -1
