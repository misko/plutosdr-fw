from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT / "manifests" / "starlink-pss15-spectrum-product-dnm-v1-source.yaml"
)
REPORT = ROOT / "reports" / "STARLINK_PSS15_SPECTRUM_PRODUCT_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-spectrum-product-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "5b2cdd3ba81e98ab3f752f334a34054d0b48f237"
SUMMARY_SHA256 = (
    "4939369a6d6f2e10e98b0583c6efaa76f18feb6feac1df271f60b11aa48f5ac4"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_spectrum_product_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "component_width": "24",
        "fraction_bits": "23",
        "product_safety_shift": "1",
        "rounding": "nearest_ties_even",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "2.362",
        "hold_whs_ns": "0.284",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "220",
        "total_ffs": "456",
        "ramb36e1": "0",
        "ramb18e1": "0",
        "dsp48e1": "8",
    }
    assert HDL_COMMIT in report
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in plan
    assert "5,413 LUTs" in report
    assert "26 DSPs" in plan


def test_spectrum_product_contract_and_replay_are_explicit() -> None:
    rtl = (
        ROOT
        / "hdl/library/starlink_pss_acquisition/"
        "starlink_pss_spectrum_product.v"
    ).read_text()
    generator = (
        ROOT
        / "hdl/library/starlink_pss_acquisition/tb/"
        "generate_spectrum_product_vectors.py"
    ).read_text()
    testbench = (
        ROOT
        / "hdl/library/starlink_pss_acquisition/tb/"
        "tb_starlink_pss_spectrum_product.sv"
    ).read_text()
    runner = (
        ROOT / "hdl/library/starlink_pss_acquisition/run_tests.sh"
    ).read_text()

    assert "localparam integer ROUND_SHIFT = 24" in rtl
    assert "use_dsp" in rtl
    assert "round_and_saturate" in rtl
    assert "quotient[0]" in rtl
    assert "input_ready = resetn && !flush && product_stage_ready" in rtl
    assert "output_stage_ready = !output_valid || output_ready" in rtl
    assert "random.Random(0x50535324)" in generator
    assert "round_shift_ties_even" in generator
    assert "--random-count" in generator
    assert "output changed while stalled" in testbench
    assert "flush did not invalidate stalled output" in testbench
    assert "bit-exact complex product mismatch" in testbench
    assert "generate_spectrum_product_vectors.py" in runner
    assert "tb_starlink_pss_spectrum_product" in runner


def test_spectrum_product_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "spectrum_product_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_spectrum_product.v"
        ),
        "spectrum_product_vector_generator_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "generate_spectrum_product_vectors.py"
        ),
        "spectrum_product_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_spectrum_product.sv"
        ),
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "spectrum_product_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "run_spectrum_product_ooc.sh"
        ),
        "spectrum_product_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_spectrum_product_ooc.xdc"
        ),
        "spectrum_product_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "synthesize_spectrum_product_ooc.tcl"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "spectrum_product_ooc_summary_sha256": (
            "reports/starlink-pss15-spectrum-product-ooc-summary.txt"
        ),
        "spectrum_product_report_sha256": (
            "reports/STARLINK_PSS15_SPECTRUM_PRODUCT_V1.md"
        ),
        "spectrum_product_evidence_test_sha256": (
            "tests/test_starlink_spectrum_product_evidence.py"
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
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/84" in manifest
    assert (
        "firmware_main_gitlink_guard_merge_commit: "
        "60169ef8c35cca1ce18c062625141c78a4bb2d3b" in manifest
    )
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "spectrum_product_simulation_verdict: PASS" in manifest
    assert "spectrum_product_ooc_verdict: PASS" in manifest
    assert "rtl_spectrum_product_implemented: true" in manifest
    assert "rtl_score_frontend_implemented: false" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
