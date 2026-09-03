from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
ACQUISITION = ROOT / "hdl/library/starlink_pss_acquisition"
MANIFEST = ROOT / "manifests/starlink-pss15-candidate-score-path-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_CANDIDATE_SCORE_PATH_V1.md"
SUMMARY = ROOT / "reports/starlink-pss15-candidate-score-path-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "e12355ec0572c0637932fed0b3846c6a0b52a99c"
FIRMWARE_COMMIT = "f8941474f5e10f4c2d3764b1f12695501daa9b44"
SUMMARY_SHA256 = "7b40dbc2e4df1b0bc9adc91b8eac07ed388a57c2aad07bce29da2cb745be45a6"
GUARD_MERGE_COMMIT = "e1966f5fe20370aa841e16143eb05c94152ea8eb"


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


def test_candidate_score_path_ooc_summary_is_frozen_and_passing() -> None:
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
        "qualified_results_per_block": "447",
        "score_divider_lanes": "2",
        "coefficient_energy": "1073742825",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "0.633",
        "hold_whs_ns": "0.265",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "1968",
        "total_ffs": "1827",
        "ramb36e1": "2",
        "ramb18e1": "0",
        "dsp48e1": "4",
    }
    assert HDL_COMMIT in report
    assert HDL_COMMIT in plan
    assert SUMMARY_SHA256 in report
    assert "7,850 LUTs" in report
    assert "11,928" in plan
    assert "344 of 512" in report
    assert "+0.633 ns" in report


def test_candidate_score_path_contract_and_simulation_are_explicit() -> None:
    prefix = "hdl/library/starlink_pss_acquisition/"
    qualifier = _checkpoint_text(prefix + "starlink_pss_ifft_qualifier.v")
    energy_join = _checkpoint_text(prefix + "starlink_pss_energy_join.v")
    score_lanes = _checkpoint_text(prefix + "starlink_pss_score_lanes.v")
    score_path = _checkpoint_text(prefix + "starlink_pss_candidate_score_path.v")
    runner = _checkpoint_text(prefix + "run_tests.sh")
    integration_test = _checkpoint_text(
        prefix + "tb/tb_starlink_pss_candidate_score_path.sv"
    )
    integration_oracle = _checkpoint_text(
        prefix + "tb/generate_candidate_score_path_vectors.py"
    )
    score_oracle = _checkpoint_text(
        prefix + "tb/generate_score_pipeline_vectors.py"
    )

    assert "localparam integer INVALID_PREFIX_RESULTS = 65" in qualifier
    assert "input_ifft_index != expected_ifft_index" in qualifier
    assert "input_block_start_index != expected_next_block_start" in qualifier
    assert "protocol_fault <= 1'b1" in qualifier
    assert "orphan_response_now" in energy_join
    assert "cache_miss_now" in energy_join
    assert "index_mismatch_now" in energy_join
    assert "!response_fault_now" in energy_join
    assert score_lanes.count("starlink_pss_score_divider #(") == 2
    assert "if (input_accept)" in score_lanes
    assert "if (output_accept)" in score_lanes
    assert "lane_zero_output_ready = !output_lane_select" in score_lanes
    assert "starlink_pss_ifft_qualifier qualifier" in score_path
    assert "starlink_pss_raw_result_fifo result_fifo" in score_path
    assert "starlink_pss_energy_join energy_join" in score_path
    assert "starlink_pss_score_lanes score_lanes" in score_path
    assert "score_valid = lane_score_valid && !path_fault" in score_path
    assert "dense 512-result IFFT block was backpressured" in integration_test
    assert "CANDIDATE_SCORE_PATH_PASS" in integration_test
    assert (
        "missing energy did not fail closed before score publication"
        in integration_test
    )
    assert "def exact_score(" in integration_oracle
    assert "quotient, remainder = divmod(255 * numerator, denominator)" in score_oracle
    assert "tb_starlink_pss_candidate_score_path" in runner
    assert "tb_starlink_pss_score_pipeline" in runner


def test_candidate_score_path_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "ifft_qualifier_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_ifft_qualifier.v"
        ),
        "energy_join_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_energy_join.v"
        ),
        "score_lanes_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_lanes.v"
        ),
        "candidate_score_path_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_candidate_score_path.v"
        ),
        "raw_result_fifo_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_raw_result_fifo.v"
        ),
        "score_prepare_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_prepare.v"
        ),
        "score_divider_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v"
        ),
        "energy_cache_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_energy_cache.v"
        ),
        "ifft_qualifier_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_ifft_qualifier.sv"
        ),
        "energy_join_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_energy_join.sv"
        ),
        "score_lanes_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_score_lanes.sv"
        ),
        "score_pipeline_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_score_pipeline.sv"
        ),
        "score_pipeline_vector_generator_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/generate_score_pipeline_vectors.py"
        ),
        "candidate_score_path_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_candidate_score_path.sv"
        ),
        "candidate_score_path_vector_generator_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "generate_candidate_score_path_vectors.py"
        ),
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "candidate_score_path_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_candidate_score_path_ooc.sh"
        ),
        "candidate_score_path_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_candidate_score_path_ooc.xdc"
        ),
        "candidate_score_path_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "synthesize_candidate_score_path_ooc.tcl"
        ),
        "candidate_score_path_ooc_summary_sha256": (
            "reports/starlink-pss15-candidate-score-path-ooc-summary.txt"
        ),
        "candidate_score_path_report_sha256": (
            "reports/STARLINK_PSS15_CANDIDATE_SCORE_PATH_V1.md"
        ),
        "candidate_score_path_evidence_test_sha256": (
            "tests/test_starlink_candidate_score_path_evidence.py"
        ),
        "raw_fifo_historical_evidence_test_sha256": (
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
        "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/89"
        in manifest
    )
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "candidate_score_path_simulation_verdict: PASS" in manifest
    assert "candidate_score_path_ooc_verdict: PASS" in manifest
    assert "candidate_path_fifo_maximum_occupancy: 344" in manifest
    assert "rtl_ifft_qualifier_implemented: true" in manifest
    assert "rtl_energy_join_implemented: true" in manifest
    assert "rtl_two_lane_dispatch_implemented: true" in manifest
    assert "rtl_ordered_score_merge_implemented: true" in manifest
    assert "rtl_candidate_score_path_composed: true" in manifest
    assert "rtl_fft_instantiated: false" in manifest
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
