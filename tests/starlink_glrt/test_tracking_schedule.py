"""Multirate C and RTL scheduling against exact rational native coordinates."""
import ctypes as c
import random
import subprocess
from fractions import Fraction

import pytest

from .test_native_schedule_port import Batch
from .test_native_schedule_rtl import BENCH, CANCEL, WAIT, config, simulate, tick
from .test_native_solver import ROOT

RATES = (2500000, 5000000, 15000000, 30000000, 60000000)


class TrackingBatch(c.Structure):
    _fields_ = [("prediction", Batch), ("rate", c.c_uint32)]


class Job(c.Structure):
    _fields_ = [("start", c.c_uint64), ("phase_step", c.c_uint32), ("reference_phase", c.c_uint32)]


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    output = tmp_path_factory.mktemp("tracking-schedule") / "port.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
        str(ROOT / "tools/glrt_tracking_schedule.c"), str(ROOT / "tools/glrt_native_solver.c"),
        "-lm", "-o", str(output)], check=True)
    lib = c.CDLL(str(output))
    lib.glrt_tracking_batch_valid.argtypes = [c.POINTER(TrackingBatch)]
    lib.glrt_tracking_prediction.argtypes = [c.POINTER(TrackingBatch), c.c_uint, c.POINTER(Job)]
    return lib


def descriptor(rate, **changes):
    fields = {"epoch": 3, "tag": 7, "start": 2**60+1001, "fraction": 0,
        "period": round(Fraction(rate*65536, 750)), "step": 7310173*65536,
        "delta": 2**48-65537, "seed": 17, "repeats": 64, "expires": 2**64-1}
    fields.update(changes)
    return TrackingBatch(Batch(**fields), rate)


def oracle(b, repeat):
    p = b.prediction
    phases = 4 if b.rate == 2500000 else 1
    coordinate = Fraction(p.start*65536+p.fraction+repeat*p.period, 65536)
    whole, phase = divmod(round(coordinate*phases), phases)
    step = round(Fraction(p.step+repeat*p.delta, 65536)) % 2**32
    return whole, step, phase


@pytest.mark.parametrize("rate", RATES)
def test_c_keeps_high_indexes_fractional_reference_and_carrier_exact(port, rate):
    rng = random.Random(rate)
    for _ in range(100):
        b = descriptor(rate, start=2**60+rng.randrange(100000), fraction=rng.randrange(65536),
            period=round(Fraction(rate*65536, 750))+rng.randrange(-100, 101),
            step=rng.randrange(2**48), delta=rng.randrange(2**48))
        assert port.glrt_tracking_batch_valid(c.byref(b)) == 1
        for n in (0, 1, 2, 31, 63):
            job = Job()
            assert port.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == 0
            assert (job.start, job.phase_step, job.reference_phase) == oracle(b, n)


@pytest.mark.parametrize("rate,phases", [(2500000, 4), (5000000, 1)])
def test_fractional_repeats_do_not_accumulate_whole_sample_drift(port, rate, phases):
    b = descriptor(rate, start=10000)
    for n in range(64):
        job = Job()
        assert port.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == 0
        origin = Fraction(job.start*phases+job.reference_phase, phases)
        assert abs(origin-Fraction(10000)-Fraction(n*rate, 750)) <= Fraction(1, 2*phases)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fraction", [8192, 24576, 32768, 40960, 57344, 65535])
def test_reference_rounding_ties_and_carries_match_rational_oracle(port, rate, fraction):
    for parity in (0, 1):
        b = descriptor(rate, start=2**60+1000+parity, fraction=fraction)
        job = Job()
        assert port.glrt_tracking_prediction(c.byref(b), 0, c.byref(job)) == 0
        assert (job.start, job.phase_step, job.reference_phase) == oracle(b, 0)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fault", ["rate", "epoch", "tag", "repeats", "fraction", "step", "delta",
    "early", "short_period", "long_period", "expiry", "overflow", "repeat"])
def test_invalid_or_expired_prediction_leaves_output_untouched(port, rate, fault):
    b = descriptor(rate)
    stride = 60000000 // rate
    minimum, issue = (64+stride-1)//stride, (512+stride-1)//stride
    count = rate*33//25000
    n = 0
    if fault == "rate": b.rate = 2500001
    elif fault in ("epoch", "tag", "repeats"): setattr(b.prediction, fault, 0)
    elif fault == "fraction": b.prediction.fraction = 65536
    elif fault in ("step", "delta"): setattr(b.prediction, fault, 2**48)
    elif fault == "early": b.prediction.start = issue-1
    elif fault == "short_period": b.prediction.period = (count+2*minimum)*65536-1
    elif fault == "long_period": b.prediction.period = 81000*65536*rate//60000000+1
    elif fault == "expiry": b.prediction.expires = b.prediction.start+count-2
    elif fault == "overflow": b.prediction.start = 2**64-1; b.prediction.fraction = 65535
    else: n = 64
    job = Job(91, 92, 93)
    assert port.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == -1
    assert (job.start, job.phase_step, job.reference_phase) == (91, 92, 93)


