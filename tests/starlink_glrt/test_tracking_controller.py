"""GLT1 controller transactions at every rate, with actual moment decoding.

The deterministic radio port models finite queues and source time. Numerical
precision and hardware throughput remain separate RTL/physical qualification.
"""
import ctypes as c

import numpy as np
import pytest

from tools.starlink_glrt_tracking_abi import TrackingResult, bank_id

from . import test_native_controller, test_tracking_solver
from .test_native_controller import Radio
from .test_native_schedule_port import Batch
from .test_tracking_schedule import RATES
from .test_tracking_schedule import TrackingBatch as CBatch

controller = test_native_controller.controller
models = test_tracking_solver.models


@pytest.fixture(scope="module")
def pilot_moments(models):
    return {key: list(test_tracking_solver.moments(raw[:,:2],raw).words)
            for key,(_,raw) in models.items()}


@pytest.mark.parametrize("rate", RATES)
def test_every_repeat_rate_bound_feedback_and_phase_delay_once(controller,pilot_moments,rate):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    assert radio.run() == 0
    heads = [TrackingResult.from_sysfs(body.decode()) for kind,name,body in radio.events
             if (kind,name) == ("retain","head")]
    estimates = [body.split() for kind,name,body in radio.events
                 if (kind,name) == ("retain","estimate")]
    assert len(heads) == 128
    assert [int(row[2]) for row in estimates] == list(range(128))
    assert all(int(row[8]) == 0 for row in estimates)
    assert all(h.rate == rate and h.count == radio.samples for h in heads)
    assert all(name.startswith("tracking_") for kind,name,_ in radio.events
               if kind in ("read","write"))
    assert radio.writes("command") == [b"4\n"]
    assert sum(b.repeats for b in radio.descriptors) == 128
    # This port fixture emits the selected reference itself, so its observations
    # follow the quantized scheduled positions, not a separate physical signal.
    # Independently regress the observations available at the first feedback
    # submission to verify that reference phase enters the prediction once.
    phases = 4 if rate == 2500000 else 1
    observed, retained_heads, submissions = [], [], 0
    for kind,name,body in radio.events:
        if (kind,name) == ("retain","head"):
            retained_heads.append(TrackingResult.from_sysfs(body.decode()))
        elif (kind,name) == ("retain","estimate"):
            row = body.split()
            h = retained_heads[-1]
            observed.append((int(row[2]), h.start-heads[0].start+
                             h.reference_phase/phases+float(row[3])*rate))
        elif (kind,name) == ("retain","descriptor"):
            submissions += 1
            if submissions == 2:
                assert len(observed) >= 8
                slope,intercept = np.polyfit(*np.array(observed).T,1)
                first_frame = int(body.split()[1])
                predicted = radio.descriptors[1]
                actual = predicted.start-heads[0].start+predicted.fraction/65536
                assert abs(actual-(intercept+slope*first_frame)) <= 2/65536
                break
    assert submissions == 2
    if rate == 2500000:
        assert heads[0].reference_phase == 2
        assert len({h.reference_phase for h in heads}) >= 3
    assert not radio.pending and not radio.queue and not radio.valid


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("failure", ["head", "estimate", "bad_head", "submit", "pop", "gap", "reject"])
def test_failures_preserve_evidence_and_bound_recovery(controller,pilot_moments,rate,failure):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    expected = {"head":-6,"estimate":-6,"bad_head":-2,"submit":-1,"pop":-1,"gap":-3,"reject":-4}
    if failure in ("head","estimate"):
        radio.fail_retain = failure
    elif failure == "bad_head": radio.bad_head = True
    elif failure == "submit": radio.submit_return_error = True
    elif failure == "reject": radio.reject = True
    else:
        assert radio.tick() == 1
        radio.advance(rate//100)
        assert len(radio.queue) > 1
        if failure == "pop": radio.pop_return_error = True
        else: radio.gap = True
    assert radio.run() == expected[failure]
    assert radio.writes("command").count(b"2\n") == 1
    assert len(radio.writes("submit")) == 1
    if failure in ("head","estimate","bad_head"):
        assert radio.queue and not radio.writes("pop")
    elif failure == "pop":
        assert radio.queue and len(radio.writes("pop")) == 1
        assert b"4\n" not in radio.writes("command")
    else:
        assert not radio.pending and not radio.queue


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("remaining", [-1,0,1])
def test_retention_reread_enforces_100us_lead_at_each_rate(controller,pilot_moments,rate,remaining):
    radio = Radio(controller,pilot_moments,frames=16,tracking_rate=rate)
    radio.retention_delay = radio.seed.start-radio.latest-(rate//10000+remaining)
    assert radio.run() == (-5 if remaining < 0 else 0)
    assert len(radio.writes("submit")) == int(remaining >= 0)


@pytest.mark.parametrize("rate", RATES)
def test_foreign_valid_snapshot_profile_is_rejected_before_submission(controller,pilot_moments,rate):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    original = radio.snapshot
    other = 15000000 if rate != 15000000 else 30000000
    def foreign():
        fields = original().split()
        fields[-4:] = [f"{x:08x}".encode() for x in (other,other*33//25000,bank_id(other),1)]
        return b" ".join(fields)+b"\n"
    radio.snapshot = foreign
    assert radio.run() == -2
    assert not radio.writes("submit") and not radio.writes("pop")


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("invalid", ["expiry", "overflow", "rate", "frames", "seconds"])
def test_invalid_bootstrap_rejected_before_io(controller,pilot_moments,rate,invalid):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    batch = CBatch(Batch(**{name:getattr(radio.seed,name) for name,_ in Batch._fields_}),rate)
    frames, seconds = 128, 2.0
    if invalid == "expiry": batch.prediction.expires = batch.prediction.start+radio.samples-1
    elif invalid == "overflow": batch.prediction.start = 2**64-100; batch.prediction.expires = 2**64-1
    elif invalid == "rate": batch.rate = 25000000
    elif invalid == "frames": frames = 15
    else: seconds = float("nan")
    assert controller.glrt_tracking_controller_init(radio.state,c.byref(radio.ports),
                                                     c.byref(batch),frames,seconds) == -1
    assert not radio.events
