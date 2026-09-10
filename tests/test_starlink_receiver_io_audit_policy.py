"""Saved receiver inventory admission, not fabricated board timing evidence."""

import hashlib
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/audit_receiver_io_checkpoint.tcl"


def probe(arguments, version="2022.2"):
    script = f"proc version {{args}} {{return {{{version}}}}}\n"
    script += 'proc open_checkpoint {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} reason]}} {{puts stderr $reason; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          check=False, timeout=10)


@pytest.fixture
def inputs(tmp_path):
    checkpoint = tmp_path / "saved.dcp"
    checkpoint.write_bytes(b"admission-only fixture, not a real checkpoint")
    return checkpoint, hashlib.sha256(checkpoint.read_bytes()).hexdigest(), tmp_path / "new audit"


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_wrong_arity_is_nonmutating(inputs, count):
    result = probe([*inputs, "extra"][:count])
    assert result.returncode == 2 and "expected CHECKPOINT" in result.stderr
    assert not inputs[2].exists()


@pytest.mark.parametrize("mutation", ["tool", "format", "hash", "missing"])
def test_untrusted_input_is_nonmutating(inputs, mutation):
    checkpoint, digest, output = inputs
    if mutation == "format":
        digest = "auto"
    elif mutation == "hash":
        digest = "0" * 64
    elif mutation == "missing":
        checkpoint.unlink()
    result = probe([checkpoint, digest, output], "2023.1" if mutation == "tool" else "2022.2")
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_admission_freezes_source_and_preserves_checkpoint(inputs):
    before = inputs[0].read_bytes()
    result = probe(inputs)
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    assert (inputs[2] / "audit_source.tcl").read_bytes() == RUNNER.read_bytes()
    assert inputs[0].read_bytes() == before
    result = probe(inputs)
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_output_is_preserved(inputs, kind):
    output = inputs[2]
    if kind == "file":
        retained = output
    else:
        destination = output.with_name("retained") if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "untouched"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("do not overwrite")
    result = probe(inputs)
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "do not overwrite"


def test_saved_constraints_only_and_reference_clock_checked():
    source = RUNNER.read_text()
    for forbidden in ("create_clock", "set_input_delay", "set_output_delay", "set_false_path",
                      "set_clock_groups", "set_max_delay", "set_multicycle_path", "read_xdc",
                      "place_design", "route_design", "write_checkpoint"):
        assert forbidden not in source
    assert "check_timing -verbose" in source
    assert "foreach delay_type {max min}" in source
    assert "REF_NAME == IDELAYCTRL" in source
    assert "REF_NAME == PS7" in source
    assert "i_system_wrapper/system_i/axi_ad9361/inst" in source
    assert "[get_property PERIOD $clocks] - 5.0" in source
    assert "NO_CONSTRAINT_CHANGES_OR_QUALIFICATION" in source
