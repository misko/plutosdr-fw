"""Causal radio trend vs independent least squares and exact native coordinates."""
import ctypes as c
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from tools.starlink_glrt_schedule_abi import ScheduleBatch


class Estimate(c.Structure):
    _fields_ = [(name,c.c_double) for name in ("delay","residual","cfo","coherence","linearized")]+[
        ("rejection",c.c_uint32)]


class Observation(c.Structure):
    _fields_ = [("frame",c.c_uint32),("offset",c.c_double),("cfo",c.c_double)]


class Trend(c.Structure):
    _fields_ = [(name,c.c_uint32) for name in ("epoch","first_frame","last_seen","last_supported","count","next")]+[
        ("anchor",c.c_uint64),("initialized",c.c_int),("valid",c.c_int),("seen",c.c_int),
        ("observations",Observation*96)]


class Batch(c.Structure):
    _fields_ = [(name,c.c_uint32) for name in ("epoch","tag")]+[
        (name,c.c_uint64) for name in ("start","period","step","delta","expires")]+[
        (name,c.c_uint32) for name in ("fraction","seed","repeats")]


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("native-trend")/"trend.so"
    subprocess.run(["cc","-std=c99","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC",
        *(str(root/"tools"/name) for name in ("glrt_native_trend.c","glrt_native_schedule.c","glrt_native_solver.c")),
        "-lm","-o",str(out)],check=True)
    lib = c.CDLL(str(out))
    lib.glrt_native_trend_reset.argtypes = [c.POINTER(Trend),c.c_uint32]
    lib.glrt_native_trend_observe.argtypes = [c.POINTER(Trend),c.c_uint32,c.c_uint32,c.c_uint64,c.POINTER(Estimate)]
    lib.glrt_native_trend_batch.argtypes = [c.POINTER(Trend),c.c_uint32,c.c_uint32,c.c_uint32,c.c_uint32,
        c.POINTER(Batch),c.POINTER(c.c_double)]
    return lib


def fresh(core):
    t = Trend()
    core.glrt_native_trend_reset(c.byref(t),3)
    return t


def observe(core,t,frame,offset=Fraction(11,4),cfo=100000,*,rejection=0,anchor=2**60):
    rounded = round(offset)
    e = Estimate(float(offset-rounded)/60000000,0,cfo,.9,.91,rejection)
    rc = core.glrt_native_trend_observe(c.byref(t),3,frame,anchor+frame*80000+rounded,c.byref(e))
    return rc,e


def predict(core,t,first,repeats=16):
    batch,rate = Batch(),c.c_double()
    rc = core.glrt_native_trend_batch(c.byref(t),first,repeats,99,17,c.byref(batch),c.byref(rate))
    return rc,batch,rate.value


def pybatch(b):
    return ScheduleBatch(**{name:getattr(b,name) for name,_ in Batch._fields_})


@pytest.mark.parametrize("slope", [-4000,4000])
@pytest.mark.parametrize("anchor", [1000000,2**60])
@pytest.mark.parametrize("base_cfo", [-100000,0,100000])
@pytest.mark.parametrize("timing_slope", [Fraction(-3,1000),Fraction(3,1000)])
def test_known_carrier_and_timing_ramps_predict_future_finite_batches(core,slope,anchor,base_cfo,timing_slope):
    t = fresh(core)
    for frame in range(128):
        offset = Fraction(11,4)+timing_slope*frame
        assert observe(core,t,frame,offset,base_cfo+slope*frame/750,anchor=anchor)[0] == 1
    rc,b,rate = predict(core,t,128)
    assert rc == 0
    expected_rate = slope*80000/(80000+float(timing_slope))
    assert rate == pytest.approx(expected_rate,abs=1e-7)
    b = pybatch(b)
    for repeat in range(16):
        frame = 128+repeat
        start,step = b.prediction(repeat)
        assert start == anchor+frame*80000+round(Fraction(11,4)+timing_slope*frame)
        signed_step = step if step < 2**31 else step-2**32
        assert signed_step*60000000/2**32 == pytest.approx(base_cfo+slope*frame/750,abs=.007)
    assert b.expires == b.prediction(15)[0]+79199


