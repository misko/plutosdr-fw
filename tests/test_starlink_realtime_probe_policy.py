"""Admission/isolation policy only; retained real Vivado replay owns numerics."""

import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_realtime_xfft_protocol_probe.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_realtime_xfft_protocol_probe.sv"
VECTORS = ("samples_ci16", "forward_q17", "product_q17", "inverse_q17",
           "forward_exponents", "inverse_exponents")


def probe(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    # Stop at the first actual Vivado API; this is not a mocked numerical run.
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_wrong_arity_creates_nothing(tmp_path, count):
    output = tmp_path / "new evidence"
    arguments = [output, tmp_path / "vectors", "extra"][:count]
    result = probe(arguments)
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_vivado_creates_nothing(tmp_path):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors"], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_existing_evidence_is_preserved(tmp_path, kind):
    output = tmp_path / "evidence"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "receipt.txt"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("retained evidence")
    result = probe([output, tmp_path / "vectors"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "retained evidence"
    if kind != "file":
        assert list(output.iterdir()) == [output / "receipt.txt"]


@pytest.mark.parametrize("missing", VECTORS)
def test_every_missing_vector_is_rejected_before_output_creation(tmp_path, missing):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        if name != missing:
            (vectors / f"{name}.mem").write_text("00\n")
    result = probe([output, vectors])
    assert result.returncode == 2 and f"missing vector {missing}" in result.stderr
    assert not output.exists()


def test_admission_snapshots_inputs_without_mutating_production(tmp_path):
    protected = [ACQ / name for name in (
        "starlink_pss_xfft_block_adapter.v", "starlink_pss_shared_xfft_service.v",
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
    for name in VECTORS:
        assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}


def test_source_policy_isolated_ip_and_frozen_numeric_contract():
    source, bench = RUNNER.read_text(), BENCH.read_text()
    assert "set module_name starlink_pss_fft512_bfp18_rt_probe" in source
    assert "-module_name $module_name" in source
    assert "starlink_pss_fft512_bfp18_rt_probe core (" in bench
    assert "add_files -fileset sim_1 -norecurse [file join $source_dir" in source
    assert "starlink_pss_shared_xfft_service" not in source + bench
    assert "starlink_pss_xfft_block_adapter" not in source + bench
    numeric = re.search(r"set required_generics \{(.*?)\}", source, re.S).group(1).split()
    generics = dict(zip(numeric[::2], numeric[1::2]))
    assert len(numeric) == 64 and len(generics) == 32
    assert {key: generics[key] for key in (
        "C_THROTTLE_SCHEME", "C_ARCH", "C_NFFT_MAX", "C_INPUT_WIDTH",
        "C_OUTPUT_WIDTH", "C_TWIDDLE_WIDTH", "C_HAS_BFP", "C_HAS_ROUNDING",
    )} == dict(C_THROTTLE_SCHEME="0", C_ARCH="1", C_NFFT_MAX="9", C_INPUT_WIDTH="18",
              C_OUTPUT_WIDTH="18", C_TWIDDLE_WIDTH="16", C_HAS_BFP="1", C_HAS_ROUNDING="1")
    assert "foreach {name value} $required_generics" in source
    assert "production_service_qualified=false" in source
    assert "universal_input_halt_fault_rule_qualified=false" in source
    assert "always #2.5 clk = !clk" in bench
    assert "{output_data[41:24], output_data[17:0]} !== expected_word" in bench
    assert "output_user !== {3'b0, expected_exponent" in bench
    assert "status_data !== {3'b0, expected_exponent}" in bench
