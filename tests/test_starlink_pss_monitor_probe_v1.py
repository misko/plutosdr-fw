from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.starlink_pss_monitor_probe_v1 as monitor


def _plan() -> dict[str, object]:
    identity = {
        "path": "/tmp/input.json",
        "bytes": 1,
        "sha256": "1" * 64,
    }
    return {
        "schema": monitor.PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": "2" * 32,
        "created_at": "2026-09-06T00:00:00Z",
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": monitor.probe_v1.ALLOCATED_SERIAL,
        "rate_msps": 15,
        "runtime_target": monitor.probe_v8.RUNTIME_TARGET,
        "expected_firmware": monitor.EXPECTED_FIRMWARE,
        "duration_ms": 1_000,
        "controller_timeout_ms": 2_000,
        "ppu_repository": "/tmp/pluto-plus-utils",
        "ppu_source_commit": "3" * 40,
        "probe_plan": identity,
        "controller_binary": {
            "path": "/tmp/controller",
            "bytes": 2,
            "sha256": "4" * 64,
        },
        "receipt_path": "/tmp/receipt.json",
        "confirmation_phrase": (
            "MONITOR STARLINK PSS MAPS "
            f"{monitor.probe_v1.ALLOCATED_SERIAL} 15 MSPS 1000 MS"
        ),
    }


def _records() -> list[dict[str, object]]:
    maps: list[dict[str, object]] = []
    for sequence in range(1, 13):
        record: dict[str, object] = {
            "schema": monitor.MAP_SCHEMA,
            "claim_scope": monitor.CLAIM_SCOPE,
            "serial": monitor.probe_v1.ALLOCATED_SERIAL,
            "sequence": sequence,
            "bank": sequence & 1,
            "generation": 100 + sequence,
            "start_index_canonical": 5_000 + (sequence - 1) * monitor.TILE_SAMPLES,
            "accepted_scores": sequence * monitor.TILE_SAMPLES,
            "published_maps": 20 + sequence,
            "health_flags": "0x00000000",
            "fault_free_epoch": True,
            "candidate_available": sequence >= 3,
            "threshold_decision": None,
            "pss_detected": False,
            "frame_lock_claim": False,
        }
        if sequence >= 3:
            record.update(
                {
                    "phase_bin": 123,
                    "drift_bins_per_64_frames": 0,
                    "combined_score": 456,
                    "combined_median": 12.5,
                    "peak_to_median": 36.48,
                    "robust_z": None,
                    "estimated_frame_period_canonical_samples": 20_000.0,
                }
            )
        maps.append(record)
    last = maps[-1]
    summary: dict[str, object] = {
        "schema": monitor.SUMMARY_SCHEMA,
        "claim_scope": monitor.CLAIM_SCOPE,
        "serial": monitor.probe_v1.ALLOCATED_SERIAL,
        "input_rate_msps": 15,
        "canonical_rate_msps": 15,
        "duration_requested_ms": 1_000,
        "duration_observed_ms": 1_024,
        "maps_copied": len(maps),
        "candidate_windows": len(maps) - 2,
        "first_generation": maps[0]["generation"],
        "last_generation": last["generation"],
        "first_start_index_canonical": maps[0]["start_index_canonical"],
        "last_start_index_canonical": last["start_index_canonical"],
        "accepted_scores_before": 0,
        "accepted_scores_at_cutoff": last["accepted_scores"],
        "accepted_scores_delta": last["accepted_scores"],
        "published_maps_before": 20,
        "published_maps_at_cutoff": last["published_maps"],
        "published_maps_delta": len(maps),
        "post_loop_published_maps": last["published_maps"],
        "post_loop_ready_mask": 0,
        "ingress_fifo_level_at_cutoff": 0,
        "ingress_fifo_maximum_at_cutoff": 2,
        "candidate_fifo_level_at_cutoff": 0,
        "candidate_fifo_maximum_at_cutoff": 300,
        "health_flags_at_cutoff": "0x00000000",
        "continuity_ok": True,
        "fault_free_epoch": True,
        "post_loop_fault_free": True,
        "threshold_decision": None,
        "pss_detected": False,
        "frame_lock_claim": False,
    }
    summary.update({field: 0 for field in monitor.ZERO_SUMMARY_FIELDS})
    return [*maps, summary]


def test_plan_contract_is_explicitly_ad9361_v6_and_bounded() -> None:
    plan = _plan()
    monitor._validate_plan(plan)

    invalid = dict(plan)
    invalid["duration_ms"] = 120_001
    invalid["confirmation_phrase"] = (
        "MONITOR STARLINK PSS MAPS "
        f"{monitor.probe_v1.ALLOCATED_SERIAL} 15 MSPS 120001 MS"
    )
    with pytest.raises(monitor.ProbeError, match="violate"):
        monitor._validate_plan(invalid)


def test_ad9361_v6_contract_is_scoped_and_restored() -> None:
    original_identity = (
        monitor.probe_v1.RUNTIME_TARGET,
        monitor.probe_v1.EXPECTED_MODEL,
    )
    original_revisions = monitor.probe_v2.SUPPORTED_SOURCE_REVISIONS

    with monitor._ad9361_v6_contract():
        assert monitor.probe_v1.RUNTIME_TARGET == "ad9361-1r1t"
        assert monitor.probe_v1.EXPECTED_MODEL == (
            "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
        )
        assert "v6" in monitor.probe_v2.SUPPORTED_SOURCE_REVISIONS

    assert (
        monitor.probe_v1.RUNTIME_TARGET,
        monitor.probe_v1.EXPECTED_MODEL,
    ) == original_identity
    assert monitor.probe_v2.SUPPORTED_SOURCE_REVISIONS == original_revisions


def test_monitor_records_prove_contiguous_zero_loss_transport() -> None:
    result = monitor._validate_monitor_records(_records(), _plan())

    assert len(result["maps"]) == 12
    assert result["summary"]["candidate_windows"] == 10
    assert result["expected_maps"] == 11


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("generation-gap", "contiguous"),
        ("map-overrun", "zero-loss"),
        ("false-detection", "transport-only"),
        ("missing-candidate", "fields"),
    ],
)
def test_monitor_records_reject_gaps_faults_and_claims(
    mutation: str, message: str
) -> None:
    records = deepcopy(_records())
    if mutation == "generation-gap":
        records[5]["generation"] = int(records[5]["generation"]) + 1
    elif mutation == "map-overrun":
        records[-1]["map_overruns_at_cutoff"] = 1
    elif mutation == "false-detection":
        records[4]["pss_detected"] = True
    else:
        del records[4]["phase_bin"]

    with pytest.raises(monitor.ProbeError, match=message):
        monitor._validate_monitor_records(records, _plan())


def test_monitor_script_is_executable() -> None:
    path = Path(monitor.__file__)
    assert path.stat().st_mode & 0o111


def test_monitor_source_manifest_is_offline_dnm_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-monitor-probe-dnm-v1-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-monitor-probe-source"
    assert values["schema_version"] == "1"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["supported_sample_rate_msps"] == "15"
    assert values["maximum_observation_ms"] == "120000"
    for prefix in (
        "host_probe",
        "host_test",
        "controller",
        "controller_test",
        "acquisition_library",
        "acquisition_header",
        "acquisition_native_test",
        "inherited_binary_helper",
        "inherited_ad9361_probe_manifest",
        "candidate_source_manifest",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