def test_noisy_causal_window_matches_independent_lstsq_and_ignores_rejected_controls(core):
    t = fresh(core)
    rng = np.random.default_rng(888)
    accepted = []
    for frame in range(160):
        offset = 2.75+.003*frame+rng.normal(0,.3)
        cfo = 100000+4000*frame/750+rng.normal(0,15)
        reject = 64 if frame in (83,90,103,107,139,158) else 0
        assert observe(core,t,frame,offset,cfo,rejection=reject)[0] == (0 if reject else 1)
        if not reject: accepted.append((frame,offset,cfo))
    rc,b,rate = predict(core,t,160)
    assert rc == 0
    points = np.array([row for row in accepted if row[0]>=159-95])
    design = np.column_stack((np.ones(len(points)),points[:,0]-159))
    fit = np.linalg.lstsq(design,points[:,1:],rcond=None)[0]
    expected = np.array([1,1])@fit
    exact_start = Fraction(b.start*65536+b.fraction,65536)-(2**60+160*80000)
    assert float(exact_start) == pytest.approx(expected[0],abs=1/65536)
    phase = b.step if b.step<2**47 else b.step-2**48
    assert phase*60000000/2**48 == pytest.approx(expected[1],abs=2e-7)
    assert rate == pytest.approx(fit[1,1]*60000000/(80000+fit[1,0]),abs=1e-7)


def test_prediction_is_causal_deterministic_and_has_no_state_side_effect(core):
    t = fresh(core)
    for frame in range(8): observe(core,t,frame)
    state = bytes(t)
    first = predict(core,t,8)
    second = predict(core,t,8)
    assert first[0] == second[0] == 0 and bytes(first[1]) == bytes(second[1])
    assert bytes(t) == state
    # The old descriptor remains immutable when later measurements arrive.
    retained = bytes(first[1])
    observe(core,t,8,cfo=100010)
    assert bytes(first[1]) == retained
    assert predict(core,t,8)[0] == -1


def test_requires_eight_recent_supported_frames_and_caps_whole_batch_horizon(core):
    t = fresh(core)
    for frame in range(7): observe(core,t,frame)
    assert predict(core,t,7)[0] == -1
    observe(core,t,7)
    assert predict(core,t,8,32)[0] == 0
    assert predict(core,t,9,32)[0] == -1
    assert predict(core,t,39,1)[0] == 0
    assert predict(core,t,40,1)[0] == -1
    observe(core,t,39,rejection=64)
    assert predict(core,t,40,1)[0] == -1
    # A long loss cannot make ancient accepted points a new trend fit.
    observe(core,t,150)
    assert predict(core,t,151,1)[0] == -1


@pytest.mark.parametrize("failure", ["epoch","duplicate","order","gap","partial","nan","inf",
    "unknown","unsupported_delay","bad_coherence","backwards_index"])
def test_source_or_protocol_failures_fence_predictions_until_explicit_reset(core,failure):
    t = fresh(core)
    for frame in range(8): observe(core,t,frame)
    epoch,frame,start = 3,8,2**60+8*80000+3
    e = Estimate(0,0,100000,.9,.91,0)
    if failure == "epoch": epoch = 4
    elif failure == "duplicate": frame = 7
    elif failure == "order": frame = 6
    elif failure == "gap": e.rejection = 1
    elif failure == "partial": e.rejection = 2
    elif failure == "nan": e.cfo = float("nan")
    elif failure == "inf": e.delay = float("inf")
    elif failure == "unknown": e.rejection = 128
    elif failure == "unsupported_delay": e.delay = 251e-9
    elif failure == "bad_coherence": e.coherence = .01
    elif failure == "backwards_index": start = t.anchor-1
    assert core.glrt_native_trend_observe(c.byref(t),epoch,frame,start,c.byref(e)) == -1
    assert predict(core,t,9,1)[0] == -1
    assert observe(core,t,9)[0] == -1
    core.glrt_native_trend_reset(c.byref(t),4)
    assert t.valid and not t.count and t.epoch == 4


def test_rejected_startup_frames_still_establish_observation_order(core):
    t = fresh(core)
    assert observe(core,t,9,rejection=64)[0] == 0
    assert observe(core,t,8)[0] == -1


def test_native_u64_overflow_cannot_create_wrapped_schedule(core):
    t = fresh(core)
    anchor = 2**64-800000
    for frame in range(8): observe(core,t,frame,anchor=anchor)
    assert predict(core,t,8,16)[0] == -1
