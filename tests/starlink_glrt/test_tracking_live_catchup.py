"""DMA-delayed history cannot admit a prediction behind the actual receiver."""
import ctypes as c
from fractions import Fraction

import pytest

from .test_tracking_catchup import Bootstrap, bootstrap, observe, RATE, N
from .test_native_trend import Estimate
from .test_tracking_schedule import Job, TrackingBatch
from .test_tracking_recent_iq import recent_iq, fresh as ring_fresh, append, read


class Live(c.Structure):
    _fields_ = [("core", Bootstrap), ("source_deadline", c.c_uint64),
        ("last_source", c.c_uint64), ("last_earliest", c.c_uint64), ("seen", c.c_uint32)]


@pytest.fixture(scope="module")
def live_api(bootstrap):
    bootstrap.glrt_tracking_bootstrap_live_init.argtypes = [c.POINTER(Live), c.c_uint32,
        c.c_uint64, c.c_uint32, c.c_double, c.c_uint64]
    bootstrap.glrt_tracking_bootstrap_live_next.argtypes = [c.POINTER(Live),c.c_uint64,
        c.c_uint64,c.c_uint64,c.c_uint32,c.POINTER(c.c_uint32),c.POINTER(Job),c.POINTER(TrackingBatch)]
    return bootstrap


def fresh(lib, start=1000000, deadline=None):
    state = Live()
    assert lib.glrt_tracking_bootstrap_live_init(c.byref(state),3,start,0,400000,
        start+2*RATE if deadline is None else deadline) == 0
    return state


def next_job(lib, state, earliest, retained, now, lead=2500):
    frame, job, batch = c.c_uint32(999), Job(), TrackingBatch()
    job.start, batch.rate = 999, 999
    rc = lib.glrt_tracking_bootstrap_live_next(c.byref(state),earliest,retained,now,lead,
        c.byref(frame),c.byref(job),c.byref(batch))
    if rc <= 0:
        assert frame.value == 0 and bytes(job) == bytes(Job()) and bytes(batch) == bytes(TrackingBatch())
    return rc, frame.value, job, batch


def history(lib, state, anchor):
    for index in range(8):
        end = anchor+index*30000+N
        rc, frame, job, _ = next_job(lib,state,anchor,end,end)
        assert rc == 1 and frame == index*9
        assert observe(lib,state.core,frame,job,Estimate(0,0,400000,.9,.91,0)) == 1


@pytest.mark.parametrize("anchor", [1000000,2**60+1])
def test_delayed_dma_can_use_entire_existing_forecast_horizon(live_api, anchor):
    state = fresh(live_api,anchor)
    history(live_api,state,anchor)
    # The next historical anchor (frame72) is incomplete in the DMA ring.
    # Actual RX has reached frame85, beyond the old fixed candidate loop.
    retained, now = anchor+72*RATE//750+N-1, anchor+85*RATE//750
    rc, frame, job, batch = next_job(live_api,state,anchor,retained,now)
    assert rc == 2 and frame == 86 and job.start >= now+2500
    assert frame+batch.prediction.repeats-1-state.core.trend.history.last_supported <= 32
    assert state.core.trend.history.last_supported == 63
    assert not state.core.pending and state.core.ready


def test_incomplete_first_pilot_waits_without_fabricating_history(live_api):
    state = fresh(live_api)
    for _ in range(3):
        assert next_job(live_api,state,1000000,1000000+N-1,1020000)[0] == 0
        assert state.core.valid and not state.core.pending and state.core.jobs == 0
    rc, frame, job, _ = next_job(live_api,state,1000000,1000000+N,1020000)
    assert rc == 1 and frame == 0
    assert observe(live_api,state.core,frame,job,Estimate(0,0,400000,.9,.91,0)) == 1


def test_excessive_delivery_lag_waits_with_unchanged_expiry_then_can_catch_up(live_api):
    state = fresh(live_api)
    history(live_api,state,1000000)
    assert next_job(live_api,state,1000000,1243299,1500000)[0] == 0
    assert state.core.trend.history.last_supported == 63
    # Delivery resumes; complete past anchors are consumed before new admission.
    while True:
        rc, frame, job, batch = next_job(live_api,state,1000000,1500000,1500000)
        if rc == 2:
            assert job.start>=1502500 and frame+7-state.core.trend.history.last_supported<=32
            break
        assert rc == 1
        assert observe(live_api,state.core,frame,job,Estimate(0,0,400000,.9,.91,0)) == 1


@pytest.mark.parametrize("damage", ["source_regression","retained_regression","earliest_regression",
                                    "deadline","future_iq","overwrite","pending"])
def test_source_ownership_and_deadline_faults_clear_outputs(live_api, damage):
    state = fresh(live_api)
    earliest, retained, now = 1000000,1001000,1002000
    assert next_job(live_api,state,earliest,retained,now)[0] == 0
    if damage == "source_regression": now -= 1
    if damage == "retained_regression": retained -= 1
    if damage == "earliest_regression": earliest -= 1
    if damage == "deadline": now = state.source_deadline+1
    if damage == "future_iq": retained = now+1
    if damage == "overwrite": earliest += 1
    if damage == "pending":
        retained = now = 1010000
        assert next_job(live_api,state,earliest,retained,now)[0] == 1
    assert next_job(live_api,state,earliest,retained,now)[0] == -1
    assert not state.core.valid and not state.core.ready and not state.core.pending
    assert state.core.failure == (3 if damage=="deadline" else 1 if damage in ("future_iq","pending") else 2)


@pytest.mark.parametrize("block_samples", [4096,65536,100000])
def test_continuous_ring_delivery_and_catchup_produce_only_future_jobs(live_api, recent_iq, block_samples):
    anchor = 2**60+99
    state = fresh(live_api,anchor)
    ring, storage = ring_fresh(recent_iq,capacity=RATE,start=anchor,epoch=3)
    now = anchor+1638500  # aged resolver input as in the measured catch-up case
    jobs = waits = 0
    # Deterministic block content makes wrapped job copies independently checkable.
    pair = (-32768,32767)
    for _ in range(300):
        delivered = anchor+((now-anchor)//block_samples)*block_samples
        while ring.end < delivered:
            assert append(recent_iq,ring,[pair]*block_samples,epoch=3) == 0
        rc, frame, job, batch = next_job(live_api,state,ring.first,ring.end,now)
        if rc == 0:
            waits += 1
            now += 2500
            continue
        assert rc in (1,2)
        if rc == 2:
            assert job.start>=now+2500 and frame+7-state.core.trend.history.last_supported<=32
            assert 60<jobs<90
            assert waits<50
            break
        assert read(recent_iq,ring,job.start,N,epoch=3) == (0,[pair]*N)
        truth = Fraction(anchor)+Fraction(frame*RATE,750)
        selected = Fraction(job.start)+Fraction(job.reference_phase,4)
        estimate = Estimate(float(truth-selected)/RATE,0,400000,.9,.91,0)
        assert observe(live_api,state.core,frame,job,estimate) == 1
        jobs += 1
        now += 5500
    else:
        pytest.fail("bounded live catch-up did not finish")
    assert len(storage) == 2*RATE
