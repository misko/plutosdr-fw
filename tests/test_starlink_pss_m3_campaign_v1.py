from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_m3_campaign_v1 as campaign
import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
from tests.test_starlink_pss_monitor_probe_v1 import _plan as monitor_plan_v1
from tools.generate_starlink_pss15_cabled_waveform import generate


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _fixture(transmitter_serial: str = "test-transmitter-0001") -> dict[str, object]:
    return {
        "schema": campaign.FIXTURE_SCHEMA,
        "schema_version": 1,
        "created_at": "2026-09-07T00:00:00Z",
        "receiver_serial": campaign.RECEIVER_SERIAL,
        "transmitter_serial": transmitter_serial,
        "direct_coaxial_path_verified": True,
        "antenna_connected": False,
        "over_the_air_authorized": False,
        "tx_port": "TX1",
        "rx_port": "RX1",
        "attenuation_components": ["30 dB fixed pad", "10 dB fixed pad"],
        "effective_attenuation_db": 40.0,
        "cable_path_description": "TX1 -> 30 dB -> 10 dB -> RX1",
        "operator_attestation": campaign.FIXTURE_ATTESTATION,
    }


def _monitor_plan(path: Path, receipt: Path, plan_id: str) -> dict[str, object]:
    plan = monitor_plan_v1()
    plan["schema"] = monitor_v2.PLAN_SCHEMA
    plan["expected_firmware"] = monitor_v2.EXPECTED_FIRMWARE
    plan["plan_id"] = plan_id
    plan["duration_ms"] = 5_000
    plan["controller_timeout_ms"] = 5_000
    plan["receipt_path"] = str(receipt)
    plan["confirmation_phrase"] = (
        "MONITOR STARLINK PSS MAPS "
        f"{campaign.RECEIVER_SERIAL} 15 MSPS 5000 MS"
    )
    _write_json(path, plan)
    return plan


def _records(*, positive: bool) -> list[dict[str, object]]:
    maps: list[dict[str, object]] = []
    map_count = 58
    for sequence in range(1, map_count + 1):
        record: dict[str, object] = {
            "schema": monitor_v1.MAP_SCHEMA,
            "claim_scope": monitor_v1.CLAIM_SCOPE,
            "serial": campaign.RECEIVER_SERIAL,
            "sequence": sequence,
            "bank": sequence & 1,
            "generation": 100 + sequence,
            "start_index_canonical": 5_000
            + (sequence - 1) * monitor_v1.TILE_SAMPLES,
            "accepted_scores": sequence * monitor_v1.TILE_SAMPLES,
            "published_maps": 20 + sequence,
            "health_flags": "0x00000000",
            "fault_free_epoch": True,
            "candidate_available": sequence >= 3,
            "threshold_decision": None,
            "pss_detected": False,
            "frame_lock_claim": False,
        }
        if sequence >= 3:
            candidate_index = sequence - 3
            record.update(
                {
                    "phase_bin": (
                        (4_000 + candidate_index * 8) % 20_000
                        if positive
                        else (sequence * 1_237) % 20_000
                    ),
                    "drift_bins_per_64_frames": 8 if positive else 0,
                    "combined_score": 4_000 if positive else 125,
                    "combined_median": 1_000.0 if positive else 115.0,
                    "peak_to_median": 4.0 if positive else 1.0869565217,
                    "robust_z": 20.0 if positive else 4.0,
                    "estimated_frame_period_canonical_samples": (
                        20_000.125 if positive else 20_000.0
                    ),
                }
            )
        maps.append(record)
    last = maps[-1]
    summary: dict[str, object] = {
        "schema": monitor_v1.SUMMARY_SCHEMA,
        "claim_scope": monitor_v1.CLAIM_SCOPE,
        "serial": campaign.RECEIVER_SERIAL,
        "input_rate_msps": 15,
        "canonical_rate_msps": 15,
        "duration_requested_ms": 5_000,
        "duration_observed_ms": 5_020,
        "maps_copied": map_count,
        "candidate_windows": map_count - 2,
        "first_generation": maps[0]["generation"],
        "last_generation": last["generation"],
        "first_start_index_canonical": maps[0]["start_index_canonical"],
        "last_start_index_canonical": last["start_index_canonical"],
        "accepted_scores_before": 0,
        "accepted_scores_at_cutoff": last["accepted_scores"],
        "accepted_scores_delta": last["accepted_scores"],
        "published_maps_before": 20,
        "published_maps_at_cutoff": last["published_maps"],
        "published_maps_delta": map_count,
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
    summary.update({field: 0 for field in monitor_v1.ZERO_SUMMARY_FIELDS})
    return [*maps, summary]


def _monitor_receipt(
    *,
    plan_path: Path,
    receipt_path: Path,
    records: list[dict[str, object]],
    started_at: str,
    completed_at: str,
) -> None:
    receipt = {
        "schema": monitor_v2.RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": "a" * 32,
        "outcome": "pass",
        "started_at": started_at,
        "completed_at": completed_at,
        "plan": campaign._identity(plan_path, label="test monitor plan"),
        "serial": campaign.RECEIVER_SERIAL,
        "rate_msps": 15,
        "runtime_target": campaign.RUNTIME_TARGET,
        "expected_firmware": campaign.EXPECTED_FIRMWARE,
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": monitor_v1.CLAIM_SCOPE,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "runtime": {
            "serial": campaign.RECEIVER_SERIAL,
            "firmware_version": campaign.EXPECTED_FIRMWARE,
            "hardware_model": monitor_v1.probe_v8.EXPECTED_MODEL,
            "single_rx_setup": {"runtime_target": campaign.RUNTIME_TARGET},
        },
        "measurement": {
            "controller_binary_upload_verified": True,
            "controller_binary_removed": True,
            "iio_restore_verified": True,
            "engine_disable_verified": True,
            "monitor_records": records,
        },
        "route_release_verified": True,
        "recovery_required": True,
        "error": None,
    }
    _write_json(receipt_path, receipt)


