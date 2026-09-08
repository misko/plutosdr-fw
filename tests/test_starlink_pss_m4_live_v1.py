from __future__ import annotations

import hashlib
import json
import math
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_m4_live_v1 as live
import scripts.starlink_pss_monitor_probe_v1 as monitor


def _identity(path: str = "/tmp/m4-input") -> dict[str, object]:
    return {"path": path, "bytes": 123, "sha256": "a" * 64}


def _fixture() -> dict[str, object]:
    return {
        "schema": live.FIXTURE_SCHEMA,
        "schema_version": 1,
        "created_at": "2026-09-07T12:00:00Z",
        "receiver_serial": live.RECEIVER_SERIAL,
        "physical_rx_port": "RX1",
        "ethernet_host": live.DEFAULT_LAN_HOST,
        "usb_data_connected": False,
        "volatile_runtime_power_continuity_verified": True,
        "transmitter_connected": False,
        "outdoor_view_verified": True,
        "lnb_model": "test universal Ku LNB",
        "lnb_lo_hz": live.LNB_LO_HZ,
        "lo_side": "low-side",
        "spectral_inversion": False,
        "polarization": "horizontal",
        "lnb_supply_volts": 18.0,
        "lnb_power_source": "external current-limited bias tee",
        "operator_attestation": live.FIXTURE_ATTESTATION,
    }


def _persistent_lan_receipt() -> dict[str, object]:
    return {
        "schema_version": 2,
        "transport": "lan_ssh_frm",
        "outcome": "success",
        "phases": [
            "preflight_revalidated",
            "remote_preflight_attested",
            "source_tx_quiesced",
            "remote_tx_safe_read_only_attested",
            "pluto_frm_staged",
            "staged_hash_verified",
            "updater_reported_done",
            "mtd3_fit_verified",
            "remote_stage_removed",
            "reboot_dispatched",
            "lan_iio_disappeared",
            "lan_iio_reappeared",
            "return_attested",
            "tx_safe_attested",
            "lan_ssh_host_key_rotated",
            "remote_return_tx_safe_read_only_attested",
        ],
        "error": None,
        "returned_serial": live.RECEIVER_SERIAL,
        "returned_firmware": live.EXPECTED_FIRMWARE,
        "returned_phy": "ad9361",
        "plan": {
            "host": live.DEFAULT_LAN_HOST,
            "target_serial": live.RECEIVER_SERIAL,
            "before_firmware": "v0.48-plutoplus-spf-iq-direct-async-v3",
            "before_phy": "ad9361",
            "image_sha256": live.EXPECTED_DFU_SHA256,
            "fit_sha256": live.EXPECTED_FIT_SHA256,
            "fit_size": live.EXPECTED_FIT_SIZE,
            "expected_firmware": live.EXPECTED_FIRMWARE,
            "mutation_profile_id": live.PERSISTENT_PROMOTION_PROFILE,
            "expected_metadata_abi": 3,
            "expected_tandem_agc": False,
            "trust_model": "explicit_lan_tofu",
            "source_iio_layout": "tx-capable-1r1t-v1",
            "return_iio_layout": "rx-only-1r1t-v1",
        },
        "host_key_rotation": {
            "previous_known_hosts_sha256": "1" * 64,
            "replacement_known_hosts_sha256": "2" * 64,
            "previous_fingerprint": "SHA256:old",
            "replacement_fingerprint": "SHA256:new",
            "previous_known_hosts_backup": "/private/radio.known_hosts.pre-reboot",
            "known_hosts_file": "/private/radio.known_hosts",
        },
        "read_only_source_attestation": {
            "serial": live.RECEIVER_SERIAL,
            "firmware": "v0.48-plutoplus-spf-iq-direct-async-v3",
            "boot_id": "11111111-1111-4111-8111-111111111111",
            "qspi_bytes": "33554432",
            "qspi_sha256": "4" * 64,
            "fit_sha256": "5" * 64,
            "all_buffer_enable": "0,0",
            "dds_present": "1",
            "tandem_present": "1",
            "tx_hardwaregain_db": "-80.000000",
            "tx_lo_powerdown": "1",
            "tx_buffer_enable": "0",
            "tx_scan_enable": "0,0",
            "tx_dds_raw": "0,0,0,0",
            "tx_dds_scale": "0.000000,0.000000,0.000000,0.000000",
            "root_marker_present": "0",
            "rx_dma_dt_state": "enabled",
            "dds_dt_state": "enabled",
            "tx_dma_dt_state": "enabled",
            "tandem_dt_state": "enabled",
        },
        "read_only_return_attestation": {
            "serial": live.RECEIVER_SERIAL,
            "firmware": live.EXPECTED_FIRMWARE,
            "boot_id": "11111111-1111-4111-8111-111111111111",
            "qspi_bytes": "33554432",
            "qspi_sha256": "3" * 64,
            "fit_sha256": live.EXPECTED_FIT_SHA256,
            "all_buffer_enable": "0",
            "dds_present": "0",
            "tandem_present": "0",
            "tx_hardwaregain_db": "-80.000000",
            "tx_lo_powerdown": "1",
            "tx_buffer_enable": "",
            "tx_scan_enable": "",
            "tx_dds_raw": "",
            "tx_dds_scale": "",
            "root_marker_present": "1",
            "rx_dma_dt_state": "enabled",
            "dds_dt_state": "disabled",
            "tx_dma_dt_state": "disabled",
            "tandem_dt_state": "disabled",
        },
    }


