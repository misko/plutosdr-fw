#!/usr/bin/env python3
"""Validate one monitor-v3 NDJSON stream and seal a compact evidence receipt.

This is an offline validator: it never opens a radio, network interface, or
firmware image.  The input stream is evidence captured by the separately
bounded hardware operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAP_SCHEMA = "starlink-pss-acqctl.monitor-map.v2"
SUMMARY_SCHEMA = "starlink-pss-acqctl.monitor-summary.v2"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-multirate-monitor-receipt.v1"
CLAIM_SCOPE = "continuous_multirate_map_transport_only"
TILE_SAMPLES = 20_000 * 64
UINT32_MAX = (1 << 32) - 1

ZERO_SUMMARY_FIELDS = {
    "discarded_scores_at_cutoff",
    "discontinuity_aborts_at_cutoff",
    "map_overruns_at_cutoff",
    "score_protocol_errors_at_cutoff",
    "arithmetic_overflows_at_cutoff",
    "map_read_errors_at_cutoff",
    "map_release_errors_at_cutoff",
    "ingress_dropped_at_cutoff",
    "scheduler_gaps_at_cutoff",
    "scheduler_index_errors_at_cutoff",
    "scheduler_overflows_at_cutoff",
    "detector_faults_at_cutoff",
    "phase_discontinuities_at_cutoff",
    "denominator_zero_at_cutoff",
    "ddc_discontinuity_after",
    "ddc_saturation_after",
}


class ReceiptError(RuntimeError):
    """The monitor stream does not satisfy the sealed evidence contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(record: dict[str, Any], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReceiptError(f"{field} is not an unsigned integer")
    return value


def _false_claims(record: dict[str, Any]) -> bool:
    return (
        record.get("threshold_decision") is None
        and record.get("pss_detected") is False
        and record.get("frame_lock_claim") is False
    )


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ReceiptError(f"line {line_number} is not JSON: {error}") from error
            if not isinstance(record, dict):
                raise ReceiptError(f"line {line_number} is not a JSON object")
            records.append(record)
    if not records:
        raise ReceiptError("monitor stream is empty")
    return records


def validate_stream(
    path: Path,
    *,
    serial: str,
    rate_msps: int,
    requested_duration_ms: int,
    minimum_maps: int,
) -> dict[str, Any]:
    if rate_msps not in (15, 30, 60):
        raise ReceiptError("rate must be exactly 15, 30, or 60 MS/s")
    if requested_duration_ms < 1_000 or requested_duration_ms > 120_000:
        raise ReceiptError("requested duration must lie in [1000, 120000] ms")
    if minimum_maps < 3:
        raise ReceiptError("minimum map count must be at least three")

    records = _load_records(path)
    maps = records[:-1]
    summary = records[-1]
    factor = rate_msps // 15
    if any(record.get("schema") != MAP_SCHEMA for record in maps):
        raise ReceiptError("all records before the summary must be monitor-map.v2")
    if summary.get("schema") != SUMMARY_SCHEMA:
        raise ReceiptError("the final record must be monitor-summary.v2")
    if len(maps) < minimum_maps:
        raise ReceiptError(f"only {len(maps)} maps; expected at least {minimum_maps}")

    first_generation = _integer(maps[0], "generation")
    first_canonical = _integer(maps[0], "start_index_canonical")
    first_bank = _integer(maps[0], "bank")
    if first_bank not in (0, 1):
        raise ReceiptError("first map bank is not zero or one")
    for offset, record in enumerate(maps):
        expected_sequence = offset + 1
        expected_generation = first_generation + offset
        expected_canonical = first_canonical + offset * TILE_SAMPLES
        expected_source = expected_canonical * factor
        if (
            record.get("claim_scope") != CLAIM_SCOPE
            or record.get("serial") != serial
            or record.get("input_rate_msps") != rate_msps
            or record.get("canonical_rate_msps") != 15
            or record.get("decimation_factor") != factor
            or _integer(record, "sequence") != expected_sequence
            or _integer(record, "generation") != expected_generation
            or _integer(record, "start_index_canonical") != expected_canonical
            or _integer(record, "start_index_source_center") != expected_source
            or record.get("bank") != ((first_bank + offset) & 1)
            or record.get("health_flags") != "0x00000000"
            or record.get("fault_free_epoch") is not True
            or not _false_claims(record)
        ):
            raise ReceiptError(f"map sequence {expected_sequence} violates identity or continuity")
        candidate_expected = offset >= 2
        if record.get("candidate_available") is not candidate_expected:
            raise ReceiptError(f"map sequence {expected_sequence} has wrong candidate availability")
        if candidate_expected:
            candidate_canonical = _integer(record, "candidate_start_index_canonical")
            canonical_period = record.get("estimated_frame_period_canonical_samples")
            source_period = record.get("estimated_frame_period_source_samples")
            if (
                not isinstance(canonical_period, (int, float))
                or isinstance(canonical_period, bool)
                or not math.isfinite(canonical_period)
                or canonical_period <= 0
                or not isinstance(source_period, (int, float))
                or isinstance(source_period, bool)
                or not math.isfinite(source_period)
                or source_period != canonical_period * factor
                or _integer(record, "candidate_start_index_source_center")
                != candidate_canonical * factor
            ):
                raise ReceiptError(f"map sequence {expected_sequence} has wrong source projection")

    if (
        summary.get("claim_scope") != CLAIM_SCOPE
        or summary.get("serial") != serial
        or summary.get("input_rate_msps") != rate_msps
        or summary.get("canonical_rate_msps") != 15
        or summary.get("decimation_factor") != factor
        or summary.get("duration_requested_ms") != requested_duration_ms
        or _integer(summary, "duration_observed_ms") < requested_duration_ms
        or _integer(summary, "duration_observed_ms") > requested_duration_ms + 5_000
        or _integer(summary, "maps_copied") != len(maps)
        or _integer(summary, "candidate_windows") != len(maps) - 2
        or _integer(summary, "first_generation") != first_generation
        or _integer(summary, "last_generation") != first_generation + len(maps) - 1
        or _integer(summary, "first_start_index_canonical") != first_canonical
        or _integer(summary, "last_start_index_canonical")
        != first_canonical + (len(maps) - 1) * TILE_SAMPLES
        or _integer(summary, "first_start_index_source_center") != first_canonical * factor
        or _integer(summary, "last_start_index_source_center")
        != (first_canonical + (len(maps) - 1) * TILE_SAMPLES) * factor
        or _integer(summary, "published_maps_delta") != len(maps)
        or _integer(summary, "post_loop_ready_mask") != 0
        or summary.get("health_flags_at_cutoff") != "0x00000000"
        or summary.get("continuity_ok") is not True
        or summary.get("fault_free_epoch") is not True
        or summary.get("post_loop_fault_free") is not True
        or not _false_claims(summary)
    ):
        raise ReceiptError("monitor summary violates the duration, identity, or continuity contract")
    for field in ZERO_SUMMARY_FIELDS:
        if _integer(summary, field) != 0:
            raise ReceiptError(f"summary fault field {field} is nonzero")

    accepted_before = _integer(summary, "ddc_accepted_before")
    accepted_after = _integer(summary, "ddc_accepted_after")
    emitted_before = _integer(summary, "ddc_emitted_before")
    emitted_after = _integer(summary, "ddc_emitted_after")
    if rate_msps == 15:
        if any((accepted_before, accepted_after, emitted_before, emitted_after)):
            raise ReceiptError("15 MS/s must expose zero DDC counters")
    else:
        accepted_delta = accepted_after - accepted_before
        emitted_delta = emitted_after - emitted_before
        expected_source_samples = requested_duration_ms * rate_msps * 1_000
        if (
            accepted_delta <= 0
            or emitted_delta <= 0
            or accepted_delta < math.floor(expected_source_samples * 0.99)
            or accepted_delta > math.ceil(expected_source_samples * 1.02)
            or abs(accepted_delta - factor * emitted_delta) > 256
        ):
            raise ReceiptError("DDC counters do not prove sustained full-rate processing")
        if rate_msps == 30 and (accepted_after >= UINT32_MAX or emitted_after >= UINT32_MAX):
            raise ReceiptError("30 MS/s legacy counters reached their saturation boundary")
        if rate_msps == 60 and accepted_delta <= UINT32_MAX:
            raise ReceiptError("120-second 60 MS/s evidence did not cross the 32-bit boundary")

    return {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "validated_at": datetime.now(UTC).isoformat(),
        "validator_hardware_accessed": False,
        "evidence_hardware_accessed": True,
        "persistent_write": False,
        "outcome": "pass",
        "claim_scope": CLAIM_SCOPE,
        "serial": serial,
        "input_rate_msps": rate_msps,
        "canonical_rate_msps": 15,
        "decimation_factor": factor,
        "monitor_path": str(path.resolve()),
        "monitor_bytes": path.stat().st_size,
        "monitor_sha256": _sha256(path),
        "duration_requested_ms": requested_duration_ms,
        "duration_observed_ms": summary["duration_observed_ms"],
        "maps_copied": len(maps),
        "candidate_windows": len(maps) - 2,
        "first_generation": first_generation,
        "last_generation": maps[-1]["generation"],
        "first_start_index_canonical": first_canonical,
        "last_start_index_canonical": maps[-1]["start_index_canonical"],
        "first_start_index_source_center": maps[0]["start_index_source_center"],
        "last_start_index_source_center": maps[-1]["start_index_source_center"],
        "accepted_scores_delta": summary["accepted_scores_delta"],
        "ddc_accepted_delta": accepted_after - accepted_before,
        "ddc_emitted_delta": emitted_after - emitted_before,
        "all_fault_counters_zero": True,
        "continuity_ok": True,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("monitor", type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--rate-msps", required=True, type=int)
    parser.add_argument("--duration-ms", required=True, type=int)
    parser.add_argument("--minimum-maps", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        receipt = validate_stream(
            arguments.monitor,
            serial=arguments.serial,
            rate_msps=arguments.rate_msps,
            requested_duration_ms=arguments.duration_ms,
            minimum_maps=arguments.minimum_maps,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ReceiptError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
