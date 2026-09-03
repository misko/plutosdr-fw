from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
MANIFEST = (
    ROOT / "manifests/starlink-pss15-iq-to-phase-map-xfft-dnm-v1-source.yaml"
)
REPORT = ROOT / "reports/STARLINK_PSS15_IQ_TO_PHASE_MAP_XFFT_V1.md"
VECTOR_EVIDENCE = ROOT / "reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json"
SIMULATION_SUMMARY = (
    ROOT / "reports/starlink-pss15-iq-to-phase-map-xfft-simulation-summary.txt"
)
OOC_SUMMARY = ROOT / "reports/starlink-pss15-iq-to-phase-map-xfft-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"

HDL_COMMIT = "c85a88109ef68020c5d318e045b7ad91660a8960"
HDL_TAG = "starlink-rx-only-dnm-v1-source/hdl-pss15-iq-to-phase-map-v2"
GUARD_MERGE_COMMIT = "f0161837c11c39acb81fa7c45a3714d2dd4d2321"
VECTOR_EVIDENCE_SHA256 = (
    "6eaf98f478b1222042aca89e76828984f6bde6e486f0eacc06b5067f3b5d296d"
)
SIMULATION_SUMMARY_SHA256 = (
    "9c819b7128f60bf19ae623741d4a0cd0008ce0f4d7ab989f4ba81d3da2cfda24"
)
OOC_SUMMARY_SHA256 = (
    "92af1c40a05c64cf5181d0f66492cd1b3da45654c6bc7b6953d3f8738a48dd9d"
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


def test_exact_map_replay_and_default_geometry_ooc_are_frozen() -> None:
    simulation = _summary(SIMULATION_SUMMARY)
    ooc = _summary(OOC_SUMMARY)
    report = REPORT.read_text()

    assert _sha256(VECTOR_EVIDENCE) == VECTOR_EVIDENCE_SHA256
    assert _sha256(SIMULATION_SUMMARY) == SIMULATION_SUMMARY_SHA256
    assert _sha256(OOC_SUMMARY) == OOC_SUMMARY_SHA256
    assert simulation == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "xfft_version": "9.1",
        "xfft_architecture": "radix_4_burst",
        "xfft_instances": "2",
        "sample_rate_msps": "15",
        "acquisition_clock_mhz": "100",
        "samples": "1406",
        "scores_checked": "1341",
        "replay_phase_bins": "447",
        "replay_tile_frames": "3",
        "exact_map_reads": "447",
        "map_peak_phase": "0",
        "map_peak_value": "264",
        "bounded_handoff_bytes": "894",
        "map_publish_count": "1",
        "discarded_score_count": "0",
        "discontinuity_abort_count": "0",
        "score_protocol_error_count": "0",
        "score_phase_index_discontinuity_count": "0",
        "verdict": "PASS",
    }
    assert ooc == {
        "vivado_version": "2022.2",
        "xfft_version": "9.1",
        "part": "xc7z010clg400-1",
        "xfft_instances": "2",
        "xfft_architecture": "radix_4_burst",
        "sample_rate_msps": "15",
        "acquisition_clock_mhz": "100",
        "phase_bins": "20000",
        "tile_frames": "64",
        "bounded_map_bytes": "40000",
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "0.364",
        "hold_whs_ns": "0.011",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "8018",
        "total_ffs": "12290",
        "ramb36e1": "26",
        "ramb18e1": "25",
        "bram_tiles": "38.5",
        "dsp48e1": "32",
    }
    assert HDL_COMMIT in report
    assert GUARD_MERGE_COMMIT in report
    assert VECTOR_EVIDENCE_SHA256 in report
    assert SIMULATION_SUMMARY_SHA256 in report
    assert OOC_SUMMARY_SHA256 in report
    assert "+0.364 ns" in report
    assert "+0.011 ns" in report
    assert "8,018" in report
    assert "12,290" in report
    assert "468.75 kB/s" in report
    assert "establish PSS frame lock" in report


