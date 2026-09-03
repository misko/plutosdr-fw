from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "hdl/library/starlink_pss_acquisition"
MANIFEST = ROOT / "manifests/starlink-pss15-kernel-rom-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_KERNEL_ROM_V1.md"
SUMMARY = ROOT / "reports/starlink-pss15-kernel-rom-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
MEMORY = ACQUISITION / "tb/upper_edge_pss_kernel_q23.mem"
HDL_COMMIT = "a7985ea3ab5b5b867caf8a34f72601c816874041"
CANONICAL_SHA256 = "d96c56b3d6bcd03419a57f23f3ce4929f1e478663119f5cb5ec9b14327b7ff2b"
MEMORY_SHA256 = "7c89ff2a026f5fab91e655ab969ac07c11bf9715215173dadec07084527aea7d"
SUMMARY_SHA256 = "a0129ef6fc12c441fd8562ddd24dd98399f0b25075157702ac88b4360b36d32d"
GUARD_MERGE_COMMIT = "250fc46cc57f38aec6a8321990f84460fb73d749"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signed_q23(value: int) -> int:
    return value - (1 << 24) if value & (1 << 23) else value


def test_kernel_memory_has_exact_independent_identity() -> None:
    raw = MEMORY.read_bytes()
    lines = raw.decode("ascii").splitlines()
    canonical = bytearray()
    coefficients: list[int] = []

    assert len(lines) == 512
    for line in lines:
        assert len(line) == 12
        assert all(character in "0123456789abcdef" for character in line)
        word = int(line, 16)
        coefficient_i = _signed_q23(word & 0xFFFFFF)
        coefficient_q = _signed_q23((word >> 24) & 0xFFFFFF)
        coefficients.extend((coefficient_i, coefficient_q))
        canonical.extend(struct.pack("<ii", coefficient_i, coefficient_q))

    assert hashlib.sha256(canonical).hexdigest() == CANONICAL_SHA256
    assert hashlib.sha256(raw).hexdigest() == MEMORY_SHA256
    assert min(coefficients) == -4727221
    assert max(coefficients) == 5434212


