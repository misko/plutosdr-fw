from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
MANIFEST = ROOT / "manifests/starlink-pss15-iq-to-score-xfft-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_IQ_TO_SCORE_XFFT_V1.md"
VECTOR_EVIDENCE = ROOT / "reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json"
SIMULATION_SUMMARY = (
    ROOT / "reports/starlink-pss15-iq-to-score-xfft-simulation-summary.txt"
)
OOC_SUMMARY = ROOT / "reports/starlink-pss15-iq-to-score-xfft-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"

HDL_COMMIT = "c6b55bd5e9afb2da293b2b08fb36cc0609586868"
GUARD_MERGE_COMMIT = "eb0fe23673e5318b42dbe9bf3e972cb9a0be217c"
VECTOR_EVIDENCE_SHA256 = (
    "6eaf98f478b1222042aca89e76828984f6bde6e486f0eacc06b5067f3b5d296d"
)
SIMULATION_SUMMARY_SHA256 = (
    "cb2526ba5b1fc464150df1801a6cdd7fb8280fa56b53264a1039d277293ec754"
)
OOC_SUMMARY_SHA256 = (
    "c958aa316e0cf3177f8134c3c885a6e54d4dee4a25837120d1eb6e084d2c8c24"
)
PLAN_HISTORICAL_SHA256 = (
    "43272b9a5e7a147c0e6e6366b6ef822a183ef8a8663995154b3794a4cb5e81b4"
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


def test_generated_xfft_vector_evidence_is_frozen_and_exact() -> None:
    evidence = json.loads(VECTOR_EVIDENCE.read_text())

    assert _sha256(VECTOR_EVIDENCE) == VECTOR_EVIDENCE_SHA256
    assert evidence["schema"] == "starlink-pss15-generated-xfft-pipeline-vectors-v1"
    assert evidence["oracle_schema"] == "starlink-xfft-bitacc-acquisition-v1"
    assert evidence["sample_rate_hz"] == 15_000_000
    assert evidence["acquisition_clock_hz"] == 100_000_000
    assert evidence["sample_count"] == 1406
    assert evidence["block_count"] == 3
    assert evidence["score_count"] == 1341
    assert evidence["valid_scores_per_block"] == 447
    assert evidence["pss_starts_relative"] == [100, 447, 1000]
    assert evidence["pss_scores"] == [255, 255, 255]
    assert evidence["forward_block_exponents"] == [5, 4, 4]
    assert evidence["inverse_block_exponents"] == [3, 4, 4]
    assert evidence["files"] == {
        "forward_exponents.mem": {
            "lines": 3,
            "sha256": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
        },
        "forward_q23.mem": {
            "lines": 1536,
            "sha256": "92240f871d3d59e66923e412d7d933fe9938438c6eabdd005182d2e8daf109cc",
        },
        "inverse_exponents.mem": {
            "lines": 3,
            "sha256": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
        },
        "inverse_q23.mem": {
            "lines": 1536,
            "sha256": "3fdebbc406d6cc3e9bfdc199820416c56fcde640777ee7cd7da0bc75078f8884",
        },
        "product_q23.mem": {
            "lines": 1536,
            "sha256": "63f6c4ba900b25d5cfc9ec8161765b8e9776e6711eedc94edef2d43d46a92615",
        },
        "samples_ci16.mem": {
            "lines": 1406,
            "sha256": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
        },
        "scores_u8.mem": {
            "lines": 1341,
            "sha256": "a8c5596bdea4f7a618082467e222c6088d589174bb69f96238df83def2ce02a0",
        },
    }


def test_generated_xfft_replay_and_whole_path_ooc_are_frozen() -> None:
    simulation = _summary(SIMULATION_SUMMARY)
    ooc = _summary(OOC_SUMMARY)
    report = REPORT.read_text()

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
        "blocks": "3",
        "forward_bins_checked": "1536",
        "product_bins_checked": "1536",
        "inverse_bins_checked": "1536",
        "scores_checked": "1341",
        "pss_full_scale_scores": "3",
        "maximum_candidate_fifo_count": "345",
        "score_backpressure_checked": "true",
        "global_fault_quarantine_recovery_checked": "true",
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
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "0.099",
        "hold_whs_ns": "0.011",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "7340",
        "total_ffs": "11362",
        "ramb36e1": "6",
        "ramb18e1": "25",
        "bram_tiles": "18.5",
        "dsp48e1": "32",
    }
    assert HDL_COMMIT in report
    assert GUARD_MERGE_COMMIT in report
    assert VECTOR_EVIDENCE_SHA256 in report
    assert SIMULATION_SUMMARY_SHA256 in report
    assert OOC_SUMMARY_SHA256 in report
    assert "+0.099 ns" in report
    assert "+0.011 ns" in report
    assert "7,340" in report
    assert "11,362" in report


