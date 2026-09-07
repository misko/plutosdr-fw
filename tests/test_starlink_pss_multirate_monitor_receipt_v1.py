from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import starlink_pss_multirate_monitor_receipt_v1 as receipt_v1


SERIAL = "104000bac4950008230026001b440a003a"


def _records(rate: int = 30, maps: int = 5) -> list[dict[str, object]]:
    factor = rate // 15
    first_index = 123_456
    result: list[dict[str, object]] = []
    for offset in range(maps):
        canonical = first_index + offset * receipt_v1.TILE_SAMPLES
        record: dict[str, object] = {
            "schema": receipt_v1.MAP_SCHEMA,
            "claim_scope": receipt_v1.CLAIM_SCOPE,
            "serial": SERIAL,
            "sequence": offset + 1,
            "input_rate_msps": rate,
            "canonical_rate_msps": 15,
            "decimation_factor": factor,
            "bank": offset & 1,
            "generation": 17 + offset,
            "start_index_canonical": canonical,
            "start_index_source_center": canonical * factor,
            "health_flags": "0x00000000",
            "fault_free_epoch": True,
            "candidate_available": offset >= 2,
            "threshold_decision": None,
            "pss_detected": False,
            "frame_lock_claim": False,
        }
        if offset >= 2:
            candidate = canonical - 500
            record.update(
                estimated_frame_period_canonical_samples=20_000,
                estimated_frame_period_source_samples=20_000 * factor,
                candidate_start_index_canonical=candidate,
                candidate_start_index_source_center=candidate * factor,
            )
        result.append(record)
    expected_samples = 120_000 * rate * 1_000
    summary: dict[str, object] = {
        "schema": receipt_v1.SUMMARY_SCHEMA,
        "claim_scope": receipt_v1.CLAIM_SCOPE,
        "serial": SERIAL,
        "input_rate_msps": rate,
        "canonical_rate_msps": 15,
        "decimation_factor": factor,
        "duration_requested_ms": 120_000,
        "duration_observed_ms": 120_041,
        "maps_copied": maps,
        "candidate_windows": maps - 2,
        "first_generation": 17,
        "last_generation": 16 + maps,
        "first_start_index_canonical": first_index,
        "last_start_index_canonical": first_index + (maps - 1) * receipt_v1.TILE_SAMPLES,
        "first_start_index_source_center": first_index * factor,
        "last_start_index_source_center": (first_index + (maps - 1) * receipt_v1.TILE_SAMPLES) * factor,
        "published_maps_delta": maps,
        "post_loop_ready_mask": 0,
        "health_flags_at_cutoff": "0x00000000",
        "continuity_ok": True,
        "fault_free_epoch": True,
        "post_loop_fault_free": True,
        "threshold_decision": None,
        "pss_detected": False,
        "frame_lock_claim": False,
        "accepted_scores_delta": expected_samples // factor - 1_000,
        "ddc_accepted_before": 0,
        "ddc_accepted_after": 0 if rate == 15 else expected_samples,
        "ddc_emitted_before": 0,
        "ddc_emitted_after": 0 if rate == 15 else expected_samples // factor,
    }
    summary.update({field: 0 for field in receipt_v1.ZERO_SUMMARY_FIELDS})
    result.append(summary)
    return result


def _write(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


@pytest.mark.parametrize("rate", [15, 30, 60])
def test_valid_multirate_stream(tmp_path: Path, rate: int) -> None:
    path = tmp_path / "monitor.ndjson"
    _write(path, _records(rate))
    receipt = receipt_v1.validate_stream(
        path,
        serial=SERIAL,
        rate_msps=rate,
        requested_duration_ms=120_000,
        minimum_maps=5,
    )
    assert receipt["outcome"] == "pass"
    assert receipt["maps_copied"] == 5
    assert receipt["ddc_accepted_delta"] == (0 if rate == 15 else 120_000 * rate * 1_000)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda records: records[2].update(sequence=99), "identity or continuity"),
        (lambda records: records[3].update(start_index_source_center=1), "identity or continuity"),
        (lambda records: records[-1].update(scheduler_gaps_at_cutoff=1), "fault field"),
        (lambda records: records[-1].update(ddc_accepted_after=123), "sustained full-rate"),
    ],
)
def test_rejects_broken_evidence(tmp_path: Path, mutation, message: str) -> None:
    records = copy.deepcopy(_records(30))
    mutation(records)
    path = tmp_path / "monitor.ndjson"
    _write(path, records)
    with pytest.raises(receipt_v1.ReceiptError, match=message):
        receipt_v1.validate_stream(
            path,
            serial=SERIAL,
            rate_msps=30,
            requested_duration_ms=120_000,
            minimum_maps=5,
        )