def _plan() -> dict[str, object]:
    geometry = live.live_geometry(live.DEFAULT_CHANNEL, live.DEFAULT_EDGE, live.LNB_LO_HZ)
    return {
        "schema": live.PLAN_SCHEMA,
        "schema_version": 3,
        "plan_id": "1" * 32,
        "created_at": "2026-09-07T12:01:00Z",
        "hardware_accessed": False,
        "persistent_write": False,
        "do_not_merge": True,
        "deployment_mode": "volatile_ram",
        "ssh_trust_mode": "legacy_unpinned",
        "ssh_known_hosts": None,
        "serial": live.RECEIVER_SERIAL,
        "runtime_target": live.RUNTIME_TARGET,
        "expected_firmware": live.EXPECTED_FIRMWARE,
        "expected_model": live.EXPECTED_MODEL,
        "claim_scope": live.CLAIM_SCOPE,
        "ppu_repository": "/tmp/pluto-plus-utils",
        "ppu_source_commit": "b" * 40,
        "probe_plan": _identity("/tmp/m4-probe.json"),
        "deployment_receipt": _identity("/tmp/m4-ram.json"),
        "runner_source": _identity("/tmp/m4-runner.py"),
        "source_manifest": _identity("/tmp/m4-source.yaml"),
        "expected_boot_id": "11111111-1111-4111-8111-111111111111",
        "expected_qspi_sha256": "c" * 64,
        "controller_binary": _identity("/tmp/m4-controller"),
        "fixture_declaration": _identity("/tmp/m4-fixture.json"),
        "ethernet_host": live.DEFAULT_LAN_HOST,
        "host_network_interface": live.DEFAULT_LAN_INTERFACE,
        "sample_rate_hz": live.SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": live.RF_BANDWIDTH_HZ,
        "rx_port_select": "A_BALANCED",
        "gain_mode": "slow_attack",
        "manual_gain_db": None,
        "starlink_channel": live.DEFAULT_CHANNEL,
        "starlink_edge": live.DEFAULT_EDGE,
        "lnb_lo_hz": live.LNB_LO_HZ,
        **geometry,
        "off_slice_shift_hz": live.DEFAULT_OFF_SLICE_SHIFT_HZ,
        "nominal_off_if_hz": geometry["nominal_on_if_hz"]
        + live.DEFAULT_OFF_SLICE_SHIFT_HZ,
        "scan_offsets_hz": list(live.OFFSET_ORDER_HZ),
        "point_duration_ms": live.DEFAULT_POINT_DURATION_MS,
        "settle_ms": live.DEFAULT_SETTLE_MS,
        "stable_candidate_windows_per_point": (
            live.STABLE_CANDIDATE_WINDOWS_PER_POINT
        ),
        "initial_discard_maps": live.INITIAL_DISCARD_MAPS,
        "post_retune_discard_maps": live.POST_RETUNE_DISCARD_MAPS,
        "role_monitor_duration_ms": live.ROLE_MONITOR_DURATION_MS,
        "accepted_score_counter_budget": live.ACCEPTED_SCORE_COUNTER_BUDGET,
        "role_order": list(live.ROLES),
        "policy": live.POLICY,
        "rail_probe_samples": live.RAIL_PROBE_SAMPLES,
        "receipt_path": "/tmp/m4-receipt.json",
        "confirmation_phrase": (
            f"OBSERVE LIVE STARLINK PSS {live.RECEIVER_SERIAL} CH4 UPPER 15 MSPS"
        ),
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }


