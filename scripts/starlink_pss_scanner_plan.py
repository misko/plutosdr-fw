#!/usr/bin/env python3
"""Hardware-free geometry for the experimental paired PSS/GLRT scanner.

This compiler opens no radios and does not authorize deployment. In particular,
listing .17 here does not bypass the production persistent-hop exclusion.
Fractional frequencies and source-sample times are kept exact until an explicit
LO request is rounded. Actual radio readback must replace that request in receipts.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from fractions import Fraction
import json
from typing import Any


SCHEMA = "plutosdr-fw.starlink-paired-scanner-plan.v1"
RADIO_SERIALS = (
    "1040007c4a94000211000b009186843ef2",  # .18: local canary
    "104000bac4950008230026001b440a003a",  # .17: outdoor, network only
)
SOURCE_RATES = (15_000_000, 30_000_000, 60_000_000)
CANONICAL_RATE_HZ = 15_000_000
OUTPUT_RATE_HZ = 2_500_000
SUBCARRIER_SPACING_HZ = 234_375
LNB_LO_HZ = 9_750_000_000
FIRST_CHANNEL_CENTER_RF_HZ = 10_825_000_000
CHANNEL_SPACING_HZ = 250_000_000
NATIVE_BANDWIDTH_HZ = 240_000_000
PILOT_OCCUPIED_BANDWIDTH_HZ = 8 * SUBCARRIER_SPACING_HZ
VISIT_MS = 120
DURATION_SECONDS = 300


def _integer(value: int, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _source_rate(value: int) -> int:
    _integer(value, "source_rate_hz", minimum=1)
    if value not in SOURCE_RATES:
        raise ValueError("source_rate_hz must be 15000000, 30000000, or 60000000")
    return value


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


@dataclass(frozen=True)
class DecimationClock:
    """Output sample centers in an unreset source-counter coordinate.

    phase_source_samples names the accepted source beat for output index zero;
    group_delay_source_samples is the complete causal filter delay. This mapping
    does not itself certify that the filter's support avoids a hop boundary.
    """

    source_rate_hz: int
    phase_source_samples: int
    group_delay_source_samples: Fraction

    def __post_init__(self) -> None:
        _source_rate(self.source_rate_hz)
        _integer(self.phase_source_samples, "phase_source_samples")
        delay = self.group_delay_source_samples
        if not isinstance(delay, Fraction) or delay < 0:
            raise ValueError("group delay must be a nonnegative exact Fraction")

    @property
    def ratio(self) -> int:
        return self.source_rate_hz // OUTPUT_RATE_HZ

    def source_center(self, output_index: int) -> Fraction:
        _integer(output_index, "output_index")
        return (
            Fraction(self.phase_source_samples + output_index * self.ratio)
            - self.group_delay_source_samples
        )

    def output_span(self, source_start: int, source_end: int) -> tuple[int, int]:
        """Return output indices with centers in the half-open source interval."""

        _integer(source_start, "source_start")
        _integer(source_end, "source_end")
        if source_end < source_start:
            raise ValueError("source interval is reversed")

        def boundary(index: int) -> int:
            return max(
                0,
                _ceil(
                    (
                        Fraction(index - self.phase_source_samples)
                        + self.group_delay_source_samples
                    )
                    / self.ratio
                ),
            )

        return boundary(source_start), boundary(source_end)


@dataclass(frozen=True)
class Target:
    ordinal: int
    channel: int
    edge: str
    source_lo_nominal_hz: Fraction
    source_lo_request_hz: int
    source_lo_rounding_error_hz: Fraction
    canonical_center_if_hz: Fraction
    source_to_canonical_mix_hz: Fraction
    pilot_template_center_if_hz: Fraction
    pilot_mix_from_canonical_hz: Fraction
    scanner_pilot_reference_if_hz: int
    template_minus_scanner_reference_hz: Fraction


@dataclass(frozen=True)
class ScannerPlan:
    serial: str
    source_rate_hz: int
    output_rate_hz: int
    total_decimation: int
    canonical_decimation: int
    pilot_decimation: int
    valid_visit_source_samples: int
    valid_visit_output_samples: int
    requested_guard_source_samples: int
    nominal_duration_source_samples: int
    requested_output_passband_hz: int
    residual_cfo_bound_hz: int
    targets: tuple[Target, ...]

    def document(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "claim_scope": "offline_geometry_only",
            "radio_access": False,
            "hardware_qualified": False,
            "pss_detected": False,
            "glrt_detected": False,
            "frame_lock_claim": False,
            "frequency_encoding": "exact rational Hz; mixer multiplies by exp(-j*2*pi*f*t)",
            "analog_and_digital_filter_response_qualified": False,
            "schedule": "120 ms valid per visit; measured transition plus guard is additional",
            "plan": _json_exact(asdict(self)),
        }


def _json_exact(value: Any) -> Any:
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, dict):
        return {key: _json_exact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_exact(item) for item in value]
    return value


def compile_plan(
    serial: str,
    source_rate_hz: int,
    *,
    guard_us: int = 1_000,
    output_passband_hz: int = 2_200_000,
    residual_cfo_bound_hz: int = 100_000,
) -> ScannerPlan:
    """Compile an explicit fixed-rate plan, never a hardware execution request.

    output_passband_hz is a requested full two-sided passband, not a measured
    filter property. Pilot occupancy includes the nominal eight-bin bandwidth.
    The residual bound is around a separately calibrated pilot center, not an
    assertion that an uncalibrated LNB lies inside this interval.
    """

    if serial not in RADIO_SERIALS:
        raise ValueError("scanner development is scoped only to the agreed .17/.18 serials")
    _source_rate(source_rate_hz)
    _integer(guard_us, "guard_us", minimum=1)
    _integer(output_passband_hz, "output_passband_hz", minimum=1)
    _integer(residual_cfo_bound_hz, "residual_cfo_bound_hz")
    if output_passband_hz >= OUTPUT_RATE_HZ:
        raise ValueError("output passband must leave an anti-alias transition band")
    if PILOT_OCCUPIED_BANDWIDTH_HZ + 2 * residual_cfo_bound_hz > output_passband_hz:
        raise ValueError("pilot occupancy plus residual CFO does not fit the output passband")
    guard_numerator = source_rate_hz * guard_us
    if guard_numerator % 1_000_000:
        raise ValueError("guard must be source-sample exact")
    if guard_us >= VISIT_MS * 1_000:
        raise ValueError("guard must be shorter than the valid visit")

    # These centers reproduce the immutable PSS oracle at all three rates.
    outer_edge = Fraction(NATIVE_BANDWIDTH_HZ - SUBCARRIER_SPACING_HZ, 2)
    canonical_magnitude = outer_edge - CANONICAL_RATE_HZ // 2
    source_magnitude = outer_edge - source_rate_hz // 2
    targets = []
    for edge, sign, mean_pilot_bin in (
        ("lower", -1, Fraction(-985, 2)),  # mean signed bins 528..535
        ("upper", 1, Fraction(983, 2)),  # mean signed bins 488..495
    ):
        for channel in range(1, 5):
            channel_if = (
                FIRST_CHANNEL_CENTER_RF_HZ
                + (channel - 1) * CHANNEL_SPACING_HZ
                - LNB_LO_HZ
            )
            source_lo = channel_if + sign * source_magnitude
            canonical = channel_if + sign * canonical_magnitude
            pilot_center = channel_if + mean_pilot_bin * SUBCARRIER_SPACING_HZ
            # The existing scanner's band reference is distinct from the
            # exact sampled pilot-template mean: both edges differ by -F/2.
            scanner_reference = channel_if + sign * 492 * SUBCARRIER_SPACING_HZ
            targets.append(
                Target(
                    ordinal=len(targets),
                    channel=channel,
                    edge=edge,
                    source_lo_nominal_hz=source_lo,
                    source_lo_request_hz=round(source_lo),
                    source_lo_rounding_error_hz=round(source_lo) - source_lo,
                    canonical_center_if_hz=canonical,
                    source_to_canonical_mix_hz=canonical - source_lo,
                    pilot_template_center_if_hz=pilot_center,
                    pilot_mix_from_canonical_hz=pilot_center - canonical,
                    scanner_pilot_reference_if_hz=scanner_reference,
                    template_minus_scanner_reference_hz=pilot_center - scanner_reference,
                )
            )
    return ScannerPlan(
        serial=serial,
        source_rate_hz=source_rate_hz,
        output_rate_hz=OUTPUT_RATE_HZ,
        total_decimation=source_rate_hz // OUTPUT_RATE_HZ,
        canonical_decimation=source_rate_hz // CANONICAL_RATE_HZ,
        pilot_decimation=6,
        valid_visit_source_samples=source_rate_hz * VISIT_MS // 1_000,
        valid_visit_output_samples=OUTPUT_RATE_HZ * VISIT_MS // 1_000,
        requested_guard_source_samples=guard_numerator // 1_000_000,
        nominal_duration_source_samples=source_rate_hz * DURATION_SECONDS,
        requested_output_passband_hz=output_passband_hz,
        residual_cfo_bound_hz=residual_cfo_bound_hz,
        targets=tuple(targets),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", choices=RADIO_SERIALS, required=True)
    parser.add_argument("--rate-msps", type=int, choices=(15, 30, 60), required=True)
    parser.add_argument("--guard-us", type=int, default=1_000)
    parser.add_argument("--residual-cfo-bound-hz", type=int, default=100_000)
    args = parser.parse_args()
    plan = compile_plan(
        args.serial,
        args.rate_msps * 1_000_000,
        guard_us=args.guard_us,
        residual_cfo_bound_hz=args.residual_cfo_bound_hz,
    )
    print(json.dumps(plan.document(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