def rate_bench(rate):
    stride = 60000000//rate
    minimum, issue = (64+stride-1)//stride, (512+stride-1)//stride
    phases, bits = (4, 2) if rate == 2500000 else (1, 1)
    bench = BENCH.replace("wire job_reference_phase,decision_reference_phase;",
        f"wire [{bits-1}:0] job_reference_phase,decision_reference_phase;")
    bench = bench.replace("starlink_glrt_native_schedule dut(.*);",
        "starlink_glrt_native_schedule #("
        f".SAMPLE_COUNT({rate*33//25000}),.ISSUE_LEAD({issue}),.MINIMUM_LEAD({minimum}),"
        f".MAX_PERIOD_SAMPLES({81000*rate//60000000}),.REFERENCE_PHASES({phases})) dut(.*);")
    bench = bench.replace("job_start-latest_index<64 || job_start-latest_index>512",
        f"job_start-latest_index<{minimum} || job_start-latest_index>{issue}")
    bench = bench.replace('"J %h %h %h %h %h",job_tag,job_repeat,job_start,job_phase_seed,job_phase_step',
        '"J %h %h %h %h %h %h",job_tag,job_repeat,job_start,job_phase_seed,job_phase_step,job_reference_phase')
    bench = bench.replace('"D %h %h %h %h",decision_tag,decision_repeat,decision_start,decision_reason',
        '"D %h %h %h %h %h",decision_tag,decision_repeat,decision_start,decision_reason,decision_reference_phase')
    return bench


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("fraction", [0, 8192, 24576, 32768, 57344, 65535])
def test_rtl_schedules_64_real_rate_opportunities_with_exact_phase_and_no_host_roundtrip(
        tmp_path, port, rate, fraction):
    b = descriptor(rate, fraction=fraction)
    p = b.prediction
    rows = [config(p.tag, p.start, fraction=p.fraction, period=p.period,
        step=p.step, delta=p.delta, count=64)] + [WAIT]*6
    jobs = []
    issue = (512+60000000//rate-1)//(60000000//rate)
    for n in range(64):
        start, step, phase = oracle(b, n)
        job = Job()
        assert port.glrt_tracking_prediction(c.byref(b), n, c.byref(job)) == 0
        assert (job.start, job.phase_step, job.reference_phase) == (start, step, phase)
        rows += [tick(start-issue-1), tick(start-issue)] + [WAIT]*5
        jobs.append((p.tag, n, start, 0xfffffff9, step, phase))
    result = simulate(tmp_path, rows, bench=rate_bench(rate))
    assert result["J"] == jobs
    assert result["D"] == [(tag, n, start, 0, phase) for tag, n, start, _, _, phase in jobs]
    assert result["R"] == [] and result["S"] == [(64, 64, 0, 0, 0, 0, 0, 0)]


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("cause", ["cancel", "source", "expiry", "unavailable", "no_space", "late"])
def test_rate_specific_schedule_fences_or_accounts_for_missing_measurements(tmp_path, rate, cause):
    p = descriptor(rate, start=1000000, fraction=24576, repeats=3).prediction
    stride = 60000000//rate
    minimum, issue = (64+stride-1)//stride, (512+stride-1)//stride
    expiry = p.start+rate*33//25000-2 if cause == "expiry" else 2**64-1
    rows = [config(p.tag, p.start, fraction=p.fraction, period=p.period, count=3, expires=expiry)]
    if cause in ("cancel", "source"):
        rows += [WAIT]*2 + [CANCEL if cause == "cancel" else tick(1, good=False)] + [WAIT]*7
    elif cause == "expiry": rows += [WAIT]*10
    else:
        rows += [WAIT]*6
        for n in range(3):
            start, _, _ = oracle(TrackingBatch(p, rate), n)
            rows += [tick(start-issue, ready=cause!="unavailable", space=cause!="no_space")
                     if cause != "late" else tick(start-minimum+1)]
            rows += [tick(start-minimum+1, ready=cause!="unavailable", space=cause!="no_space")]+[WAIT]*6
    result = simulate(tmp_path, rows, bench=rate_bench(rate))
    counts = {"late": 2, "no_space": 3, "unavailable": 4, "source": 4, "expiry": 5, "cancel": 6}
    expected = [3, 0, 0, 0, 0, 0, 0, 0]
    expected[counts[cause]] = 3
    assert not result["J"] and result["S"] == [tuple(expected)]
