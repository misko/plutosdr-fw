"""Finite radio bootstrap catches up on past IQ without extending forecast expiry."""
import ctypes as c
from fractions import Fraction
from pathlib import Path
import subprocess

import pytest

from .test_native_trend import Estimate
from .test_tracking_trend import TrackingTrend
from .test_tracking_schedule import TrackingBatch, Job

RATE, N = 2500000, 3300


class Bootstrap(c.Structure):
    _fields_ = [("trend", TrackingTrend), ("pending_job", Job),
        ("seed_start", c.c_uint64), ("last_available", c.c_uint64), ("seed_cfo", c.c_double)]+[
        (name, c.c_uint32) for name in ("seed_fraction", "seed_frame", "jobs", "pending",
                                      "ready", "valid", "clock_seen", "spacing", "failure")]


@pytest.fixture(scope="module")
def bootstrap(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path_factory.mktemp("bootstrap")/"bootstrap.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
        *(str(root/"tools"/name) for name in ("glrt_tracking_bootstrap.c", "glrt_native_trend.c",
            "glrt_native_schedule.c", "glrt_tracking_schedule.c", "glrt_native_solver.c")),
        "-lm", "-o", str(path)], check=True)
    lib = c.CDLL(str(path))
    lib.glrt_tracking_bootstrap_init.argtypes = [c.POINTER(Bootstrap), c.c_uint32,
        c.c_uint64, c.c_uint32, c.c_double]
    lib.glrt_tracking_bootstrap_set_spacing.argtypes = [c.POINTER(Bootstrap), c.c_uint32]
    lib.glrt_tracking_bootstrap_next.argtypes = [c.POINTER(Bootstrap), c.c_uint64,
        c.c_uint64, c.c_uint32, c.POINTER(c.c_uint32), c.POINTER(Job), c.POINTER(TrackingBatch)]
    lib.glrt_tracking_bootstrap_observe.argtypes = [c.POINTER(Bootstrap), c.c_uint32,
        c.c_uint32, c.POINTER(Job), c.POINTER(Estimate)]
    lib.glrt_tracking_prediction.argtypes = [c.POINTER(TrackingBatch), c.c_uint, c.POINTER(Job)]
    return lib


def fresh(lib, start=1000000, fraction=0, cfo=400000, epoch=3):
    state = Bootstrap()
    assert lib.glrt_tracking_bootstrap_init(c.byref(state), epoch, start, fraction, cfo) == 0
    return state


def test_three_frame_spacing_is_explicit_and_locked_after_first_job(bootstrap):
    state=fresh(bootstrap)
    assert state.spacing == 9
    assert bootstrap.glrt_tracking_bootstrap_set_spacing(c.byref(state),3) == 0
    rc,frame,_,_=next_job(bootstrap,state,state.seed_start,state.seed_start+3300)
    assert rc == 1 and frame == 0 and state.spacing == 3
    assert bootstrap.glrt_tracking_bootstrap_set_spacing(c.byref(state),9) == -1
    for invalid in (0,1,2,4,8,10):
        other=fresh(bootstrap)
        assert bootstrap.glrt_tracking_bootstrap_set_spacing(c.byref(other),invalid) == -1


def next_job(lib, state, earliest, available, lead=2500):
    frame, job, batch = c.c_uint32(999), Job(), TrackingBatch()
    job.start = 999
    batch.rate = 999
    rc = lib.glrt_tracking_bootstrap_next(c.byref(state), earliest, available, lead,
                                         c.byref(frame), c.byref(job), c.byref(batch))
    if rc < 0:
        assert frame.value == 0 and bytes(job) == bytes(Job()) and bytes(batch) == bytes(TrackingBatch())
    return rc, frame.value, job, batch


def observe(lib, state, frame, job, estimate, epoch=3):
    return lib.glrt_tracking_bootstrap_observe(c.byref(state), epoch, frame, c.byref(job), c.byref(estimate))


