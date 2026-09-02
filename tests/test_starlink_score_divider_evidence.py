from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "starlink-pss15-score-divider-dnm-v1-source.yaml"
REPORT = ROOT / "reports" / "STARLINK_PSS15_SCORE_DIVIDER_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-score-divider-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "8755d94eefb65cba6155a28c8a4c9c3f2ec69e41"
SUMMARY_SHA256 = "01be7ab19505f349e420825a412cb73038609ab3a4b96d0f12471e3469610374"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_score_divider_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "ratio_bits": "69",
        "score_bits": "8",
        "restoring_iterations": "8",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "0.962",
        "hold_whs_ns": "0.284",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "599",
        "total_ffs": "378",
        "ramb36e1": "0",
        "ramb18e1": "0",
        "dsp48e1": "0",
    }
    assert HDL_COMMIT in report
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in plan
    assert "7,080 LUTs" in report
    assert "22.22 million scores/s" in plan


def test_score_divider_contract_and_simulation_are_explicit() -> None:
    rtl = (
        ROOT / "hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v"
    ).read_text()
    testbench = (
        ROOT / "hdl/library/starlink_pss_acquisition/tb/"
        "tb_starlink_pss_score_divider.sv"
    ).read_text()
    generator = (
        ROOT / "hdl/library/starlink_pss_acquisition/tb/"
        "generate_score_divider_vectors.py"
    ).read_text()
    runner = (ROOT / "hdl/library/starlink_pss_acquisition/run_tests.sh").read_text()

    assert "parameter integer RATIO_BITS = 69" in rtl
    assert "parameter integer SCORE_BITS = 8" in rtl
    assert "input_scaled_by_score_max" in rtl
    assert "doubled_remainder == denominator_extended" in rtl
    assert "next_quotient[0]" in rtl
    assert "iteration <= SCORE_BITS - 1" in rtl
    assert "output changed while stalled" in testbench
    assert "mid-calculation flush did not clear the lane" in testbench
    assert "SCORE_DIVIDER_PASS" in testbench
    assert "rng = random.Random(0x50535308)" in generator
    assert "divmod(numerator * SCORE_MAX, denominator)" in generator
    assert "tb_starlink_pss_score_divider" in runner


def test_score_divider_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "score_divider_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v"
        ),
        "score_divider_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_score_divider.sv"
        ),
        "score_divider_vector_generator_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/generate_score_divider_vectors.py"
        ),
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "score_divider_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_score_divider_ooc.sh"
        ),
        "score_divider_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_divider_ooc.xdc"
        ),
        "score_divider_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/synthesize_score_divider_ooc.tcl"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "score_divider_ooc_summary_sha256": (
            "reports/starlink-pss15-score-divider-ooc-summary.txt"
        ),
        "score_divider_report_sha256": ("reports/STARLINK_PSS15_SCORE_DIVIDER_V1.md"),
        "score_divider_evidence_test_sha256": (
            "tests/test_starlink_score_divider_evidence.py"
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
        "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/86"
        in manifest
    )
    assert (
        "firmware_main_gitlink_guard_merge_commit: "
        "0c6f96ef4d95426da4c62a4b30828e5535b7b5c4" in manifest
    )
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "score_divider_simulation_verdict: PASS" in manifest
    assert "score_divider_ooc_verdict: PASS" in manifest
    assert "rtl_score_divider_lane_implemented: true" in manifest
    assert "rtl_score_preprocessor_implemented: false" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
