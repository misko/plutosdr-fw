from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m4-live-dnm-v1-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m4_manifest_preserves_live_rx_only_claim_scope() -> None:
    values = _values()
    assert values["schema"] == "plutosdr-fw.starlink-pss-m4-live-source"
    assert values["schema_version"] == "3"
    assert values["release_state"] == "pinned-ssh-v3-cabled-qualified-live-ready"
    assert values["bench_preflight_completed"] == "true"
    assert values["live_execution_approved"] == "true"
    assert values["required_revision"] == "complete"
    for field in (
        "do_not_merge",
        "do_not_release",
        "experimental_receiver_rx_only",
        "ethernet_only_observation",
        "transmitter_connected",
        "persistent_flash_eligible",
        "persistent_write",
        "hardware_accessed",
        "live_pss_detected",
        "sss_detected",
        "frame_lock_claim",
    ):
        expected = "true" if field in {
            "do_not_merge",
            "do_not_release",
            "experimental_receiver_rx_only",
            "ethernet_only_observation",
            "hardware_accessed",
            "persistent_flash_eligible",
        } else "false"
        assert values[field] == expected
    assert values["allocated_receiver_serial"] == (
        "104000bac4950008230026001b440a003a"
    )
    assert values["ethernet_host"] == "192.168.1.17"
    assert values["role_order"] == "on_channel_a,off_slice_control,on_channel_b"
    assert values["claim_scope"] == (
        "live_lnb_pss_acquisition_and_local_timing_only"
    )
    assert values["cabled_production_requalification_passed"] == "true"
    assert values["cabled_over_the_air"] == "false"
    assert values["cabled_control_passing_points"] == "0"
    assert values["cabled_all_transport_fault_counters_zero"] == "true"
    assert values["cabled_transmitter_final_mute_verified"] == "true"
    assert values["cabled_receiver_recovery_verified"] == "true"


def test_m4_manifest_binds_every_direct_source_and_contract() -> None:
    values = _values()
    for prefix in (
        "runner_source",
        "runner_test",
        "manifest_test",
        "m3_policy_source",
        "monitor_probe_v1_source",
        "monitor_probe_v2_source",
        "progress_probe_source",
        "numerology_oracle",
        "monitor_v2_controller_source",
        "acquisition_library_source",
        "acquisition_header",
        "controller_makefile",
        "inherited_m3_manifest",
        "inherited_monitor_manifest",
        "inherited_fpga_manifest",
        "tracker_ledger",
        "canonical_plan",
        "controller_readme",
    ):
        path = ROOT / values[f"{prefix}_path"]
        assert path.is_file()
        assert _sha256(path) == values[f"{prefix}_sha256"]


def test_m4_manifest_freezes_scan_geometry_and_decision_policy() -> None:
    values = _values()
    assert values["sample_rate_hz"] == "15000000"
    assert values["rf_bandwidth_hz"] == "15000000"
    assert values["lnb_lo_hz"] == "9750000000"
    assert values["nominal_on_if_hz"] == "1937500000"
    assert values["nominal_on_rf_hz"] == "11687500000"
    assert values["nominal_control_if_hz"] == "1887500000"
    assert values["scan_offset_minimum_hz"] == "-1200000"
    assert values["scan_offset_maximum_hz"] == "1200000"
    assert values["scan_offset_step_hz"] == "100000"
    assert values["scan_point_count_per_role"] == "25"
    assert values["point_duration_ms"] == "2731"
    assert values["settle_ms"] == "200"
    assert values["role_duration_ms"] == "80500"
    assert values["stable_candidate_windows_per_point"] == "32"
    assert values["initial_discard_maps"] == "2"
    assert values["post_retune_discard_maps"] == "5"
    assert values["maximum_role_maps"] == "946"
    assert values["accepted_score_counter_budget"] == "3632640000"
    assert values["accepted_score_counter_saturation"] == "4294967295"
    assert values["maximum_control_passing_points"] == "0"
    assert values["minimum_positive_to_control_ratio"] == "1.10"
    assert values["maximum_rail_fraction"] == "0.0001"
