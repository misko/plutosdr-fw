"""Isolated service admission/source checks; actual Vivado log owns numerics."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[1] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_shared_realtime_xfft_service.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_shared_realtime_xfft_service.sv"
SERVICE = ACQ / "starlink_pss_shared_realtime_xfft_service.v"
VECTORS = ("samples_ci16", "forward_q17", "product_q17", "inverse_q17",
           "forward_exponents", "inverse_exponents")
SOURCES = (SERVICE.name, "starlink_pss_realtime_input_guard.v",
           "starlink_pss_realtime_result_guard.v", "starlink_pss_block_mailbox.v",
           "verify_realtime_probe_result.tcl")


def probe(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                          timeout=10, check=False)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_wrong_arity_is_nonmutating(tmp_path, count):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors", "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_tool_is_nonmutating(tmp_path):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors"], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_preserves_existing_evidence(tmp_path, kind):
    output = tmp_path / "evidence"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "retained.txt"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("retained")
    result = probe([output, tmp_path / "vectors"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "retained"


@pytest.mark.parametrize("missing", VECTORS)
def test_requires_every_frozen_vector_before_allocation(tmp_path, missing):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        if name != missing:
            (vectors / f"{name}.mem").write_text("00\n")
    result = probe([output, vectors])
    assert result.returncode == 2 and f"missing vector {missing}" in result.stderr
    assert not output.exists()


def test_snapshots_exact_service_dependencies_without_touching_production(tmp_path):
    protected = [ACQ / name for name in (
        "starlink_pss_shared_xfft_service.v", "starlink_pss_xfft_block_adapter.v",
        "starlink_pss_iq_to_score_shared.v", "simulate_shared_xfft_mailbox.tcl",
    )]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        (vectors / f"{name}.mem").write_text("00\n")
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    frozen = output / "frozen_sources"
    assert (frozen / "probe_runner.tcl").read_bytes() == RUNNER.read_bytes()
    assert (frozen / BENCH.name).read_bytes() == BENCH.read_bytes()
    for name in SOURCES:
        assert (frozen / name).read_bytes() == (ACQ / name).read_bytes()
    for name in VECTORS:
        assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}


def test_pinned_arithmetic_and_machine_checked_terminal_evidence():
    source, bench = RUNNER.read_text(), BENCH.read_text()
    old = (ACQ / "simulate_realtime_xfft_protocol_probe.tcl").read_text()
    pattern = r"set required_generics \{(.*?)\}"
    values = re.search(pattern, source, re.DOTALL).group(1).split()
    assert len(values) == 64 and values == re.search(pattern, old, re.DOTALL).group(1).split()
    assert "set module_name starlink_pss_fft512_bfp18_rt_candidate" in source
    assert "starlink_pss_fft512_bfp18_rt_candidate shared_xfft (" in SERVICE.read_text()
    assert "source [file join $source_dir verify_realtime_probe_result.tcl]" in source
    assert "require_realtime_probe_pass" in source and "RT_SERVICE_RESULT 26" in source
    assert "cause_coverage_fence_independent_review_required=true" in source
    assert "physical_timing_or_CDC_qualified=false" in source
    assert "sustained_service_capacity_qualified=false" in source
    assert "launch_runs" not in source and "create_clock" not in source
    assert "output_data !== expected_word" in bench
    assert "{dut.core_output_data[41:24], dut.core_output_data[17:0]} !== expected_word" in bench
    assert "output_metadata !== {descriptors[published_jobs], expected_exponent}" in bench


def test_persistent_mailbox_epochs_registered_admission_and_sticky_fault_crossings():
    service, bench = SERVICE.read_text(), BENCH.read_text()
    assert service.count("RESET_RELEASE_EXTERNAL(1)") == 2
    assert "input_fault_fast_sync <= {input_fault_fast_sync[0], input_mailbox_fault};" in service
    assert "fast_fault_sync <= {fast_fault_sync[0], fast_fault};" in service
    assert "input_fault_fast_sync[1] || vendor_fault_now || fast_fault" in service
    assert ".resetn(fast_running), .job_valid(job_valid)" in service
    assert ".resetn(core_aresetn), .job_start(input_job_start)" in service
    assert "engine_metadata <= fast_input_metadata;" in service
    assert "input_job_start <= 1;" in service and "assign input_job_start" not in service
    assert "CHECK_INPUT_BLOCK_IDENTITY(0)" in service
    assert "input_metadata = i == bad_position ? 70'h124 : 70'h123" in bench
    # The pinned phase-input contract already replaced the redundant full
    # framing predicate after input completion. Keep its duplicate-start and
    # sticky/current external vetoes explicit. Executed shadow/mutation tests
    # in test_phase_input_contract.py independently check that equivalence.
    normalized = re.sub(r"\s+", "", service)
    assert ("wirefinal_fence=checked_input_complete&&!input_guard_fault&&"
            "!(core_aresetn&&input_job_start);") in normalized
    assert ("wireexternal_fault_now=input_fault_now||input_guard_fault||"
            "input_fault_fast_sync[1]||vendor_fault_now||fast_fault;") in normalized
    assert ("wirephase_input_fault_now=(core_aresetn&&input_job_start)||input_guard_fault||"
            "input_fault_fast_sync[1]||vendor_fault_now||fast_fault;") in normalized
    assert "ACK_DRAIN: if (!result_busy && output_mailbox_ready)" in service
    assert "fast_input_ready = input_transport_ready && engine_input_enable;" in service
    assert "dut.fast_input_metadata !== descriptors[1]" in bench
    assert "first_vendor_halt <= first_local_fault" in bench


def test_actual_service_covers_active_epoch_resets_and_final_metadata_mismatch():
    bench, runner = BENCH.read_text(), RUNNER.read_text()
    assert "bad_position = kind == 0 ? 10 : 511;" in bench
    assert "input_last = i == 511;" in bench
    assert "admitted || dut.input_mailbox.request_toggle" in bench
    assert "for (side = 1; side <= 2; side = side + 1)" in bench
    assert "interrupt_active_job(side, 0);" in bench
    assert "interrupt_active_job(side, 1);" in bench
    assert "partial_input ? delivered != 128 : dut.state != dut.CONFIGURE" in bench
    assert "config_cycle != -1 || delivered || dut.engine_input_enable" in bench
    assert "reset_epoch(reset_side); reset_cases = reset_cases + 1;" in bench
    marker = (
        "REALTIME_SERVICE_CANDIDATE_PASS healthy_jobs=26 exact_words=13312 "
        "starvation_cases=6 final_veto_cases=3 malformed_bank_cases=2 "
        "independent_reset_cases=6 configure_reset_cases=2 partial_input_reset_cases=2 "
        "postcommit_ACK_fault_cases=1 CAUSE_FENCE_REVIEW_REQUIRED CAPACITY_AND_PHYSICAL_UNQUALIFIED"
    )
    assert marker in bench and marker in runner


def test_actual_service_requires_idle_mailbox_premise_and_frozen_public_checks():
    bench, runner = BENCH.read_text(), RUNNER.read_text()
    marker = ("IDLE_MAILBOX_SERVICE_PREMISE_PASS actual_mailbox_and_FFT=1 "
              "inactive_and_ACK=1 private_writes_active=1 public_golden=1")
    assert marker in bench and marker in runner
    assert "IDLE_MAILBOX_SERVICE_PREMISE_MISSING" in bench
    assert "IDLE_MAILBOX_SERVICE_ACK_ACTIVE" in bench
    assert "IDLE_MAILBOX_SERVICE_WRITE_INACTIVE" in bench
    assert "IDLE_MAILBOX_SERVICE_COVERAGE_MISSING" in bench
    assert "RETIRED_SERVICE_PUBLIC_MISMATCH" in bench
    assert "FINAL_AUTH_SERVICE_MISMATCH" in bench
