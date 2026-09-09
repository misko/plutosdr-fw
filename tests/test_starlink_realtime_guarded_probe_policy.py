"""Admission/isolation checks only; retained actual Vivado replay owns numerics."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_realtime_guarded_mailbox_probe.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_realtime_guarded_mailbox_probe.sv"
VECTORS = ("samples_ci16", "forward_q17", "product_q17", "inverse_q17",
           "forward_exponents", "inverse_exponents")
RTL_NAMES = ("starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v",
             "starlink_pss_block_mailbox.v")


def probe(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_wrong_arity_creates_nothing(tmp_path, count):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors", "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_tool_creates_nothing(tmp_path):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors"], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_evidence_is_preserved(tmp_path, kind):
    output = tmp_path / "evidence"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "retained.txt"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("original evidence")
    result = probe([output, tmp_path / "vectors"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "original evidence"
    if kind != "file":
        assert list(output.iterdir()) == [output / "retained.txt"]


@pytest.mark.parametrize("missing", VECTORS)
def test_missing_vectors_fail_before_output(tmp_path, missing):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        if name != missing:
            (vectors / f"{name}.mem").write_text("00\n")
    result = probe([output, vectors])
    assert result.returncode == 2 and f"missing vector {missing}" in result.stderr
    assert not output.exists()


def test_snapshots_are_exact_and_production_is_untouched(tmp_path):
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
    for name in RTL_NAMES:
        assert (frozen / name).read_bytes() == (ACQ / name).read_bytes()
    for name in VECTORS:
        assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}


def test_pinned_generics_two_mailboxes_and_registered_admission_scope():
    source, bench = RUNNER.read_text(), BENCH.read_text()
    assert "set module_name starlink_pss_fft512_bfp18_rt_guarded_probe" in source
    assert "starlink_pss_fft512_bfp18_rt_guarded_probe core (" in bench
    assert "starlink_pss_block_mailbox input_mailbox (" in bench
    assert "starlink_pss_block_mailbox #(.METADATA_WIDTH(75)) output_mailbox (" in bench
    assert "input_job_start <= job_valid && job_ready;" in bench
    assert "assign input_job_start" not in bench
    assert "{core_output_data[41:24], core_output_data[17:0]} !== expected_word" in bench
    assert "sink_data !== expected_word" in bench
    assert "sink_metadata !== {descriptor, expected_exponent}" in bench
    assert "core_status_data !== {3'b0, expected_exponent}" in bench
    assert "first_gap != first_local_fault || first_vendor_halt <= first_local_fault" in bench
    assert "gap_case == 0 ? 1 : gap_case == 1 ? 255 : 511" in bench
    assert "EVENT_FENCE_PREMISE_UNQUALIFIED CAPACITY_UNQUALIFIED" in bench
    old = (ACQ / "simulate_realtime_xfft_protocol_probe.tcl").read_text()
    pattern = r"set required_generics \{(.*?)\}"
    generics = re.search(pattern, source, re.S).group(1).split()
    assert len(generics) == 64
    assert generics == re.search(pattern, old, re.S).group(1).split()
    assert "production_service_qualified=false" in source
    assert "universal_event_fence_qualified=false" in source
    assert "sustained_service_capacity_qualified=false" in source
    assert "launch_runs" not in source and "create_clock" not in source