@pytest.mark.parametrize("anchor", [1000000, 2**60+3])
@pytest.mark.parametrize("fraction", [0, 21845, 65535])
@pytest.mark.parametrize("slope", [-2000, 2000])
@pytest.mark.parametrize("drift", [Fraction(-1,60), Fraction(1,60)])
def test_known_ramps_catch_up_and_predict_current_future_jobs(bootstrap, anchor, fraction, slope, drift):
    lib = bootstrap
    state = fresh(lib, anchor, fraction)
    origin = Fraction(anchor)+Fraction(fraction,65536)
    # Resolver finished about 655 ms after its first history pilot. Each 2.2-ms
    # software call advances wall time while anchors advance by twelve ms.
    available = anchor+round(Fraction(6554,10000)*RATE)
    original_available = available
    calls = 0
    while True:
        rc, frame, job, batch = next_job(lib, state, anchor-2, available)
        assert rc in (1,2)
        if rc == 2:
            assert 60 < calls < 80 and job.start >= available+2500
            assert batch.rate == RATE and batch.prediction.repeats == 8
            assert frame+7-state.trend.history.last_supported <= 32
            for n in range(8):
                out = Job()
                assert lib.glrt_tracking_prediction(c.byref(batch), n, c.byref(out)) == 0
                truth = origin+Fraction((frame+n)*RATE,750)+drift*(frame+n)
                estimate = Fraction(out.start)+Fraction(out.reference_phase,4)
                assert abs(estimate-truth) <= Fraction(1,8)+Fraction(1,65536)
                signed = out.phase_step if out.phase_step<2**31 else out.phase_step-2**32
                assert signed*RATE/2**32 == pytest.approx(400000+slope*(frame+n)/750,abs=.002)
            break
        assert frame == calls*9 and job.start+N <= available
        truth = origin+Fraction(frame*RATE,750)+drift*frame
        selected = Fraction(job.start)+Fraction(job.reference_phase,4)
        estimate = Estimate(float(truth-selected)/RATE,0,400000+slope*frame/750,.9,.91,0)
        assert observe(lib,state,frame,job,estimate) == 1
        calls += 1
        available += 5500
    assert available-original_available == calls*5500


@pytest.mark.parametrize("kind", ["noise", "loss_after_lock", "too_slow"])
def test_controls_loss_and_compute_budget_never_create_a_future_batch(bootstrap, kind):
    state = fresh(bootstrap)
    available = 1000000+1640000
    calls = 0
    while True:
        rc, frame, job, _ = next_job(bootstrap,state,900000,available)
        if rc < 0:
            assert state.failure == (3 if kind == "too_slow" else 4)
            break
        assert rc == 1
        rejected = kind == "noise" or (kind == "loss_after_lock" and calls >= 8)
        estimate = Estimate(0,0,400000,.01 if rejected else .9,.9,64 if rejected else 0)
        assert observe(bootstrap,state,frame,job,estimate) == (0 if rejected else 1)
        calls += 1
        available += 30000 if kind == "too_slow" else 5500
    assert calls == (200 if kind == "too_slow" else 8 if kind == "noise" else 11)
    assert not state.valid and not state.ready


@pytest.mark.parametrize("damage", ["epoch", "frame", "start", "phase", "step", "nan", "fault"])
def test_association_and_faults_invalidate_the_pending_bootstrap(bootstrap, damage):
    state = fresh(bootstrap)
    rc, frame, job, _ = next_job(bootstrap,state,0,3000000)
    assert rc == 1
    estimate = Estimate(0,0,400000,.9,.91,0)
    epoch = 3
    if damage == "epoch": epoch = 4
    if damage == "frame": frame += 1
    if damage == "start": job.start += 1
    if damage == "phase": job.reference_phase ^= 1
    if damage == "step": job.phase_step ^= 1
    if damage == "nan": estimate.delay = float('nan')
    if damage == "fault": estimate.rejection = 1
    assert observe(bootstrap,state,frame,job,estimate,epoch) == -1
    assert not state.valid and not state.pending and state.failure == 1