def test_kernel_rom_ooc_summary_is_frozen_and_passing() -> None:
    summary = dict(
        line.split("=", 1) for line in SUMMARY.read_text().splitlines() if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert summary == {
        "vivado_version": "2022.2",
        "part": "xc7z010clg400-1",
        "kernel_bins": "512",
        "kernel_format": "signed_q1_23",
        "memory_word_format": "q_then_i_48_bits",
        "canonical_binary_sha256": CANONICAL_SHA256,
        "memory_text_sha256": MEMORY_SHA256,
        "clock_period_ns": "10.000",
        "timing_scope": "post_opt_unplaced",
        "setup_wns_ns": "3.634",
        "hold_whs_ns": "0.056",
        "methodology_violations": "0",
        "check_timing_nonzero_categories": "0",
        "total_luts": "88",
        "total_ffs": "229",
        "ramb36e1": "0",
        "ramb18e1": "2",
        "bram_tiles": "1.0",
        "nonzero_init_words": "128",
        "dsp48e1": "0",
    }
    assert HDL_COMMIT in report
    assert HDL_COMMIT in plan
    assert CANONICAL_SHA256 in report
    assert MEMORY_SHA256 in report
    assert SUMMARY_SHA256 in report
    assert "+3.634 ns" in report
    assert "+0.056 ns" in report
    assert "8,144 LUTs" in report
    assert "12,379 registers" in plan


def test_kernel_rom_contract_and_simulation_are_explicit() -> None:
    rom = (ACQUISITION / "starlink_pss_kernel_rom.v").read_text()
    verifier = (ACQUISITION / "tb/verify_upper_edge_pss_kernel.py").read_text()
    testbench = (ACQUISITION / "tb/tb_starlink_pss_kernel_rom.sv").read_text()
    runner = (ACQUISITION / "run_tests.sh").read_text()
    ooc_gate = (ACQUISITION / "synthesize_kernel_rom_ooc.tcl").read_text()

    assert 'parameter ROM_FILE = "upper_edge_pss_kernel_q23.mem"' in rom
    assert '(* rom_style = "block" *) reg [47:0] kernel_memory [0:511]' in rom
    assert "output_kernel_word <= kernel_memory[input_bin_index]" in rom
    assert "input_bin_index != expected_bin_index" in rom
    assert "input_last != (expected_bin_index == 9'd511)" in rom
    assert "input_block_exponent != block_exponent" in rom
    assert "input_block_start_index != expected_next_block_start" in rom
    assert "protocol_fault <= 1'b1" in rom
    assert CANONICAL_SHA256 in verifier
    assert MEMORY_SHA256 in verifier
    assert "longest_accept_run < 512" in testbench
    assert 'expect_fault(1\'b1, 1\'b0, "wrong first bin")' in testbench
    assert 'expect_fault(1\'b1, 1\'b0, "early TLAST")' in testbench
    assert 'expect_fault(1\'b0, 1\'b1, "changed exponent")' in testbench
    assert 'expect_fault(1\'b0, 1\'b1, "changed block start")' in testbench
    assert 'expect_fault(1\'b0, 1\'b1, "wrong next-block stride")' in testbench
    assert "KERNEL_ROM_PASS" in testbench
    assert "tb_starlink_pss_kernel_rom" in runner
    assert "exactly two RAMB18 and no RAMB36/DSP" in ooc_gate
    assert "inferred RAMB18 has no nonzero INIT payload" in ooc_gate
    assert "100 MHz post-opt timing failed" in ooc_gate


def test_kernel_rom_manifest_is_safe_and_binds_sources() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "kernel_rom_rtl_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_kernel_rom.v"
        ),
        "kernel_memory_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/upper_edge_pss_kernel_q23.mem"
        ),
        "kernel_verifier_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/verify_upper_edge_pss_kernel.py"
        ),
        "kernel_rom_testbench_sha256": (
            "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_kernel_rom.sv"
        ),
        "kernel_rom_ooc_runner_sha256": (
            "hdl/library/starlink_pss_acquisition/run_kernel_rom_ooc.sh"
        ),
        "kernel_rom_ooc_xdc_sha256": (
            "hdl/library/starlink_pss_acquisition/starlink_pss_kernel_rom_ooc.xdc"
        ),
        "kernel_rom_ooc_tcl_sha256": (
            "hdl/library/starlink_pss_acquisition/synthesize_kernel_rom_ooc.tcl"
        ),
        "kernel_rom_ooc_summary_sha256": (
            "reports/starlink-pss15-kernel-rom-ooc-summary.txt"
        ),
        "xfft_adapter_historical_evidence_test_sha256": (
            "tests/test_starlink_xfft_block_adapter_evidence.py"
        ),
        "kernel_rom_report_sha256": "reports/STARLINK_PSS15_KERNEL_ROM_V1.md",
    }
    historical_shared_hashes = {
        "acquisition_test_runner_sha256": (
            "279b7029618f8703ab5a17753a1e8e3a12e774563ee2aeff9f55de2d2e596331"
        ),
        "acquisition_hdl_readme_sha256": (
            "f6dd7fd77ad26d49029999b669d9ee562eee007ad173fbb1b1e28d7a0ad0d972"
        ),
        "kernel_rom_evidence_test_sha256": (
            "d0162f2f710bad4ba3f511f1e12b31e819ebe66e1d2f670fb8f9afe91993dd4f"
        ),
        "starlink_plan_sha256": (
            "1a69cc25d4e6d6439921cd41275adb7d509f3f016e99ea4eac6fa85a5e398ddb"
        ),
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
    assert "firmware_main_gitlink_guard_required: true" in manifest
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/91" in manifest
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_MERGE_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_all_five_checks_passed: true" in manifest
    assert "kernel_rom_simulation_verdict: PASS" in manifest
    assert "kernel_rom_ooc_verdict: PASS" in manifest
    assert f"kernel_canonical_binary_sha256: {CANONICAL_SHA256}" in manifest
    assert f"kernel_memory_text_sha256: {MEMORY_SHA256}" in manifest
    assert "rtl_coefficient_rom_packaged: true" in manifest
    assert "rtl_fft_instantiated: false" in manifest
    assert "rtl_raw_iq_to_score_complete: false" in manifest
    assert "rtl_phase_map_connected_to_score_path: false" in manifest
    assert "rtl_detector_integrated: false" in manifest
    assert "rx_dma_changed: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, relative in bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    for field, digest in historical_shared_hashes.items():
        assert f"{field}: {digest}" in manifest
