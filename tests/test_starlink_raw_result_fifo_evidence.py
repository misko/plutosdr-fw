from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "starlink-pss15-raw-result-fifo-dnm-v1-source.yaml"
REPORT = ROOT / "reports" / "STARLINK_PSS15_RAW_RESULT_FIFO_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-raw-result-fifo-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "7cba0eac1cd83e29846b812caca0f0dfee2523d4"
SUMMARY_SHA256 = "8226e38e2c7739350173a335129cd2398e4eb038091fc7d1ea6312f70abe5a38"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_raw_result_fifo_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "fifo_depth": "512",
        "payload_bits": "123",
        "qualified_ifft_burst_results": "447",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "3.342",
        "hold_whs_ns": "0.011",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "79",
        "total_ffs": "42",
        "ramb36e1": "2",
        "ramb18e1": "0",
        "dsp48e1": "0",
    }
    assert HDL_COMMIT in report
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in plan
    assert "7,720 LUTs" in report
    assert "37.5 BRAM tiles" in plan
    assert "+0.011 ns" in report


def test_raw_result_fifo_contract_and_simulation_are_explicit() -> None:
    rtl = (
        ROOT / "hdl/library/starlink_pss_acquisition/starlink_pss_raw_result_fifo.v"
    ).read_text()
    testbench = (
        ROOT / "hdl/library/starlink_pss_acquisition/tb/"
        "tb_starlink_pss_raw_result_fifo.sv"
    ).read_text()
    runner = (ROOT / "hdl/library/starlink_pss_acquisition/run_tests.sh").read_text()

    assert "parameter integer FIFO_DEPTH = 512" in rtl
    assert "localparam integer PAYLOAD_BITS = 123" in rtl
    assert 'ram_style = "block"' in rtl
    assert "current_stored_count = memory_count + output_valid" in rtl
    assert "input_valid && !input_ready" in rtl
    assert "result_memory[write_pointer] <= input_payload" in rtl
    assert "447-result burst experienced input backpressure" in testbench
    assert "concurrent stream did not drain exactly" in testbench
    assert "overflow was not reported without state mutation" in testbench
    assert "RAW_FIFO_PASS" in testbench
    assert "tb_starlink_pss_raw_result_fifo" in runner


def test_raw_result_fifo_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "raw_result_fifo_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_raw_result_fifo.v"
        ),
        "raw_result_fifo_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_raw_result_fifo.sv"
        ),
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "raw_result_fifo_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_raw_result_fifo_ooc.sh"
        ),
        "raw_result_fifo_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_raw_result_fifo_ooc.xdc"
        ),
        "raw_result_fifo_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/synthesize_raw_result_fifo_ooc.tcl"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "raw_result_fifo_ooc_summary_sha256": (
            "reports/starlink-pss15-raw-result-fifo-ooc-summary.txt"
        ),
        "raw_result_fifo_report_sha256": (
            "reports/STARLINK_PSS15_RAW_RESULT_FIFO_V1.md"
        ),
        "raw_result_fifo_evidence_test_sha256": (
            "tests/test_starlink_raw_result_fifo_evidence.py"
        ),
        "starlink_plan_sha256": "STARLINK_PSS_15_30_60_PLAN.md",
    }

    assert "do_not_merge: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_required: true" in manifest
    assert (
        "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/88"
        in manifest
    )
    assert (
        "firmware_main_gitlink_guard_merge_commit: "
        "627f1f48e776e174095d34822a8ce3506ed0aebb" in manifest
    )
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "raw_result_fifo_simulation_verdict: PASS" in manifest
    assert "raw_result_fifo_ooc_verdict: PASS" in manifest
    assert "rtl_score_preprocessor_implemented: true" in manifest
    assert "rtl_raw_result_fifo_implemented: true" in manifest
    assert "rtl_energy_join_implemented: false" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    historical_shared_files = {"acquisition_test_runner_sha256"}
    for field, relative in bound_files.items():
        if field in historical_shared_files:
            continue
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    # The living runner advances with the next independently checkpointed RTL
    # slice. Preserve the raw-FIFO checkpoint's reviewed runner digest.
    assert (
        "acquisition_test_runner_sha256: "
        "d8b1adb8152919f90b927c0026dd78da4293fee0356750272e225ec86063d688" in manifest
    )