@pytest.mark.parametrize("damage", ["overwrite", "clock_regression", "pending", "empty_history", "lead_overflow", "no_lead"])
def test_retention_time_and_ownership_are_explicit_gates(bootstrap, damage):
    state = fresh(bootstrap)
    earliest, available, lead = 0, 3000000, 2500
    if damage in ("pending", "clock_regression"):
        rc, frame, job, _ = next_job(bootstrap,state,earliest,available)
        assert rc == 1
        if damage == "clock_regression":
            assert observe(bootstrap,state,frame,job,Estimate(0,0,400000,.9,.91,0)) == 1
            available -= 1
    if damage == "overwrite": earliest = 1000001
    if damage == "empty_history": available = 1000000
    if damage == "lead_overflow": available = 2**64-1
    if damage == "no_lead": lead = 0
    assert next_job(bootstrap,state,earliest,available,lead)[0] == -1
    assert state.failure == (2 if damage in ("overwrite","clock_regression") else 4 if damage == "empty_history" else 1)
    assert not state.valid
    assert bootstrap.glrt_tracking_bootstrap_init(c.byref(state),4,2000000,0,0) == 0
    assert state.valid and not state.pending and state.jobs == 0 and state.failure == 0


@pytest.mark.parametrize("epoch,start,fraction,cfo", [(0,1,0,0),(3,2**64-1,0,0),
    (3,1,65536,0),(3,1,0,float('nan')),(3,1,0,1249750),(3,1,0,-1249750)])
def test_invalid_seed_cannot_initialize(bootstrap, epoch, start, fraction, cfo):
    state = fresh(bootstrap)
    assert bootstrap.glrt_tracking_bootstrap_init(c.byref(state),epoch,start,fraction,cfo) == -1
    assert not state.valid and not state.ready and not state.pending


@pytest.mark.parametrize('slope', [-5000,0,5000])
def test_initial_carrier_ramp_uses_only_three_or_more_earlier_supported_pilots(bootstrap,slope):
    state=fresh(bootstrap)
    for index in range(8):
        rc,frame,job,_=next_job(bootstrap,state,0,3000000)
        assert rc==1 and frame==index*9
        hz=(job.phase_step if job.phase_step<2**31 else job.phase_step-2**32)*RATE/2**32
        expected=400000+slope*(frame if index>=3 else max(0,frame-9))/750
        assert hz==pytest.approx(expected,abs=.001)
        # The estimate at this frame is supplied only after inspecting the
        # proposed carrier. It cannot influence this same job's prediction.
        truth=400000+slope*frame/750
        assert observe(bootstrap,state,frame,job,Estimate(0,truth-hz,truth,.9,.91,0))==1
        assert state.trend.history.count==index+1
    assert state.jobs==8 and not state.ready


@pytest.mark.parametrize('mode', ['rejected','extrapolation_bound','nyquist_bound'])
def test_startup_forecast_falls_back_without_relaxing_history_or_frequency_guards(bootstrap,mode):
    values=[400000,400060,400120] if mode=='rejected' else (
        [400000,400240,400480,400960,401440] if mode=='extrapolation_bound' else [1249550,1249630,1249710])
    state=fresh(bootstrap,cfo=values[0])
    for index,value in enumerate(values):
        rc,frame,job,_=next_job(bootstrap,state,0,3000000)
        assert rc==1
        reject=mode=='rejected' and index==1
        predicted=(job.phase_step if job.phase_step<2**31 else job.phase_step-2**32)*RATE/2**32
        assert abs(value-predicted)<250
        assert observe(bootstrap,state,frame,job,Estimate(0,value-predicted,value,.01 if reject else .9,.91,64 if reject else 0))==int(not reject)
    rc,frame,job,_=next_job(bootstrap,state,0,3000000)
    assert rc==1 and frame==9*len(values)
    hz=(job.phase_step if job.phase_step<2**31 else job.phase_step-2**32)*RATE/2**32
    assert hz==pytest.approx(values[-1],abs=.001)
    assert not state.ready