def _stimulus(
    *,
    plan: dict[str, object],
    state: str,
    started_at: str,
    completed_at: str,
) -> dict[str, object]:
    active = state == "active"
    return {
        "schema": campaign.STIMULUS_SCHEMA,
        "schema_version": 1,
        "receipt_id": "b" * 32,
        "started_at": started_at,
        "completed_at": completed_at,
        "outcome": "pass",
        "fixture_declaration": plan["fixture_declaration"],
        "transmitter_serial": plan["transmitter_serial"],
        "state": state,
        "hardware_accessed": True,
        "persistent_write": False,
        "cabled_only": True,
        "over_the_air_transmission": False,
        "waveform_evidence": plan["waveform_evidence"] if active else None,
        "waveform_binary": plan["waveform_binary"] if active else None,
        "requested_sample_rate_hz": (
            plan["transmitter_sample_rate_hz"] if active else None
        ),
        "readback_sample_rate_hz": (
            plan["transmitter_sample_rate_hz"] if active else None
        ),
        "cyclic_buffer_active": active,
        "tx_lo_hz": plan["transmitter_lo_hz"] if active else None,
        "tx_hardwaregain_db": (
            plan["transmitter_hardwaregain_db"] if active else -89.75
        ),
        "tx_buffer_disabled": not active,
        "tx_lo_powerdown": not active,
        "cleanup_verified": not active,
        "error": None,
    }


def test_dwell_policy_accepts_a_track_and_rejects_muted_background() -> None:
    positive = campaign.analyze_dwell(_records(positive=True), campaign.POLICY)
    negative = campaign.analyze_dwell(_records(positive=False), campaign.POLICY)

    assert positive["passing_windows"] == 56
    assert positive["longest_consecutive_track_windows"] == 56
    assert positive["maximum_absolute_phase_residual_samples"] == 0
    assert campaign._positive_passes(positive, campaign.POLICY)
    assert negative["passing_windows"] == 0
    assert negative["longest_consecutive_track_windows"] == 0
    assert campaign._negative_passes(negative, campaign.POLICY)


def test_fixture_contract_rejects_an_antenna_or_insufficient_attenuation() -> None:
    campaign._validate_fixture(_fixture())
    for field, value in (
        ("antenna_connected", True),
        ("effective_attenuation_db", 29.9),
        ("over_the_air_authorized", True),
    ):
        invalid = deepcopy(_fixture())
        invalid[field] = value
        with pytest.raises(campaign.ProbeError, match="cabled-only"):
            campaign._validate_fixture(invalid)


def test_fixture_builder_requires_explicit_attestation(tmp_path: Path) -> None:
    output = tmp_path / "fixture.json"
    arguments = SimpleNamespace(
        transmitter_serial="test-transmitter-0001",
        tx_port="TX1",
        rx_port="RX1",
        attenuation_component=["30 dB fixed pad", "10 dB fixed pad"],
        effective_attenuation_db=40.0,
        cable_path_description="TX1 -> 30 dB -> 10 dB -> RX1",
        attest=campaign.FIXTURE_ATTESTATION,
        output=output,
    )
    result = campaign.build_fixture(arguments)
    assert result["verdict"] == "PASS_OFFLINE_M3_FIXTURE_DECLARATION_ONLY"
    assert output.stat().st_mode & 0o777 == 0o600
    campaign._validate_fixture(campaign._load(output, label="test fixture"))

    invalid = deepcopy(arguments)
    invalid.attest = "I think it is connected"
    invalid.output = tmp_path / "invalid.json"
    with pytest.raises(campaign.ProbeError, match="must be exactly"):
        campaign.build_fixture(invalid)


