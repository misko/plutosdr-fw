from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
MANIFEST = (
    ROOT / "manifests" / "starlink-pss15-overlap-scheduler-dnm-v1-source.yaml"
)
REPORT = ROOT / "reports" / "STARLINK_PSS15_OVERLAP_SCHEDULER_V1.md"
SUMMARY = ROOT / "reports" / "starlink-pss15-overlap-scheduler-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
SUMMARY_SHA256 = (
    "37682496c3f6edcee513c6c775aa42e0a5837defd5da98b791eda88baa4a60b3"
)
HDL_COMMIT = "2c9e564350e1c42d9aa5b14e7ee61929a754f1fd"
FIRMWARE_COMMIT = "afc91c7bb280126e02140d9013b493d17be182e1"


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


def test_overlap_scheduler_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "fft_samples": "512",
        "overlap_samples": "65",
        "stride_samples": "447",
        "ring_samples": "2048",
        "descriptor_queue_depth": "4",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "2.012",
        "hold_whs_ns": "0.011",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "273",
        "total_ffs": "695",
        "ramb36e1": "2",
        "ramb18e1": "0",
        "dsp48e1": "0",
    }
    assert SUMMARY_SHA256 in report
    assert HDL_COMMIT in report
    assert HDL_COMMIT in plan
    assert "5,193 LUTs" in report
    assert "33 BRAM tiles" in plan


def test_overlap_scheduler_contract_and_tests_are_explicit() -> None:
    prefix = "hdl/library/starlink_pss_acquisition/"
    rtl = _checkpoint_text(prefix + "starlink_pss_overlap_scheduler.v")
    runner = _checkpoint_text(prefix + "run_tests.sh")
    lifecycle = _checkpoint_text(
        prefix + "tb/tb_starlink_pss_overlap_scheduler_lifecycle.sv"
    )

    assert "parameter integer FFT_SAMPLES = 512" in rtl
    assert "parameter integer OVERLAP_SAMPLES = 65" in rtl
    assert "parameter integer RING_SAMPLES = 2048" in rtl
    assert "parameter integer BLOCK_QUEUE_DEPTH = 4" in rtl
    assert 'ram_style = "block"' in rtl
    assert "sample_index != expected_sample_index" in rtl
    assert "write_pointer == earliest_required_pointer" in rtl
    assert "memory_read_enable = enable && !restart_segment && issue_read" in rtl
    assert "tb_starlink_pss_phase_map" in runner
    assert "tb_starlink_pss_overlap_scheduler" in runner
    assert "tb_starlink_pss_overlap_scheduler_lifecycle" in runner
    assert "queue_overflow_restart=1" in lifecycle
    assert "retention_overflow_restart=1" in lifecycle


def test_overlap_scheduler_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "scheduler_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_overlap_scheduler.v"
        ),
        "scheduler_default_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_overlap_scheduler.sv"
        ),
        "scheduler_lifecycle_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_overlap_scheduler_lifecycle.sv"
        ),
        "scheduler_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "run_overlap_scheduler_ooc.sh"
        ),
        "scheduler_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "starlink_pss_overlap_scheduler_ooc.xdc"
        ),
        "scheduler_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/"
            "synthesize_overlap_scheduler_ooc.tcl"
        ),
        "scheduler_ooc_summary_sha256": (
            "reports/starlink-pss15-overlap-scheduler-ooc-summary.txt"
        ),
        "scheduler_report_sha256": (
            "reports/STARLINK_PSS15_OVERLAP_SCHEDULER_V1.md"
        ),
        "historical_phase_map_test_sha256": (
            "tests/test_starlink_rx_only_contract.py"
        ),
        "historical_xfft_test_sha256": (
            "tests/test_starlink_xfft_bitacc_evidence.py"
        ),
    }

    assert "do_not_merge: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_required: true" in manifest
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/83" in manifest
    assert "scheduler_simulation_verdict: PASS" in manifest
    assert "scheduler_ooc_verdict: PASS" in manifest
    assert "rtl_overlap_scheduler_implemented: true" in manifest
    assert "rtl_score_frontend_implemented: false" in manifest
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
        "scheduler_evidence_test_sha256": (
            "tests/test_starlink_overlap_scheduler_evidence.py"
        ),
        "starlink_plan_sha256": "STARLINK_PSS_15_30_60_PLAN.md",
    }.items():
        digest = _sha256_bytes(_checkpoint_blob(relative))
        assert f"{field}: {digest}" in manifest
