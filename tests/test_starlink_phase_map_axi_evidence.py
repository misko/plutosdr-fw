from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
BRIDGE = "library/axi_starlink_pss_phase_map"
MANIFEST = ROOT / "manifests/starlink-pss15-phase-map-axi-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_PHASE_MAP_AXI_V1.md"
SIMULATION_SUMMARY = (
    ROOT / "reports/starlink-pss15-phase-map-axi-v1-simulation-summary.txt"
)
OOC_SUMMARY = ROOT / "reports/starlink-pss15-phase-map-axi-v1-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"

HDL_COMMIT = "e2e1b87fccfb7efbeb3612e2a3b5a0fea919ba93"
HDL_TAG = "starlink-rx-only-dnm-v1-source/hdl-pss15-phase-map-axi-v1"
GUARD_MERGE_COMMIT = "d2fcc1175dbf0c866288b0c369cc2cfb314979ba"
SIMULATION_SUMMARY_SHA256 = (
    "a9d3773e1facb112402536e4bde83d046b393dd81bd7d4808c0c945303542469"
)
OOC_SUMMARY_SHA256 = (
    "c7ad80b1debcbbc7f204728508398e21acbff34c57671dba7b4c7d7067755e0f"
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _summary(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if line)


def _hdl_at_checkpoint(relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(HDL), "show", f"{HDL_COMMIT}:{relative}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def test_phase_map_axi_functional_summary_is_frozen_and_passing() -> None:
    summary = _summary(SIMULATION_SUMMARY)
    assert _sha256(SIMULATION_SUMMARY) == SIMULATION_SUMMARY_SHA256
    assert summary == {
        "iverilog_version": "12.0",
        "structure_verdict": "PASS",
        "axi_lite_long_latency": "true",
        "snapshot_bits": "482",
        "atomic_snapshot": "true",
        "reset_abort": "true",
        "asynchronous_clocks": "true",
        "skew_constraints": "3",
        "routed_gate_present": "true",
        "integrated_clock_cases": "4",
        "integrated_map_data_requests_per_case": "11",
        "integrated_snapshots_per_case": "2",
        "integrated_split_writes_per_case": "2",
        "integrated_concurrent_read_write_per_case": "1",
        "integrated_read_backpressure_per_case": "1",
        "integrated_reset_abort_per_case": "1",
        "integrated_read_errors_per_case": "1",
        "integrated_release_errors_per_case": "1",
        "integrated_flushes_per_case": "1",
        "map_read_max_axi_cycles_71mhz": "17",
        "map_read_max_axi_cycles_62_5mhz": "18",
        "map_read_max_axi_cycles_100mhz": "14",
        "map_read_max_axi_cycles_125mhz": "13",
        "snapshot_stress_map_clock_hz": "10000000",
        "snapshot_stress_axi_clock_hz": "100000000",
        "snapshot_words_checked": "16",
        "snapshot_coherent_sets": "2",
        "snapshot_request_overruns": "1",
        "verdict": "PASS",
    }


def test_phase_map_axi_routed_summary_is_frozen_and_passing() -> None:
    summary = _summary(OOC_SUMMARY)
    report = REPORT.read_text()
    assert _sha256(OOC_SUMMARY) == OOC_SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "map_clock_period_ns": "10.000",
        "axi_clock_period_ns": "10.000",
        "timing_scope": "post_route",
        "setup_wns_ns": "2.648",
        "hold_whs_ns": "0.037",
        "methodology_violations": "0",
        "check_timing_expected_async_reset_only": "1",
        "critical_cdc_rows": "0",
        "bus_skew_met": "3",
        "bus_skew_violated": "0",
        "snapshot_source_bits": "482",
        "snapshot_synchronizer_bits": "964",
        "snapshot_destination_bits": "482",
        "total_luts": "398",
        "total_ffs": "2455",
        "ramb36e1": "0",
        "ramb18e1": "0",
        "dsp48e1": "0",
    }
    assert "+2.648 ns" in report
    assert "+0.037 ns" in report
    assert "2,455" in report
    assert "468.75 kB/s" in report
    assert HDL_COMMIT in report


def test_phase_map_axi_checkpoint_tree_has_required_protocols() -> None:
    bridge = _hdl_at_checkpoint(f"{BRIDGE}/axi_starlink_pss_phase_map.v").decode()
    axi = _hdl_at_checkpoint(f"{BRIDGE}/starlink_pss_axi_lite.v").decode()
    constraints = _hdl_at_checkpoint(
        f"{BRIDGE}/axi_starlink_pss_phase_map_constr.xdc"
    ).decode()
    ooc = _hdl_at_checkpoint(f"{BRIDGE}/synthesize_ooc.tcl").decode()
    runner = _hdl_at_checkpoint(f"{BRIDGE}/run_tests.sh").decode()
    testbench = _hdl_at_checkpoint(
        f"{BRIDGE}/tb/tb_axi_starlink_pss_phase_map.sv"
    ).decode()

    assert "localparam integer SNAPSHOT_BITS = 482" in bridge
    assert "reg read_request_toggle" in bridge
    assert "reg release_request_toggle" in bridge
    assert "reg snapshot_request_toggle" in bridge
    assert "map_reset_control_sync[1]" in bridge
    assert "selected_map_bank == read_request_bank" in bridge
    assert "selected_map_index == read_request_index" in bridge
    assert "assign irq = core_control_resetn && |ready_mask_sync_2" in bridge
    assert "reg aw_pending" in axi
    assert "reg w_pending" in axi
    assert "write_waiting && up_wack" in axi
    assert "read_waiting && up_rack" in axi
    assert "s_axi_rvalid && s_axi_rready" in axi
    assert "deaddead" not in axi.lower()
    assert constraints.count("set_bus_skew") == 3
    assert "critical_cdc_count != 0" in ooc
    assert "bus_skew_met != 3" in ooc
    assert "setup_wns < 0.0 || $hold_whs < 0.0" in ooc
    assert runner.count("run_case ") == 4
    assert "completed MAP_DATA read overwrote a newer map selection" in testbench
    assert "map reset did not abort an in-flight AXI read cleanly" in testbench

    peeled_tag = subprocess.run(
        ["git", "-C", str(HDL), "rev-parse", f"{HDL_TAG}^{{}}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert peeled_tag == HDL_COMMIT


def test_phase_map_axi_manifest_is_safe_and_hash_locked() -> None:
    manifest = MANIFEST.read_text()
    assert "do_not_merge: true" in manifest
    assert "do_not_release: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert "qualification_radio_serial: 104000bac4950008230026001b440a003a" in manifest
    assert "qualification_utility_changed: false" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert f"submodule_hdl_ref: refs/tags/{HDL_TAG}" in manifest
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/95" in manifest
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "simulation_verdict: PASS" in manifest
    assert "ooc_verdict: PASS" in manifest
    assert "rtl_axi_cdc_control_implemented: true" in manifest
    assert "rtl_candidate_selection_implemented: false" in manifest
    assert "rtl_frame_lock_state_machine_implemented: false" in manifest
    assert "rtl_rx_shell_connected: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "frame_alignment_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest

    checkpoint_files = {
        "axi_bridge_rtl_sha256": f"{BRIDGE}/axi_starlink_pss_phase_map.v",
        "axi_lite_rtl_sha256": f"{BRIDGE}/starlink_pss_axi_lite.v",
        "axi_bridge_constraints_sha256": (
            f"{BRIDGE}/axi_starlink_pss_phase_map_constr.xdc"
        ),
        "axi_bridge_ip_tcl_sha256": f"{BRIDGE}/axi_starlink_pss_phase_map_ip.tcl",
        "axi_bridge_ooc_xdc_sha256": (
            f"{BRIDGE}/axi_starlink_pss_phase_map_ooc.xdc"
        ),
        "axi_bridge_ooc_runner_sha256": f"{BRIDGE}/run_ooc.sh",
        "axi_bridge_test_runner_sha256": f"{BRIDGE}/run_tests.sh",
        "axi_bridge_ooc_tcl_sha256": f"{BRIDGE}/synthesize_ooc.tcl",
        "axi_bridge_testbench_sha256": (
            f"{BRIDGE}/tb/tb_axi_starlink_pss_phase_map.sv"
        ),
        "axi_bridge_snapshot_testbench_sha256": (
            f"{BRIDGE}/tb/tb_axi_starlink_pss_phase_map_snapshot.sv"
        ),
        "axi_bridge_structure_verifier_sha256": f"{BRIDGE}/tb/verify_structure.py",
        "axi_bridge_readme_sha256": f"{BRIDGE}/README.md",
    }
    current_files = {
        "phase_map_axi_simulation_summary_sha256": (
            "reports/starlink-pss15-phase-map-axi-v1-simulation-summary.txt"
        ),
        "phase_map_axi_ooc_summary_sha256": (
            "reports/starlink-pss15-phase-map-axi-v1-ooc-summary.txt"
        ),
        "phase_map_axi_simulation_runner_sha256": "run_starlink_pss15_phase_map_axi.sh",
        "phase_map_axi_ooc_parent_runner_sha256": (
            "run_starlink_pss15_phase_map_axi_ooc.sh"
        ),
        "phase_map_axi_report_sha256": "reports/STARLINK_PSS15_PHASE_MAP_AXI_V1.md",
        "phase_map_axi_evidence_test_sha256": "tests/test_starlink_phase_map_axi_evidence.py",
    }
    for field, relative in checkpoint_files.items():
        digest = _sha256_bytes(_hdl_at_checkpoint(relative))
        assert f"{field}: {digest}" in manifest
    for field, relative in current_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest

    plan = PLAN.read_text()
    assert HDL_COMMIT in plan
    assert GUARD_MERGE_COMMIT in plan
    assert "ARM candidate extraction" in plan