def test_checkpoint_tree_contains_real_generated_xfft_composition() -> None:
    top = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_iq_to_score.v"
    ).decode()
    join = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/starlink_pss_forward_kernel_join.v"
    ).decode()
    testbench = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/tb/tb_starlink_pss_iq_to_score_xfft.sv"
    ).decode()
    simulation_tcl = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/simulate_iq_to_score_xfft.tcl"
    ).decode()
    synthesis_tcl = _hdl_at_checkpoint(
        "library/starlink_pss_acquisition/synthesize_iq_to_score_xfft_ooc.tcl"
    ).decode()

    assert "module starlink_pss_iq_to_score" in top
    assert "starlink_pss_fft512_bfp24 forward_xfft" in top
    assert "starlink_pss_fft512_bfp24 inverse_xfft" in top
    assert "starlink_pss_forward_kernel_join" in top
    assert "starlink_pss_candidate_score_path" in top
    assert "assign pipeline_resetn = resetn && effective_enable" in top
    assert "output reg                     detector_fault" in top
    assert "module starlink_pss_forward_kernel_join" in join
    assert "starlink_pss_kernel_rom" in join
    assert "force dut.forward_adapter.protocol_fault = 1'b1" in testbench
    assert "global_fault_recovery=1" in testbench
    assert "create_ip -name xfft -vendor xilinx.com -library ip -version 9.1" in simulation_tcl
    assert "launch_simulation -simset sim_1 -mode behavioral" in simulation_tcl
    assert "open_run synth_1" in synthesis_tcl
    assert "opt_design" in synthesis_tcl
    assert "methodology violation" in synthesis_tcl


def test_checkpoint_manifest_is_safe_and_binds_immutable_evidence() -> None:
    manifest = MANIFEST.read_text()
    current_bound_files = {
        "pipeline_vector_generator_sha256": (
            "tools/generate_starlink_pss15_pipeline_vectors.py"
        ),
        "pipeline_vector_test_sha256": "tests/test_starlink_pss15_pipeline_vectors.py",
        "pipeline_simulation_runner_sha256": (
            "run_starlink_pss15_iq_to_score_xfft.sh"
        ),
        "pipeline_ooc_runner_sha256": "run_starlink_pss15_iq_to_score_xfft_ooc.sh",
        "pipeline_vector_evidence_sha256": (
            "reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json"
        ),
        "pipeline_simulation_summary_sha256": (
            "reports/starlink-pss15-iq-to-score-xfft-simulation-summary.txt"
        ),
        "pipeline_ooc_summary_sha256": (
            "reports/starlink-pss15-iq-to-score-xfft-ooc-summary.txt"
        ),
        "pipeline_report_sha256": "reports/STARLINK_PSS15_IQ_TO_SCORE_XFFT_V1.md",
        "pipeline_evidence_test_sha256": (
            "tests/test_starlink_iq_to_score_xfft_evidence.py"
        ),
    }
    checkpoint_bound_files = {
        "iq_to_score_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_iq_to_score.v"
        ),
        "forward_kernel_join_rtl_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_forward_kernel_join.v"
        ),
        "forward_kernel_join_testbench_sha256": (
            "library/starlink_pss_acquisition/tb/tb_starlink_pss_forward_kernel_join.sv"
        ),
        "iq_to_score_testbench_sha256": (
            "library/starlink_pss_acquisition/tb/tb_starlink_pss_iq_to_score_xfft.sv"
        ),
        "iq_to_score_simulation_tcl_sha256": (
            "library/starlink_pss_acquisition/simulate_iq_to_score_xfft.tcl"
        ),
        "iq_to_score_ooc_tcl_sha256": (
            "library/starlink_pss_acquisition/synthesize_iq_to_score_xfft_ooc.tcl"
        ),
        "iq_to_score_ooc_xdc_sha256": (
            "library/starlink_pss_acquisition/starlink_pss_iq_to_score_xfft_ooc.xdc"
        ),
        "upper_edge_kernel_memory_sha256": (
            "library/starlink_pss_acquisition/tb/upper_edge_pss_kernel_q23.mem"
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
    assert (
        "submodule_hdl_ref: refs/tags/starlink-rx-only-dnm-v1-source/"
        "hdl-pss15-iq-to-score-xfft-v1" in manifest
    )
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/92" in manifest
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "generated_xfft_replay_verdict: PASS" in manifest
    assert "iq_to_score_ooc_verdict: PASS" in manifest
    assert "rtl_fft_instantiated: true" in manifest
    assert "rtl_coefficient_rom_packaged: true" in manifest
    assert "rtl_raw_iq_to_score_complete: true" in manifest
    assert "rtl_phase_map_connected_to_score_path: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    assert f"starlink_plan_historical_sha256: {PLAN_HISTORICAL_SHA256}" in manifest
    for field, relative in current_bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    for field, relative in checkpoint_bound_files.items():
        assert f"{field}: {_sha256_bytes(_hdl_at_checkpoint(relative))}" in manifest
    assert HDL_COMMIT in PLAN.read_text()