def _records(
    *,
    positive: bool,
    map_count: int = 52,
    duration_ms: int | None = None,
    accepted_before: int = 0,
) -> list[dict[str, object]]:
    if duration_ms is None:
        duration_ms = live.DEFAULT_POINT_DURATION_MS
    maps: list[dict[str, object]] = []
    for sequence in range(1, map_count + 1):
        record: dict[str, object] = {
            "schema": monitor.MAP_SCHEMA,
            "claim_scope": monitor.CLAIM_SCOPE,
            "serial": live.RECEIVER_SERIAL,
            "sequence": sequence,
            "bank": sequence & 1,
            "generation": 100 + sequence,
            "start_index_canonical": 5_000
            + (sequence - 1) * monitor.TILE_SAMPLES,
            "accepted_scores": accepted_before + sequence * monitor.TILE_SAMPLES,
            "published_maps": 20 + sequence,
            "health_flags": "0x00000000",
            "fault_free_epoch": True,
            "candidate_available": sequence >= 3,
            "threshold_decision": None,
            "pss_detected": False,
            "frame_lock_claim": False,
        }
        if sequence >= 3:
            index = sequence - 3
            record.update(
                {
                    "phase_bin": (
                        (4_000 + index * 8) % 20_000
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
        "schema": monitor.SUMMARY_SCHEMA,
        "claim_scope": monitor.CLAIM_SCOPE,
        "serial": live.RECEIVER_SERIAL,
        "input_rate_msps": 15,
        "canonical_rate_msps": 15,
        "duration_requested_ms": duration_ms,
        "duration_observed_ms": duration_ms + 20,
        "maps_copied": map_count,
        "candidate_windows": map_count - 2,
        "first_generation": maps[0]["generation"],
        "last_generation": last["generation"],
        "first_start_index_canonical": maps[0]["start_index_canonical"],
        "last_start_index_canonical": last["start_index_canonical"],
        "accepted_scores_before": accepted_before,
        "accepted_scores_at_cutoff": last["accepted_scores"],
        "accepted_scores_delta": last["accepted_scores"] - accepted_before,
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
    summary.update({field: 0 for field in monitor.ZERO_SUMMARY_FIELDS})
    return [*maps, summary]


def _point(
    plan: dict[str, object],
    role: str,
    ordinal: int,
    *,
    positive: bool,
    started_at: datetime,
) -> dict[str, object]:
    base = (
        plan["nominal_off_if_hz"]
        if role == "off_slice_control"
        else plan["nominal_on_if_hz"]
    )
    offset = live.OFFSET_ORDER_HZ[ordinal - 1]
    records = _records(
        positive=positive,
        map_count=live.STABLE_CANDIDATE_WINDOWS_PER_POINT + 2,
    )[2:-1]
    return {
        "role": role,
        "ordinal": ordinal,
        "offset_hz": offset,
        "base_if_hz": base,
        "requested_rx_lo_hz": base + offset,
        "readback_rx_lo_hz": base + offset,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": (
            started_at + timedelta(milliseconds=live.DEFAULT_POINT_DURATION_MS)
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "settle_ms": live.DEFAULT_SETTLE_MS,
        "duration_ms": live.DEFAULT_POINT_DURATION_MS,
        "rssi_before_db": 62.0,
        "rssi_after_db": 62.25,
        "hardwaregain_before_db": 40.0,
        "hardwaregain_after_db": 40.0,
        "monitor_stderr": "",
        "monitor_start_attempts": 1,
        "monitor_records": records,
        "metrics": live._point_metrics(records, plan),
    }


def _roles(plan: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    now = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)
    result: dict[str, list[dict[str, object]]] = {}
    selected = {"on_channel_a": 6, "on_channel_b": 11}
    for role in live.ROLES:
        points = []
        for ordinal in range(1, len(live.OFFSET_ORDER_HZ) + 1):
            points.append(
                _point(
                    plan,
                    role,
                    ordinal,
                    positive=selected.get(role) == ordinal,
                    started_at=now,
                )
            )
            now += timedelta(
                milliseconds=live.DEFAULT_POINT_DURATION_MS + live.DEFAULT_SETTLE_MS
            )
        result[role] = points
    return result


def _role_monitors() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    accepted_before = 0
    for role in live.ROLES:
        records = _records(
            positive=role != "off_slice_control",
            map_count=live.MAXIMUM_ROLE_MAPS - 3,
            duration_ms=live.ROLE_MONITOR_DURATION_MS,
            accepted_before=accepted_before,
        )
        result[role] = {"monitor_records": records, "monitor_stderr": ""}
        accepted_before = int(records[-1]["accepted_scores_at_cutoff"])
    return result


def _runtime(plan: dict[str, object]) -> dict[str, str]:
    return {
        "boot_id": plan["expected_boot_id"],
        "firmware_version": plan["expected_firmware"],
        "qspi_partition": "/dev/mtdblock3",
        "qspi_mtd_name": "qspi-linux",
        "qspi_bytes": "31457280",
        "qspi_sha256": plan["expected_qspi_sha256"],
        "uboot_attr_name_present": "1",
        "uboot_attr_name": "compatible",
        "uboot_attr_val_present": "1",
        "uboot_attr_val": "ad9361",
        "uboot_compatible": "ad9361",
        "uboot_mode": "1r1t",
        "root_marker_present": "1",
        "rx_dma_dt_state": "enabled",
        "dds_dt_state": "disabled",
        "tx_dma_dt_state": "disabled",
        "tandem_dt_state": "disabled",
    }


def _rail() -> dict[str, object]:
    components = live.RAIL_PROBE_SAMPLES * 2
    return {
        "sample_count": live.RAIL_PROBE_SAMPLES,
        "component_count": components,
        "bytes": live.RAIL_PROBE_SAMPLES * 4,
        "sha256": "d" * 64,
        "minimum_component": -1000,
        "maximum_component": 900,
        "maximum_absolute_component": 1000,
        "rms_component": 300.0,
        "rail_count": 0,
        "near_rail_count": 0,
        "rail_fraction": 0.0,
        "payload_retained": False,
    }


def _settings(plan: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    before = {
        "phy_rx_sampling_frequency_hz": 30_720_000,
        "capture_i_sampling_frequency_hz": 30_720_000,
        "rf_bandwidth_hz": 18_000_000,
        "rx_port_select": "A_BALANCED",
        "gain_mode": "slow_attack",
        "hardwaregain_db": 55.0,
        "rx_lo_hz": 2_400_000_000,
        "rx_lo_powerdown": 0,
    }
    selected = {
        **before,
        "phy_rx_sampling_frequency_hz": live.SAMPLE_RATE_HZ,
        "capture_i_sampling_frequency_hz": live.SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": live.RF_BANDWIDTH_HZ,
        "rx_lo_hz": plan["nominal_on_if_hz"],
        "capture_rates_available_hz": [15_000_000, 1_875_000],
        "adc_gp_control": 0,
        "fpga_decimation_factor": 1,
    }
    return before, selected, deepcopy(before)


def _receipt(plan: dict[str, object]) -> dict[str, object]:
    roles = _roles(plan)
    role_monitors = _role_monitors()
    before, selected, restored = _settings(plan)
    partial = {"roles": roles, "rail_probe": _rail()}
    evaluation = live._evaluate_receipt(plan, partial)
    runtime = _runtime(plan)
    return {
        "schema": live.RECEIPT_SCHEMA,
        "schema_version": 3,
        "receipt_id": "e" * 32,
        "started_at": "2026-09-07T13:00:00Z",
        "completed_at": "2026-09-07T13:06:00Z",
        "outcome": "pass",
        "plan": _identity("/tmp/m4-plan.json"),
        "serial": plan["serial"],
        "runtime_target": plan["runtime_target"],
        "expected_firmware": plan["expected_firmware"],
        "hardware_accessed": True,
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": live.CLAIM_SCOPE,
        "route_readback": {
            "destination": live.DEFAULT_LAN_HOST,
            "interface": live.DEFAULT_LAN_INTERFACE,
            "source": "192.168.1.142",
        },
        "radio_and_physical_lan_locks_acquired": True,
        "runtime_before": runtime,
        "runtime_after": deepcopy(runtime),
        "iio_before": before,
        "iio_selected": selected,
        "rail_probe": partial["rail_probe"],
        "roles": roles,
        "role_monitors": role_monitors,
        "controller_info_after": {
            "schema": "starlink-pss-acqctl.info.v1",
            "serial": live.RECEIVER_SERIAL,
            "input_rate_msps": 15,
            "status": "0x00000000",
        },
        "controller_binary_removed": True,
        "iio_restored": restored,
        "iio_context_close_verified": True,
        "evaluation": evaluation,
        "live_pss_acquired": True,
        "timing_trajectory_qualified": True,
        "off_slice_control_rejected": True,
        "pss_detected": True,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": plan["deployment_mode"] == "volatile_ram",
        "cleanup_errors": [],
        "error": None,
    }


def test_exact_ch4_upper_15m_geometry() -> None:
    geometry = live.live_geometry(4, "upper", 9_750_000_000)

    assert geometry == {
        "channel_reference_rf_hz_x2": 23_150_234_375,
        "channel_reference_if_hz_x2": 3_650_234_375,
        "edge_center_offset_hz_x2": 224_765_625,
        "nominal_on_if_hz": 1_937_500_000,
        "nominal_on_rf_hz": 11_687_500_000,
    }


def test_scan_is_interleaved_symmetric_and_fits_one_120s_role() -> None:
    assert live.OFFSET_ORDER_HZ[:7] == (0, 100_000, -100_000, 200_000, -200_000, 300_000, -300_000)
    assert len(live.OFFSET_ORDER_HZ) == 25
    assert set(live.OFFSET_ORDER_HZ) == set(range(-1_200_000, 1_200_001, 100_000))
    consumed_maps = live.INITIAL_DISCARD_MAPS + live.STABLE_CANDIDATE_WINDOWS_PER_POINT
    consumed_maps += (len(live.OFFSET_ORDER_HZ) - 1) * (
        live.POST_RETUNE_DISCARD_MAPS + live.STABLE_CANDIDATE_WINDOWS_PER_POINT
    )
    assert consumed_maps == 922
    assert live.ROLE_MONITOR_DURATION_MS == 80_500
    assert live.ROLE_MONITOR_DURATION_MS < 120_000
    assert live.ACCEPTED_SCORE_COUNTER_BUDGET == 3_632_640_000
    assert live.ACCEPTED_SCORE_COUNTER_BUDGET < live.ACCEPTED_SCORE_COUNTER_SATURATION


def test_fixture_requires_no_tx_and_ram_power_continuity() -> None:
    live._validate_fixture(_fixture())

    invalid = _fixture()
    invalid["transmitter_connected"] = True
    with pytest.raises(live.ProbeError, match="live-LNB"):
        live._validate_fixture(invalid)

    invalid = _fixture()
    invalid["volatile_runtime_power_continuity_verified"] = False
    with pytest.raises(live.ProbeError, match="live-LNB"):
        live._validate_fixture(invalid)


def test_handoff_loader_keeps_ad9361_v7_profile_contract_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, tuple[str, ...]]] = []
    profiled: list[object] = []
    handoff = SimpleNamespace(candidate=object())
    base = {
        "ppu_repository": "/tmp/pluto-plus-utils",
        "ppu_source_commit": "b" * 40,
        "candidate_plan": {"path": "/tmp/candidate.json"},
        "operation_plan": {"path": "/tmp/operation.json"},
        "ram_receipt": {"path": "/tmp/ram-receipt.json"},
    }

    def fake_loader(**_kwargs: object) -> object:
        observed.append(
            (
                live.monitor_v1.probe_v1.RUNTIME_TARGET,
                live.monitor_v2.probe_v9.probe_v2.SUPPORTED_SOURCE_REVISIONS,
            )
        )
        return handoff

    monkeypatch.setattr(live.monitor_v1, "_validate_base_plan", lambda _base: None)
    monkeypatch.setattr(live.monitor_v1.probe_v1, "_load_handoff", fake_loader)
    monkeypatch.setattr(
        live.monitor_v2.probe_v9, "_require_acquisition_injection_profile", profiled.append
    )

    assert live._load_handoff(base) is handoff
    assert observed == [("ad9361-1r1t", ("v2", "v3", "v4", "v5", "v6", "v7"))]
    assert profiled == [handoff]


def test_plan_is_exact_dnm_rx_only_and_has_nonoverlapping_control() -> None:
    plan = _plan()
    live._validate_plan(plan)

    assert plan["nominal_on_if_hz"] - plan["nominal_off_if_hz"] == 50_000_000
    assert plan["do_not_merge"] is True
    assert plan["pss_detected"] is False
    assert plan["sss_detected"] is False
    assert plan["frame_lock_claim"] is False
    assert plan["stable_candidate_windows_per_point"] == 32
    assert plan["role_monitor_duration_ms"] == 80_500


def test_persistent_lan_receipt_binds_exact_v7_return_and_qspi() -> None:
    receipt = _persistent_lan_receipt()

    boot_id, qspi_sha256 = live._validate_persistent_lan_receipt(receipt)

    assert boot_id == "11111111-1111-4111-8111-111111111111"
    assert qspi_sha256 == "3" * 64


def test_external_ppu_receipt_loader_accepts_pretty_strict_private_json(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    path = tmp_path / "ppu-receipt.json"
    path.write_text(json.dumps({"schema_version": 2, "outcome": "success"}, indent=2))
    path.chmod(0o600)

    assert live._load_external_receipt(path, label="persistent LAN receipt") == {
        "schema_version": 2,
        "outcome": "success",
    }


def test_external_ppu_receipt_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    path = tmp_path / "ppu-receipt.json"
    path.write_text('{"outcome":"success","outcome":"failed"}\n')
    path.chmod(0o600)

    with pytest.raises(live.ProbeError, match="duplicate key"):
        live._load_external_receipt(path, label="persistent LAN receipt")


def test_public_identity_accepts_executable_and_detects_a_later_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "controller"
    path.write_bytes(b"sealed-controller\n")
    path.chmod(0o755)

    identity = live._public_identity(path, label="controller binary")

    assert identity["bytes"] == len(b"sealed-controller\n")
    live._require_public_unchanged(identity, label="controller binary")
    path.write_bytes(b"changed-controller\n")
    with pytest.raises(live.ProbeError, match="changed after plan sealing"):
        live._require_public_unchanged(identity, label="controller binary")


def test_persistent_lan_receipt_rejects_a_different_profile_or_tx_state() -> None:
    receipt = _persistent_lan_receipt()
    receipt["plan"]["mutation_profile_id"] = "persistent-canary"
    with pytest.raises(live.ProbeError, match="persistent LAN receipt"):
        live._validate_persistent_lan_receipt(receipt)

    receipt = _persistent_lan_receipt()
    receipt["read_only_source_attestation"]["tx_lo_powerdown"] = "0"
    with pytest.raises(live.ProbeError, match="persistent LAN receipt"):
        live._validate_persistent_lan_receipt(receipt)

    receipt = _persistent_lan_receipt()
    receipt["read_only_return_attestation"]["tx_lo_powerdown"] = "0"
    with pytest.raises(live.ProbeError, match="persistent LAN receipt"):
        live._validate_persistent_lan_receipt(receipt)


def test_persistent_live_receipt_does_not_claim_recovery_is_required() -> None:
    plan = _plan()
    plan["deployment_mode"] = "persistent_lan"
    receipt = _receipt(plan)

    live._validate_passing_receipt(receipt, plan)

    assert receipt["recovery_required"] is False


def test_persistent_ssh_uses_only_the_receipt_bound_host_key() -> None:
    plan = _plan()
    plan["deployment_mode"] = "persistent_lan"
    plan["ssh_trust_mode"] = "pinned"
    plan["ssh_known_hosts"] = _identity("/private/radio.known_hosts")

    argv = live._ssh_argv(plan, Path("/private/radio.password"), "true")

    assert "StrictHostKeyChecking=yes" in argv
    assert "UserKnownHostsFile=/private/radio.known_hosts" in argv
    assert "GlobalKnownHostsFile=/dev/null" in argv
    assert "CheckHostIP=yes" in argv
    assert "StrictHostKeyChecking=no" not in argv


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("serial", "wrong-radio"),
        ("ethernet_host", "192.168.1.20"),
        ("expected_firmware", "main"),
        ("off_slice_shift_hz", -10_000_000),
        ("do_not_merge", False),
    ],
)
def test_plan_rejects_wrong_identity_geometry_or_branch_scope(field: str, value: object) -> None:
    plan = _plan()
    plan[field] = value
    with pytest.raises(live.ProbeError, match="violate"):
        live._validate_plan(plan)


def test_positive_role_selects_the_single_tracked_offset() -> None:
    plan = _plan()
    roles = _roles(plan)

    result = live.analyze_role("on_channel_a", roles["on_channel_a"], live.POLICY)

    assert result["passing_point_count"] == 1
    assert result["passing_offsets_hz"] == [300_000]
    assert result["best_offset_hz"] == 300_000
    assert result["best_metrics"]["longest_consecutive_track_windows"] == 32


def test_complete_live_policy_requires_positive_control_positive() -> None:
    plan = _plan()
    receipt = _receipt(plan)

    result = live._validate_passing_receipt(receipt, plan)

    assert result["qualified"] is True
    assert result["role_analyses"]["on_channel_a"]["passing_point_count"] == 1
    assert result["role_analyses"]["off_slice_control"]["passing_point_count"] == 0
    assert result["role_analyses"]["on_channel_b"]["passing_point_count"] == 1
    assert result["positive_to_control_median_ratio"] > 3.0


def test_live_policy_rejects_equivalent_control_track() -> None:
    plan = _plan()
    receipt = _receipt(plan)
    control = receipt["roles"]["off_slice_control"][4]
    records = _records(
        positive=True,
        map_count=live.STABLE_CANDIDATE_WINDOWS_PER_POINT + 2,
    )[2:-1]
    control["monitor_records"] = records
    control["metrics"] = live._point_metrics(records, plan)
    receipt["evaluation"] = live._evaluate_receipt(plan, receipt)

    assert receipt["evaluation"]["qualified"] is False
    with pytest.raises(live.ProbeError, match="qualification"):
        live._validate_passing_receipt(receipt, plan)


def test_live_policy_rejects_clipping() -> None:
    plan = _plan()
    receipt = _receipt(plan)
    receipt["rail_probe"]["rail_count"] = 100
    receipt["rail_probe"]["near_rail_count"] = 100
    receipt["rail_probe"]["rail_fraction"] = 100 / (live.RAIL_PROBE_SAMPLES * 2)
    receipt["evaluation"] = live._evaluate_receipt(plan, receipt)

    assert receipt["evaluation"]["qualified"] is False
    with pytest.raises(live.ProbeError, match="qualification"):
        live._validate_passing_receipt(receipt, plan)


def test_point_rejects_faulted_transport_before_signal_decision() -> None:
    plan = _plan()
    receipt = _receipt(plan)
    receipt["role_monitors"]["on_channel_a"]["monitor_records"][-1][
        "map_overruns_at_cutoff"
    ] = 1

    with pytest.raises(live.ProbeError, match="zero-loss"):
        live._validate_passing_receipt(receipt, plan)


def test_campaign_rejects_insufficient_accepted_score_counter_headroom() -> None:
    plan = _plan()
    records = _records(
        positive=True,
        map_count=live.MAXIMUM_ROLE_MAPS - 3,
        duration_ms=live.ROLE_MONITOR_DURATION_MS,
        accepted_before=(
            live.ACCEPTED_SCORE_COUNTER_SATURATION
            - live.ACCEPTED_SCORE_COUNTER_BUDGET
        ),
    )

    with pytest.raises(live.ProbeError, match="counter lacks campaign headroom"):
        live._validate_counter_headroom(records, plan)


def test_scan_role_partitions_one_continuous_stream_by_map_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _plan()
    records = _records(
        positive=True,
        map_count=live.MAXIMUM_ROLE_MAPS - 3,
        duration_ms=live.ROLE_MONITOR_DURATION_MS,
    )
    stream = tmp_path / "continuous-role.ndjson"
    stream.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    writes: list[int] = []

    monkeypatch.setattr(
        live,
        "_ssh_argv",
        lambda *_args: (
            sys.executable,
            "-c",
            "import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",
            str(stream),
        ),
    )

    def fake_write(
        _owner: object,
        _name: str,
        value: int,
        **_kwargs: object,
    ) -> float:
        writes.append(value)
        return float(value)

    monkeypatch.setattr(live, "_write_number", fake_write)
    monkeypatch.setattr(live, "_read_number", lambda *_args, **_kwargs: 40.0)

    points, monitor_evidence = live._scan_role(
        plan,
        "on_channel_a",
        {"rx_lo": object(), "phy_rx": object()},
        Path("/tmp/password"),
        "/tmp/controller",
        sleeper=lambda _seconds: None,
    )

    assert writes == [
        plan["nominal_on_if_hz"] + offset for offset in live.OFFSET_ORDER_HZ
    ]
    assert len(points) == 25
    assert all(len(point["monitor_records"]) == 32 for point in points)
    assert points[0]["monitor_records"][0]["sequence"] == 3
    assert points[1]["monitor_records"][0]["sequence"] == 40
    assert points[-1]["monitor_records"][-1]["sequence"] == 922
    assert monitor_evidence["monitor_records"] == records


def test_rail_probe_calculates_exact_s12_clipping(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan()
    components = [0] * (live.RAIL_PROBE_SAMPLES * 2)
    components[10] = -2_048
    components[11] = 2_047
    payload = bytearray()
    for value in components:
        payload.extend(int(value).to_bytes(2, "little", signed=True))

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=bytes(payload), stderr=b"", returncode=0)

    monkeypatch.setattr(live, "_run", fake_run)
    result = live._rail_probe(plan)

    assert result["rail_count"] == 2
    assert result["near_rail_count"] == 2
    assert result["rail_fraction"] == 2 / len(components)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["rms_component"] == pytest.approx(
        math.sqrt((2_048**2 + 2_047**2) / len(components))
    )


def test_apply_settings_moves_phy_clock_before_capture_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    objects = {
        "rx_lo": object(),
        "phy_rx": object(),
        "capture_i": object(),
        "rx": SimpleNamespace(reg_read=lambda _address: 0),
    }
    writes: list[tuple[object, str]] = []
    selected = {
        "phy_rx_sampling_frequency_hz": live.SAMPLE_RATE_HZ,
        "capture_i_sampling_frequency_hz": live.SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": live.RF_BANDWIDTH_HZ,
        "rx_port_select": plan["rx_port_select"],
        "gain_mode": plan["gain_mode"],
        "hardwaregain_db": 20.0,
        "rx_lo_hz": plan["nominal_on_if_hz"],
        "rx_lo_powerdown": 0,
    }

    def fake_write(owner: object, name: str, *_args: object, **_kwargs: object) -> float:
        writes.append((owner, name))
        return 0.0

    monkeypatch.setattr(live, "_write_number", fake_write)
    monkeypatch.setattr(live, "_write_text", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        live,
        "_read_text",
        lambda *_args, **_kwargs: "15000000 1875000",
    )
    monkeypatch.setattr(live, "_snapshot_settings", lambda _objects: selected)

    live._apply_settings(objects, plan, plan["nominal_on_if_hz"])

    assert writes[:3] == [
        (objects["rx_lo"], "powerdown"),
        (objects["phy_rx"], "sampling_frequency"),
        (objects["capture_i"], "sampling_frequency"),
    ]


def test_remote_identity_keeps_multiline_shell_script(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan()
    captured: dict[str, object] = {}
    expected = _runtime(plan)

    def fake_run(argv: object, **_kwargs: object) -> SimpleNamespace:
        captured["argv"] = argv
        payload = "".join(f"{key}={value}\n" for key, value in expected.items()).encode()
        return SimpleNamespace(stdout=payload, stderr=b"", returncode=0)

    monkeypatch.setattr(live, "_run", fake_run)
    handoff = SimpleNamespace(
        ppu=SimpleNamespace(
            linux=SimpleNamespace(
                REMOTE_RX_ONLY_IDENTITY_SCRIPT="set -eu\na=1\nprintf x"
            )
        )
    )
    result = live._remote_identity(plan, handoff, Path("/tmp/password"))

    assert result == expected
    assert captured["argv"][-1] == "set -eu\na=1\nprintf x"


def test_script_is_executable_and_never_claims_sss_or_frame_lock() -> None:
    assert Path(live.__file__).stat().st_mode & 0o111
    plan = _plan()
    receipt = _receipt(plan)
    assert plan["sss_detected"] is False
    assert plan["frame_lock_claim"] is False
    assert receipt["sss_detected"] is False
    assert receipt["frame_lock_claim"] is False
