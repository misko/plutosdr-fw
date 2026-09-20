#!/usr/bin/env python3
"""Finite RX-only functional and counter/UTC evidence capture for issue #107.

No IQ payload is persisted. Visit boundaries, energy decisions, the scanner
terminal, receiver restoration and counter/UTC anchors are retained in a new
immutable JSON file. This reports timing evidence; it cannot qualify UTC
accuracy without an independently validated timing policy and RF reference.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import math
import os
import secrets
import sys
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

EXPECTED_FIRMWARE = "v0.54-plutoplus-spf-counter-utc-v1-rc1"
SUPPORTED_RATES = (10_000_000, 15_000_000, 20_000_000)
DUAL_RX_RATE_HZ = 2_500_000
DEFAULT_FREQUENCIES_HZ = (959_687_498, 1_209_687_498, 1_459_687_498, 1_709_687_500)
MAX_COUNTER_ANCHOR_GAP_NS = 10_000_000_000


def _json(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def counter_continuity_passed(visits: list[dict[str, Any]]) -> bool:
    """Require nonempty sample ranges without DMA loss or overlap.

    Positive gaps between adjacent visits are valid: retuning intentionally
    leaves samples outside each visit's admitted interval. DMA loss reported
    inside a visit and overlapping visit ranges remain continuity failures.
    """

    if not visits:
        return False
    previous_end: int | None = None
    for visit in visits:
        first = visit["first_sample"]
        end = visit["end_sample_exclusive"]
        if (
            visit["valid_sample_count"] <= 0
            or end <= first
            or visit["missing_samples_before"] != 0
            or (previous_end is not None and first < previous_end)
        ):
            return False
        previous_end = end
    return True


def iq_geometry_passed(
    visits: list[dict[str, Any]], *, rx_mask: int, terminal_iq_bytes: int | None
) -> tuple[bool, int, int]:
    """Check payload bytes against the shared per-channel sample counter.

    The source counter advances once per complex sample time index. With paired
    RX, that index contains one sample from each enabled receiver; it is not
    multiplied by the channel count when calculating continuity or anchors.
    """

    receiver_count = rx_mask.bit_count()
    if rx_mask not in (1, 3) or not visits or type(terminal_iq_bytes) is not int:
        return False, 0, 0
    sample_count = 0
    iq_bytes = 0
    for visit in visits:
        samples = visit.get("valid_sample_count")
        payload_bytes = visit.get("iq_bytes_received")
        if (
            type(samples) is not int
            or samples <= 0
            or type(payload_bytes) is not int
            or payload_bytes != samples * 4 * receiver_count
        ):
            return False, sample_count, iq_bytes
        sample_count += samples
        iq_bytes += payload_bytes
    return (
        terminal_iq_bytes == iq_bytes
        and terminal_iq_bytes == sample_count * 4 * receiver_count,
        sample_count,
        iq_bytes,
    )


def timing_anchor_coverage_passed(
    anchors: list[dict[str, Any]],
    *,
    first_valid_sample: int | None,
    last_valid_sample: int | None,
    sample_rate_hz: int,
) -> bool:
    """Require consistent anchors to cover both capture endpoints and gaps."""

    if (
        len(anchors) < 2
        or first_valid_sample is None
        or last_valid_sample is None
        or sample_rate_hz <= 0
    ):
        return False
    observations = [anchor["observation"] for anchor in anchors]
    origin = observations[0]
    identity = (
        origin["boot_id"], origin["session"], origin["generation"],
        origin["sample_rate_hz"], origin["epoch"],
    )
    if origin["sample_rate_hz"] != sample_rate_hz:
        return False
    if any(
        (
            observation["boot_id"],
            observation["session"],
            observation["generation"],
            observation["sample_rate_hz"],
            observation["epoch"],
        )
        != identity
        for observation in observations[1:]
    ):
        return False
    counters = [observation["counter"] for observation in observations]
    if any(right <= left for left, right in pairwise(counters)):
        return False
    inclusive_gaps = [
        anchors[index + 1]["receive_monotonic_ns"]
        - anchors[index]["send_monotonic_ns"]
        for index in range(len(anchors) - 1)
    ]
    maximum_samples = (
        sample_rate_hz * MAX_COUNTER_ANCHOR_GAP_NS // 1_000_000_000
    )
    return (
        all(0 <= gap <= MAX_COUNTER_ANCHOR_GAP_NS for gap in inclusive_gaps)
        and abs(counters[0] - first_valid_sample) <= maximum_samples
        and abs(counters[-1] - last_valid_sample) <= maximum_samples
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serial", required=True, help="exact hw_serial of the test radio"
    )
    parser.add_argument(
        "--uri", required=True, help="physical LAN URI, for example ip:192.168.1.18"
    )
    parser.add_argument(
        "--rate", type=int, required=True, choices=(*SUPPORTED_RATES, DUAL_RX_RATE_HZ)
    )
    parser.add_argument(
        "--rx-mask",
        type=int,
        choices=(1, 3),
        default=1,
        help="1 for single RX; 3 for shared-LO dual RX at 2.5 MS/s",
    )
    parser.add_argument("--duration-seconds", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new path; existing files are never replaced",
    )
    parser.add_argument(
        "--frequencies-hz", type=int, nargs="+", default=DEFAULT_FREQUENCIES_HZ
    )
    parser.add_argument("--dwell-ms", type=int, default=120)
    parser.add_argument("--energy-threshold-dbfs", type=float, default=-38.0)
    parser.add_argument("--manual-gain-db", type=float, default=40.0)
    parser.add_argument("--samples-per-block", type=int, default=1_000_000)
    return parser


def _validate(args: argparse.Namespace) -> None:
    if not args.serial.strip():
        raise ValueError("serial must be nonempty")
    if not args.uri.startswith("ip:") or not args.uri[3:]:
        raise ValueError("URI must be a physical LAN URI in ip:host form")
    _validate_rx_mode(args.rate, args.rx_mask)
    if not 1 <= args.duration_seconds <= 300:
        raise ValueError("duration must be in 1..300 seconds")
    if not 20 <= args.dwell_ms <= 240:
        raise ValueError("dwell must be in 20..240 ms")
    if not 1 <= len(args.frequencies_hz) <= 7 or len(set(args.frequencies_hz)) != len(
        args.frequencies_hz
    ):
        raise ValueError("frequencies must contain one to seven unique values")
    if any(frequency <= 0 for frequency in args.frequencies_hz):
        raise ValueError("frequencies must be positive")
    if args.samples_per_block <= 0 or args.samples_per_block % 2:
        raise ValueError("samples per block must be positive and even")
    if not 0 <= args.manual_gain_db <= 73:
        raise ValueError("manual gain must be in 0..73 dB")
    if args.output.expanduser().absolute().exists():
        raise FileExistsError(
            f"immutable evidence output already exists: {args.output}"
        )


def _validate_rx_mode(rate_hz: int, rx_mask: int) -> None:
    if rx_mask == 3 and rate_hz != DUAL_RX_RATE_HZ:
        raise ValueError("paired RX validation is supported only at 2.5 MS/s")
    if rx_mask == 1 and rate_hz == DUAL_RX_RATE_HZ:
        raise ValueError("2.5 MS/s capture requires the paired-RX mask")
    if rx_mask not in (1, 3) or rate_hz not in (*SUPPORTED_RATES, DUAL_RX_RATE_HZ):
        raise ValueError("unsupported rate/RX-mask pair")


def _preflight(serial: str, uri: str) -> dict[str, Any]:
    # Verify the release-local libiio receipt before importing pylibiio or
    # opening the device, so ambient host runtimes cannot silently be used.
    from pluto_plus.hardware.preflight import verify_metadata_runtime

    runtime = verify_metadata_runtime(expected_abi=3)
    import iio

    context = iio.Context(uri)
    attrs = dict(context.attrs)
    observed_serial = attrs.get("hw_serial")
    observed_firmware = attrs.get("fw_version")
    adaptive_scan = attrs.get("iio,adaptive-scan")
    identity = {
        "requested_serial": serial,
        "observed_serial": observed_serial,
        "uri": uri,
        "firmware_version": observed_firmware,
        "adaptive_scan_capability": adaptive_scan,
        "runtime": _json(runtime),
    }
    if observed_serial != serial:
        raise RuntimeError(
            f"radio serial mismatch: requested {serial!r}, observed {observed_serial!r}"
        )
    if observed_firmware != EXPECTED_FIRMWARE:
        raise RuntimeError(
            f"radio firmware mismatch: expected {EXPECTED_FIRMWARE!r}, observed {observed_firmware!r}"
        )
    if adaptive_scan != "1":
        raise RuntimeError("radio does not attest the adaptive-scan firmware interface")
    return identity


def run(args: argparse.Namespace) -> dict[str, Any]:
    _validate(args)
    result: dict[str, Any] = {
        "schema": "issue107-rx-validation-v1",
        "started_utc_ns": time.time_ns(),
        "requested": {
            "serial": args.serial,
            "uri": args.uri,
            "firmware": EXPECTED_FIRMWARE,
            "rate_hz": args.rate,
            "rx_mask": args.rx_mask,
            "rx_channels": [0, 1] if args.rx_mask == 3 else [0],
            "capture_mode": "dual-rx" if args.rx_mask == 3 else "single-rx",
            "duration_seconds": args.duration_seconds,
            "frequencies_hz": args.frequencies_hz,
            "dwell_ms": args.dwell_ms,
            "iq_payload_persisted": False,
            "rf_transmission": False,
        },
        "radio_identity": None,
        "visits": [],
        "counter_utc_evidence": None,
        "counter_sample_unit": "shared-complex-sample-time-index",
        "counter_timing": {},
        "campaign": None,
        "functional_pass": False,
        "counter_continuity_passed": False,
        "timing_query_pass": False,
        "timing_anchor_coverage_pass": False,
        "utc_accuracy_qualified": False,
        "errors": [],
    }

    radio_lock = None
    try:
        from pluto_plus.radio_lock import acquire_radio_lock

        # Hold the shared per-radio lease across identity attestation and the
        # whole lifecycle, so another local tool cannot swap the target state
        # between preflight and receiver preparation.
        radio_lock = acquire_radio_lock(args.serial)
        radio_lock.__enter__()
        identity = _preflight(args.serial, args.uri)
        result["radio_identity"] = identity
        from pluto_plus.adaptive_scan import ScanOutcome, VisitResult
        from pluto_plus.adaptive_scan_campaign import (
            build_adaptive_scan_setup,
            run_adaptive_scan_campaign,
        )
        from pluto_plus.adaptive_scan_detector import (
            Ci16EnergyDetector,
            Ci16EnergyDetectorConfig,
        )
        from pluto_plus.adaptive_scan_shadow import AdaptiveScanMode
        from pluto_plus.counter_utc import DEFAULT_TIMING_POLICY

        session = secrets.randbits(63) or 1
        generation = secrets.randbits(63) or 1
        detector = Ci16EnergyDetector(
            Ci16EnergyDetectorConfig(args.energy_threshold_dbfs)
        )
        setup = build_adaptive_scan_setup(
            session=session,
            generation=generation,
            seed=secrets.randbits(63),
            source_rate_hz=args.rate,
            analog_bandwidth_hz=min(args.rate, 50_000_000),
            duration_ms=args.duration_seconds * 1_000,
            dwell_ms=args.dwell_ms,
            frequencies_hz=tuple(args.frequencies_hz),
            baseline_weights=(1,) * len(args.frequencies_hz),
            transition_budget_ms=20,
            analysis_digest=detector.config.analysis_digest,
            rx_mask=args.rx_mask,
        )
        timing_documents: list[dict[str, Any]] = []

        def observe(visit: Any) -> None:
            record = visit.record
            item = {
                "visit": record.visit,
                "target": record.target,
                "result": _json(record.result),
                "first_sample": record.valid_start,
                "end_sample_exclusive": record.valid_end,
                "valid_sample_count": record.valid_end - record.valid_start,
                "sample_counter_channel_count": args.rx_mask.bit_count(),
                "missing_samples_before": record.missing_samples_before,
                "iq_bytes_received": record.iq_bytes,
                "iq_bytes_per_counter_sample": (
                    record.iq_bytes // (record.valid_end - record.valid_start)
                    if record.valid_end > record.valid_start
                    else None
                ),
                "iq_payload_retained": False,
            }
            if result["visits"]:
                previous = result["visits"][-1]
                item["sample_gap_from_previous"] = max(
                    0, record.valid_start - previous["end_sample_exclusive"]
                )
                item["sample_overlap_from_previous"] = max(
                    0, previous["end_sample_exclusive"] - record.valid_start
                )
            else:
                item["sample_gap_from_previous"] = None
                item["sample_overlap_from_previous"] = None
            result["visits"].append(item)

        def detect(visit: Any) -> Any:
            if visit.record.result is VisitResult.COMPLETE and visit.iq:
                outcome = detector(visit)
                observation = detector.observations[-1]
                if (
                    result["visits"]
                    and result["visits"][-1]["visit"] == observation.visit
                ):
                    result["visits"][-1]["energy_dbfs"] = (
                        observation.power_dbfs
                        if math.isfinite(observation.power_dbfs)
                        else None
                    )
                    result["visits"][-1]["zero_signal_power"] = math.isinf(
                        observation.power_dbfs
                    )
                    result["visits"][-1]["detector_outcome"] = observation.outcome.value
                return outcome
            if result["visits"]:
                result["visits"][-1]["detector_outcome"] = "unknown_incomplete_visit"
            return ScanOutcome.UNKNOWN

        try:
            receipt = run_adaptive_scan_campaign(
                args.uri,
                args.serial,
                setup,
                detect,
                mode=AdaptiveScanMode.ADAPTIVE,
                manual_gain_db=args.manual_gain_db,
                samples_per_block=args.samples_per_block,
                feedback_period_visits=8,
                visit_sink=observe,
                counter_clock_sink=lambda evidence: timing_documents.append(
                    evidence.model_dump(mode="json")
                ),
                timing_policy=DEFAULT_TIMING_POLICY,
            )
            result["campaign"] = _json(receipt)
        except BaseException as error:  # noqa: BLE001 - retain interrupted hardware attempts
            detail = f"{type(error).__name__}: {error}"
            notes = getattr(error, "__notes__", ())
            if notes:
                detail += " | " + " | ".join(notes)
            result["errors"].append(detail)

        if timing_documents:
            result["counter_utc_evidence"] = timing_documents[-1]
        elif not result["errors"]:
            result["errors"].append("timing collector produced no evidence")

        anchors = (result["counter_utc_evidence"] or {}).get("anchors", [])
        widths = [
            anchor["receive_monotonic_ns"] - anchor["send_monotonic_ns"]
            for anchor in anchors
        ]
        gaps = [
            anchors[i]["send_monotonic_ns"] - anchors[i - 1]["receive_monotonic_ns"]
            for i in range(1, len(anchors))
        ]
        inclusive_anchor_spans = [
            anchors[i + 1]["receive_monotonic_ns"] - anchors[i]["send_monotonic_ns"]
            for i in range(len(anchors) - 1)
        ]
        counters = [anchor["observation"]["counter"] for anchor in anchors]
        boot_ids = sorted({anchor["observation"]["boot_id"] for anchor in anchors})
        sessions = sorted({anchor["observation"]["session"] for anchor in anchors})
        generations = sorted(
            {anchor["observation"]["generation"] for anchor in anchors}
        )
        rates = sorted({anchor["observation"]["sample_rate_hz"] for anchor in anchors})
        epochs = sorted({anchor["observation"]["epoch"] for anchor in anchors})
        result["counter_timing"] = {
            "anchor_count": len(anchors),
            "query_width_min_ns": min(widths) if widths else None,
            "query_width_max_ns": max(widths) if widths else None,
            "query_width_over_50ms_count": sum(w > 50_000_000 for w in widths),
            "maximum_anchor_gap_ns": max(gaps) if gaps else None,
            "maximum_inclusive_anchor_span_ns": (
                max(inclusive_anchor_spans) if inclusive_anchor_spans else None
            ),
            "first_counter": counters[0] if counters else None,
            "last_counter": counters[-1] if counters else None,
            "low_word_wrap_count": (
                counters[-1] // (1 << 32) - counters[0] // (1 << 32)
                if counters
                else None
            ),
            "boot_ids": boot_ids,
            "sessions": sessions,
            "generations": generations,
            "sample_rates_hz": rates,
            "device_epochs": epochs,
            "collector_errors": (result["counter_utc_evidence"] or {}).get(
                "errors", []
            ),
            "policy_has_calibration": bool(
                (result["counter_utc_evidence"] or {})
                .get("policy", {})
                .get("calibration_reference")
            ),
        }

        terminal = (result.get("campaign") or {}).get("terminal")
        restoration = (result.get("campaign") or {}).get("restoration")
        visits = result["visits"]
        sample_gaps = [
            item["sample_gap_from_previous"]
            for item in visits
            if item["sample_gap_from_previous"] is not None
        ]
        result["counter_timing"]["missing_samples_reported_by_visits"] = sum(
            item["missing_samples_before"] for item in visits
        )
        result["counter_timing"]["inter_visit_sample_gap_total"] = sum(sample_gaps)
        result["counter_timing"]["maximum_inter_visit_sample_gap"] = max(
            sample_gaps, default=0
        )
        valid_visits = [item for item in visits if item["valid_sample_count"] > 0]
        first_valid_sample = valid_visits[0]["first_sample"] if valid_visits else None
        last_valid_sample = (
            valid_visits[-1]["end_sample_exclusive"] - 1 if valid_visits else None
        )
        result["counter_timing"]["first_valid_sample"] = first_valid_sample
        result["counter_timing"]["last_valid_sample"] = last_valid_sample
        continuity_passed = counter_continuity_passed(visits)
        result["counter_continuity_passed"] = continuity_passed
        terminal_iq_bytes = terminal["iq_bytes"] if terminal else None
        iq_geometry, sample_count_per_receiver, total_iq_bytes = iq_geometry_passed(
            visits, rx_mask=args.rx_mask, terminal_iq_bytes=terminal_iq_bytes
        )
        result["iq_geometry_passed"] = iq_geometry
        result["counter_timing"]["valid_sample_count_per_receiver"] = (
            sample_count_per_receiver
        )
        result["counter_timing"]["iq_bytes_received"] = total_iq_bytes
        anchor_coverage_passed = timing_anchor_coverage_passed(
            anchors,
            first_valid_sample=first_valid_sample,
            last_valid_sample=last_valid_sample,
            sample_rate_hz=args.rate,
        )
        result["timing_anchor_coverage_pass"] = anchor_coverage_passed
        anchors_consistent = (
            len(boot_ids)
            == len(sessions)
            == len(generations)
            == len(rates)
            == len(epochs)
            == 1
            and sessions == [session]
            and generations == [generation]
            and rates == [args.rate]
            and len(counters) >= 2
            and all(right > left for left, right in pairwise(counters))
            and not (result["counter_utc_evidence"] or {}).get("errors")
        )
        functional = bool(
            terminal
            and terminal["state"] == 1
            and terminal["session"] == session
            and terminal["generation"] == generation
            and terminal["planned"] == terminal["delivered"]
            and terminal["skipped"] == terminal["invalid"] == terminal["cancelled"] == 0
            and all(item["result"] == VisitResult.COMPLETE.value for item in visits)
            and restoration
            and restoration["observed"] == restoration["expected"]
            and restoration["observed_kernel_buffers"]
            == restoration["expected_kernel_buffers"]
            and restoration["fastlock_inactive"]
            and anchors_consistent
            and continuity_passed
            and iq_geometry
            and not result["errors"]
        )
        result["functional_pass"] = functional
        result["timing_query_pass"] = bool(widths) and max(widths) <= 50_000_000
        # This harness has no independent RF marker and no calibration policy.
        result["utc_accuracy_qualified"] = False
        result["finished_utc_ns"] = time.time_ns()
    except BaseException as error:  # noqa: BLE001 - persist diagnostics after cleanup
        detail = f"{type(error).__name__}: {error}"
        notes = getattr(error, "__notes__", ())
        if notes:
            detail += " | " + " | ".join(notes)
        result["errors"].append(detail)
        result["finished_utc_ns"] = time.time_ns()
    finally:
        if radio_lock is not None:
            radio_lock.__exit__(None, None, None)
    _write_new(args.output, result)
    return result


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run(args)
    except Exception as error:  # noqa: BLE001 - CLI boundary reports evidence-write failures
        print(
            json.dumps({"error": f"{type(error).__name__}: {error}"}), file=sys.stderr
        )
        return 4
    print(
        json.dumps(
            {
                "output": str(args.output.expanduser().absolute()),
                "functional_pass": result["functional_pass"],
                "iq_geometry_passed": result["iq_geometry_passed"],
                "counter_continuity_passed": result["counter_continuity_passed"],
                "timing_query_pass": result["timing_query_pass"],
                "timing_anchor_coverage_pass": result["timing_anchor_coverage_pass"],
                "utc_accuracy_qualified": result["utc_accuracy_qualified"],
                "error_count": len(result["errors"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if result["functional_pass"]
        and result["timing_query_pass"]
        and result["timing_anchor_coverage_pass"]
        else 5
    )


if __name__ == "__main__":
    raise SystemExit(main())
