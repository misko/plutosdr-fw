from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
ACQUISITION = ROOT / "hdl/library/starlink_pss_acquisition"
MANIFEST = ROOT / "manifests/starlink-pss15-xfft-block-adapter-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_XFFT_BLOCK_ADAPTER_V1.md"
SUMMARY = ROOT / "reports/starlink-pss15-xfft-block-adapter-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "b8657819e56c9a2b836319e9b9b8596fc4ce3204"
FIRMWARE_COMMIT = "aca2cc30e477a749dda58f447f602c6c5b93cadd"
SUMMARY_SHA256 = "599ca4afa10a9164227834956e45f7e34d8084a4436fa267aa52563cc0570501"
GUARD_MERGE_COMMIT = "68ef649d2fd76b62f437148a222f0881d50ea7f2"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_blob(commit: str, relative: str, cwd: Path = ROOT) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def _checkpoint_blob(relative: str) -> bytes:
    if relative.startswith("hdl/"):
        return _git_blob(HDL_COMMIT, relative.removeprefix("hdl/"), HDL)
    return _git_blob(FIRMWARE_COMMIT, relative)


def _checkpoint_text(relative: str) -> str:
    return _checkpoint_blob(relative).decode()


def test_xfft_block_adapter_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "transform_samples": "512",
        "transform_direction": "forward",
        "data_bits": "24",
        "tuser_bits": "24",
        "status_bits": "8",
        "maximum_blocks_inflight": "1",
        "core_reset_low_cycles_after_flush": "2",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "2.328",
        "hold_whs_ns": "0.269",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "103",
        "total_ffs": "111",
        "ramb36e1": "0",
        "ramb18e1": "0",
        "dsp48e1": "0",
    }
    assert HDL_COMMIT in report
    assert HDL_COMMIT in plan
    assert SUMMARY_SHA256 in report
    assert "-1.018 ns" in report
    assert "+2.328 ns" in report
    assert "8,056 LUTs" in report
    assert "12,150 registers" in plan


def test_xfft_block_adapter_contract_and_simulation_are_explicit() -> None:
    prefix = "hdl/library/starlink_pss_acquisition/"
    adapter = _checkpoint_text(prefix + "starlink_pss_xfft_block_adapter.v")
    testbench = _checkpoint_text(prefix + "tb/tb_starlink_pss_xfft_block_adapter.sv")
    runner = _checkpoint_text(prefix + "run_tests.sh")
    ooc_gate = _checkpoint_text(prefix + "synthesize_xfft_block_adapter_ooc.tcl")

    assert "parameter integer FORWARD_TRANSFORM = 1" in adapter
    assert "reset_release_count == 2" in adapter
    assert "core_config_tdata = {7'b0, FORWARD_TRANSFORM[0]}" in adapter
    assert "input_position == expected_input_position" in adapter
    assert "input_block_start_index == active_block_start_index" in adapter
    assert "core_status_tdata[7:5] != 0" in adapter
    assert "core_output_tuser[15:9] == 0" in adapter
    assert "core_output_tuser[23:21] == 0" in adapter
    assert "core_output_tuser[20:16] == effective_status_exponent" in adapter
    assert "effective_status_seen ? output_ready : 1'b0" in adapter
    assert "input_framing_error_now ||" in adapter
    assert "status_or_padding_error_now ||" in adapter
    assert "hard_core_error_now ||" in adapter
    assert "output_metadata_error_now" in adapter
    assert "fault_event_now && !protocol_fault" in adapter
    assert ".FORWARD_TRANSFORM (0)" in testbench
    assert "data escaped before frame status arrived" in testbench
    assert "bad application frame was not consumed fail-closed" in testbench
    assert "bad XFFT output metadata was not consumed fail-closed" in testbench
    assert "XFFT_ADAPTER_PASS" in testbench
    assert "tb_starlink_pss_xfft_block_adapter" in runner
    assert "methodology violations are not allowed" in ooc_gate
    assert "100 MHz post-opt timing failed" in ooc_gate


def test_xfft_block_adapter_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "xfft_block_adapter_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_xfft_block_adapter.v"
        ),
        "xfft_block_adapter_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_xfft_block_adapter.sv"
        ),
        "xfft_block_adapter_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_xfft_block_adapter_ooc.sh"
        ),
        "xfft_block_adapter_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_xfft_block_adapter_ooc.xdc"
        ),
        "xfft_block_adapter_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/synthesize_xfft_block_adapter_ooc.tcl"
        ),
        "xfft_block_adapter_ooc_summary_sha256": (
            "reports/starlink-pss15-xfft-block-adapter-ooc-summary.txt"
        ),
        "candidate_path_historical_evidence_test_sha256": (
            "tests/test_starlink_candidate_score_path_evidence.py"
        ),
        "xfft_block_adapter_report_sha256": (
            "reports/STARLINK_PSS15_XFFT_BLOCK_ADAPTER_V1.md"
        ),
    }
    historical_shared_files = {
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "xfft_block_adapter_evidence_test_sha256": (
            "tests/test_starlink_xfft_block_adapter_evidence.py"
        ),
        "starlink_plan_sha256": "STARLINK_PSS_15_30_60_PLAN.md",
    }

    assert "do_not_merge: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert "submodule_buildroot: daf5ec3fe6b394337379394fa98a52815520d886" in manifest
    assert (
        "submodule_hdl_quantulum: 364b3dc7e770c3971d1f41a75c00e6cae76e2e6d" in manifest
    )
    assert "submodule_linux: 154bda793ee846c57421d07b722fae898f0ae134" in manifest
    assert "submodule_u_boot_xlnx: 1ff0468e9bea29b0a768a7bf52db8d025c521b9a" in manifest
    assert (
        "superseded_manifest_recorded_hdl_quantulum: "
        "70142c3d495b787857173d0dc8cc59da67bcf242" in manifest
    )
    assert "firmware_main_gitlink_guard_required: true" in manifest
    assert (
        "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/90"
        in manifest
    )
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "xfft_block_adapter_simulation_verdict: PASS" in manifest
    assert "xfft_block_adapter_ooc_verdict: PASS" in manifest
    assert "rtl_xfft_block_adapter_implemented: true" in manifest
    assert "rtl_xfft_forward_inverse_config_qualified: true" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_coefficient_rom_packaged: false" in manifest
    assert "rtl_raw_iq_to_score_complete: false" in manifest
    assert "rtl_phase_map_connected_to_score_path: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        digest = _sha256_bytes(_checkpoint_blob(relative))
        assert f"{field}: {digest}" in manifest
    for field, relative in historical_shared_files.items():
        digest = _sha256_bytes(_checkpoint_blob(relative))
        assert f"{field}: {digest}" in manifest
