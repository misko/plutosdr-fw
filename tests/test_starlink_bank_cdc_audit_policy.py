"""Read-only saved-checkpoint inventory admission; no fabricated timing pass."""

import hashlib
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/audit_bank_owned_cdc_checkpoint.tcl"


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
    checkpoint.write_bytes(b"test admission only, never a Vivado checkpoint")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    return checkpoint, digest, tmp_path / "new audit"


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_bad_arity_has_no_side_effect(inputs, count):
    result = probe([*inputs, "extra"][:count])
    assert result.returncode == 2 and "expected CHECKPOINT" in result.stderr
    assert not inputs[2].exists()


@pytest.mark.parametrize("mutation", ["wrong_tool", "bad_hash", "wrong_hash", "missing"])
def test_untrusted_checkpoint_rejected_before_output(inputs, mutation):
    checkpoint, digest, output = inputs
    if mutation == "bad_hash":
        digest = "auto"
    elif mutation == "wrong_hash":
        digest = "0" * 64
    elif mutation == "missing":
        checkpoint.unlink()
    result = probe([checkpoint, digest, output], "2023.1" if mutation == "wrong_tool" else "2022.2")
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_admitted_hash_pins_audit_source_without_editing_checkpoint(inputs):
    before = inputs[0].read_bytes()
    result = probe(inputs)
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    assert (inputs[2] / "audit_source.tcl").read_bytes() == RUNNER.read_bytes()
    assert inputs[0].read_bytes() == before
    result = probe(inputs)
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr


def test_inventory_does_not_apply_or_waive_constraints():
    source = RUNNER.read_text()
    for forbidden in ("create_clock", "set_false_path", "set_clock_groups", "set_max_delay",
                      "set_multicycle_path", "read_xdc", "place_design", "route_design", "write_checkpoint"):
        assert forbidden not in source
    assert "foreach capture $destination" in source
    assert "bank_path $channel fault/second" in source
    assert "product_bank 5.714 5.714 70" in source
    assert "NO_PHYSICAL_OR_RECEIVER_QUALIFICATION" in source