def test_full_offline_campaign_plan_qualify_and_verify(tmp_path: Path) -> None:
    waveform_directory = tmp_path / "waveform"
    generate(waveform_directory)
    fixture_path = tmp_path / "fixture.json"
    _write_json(fixture_path, _fixture())

    roles = ("positive-a", "negative", "positive-b")
    monitor_paths = {role: tmp_path / f"{role}-monitor-plan.json" for role in roles}
    monitor_receipt_paths = {
        role: tmp_path / f"{role}-monitor-receipt.json" for role in roles
    }
    stimulus_paths = {role: tmp_path / f"{role}-stimulus.json" for role in roles}
    for index, role in enumerate(roles, 1):
        _monitor_plan(
            monitor_paths[role], monitor_receipt_paths[role], f"{index}" * 32
        )

    campaign_plan_path = tmp_path / "campaign-plan.json"
    campaign_receipt_path = tmp_path / "campaign-receipt.json"
    final_mute_path = tmp_path / "final-mute.json"
    result = campaign.build_plan(
        SimpleNamespace(
            waveform_evidence=waveform_directory
            / "starlink_pss15_upper_cabled_waveform.json",
            fixture_declaration=fixture_path,
            transmitter_sample_rate_hz=campaign.SAMPLE_RATE_HZ,
            transmitter_lo_hz=1_000_000_000,
            transmitter_hardwaregain_db=-30.0,
            positive_a_monitor_plan=monitor_paths["positive-a"],
            negative_monitor_plan=monitor_paths["negative"],
            positive_b_monitor_plan=monitor_paths["positive-b"],
            positive_a_stimulus_receipt=stimulus_paths["positive-a"],
            negative_stimulus_receipt=stimulus_paths["negative"],
            positive_b_stimulus_receipt=stimulus_paths["positive-b"],
            final_mute_stimulus_receipt=final_mute_path,
            receipt=campaign_receipt_path,
            output=campaign_plan_path,
        )
    )
    assert result["verdict"] == "PASS_OFFLINE_M3_CAMPAIGN_PLAN_ONLY"
    plan = campaign._load(campaign_plan_path, label="test campaign plan")
    campaign._validate_plan(plan)

    times = (
        ("2026-09-07T00:00:00Z", "2026-09-07T00:00:01Z"),
        ("2026-09-07T00:00:07Z", "2026-09-07T00:00:08Z"),
        ("2026-09-07T00:00:14Z", "2026-09-07T00:00:15Z"),
    )
    for role, state, (stimulus_start, stimulus_complete) in zip(
        roles, ("active", "muted", "active"), times, strict=True
    ):
        _write_json(
            stimulus_paths[role],
            _stimulus(
                plan=plan,
                state=state,
                started_at=stimulus_start,
                completed_at=stimulus_complete,
            ),
        )
    _monitor_receipt(
        plan_path=monitor_paths["positive-a"],
        receipt_path=monitor_receipt_paths["positive-a"],
        records=_records(positive=True),
        started_at="2026-09-07T00:00:02Z",
        completed_at="2026-09-07T00:00:07Z",
    )
    _monitor_receipt(
        plan_path=monitor_paths["negative"],
        receipt_path=monitor_receipt_paths["negative"],
        records=_records(positive=False),
        started_at="2026-09-07T00:00:09Z",
        completed_at="2026-09-07T00:00:14Z",
    )
    _monitor_receipt(
        plan_path=monitor_paths["positive-b"],
        receipt_path=monitor_receipt_paths["positive-b"],
        records=_records(positive=True),
        started_at="2026-09-07T00:00:16Z",
        completed_at="2026-09-07T00:00:21Z",
    )
    _write_json(
        final_mute_path,
        _stimulus(
            plan=plan,
            state="muted",
            started_at="2026-09-07T00:00:21Z",
            completed_at="2026-09-07T00:00:22Z",
        ),
    )

    qualified = campaign.qualify(
        SimpleNamespace(plan=campaign_plan_path, output=campaign_receipt_path)
    )
    assert qualified["verdict"] == "PASS_M3_CABLED_PSS_ACQUISITION_ONLY"
    assert qualified["pss_detected"] is True
    assert qualified["sss_detected"] is False
    assert qualified["frame_lock_claim"] is False
    verified = campaign.verify_receipt(
        SimpleNamespace(plan=campaign_plan_path, receipt=campaign_receipt_path)
    )
    assert verified["verdict"] == "PASS_M3_RECEIPT_STRUCTURE"

    tampered = campaign._load(campaign_receipt_path, label="test campaign receipt")
    tampered["metrics"]["positive_a"]["passing_windows"] -= 1
    _write_json(campaign_receipt_path, tampered)
    with pytest.raises(campaign.ProbeError, match="recomputed evidence"):
        campaign.verify_receipt(
            SimpleNamespace(plan=campaign_plan_path, receipt=campaign_receipt_path)
        )


def test_campaign_script_is_executable() -> None:
    assert Path(campaign.__file__).stat().st_mode & 0o111
