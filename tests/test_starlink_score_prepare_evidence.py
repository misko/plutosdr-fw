from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
MANIFEST = ROOT / "manifests" / "starlink-pss15-score-prepare-dnm-v1-source.yaml"
REPORT = ROOT / "reports" / "STARLINK_PSS15_SCORE_PREPARE_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-score-prepare-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "078e725389c8c790e1f3c3c612b242697f87de77"
FIRMWARE_COMMIT = "801dd4557f6e5c722b529255fbf3dd5ed0bde9d7"
SUMMARY_SHA256 = "b2f50c5122f2341e3569844e902e488943ac763507e04300d1e5c1e495ac6311"


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


def test_score_prepare_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "correlation_component_bits": "24",
        "sample_energy_bits": "38",
        "coefficient_energy": "1073742825",
        "ratio_bits": "69",
        "pipeline_stages": "3",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "0.396",
        "hold_whs_ns": "0.269",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "561",
        "total_ffs": "581",
        "ramb36e1": "0",
        "ramb18e1": "0",
        "dsp48e1": "4",
    }
    assert HDL_COMMIT in report
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in plan
    assert "7,641 LUTs" in report
    assert "32 DSPs" in plan
    assert "1073776498" in report


def test_score_prepare_contract_and_simulation_are_explicit() -> None:
    prefix = "hdl/library/starlink_pss_acquisition/"
    rtl = _checkpoint_text(prefix + "starlink_pss_score_prepare.v")
    testbench = _checkpoint_text(prefix + "tb/tb_starlink_pss_score_prepare.sv")
    generator = _checkpoint_text(prefix + "tb/generate_score_prepare_vectors.py")
    runner = _checkpoint_text(prefix + "run_tests.sh")

    assert "COEFFICIENT_ENERGY = 31'd1073742825" in rtl
    assert rtl.count('use_dsp = "yes"') == 2
    assert 'use_dsp = "no"' in rtl
    assert "product_square_i + product_square_q" in rtl
    assert "sum_power_shift >= RATIO_BITS" in rtl
    assert "{RATIO_BITS{1'b1}}" in rtl
    assert "input_sample_energy * COEFFICIENT_ENERGY" in rtl
    assert "output changed while stalled" in testbench
    assert "pipeline flush published a partial ratio" in testbench
    assert "SCORE_PREPARE_PASS" in testbench
    assert "random.Random(0x50535369)" in generator
    assert "mathematical_numerator = power << power_shift" in generator
    assert "generate_score_prepare_vectors.py" in runner
    assert "tb_starlink_pss_score_prepare" in runner


def test_score_prepare_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "score_prepare_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_prepare.v"
        ),
        "score_prepare_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_score_prepare.sv"
        ),
        "score_prepare_vector_generator_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/generate_score_prepare_vectors.py"
        ),
        "score_prepare_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_score_prepare_ooc.sh"
        ),
        "score_prepare_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_score_prepare_ooc.xdc"
        ),
        "score_prepare_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/synthesize_score_prepare_ooc.tcl"
        ),
        "score_prepare_ooc_summary_sha256": (
            "reports/starlink-pss15-score-prepare-ooc-summary.txt"
        ),
        "score_prepare_report_sha256": ("reports/STARLINK_PSS15_SCORE_PREPARE_V1.md"),
    }

    assert "do_not_merge: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_required: true" in manifest
    assert (
        "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/87"
        in manifest
    )
    assert (
        "firmware_main_gitlink_guard_merge_commit: "
        "bfb0247a374724efde0589dcb259bb1396cf4abd" in manifest
    )
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "score_prepare_simulation_verdict: PASS" in manifest
    assert "score_prepare_ooc_verdict: PASS" in manifest
    assert "score_prepare_template_edge: upper" in manifest
    assert "score_prepare_lower_edge_parameter_override_qualified: false" in manifest
    assert "rtl_score_divider_lane_implemented: true" in manifest
    assert "rtl_score_preprocessor_implemented: true" in manifest
    assert "rtl_raw_result_fifo_implemented: false" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        digest = _sha256_bytes(_checkpoint_blob(relative))
        assert f"{field}: {digest}" in manifest

    for field, relative in {
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "score_prepare_evidence_test_sha256": (
            "tests/test_starlink_score_prepare_evidence.py"
        ),
        "starlink_plan_sha256": "STARLINK_PSS_15_30_60_PLAN.md",
    }.items():
        digest = _sha256_bytes(_checkpoint_blob(relative))
        assert f"{field}: {digest}" in manifest
