from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.starlink_pss_scanner_plan import (
    DecimationClock,
    RADIO_SERIALS,
    SOURCE_RATES,
    compile_plan,
)
from tests.starlink_oracle.numerology import numerology_for_rate


@pytest.mark.parametrize("rate", SOURCE_RATES)
def test_all_targets_close_the_existing_pss_geometry(rate: int) -> None:
    plan = compile_plan(RADIO_SERIALS[0], rate)
    geometry = numerology_for_rate(rate)
    assert [(target.channel, target.edge) for target in plan.targets] == [
        (channel, edge) for edge in ("lower", "upper") for channel in range(1, 5)
    ]
    assert plan.total_decimation == plan.canonical_decimation * plan.pilot_decimation
    assert plan.valid_visit_output_samples == 300_000
    assert plan.valid_visit_source_samples == plan.total_decimation * 300_000
    assert plan.nominal_duration_source_samples == rate * 300
    for target in plan.targets:
        channel_if = 1_075_000_000 + (target.channel - 1) * 250_000_000
        assert target.source_lo_nominal_hz - channel_if == Fraction(
            geometry.edge_center_offset_hz(target.edge)
        )
        assert target.source_lo_nominal_hz + target.source_to_canonical_mix_hz == (
            target.canonical_center_if_hz
        )
        assert target.canonical_center_if_hz + target.pilot_mix_from_canonical_hz == (
            target.pilot_template_center_if_hz
        )
        assert target.source_lo_request_hz == round(target.source_lo_nominal_hz)
        assert abs(target.source_lo_rounding_error_hz) == Fraction(1, 2)


def test_band_reference_is_not_silently_confused_with_template_center() -> None:
    plan = compile_plan(RADIO_SERIALS[1], 30_000_000)
    assert plan.targets[0].scanner_pilot_reference_if_hz == 959_687_500
    assert plan.targets[-1].scanner_pilot_reference_if_hz == 1_940_312_500
    for target in plan.targets:
        assert target.template_minus_scanner_reference_hz == Fraction(-234_375, 2)
        assert target.pilot_mix_from_canonical_hz == (
            2_812_500 if target.edge == "upper" else -3_046_875
        )


@pytest.mark.parametrize("rate", SOURCE_RATES)
@pytest.mark.parametrize("delay", (Fraction(0), Fraction(7), Fraction(31, 2)))
def test_counter_mapping_preserves_120ms_even_near_uint64_limit(
    rate: int, delay: Fraction
) -> None:
    clock = DecimationClock(rate, 17, delay)
    for start in (1001, 999_999, (1 << 64) - 2 * rate):
        end = start + rate * 120 // 1000
        first, stop = clock.output_span(start, end)
        assert stop - first == 300_000
        assert clock.source_center(first) >= start
        assert clock.source_center(first - 1) < start
        assert clock.source_center(stop - 1) < end
        assert clock.source_center(stop) >= end


def test_counter_boundary_does_not_drop_or_duplicate_fractional_centers() -> None:
    clock = DecimationClock(60_000_000, 7, Fraction(21, 2))
    first, middle = clock.output_span(1_001, 8_888)
    repeated_middle, last = clock.output_span(8_888, 22_222)
    assert middle == repeated_middle
    assert (first, last) == clock.output_span(1_001, 22_222)
    assert clock.output_span(8_888, 8_888) == (middle, middle)
    with pytest.raises(ValueError, match="reversed"):
        clock.output_span(8_888, 1_001)
    with pytest.raises(ValueError, match="Fraction"):
        DecimationClock(60_000_000, 0, 0.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("rate", (True, 2_500_000, 30_000_000.0, 61_440_000))
def test_rejects_unsupported_or_ambiguous_rates(rate: int) -> None:
    with pytest.raises(ValueError, match="source_rate_hz"):
        compile_plan(RADIO_SERIALS[0], rate)


@pytest.mark.parametrize("serial", ("ip:192.168.1.17", "192.168.1.18", "other-radio"))
def test_rejects_unscoped_radio_identities(serial: str) -> None:
    with pytest.raises(ValueError, match="agreed"):
        compile_plan(serial, 15_000_000)


@pytest.mark.parametrize(
    "parameters",
    (
        {"residual_cfo_bound_hz": 1_200_000},
        {"output_passband_hz": 2_500_000},
        {"residual_cfo_bound_hz": -1},
        {"guard_us": 0},
        {"guard_us": 120_000},
        {"guard_us": True},
    ),
)
def test_rejects_impossible_coverage_and_invalid_guards(parameters: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        compile_plan(RADIO_SERIALS[0], 15_000_000, **parameters)


def test_offline_report_cannot_be_mistaken_for_hardware_qualification() -> None:
    document = compile_plan(RADIO_SERIALS[0], 60_000_000).document()
    assert document["claim_scope"] == "offline_geometry_only"
    for name in (
        "radio_access",
        "hardware_qualified",
        "pss_detected",
        "glrt_detected",
        "frame_lock_claim",
        "analog_and_digital_filter_response_qualified",
    ):
        assert document[name] is False
    assert json.loads(json.dumps(document)) == document
    assert document["plan"]["targets"][0]["source_lo_nominal_hz"]["denominator"] == 2


def test_cli_runs_with_only_the_python_standard_library() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts/starlink_pss_scanner_plan.py"
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(script), "--serial", RADIO_SERIALS[0],
         "--rate-msps", "30"],
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)
    assert document["radio_access"] is False
    assert document["plan"]["total_decimation"] == 12
