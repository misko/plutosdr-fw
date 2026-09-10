"""Conditional source-time arithmetic, never hardware/lock acceptance tests."""

from pathlib import Path

import pytest

from tests.starlink_oracle.visit_handoff_budget import nominal_visit_budget


def budget(rate=15_000_000, phase=520, delay=0, start=0):
    ratio = rate // 15_000_000
    return nominal_visit_budget(rate_hz=rate, visit_start=start, coarse_phase=phase,
                                map_available=start + 1_280_854 * ratio,
                                command_delay_bound=delay)


@pytest.mark.parametrize("rate", (15_000_000, 30_000_000, 60_000_000))
@pytest.mark.parametrize("phase", (0, 1, 520, 6390, 19999))
@pytest.mark.parametrize("delay_us", (0, 1, 1000, 5000, 10000, 20000, 30000, 40000))
def test_exact_slots_against_brute_force_independent_inequalities(rate, phase, delay_us):
    start = (1 << 33) + 123
    result = budget(rate, phase, delay_us * rate // 1_000_000, start)
    ratio = rate // 15_000_000
    expected = []
    for ordinal in range(91):
        center = start + (phase + ordinal * 20000) * ratio
        capture_first = center - 32 * ratio
        capture_stop = capture_first + 130 * ratio
        if (capture_first >= start and capture_stop <= start + rate * 12 // 100
                and center - result.assumed_latest_admission >= 65536 * ratio
                and capture_first - (result.assumed_latest_admission + 1) >= 64 * ratio):
            expected.append(center)
    assert result.count == len(expected)
    assert result.first_center == (expected[0] if expected else None)
    assert result.last_center == (expected[-1] if expected else None)


def test_scaled_rate_does_not_create_more_observation_time():
    for rate in (15_000_000, 30_000_000, 60_000_000):
        result = budget(rate)
        ratio = rate // 15_000_000
        assert result.count == 22
        assert result.first_center == 1_360_520 * ratio
        assert result.last_center == 1_780_520 * ratio
        assert result.host_lead_samples == 65536 * ratio


def test_half_open_capture_end_and_exact_host_lead_boundary():
    result = nominal_visit_budget(rate_hz=15_000_000, visit_start=0,
                                 coarse_phase=19902, map_available=1_734_366,
                                 command_delay_bound=0)
    assert result.count == 1 and result.first_center == 1_799_902
    assert result.last_center + result.capture_after == result.visit_stop
    assert result.first_center - result.assumed_latest_admission == 65536
    assert nominal_visit_budget(rate_hz=15_000_000, visit_start=0,
                                coarse_phase=19902, map_available=1_734_367,
                                command_delay_bound=0).count == 0


def test_uint64_end_never_wraps_and_no_false_empty_center():
    start = (1 << 64) - 1_800_000
    result = budget(start=start)
    assert result.visit_stop == 1 << 64
    assert result.last_center < 1 << 64
    result = budget(delay=1_000_000)
    assert result.count == 0 and result.first_center is None and result.last_center is None
    with pytest.raises(ValueError, match="wrap"):
        budget(start=start+1)
    with pytest.raises(ValueError, match="wrap"):
        budget(start=start, delay=1_000_000)


@pytest.mark.parametrize("field", ("rate_hz", "visit_start", "coarse_phase", "map_available", "command_delay_bound"))
@pytest.mark.parametrize("bad", (True, -1, 1.0, None, 1 << 64))
def test_invalid_scalar_rejected(field, bad):
    args = {"rate_hz": 15_000_000, "visit_start": 0, "coarse_phase": 520,
            "map_available": 1_280_854, "command_delay_bound": 0}
    args[field] = bad
    with pytest.raises(ValueError):
        nominal_visit_budget(**args)


def test_contract_bounds_and_geometry_remain_tied_to_native_sources():
    root = Path(__file__).resolve().parents[1]
    header = (root / "tools/starlink_pssctl/starlink_pss_hw.h").read_text()
    rtl = (root / "hdl/library/starlink_pss_raw_correlator/starlink_pss_candidate_scheduler.v").read_text()
    assert "#define PSS_MINIMUM_HOST_LEAD (UINT64_C(65536) * PSS_RATE_MULTIPLIER)" in header
    assert "#define PSS_CAPTURE_SAMPLES (130U * PSS_RATE_MULTIPLIER)" in header
    assert "MINIMUM_LEAD_SAMPLES = 64'd64 * RATE_MULTIPLIER" in rtl
    assert "admission_next_index = i_sample_index + 1'b1" in rtl


@pytest.mark.parametrize("change", ({"rate_hz": 25_000_000}, {"coarse_phase": 20000},
                                   {"map_available": 1_800_000}, {"visit_start": 1_280_855}))
def test_out_of_contract_geometry_rejected(change):
    args = {"rate_hz": 15_000_000, "visit_start": 0, "coarse_phase": 520,
            "map_available": 1_280_854, "command_delay_bound": 0}
    args.update(change)
    with pytest.raises(ValueError):
        nominal_visit_budget(**args)