def test_checkpoint_tree_composes_score_phase_and_bounded_map() -> None:
    top = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_iq_to_phase_map.v"
    ).decode()
    tagger = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_score_phase_tagger.v"
    ).decode()
    scorer = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_iq_to_score.v"
    ).decode()
    fifo = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_raw_result_fifo.v"
    ).decode()
    testbench = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/tb/"
        "tb_starlink_pss_iq_to_phase_map_xfft.sv"
    ).decode()
    simulation_tcl = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/simulate_iq_to_phase_map_xfft.tcl"
    ).decode()
    synthesis_tcl = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/"
        "synthesize_iq_to_phase_map_xfft_ooc.tcl"
    ).decode()

    assert "module starlink_pss_iq_to_phase_map" in top
    assert "starlink_pss_iq_to_score" in top
    assert ".score_ready                         (1'b1)" in top
    assert "starlink_pss_score_phase_tagger" in top
    assert "starlink_pss_phase_map" in top
    assert "reg map_score_valid;" in top
    assert ".score_valid                  (map_score_valid)" in top
    assert "module starlink_pss_score_phase_tagger" in tagger
    assert "score_start_index == expected_score_index" in tagger
    assert "assign index_discontinuity_pulse = index_discontinuity" in tagger
    assert "reg pipeline_active;" in scorer
    assert "assign pipeline_resetn = pipeline_active;" in scorer
    assert "current_stored_count < FIFO_DEPTH || output_accept" in fifo
    assert "assign inverse_output_ready = 1'b1;" in scorer
    assert "candidate_backpressure_fault" in scorer
    assert "expected_scores[phase_index + 2 * PHASE_BINS]" in testbench
    assert "exact_map_reads=%0d" in testbench
    assert "create_ip -name xfft -vendor xilinx.com -library ip -version 9.1" in simulation_tcl
    assert "launch_simulation -simset sim_1 -mode behavioral" in simulation_tcl
    assert "phase_bins=20000" in synthesis_tcl
    assert "tile_frames=64" in synthesis_tcl
    assert "bounded_map_bytes=40000" in synthesis_tcl
    assert "100 MHz post-opt timing failed" in synthesis_tcl

    peeled_tag = subprocess.run(
        ["git", "-C", str(HDL), "rev-parse", f"{HDL_TAG}^{{}}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert peeled_tag == HDL_COMMIT


def test_checkpoint_manifest_is_safe_and_binds_immutable_evidence() -> None:
    manifest = MANIFEST.read_text()
    current_bound_files = {
        "pipeline_vector_evidence_sha256": (
            "reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json"
        ),
        "phase_map_simulation_summary_sha256": (
            "reports/starlink-pss15-iq-to-phase-map-xfft-simulation-summary.txt"
        ),
        "phase_map_ooc_summary_sha256": (
            "reports/starlink-pss15-iq-to-phase-map-xfft-ooc-summary.txt"
        ),
        "phase_map_simulation_runner_sha256": (
            "run_starlink_pss15_iq_to_phase_map_xfft.sh"
        ),
        "phase_map_ooc_runner_sha256": (
            "run_starlink_pss15_iq_to_phase_map_xfft_ooc.sh"
        ),
        "phase_map_report_sha256": (
            "reports/STARLINK_PSS15_IQ_TO_PHASE_MAP_XFFT_V1.md"
        ),
        "phase_map_evidence_test_sha256": (
            "tests/test_starlink_iq_to_phase_map_xfft_evidence.py"
        ),
    }
    checkpoint_bound_files = {
        "iq_to_phase_map_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_iq_to_phase_map.v"
        ),
        "score_phase_tagger_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_score_phase_tagger.v"
        ),
        "iq_to_score_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_iq_to_score.v"
        ),
        "raw_result_fifo_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_raw_result_fifo.v"
        ),
        "iq_to_phase_map_testbench_sha256": (
            "library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_iq_to_phase_map_xfft.sv"
        ),
        "score_phase_tagger_testbench_sha256": (
            "library/starlink_pss_acquisition/tb/"
            "tb_starlink_pss_score_phase_tagger.sv"
        ),
        "iq_to_phase_map_simulation_tcl_sha256": (
            "library/starlink_pss_acquisition/simulate_iq_to_phase_map_xfft.tcl"
        ),
        "iq_to_phase_map_ooc_tcl_sha256": (
            "library/starlink_pss_acquisition/"
            "synthesize_iq_to_phase_map_xfft_ooc.tcl"
        ),
        "iq_to_phase_map_ooc_xdc_sha256": (
            "library/starlink_pss_acquisition/"
            "starlink_pss_iq_to_phase_map_xfft_ooc.xdc"
        ),
        "acquisition_test_runner_sha256": (
            "library/starlink_pss_acquisition/run_tests.sh"
        ),
        "acquisition_readme_sha256": (
            "library/starlink_pss_acquisition/README.md"
        ),
    }

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
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/94" in manifest
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "generated_xfft_phase_map_replay_verdict: PASS" in manifest
    assert "iq_to_phase_map_ooc_verdict: PASS" in manifest
    assert "inverse_xfft_output_backpressure: false" in manifest
    assert "candidate_backpressure_violation_fail_closed: true" in manifest
    assert "rtl_phase_map_connected_to_score_path: true" in manifest
    assert "rtl_bounded_map_handoff_complete: true" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "frame_alignment_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in current_bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    for field, relative in checkpoint_bound_files.items():
        assert f"{field}: {_sha256_bytes(_hdl_at_checkpoint(relative))}" in manifest
    assert HDL_COMMIT in PLAN.read_text()
