from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT / "manifests" / "starlink-pss15-energy-cache-dnm-v1-source.yaml"
)
REPORT = ROOT / "reports" / "STARLINK_PSS15_ENERGY_CACHE_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-energy-cache-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
HDL_COMMIT = "8282a4a7b2aef1ff05f40f2342cca71e20521fd5"
SUMMARY_SHA256 = (
    "f0720542c1f2dddb86b1717ecb4d0b6b76d61ec431c2b6d4f1688c59f3ae456c"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_energy_cache_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "window_samples": "66",
        "cache_entries": "2048",
        "energy_bits": "38",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "1.960",
        "hold_whs_ns": "0.056",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "469",
        "total_ffs": "534",
        "ramb36e1": "2",
        "ramb18e1": "1",
        "dsp48e1": "2",
    }
    assert HDL_COMMIT in report
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in plan
    assert "5,882 LUTs" in report
    assert "35.5 BRAM tiles" in plan


def test_energy_cache_contract_and_simulation_are_explicit() -> None:
    rtl = (
        ROOT
        / "hdl/library/starlink_pss_acquisition/"
        "starlink_pss_energy_cache.v"
    ).read_text()
    testbench = (
        ROOT
        / "hdl/library/starlink_pss_acquisition/tb/"
        "tb_starlink_pss_energy_cache.sv"
    ).read_text()
    runner = (
        ROOT / "hdl/library/starlink_pss_acquisition/run_tests.sh"
    ).read_text()

    assert "parameter integer WINDOW_SAMPLES = 66" in rtl
    assert "parameter integer CACHE_ENTRIES = 2048" in rtl
    assert 'ram_style = "block"' in rtl
    assert 'ram_style = "distributed"' in rtl
    assert rtl.count('use_dsp = "yes"') == 2
    assert "sample_index != expected_sample_index" in rtl
    assert "lookup_hits_new_energy" in rtl
    assert "lookup_overwrite_collision" in rtl
    assert "energy_read_data <= energy_memory[lookup_address]" in rtl
    assert "lookup output changed while stalled" in testbench
    assert "same-cycle newest-energy bypass mismatch" in testbench
    assert "gap did not invalidate stalled lookup response" in testbench
    assert "ENERGY_CACHE_PASS" in testbench
    assert "tb_starlink_pss_energy_cache" in runner


def test_energy_cache_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "energy_cache_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_energy_cache.v"
        ),
        "energy_cache_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_energy_cache.sv"
        ),
        "acquisition_test_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_tests.sh"
        ),
        "energy_cache_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_energy_cache_ooc.sh"
        ),
        "energy_cache_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_energy_cache_ooc.xdc"
        ),
        "energy_cache_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "synthesize_energy_cache_ooc.tcl"
        ),
        "acquisition_hdl_readme_sha256": (
            "hdl/library/starlink_pss_acquisition/README.md"
        ),
        "energy_cache_ooc_summary_sha256": (
            "reports/starlink-pss15-energy-cache-ooc-summary.txt"
        ),
        "energy_cache_report_sha256": (
            "reports/STARLINK_PSS15_ENERGY_CACHE_V1.md"
        ),
        "energy_cache_evidence_test_sha256": (
            "tests/test_starlink_energy_cache_evidence.py"
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
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/85" in manifest
    assert (
        "firmware_main_gitlink_guard_merge_commit: "
        "dfe129b6eed7c7d9adbe4bd1d5451442284dce81" in manifest
    )
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "energy_cache_simulation_verdict: PASS" in manifest
    assert "energy_cache_ooc_verdict: PASS" in manifest
    assert "rtl_energy_cache_implemented: true" in manifest
    assert "rtl_score_frontend_implemented: false" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
