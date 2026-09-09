"""Execute placement-only probe admission; mocked entry is not placement proof."""

import os
import re
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl"))
PROBE = HDL / "projects/pluto/probe_pss_placement.tcl"


@pytest.fixture
def probe(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "--quiet", "--allow-empty",
                    "-m", "fixture"], check=True, capture_output=True)
    revision = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    script = repo / "projects/pluto/probe_pss_placement.tcl"
    script.parent.mkdir(parents=True)
    script.write_bytes(PROBE.read_bytes())
    checkpoint = tmp_path / "source.dcp"
    checkpoint.write_bytes(b"checkpoint fixture, not a real netlist")
    return script, checkpoint, tmp_path / "output", revision


def invoke(probe, *, field=None, value=None, version="2022.2", existing=False):
    script, checkpoint, output, revision = probe
    args = [str(checkpoint), str(output), revision,
            sha256(checkpoint.read_bytes()).hexdigest(), "AltSpreadLogic_medium"]
    if field is not None:
        args[field] = value
    if existing:
        output.mkdir()
        (output / "retained.txt").write_text("keep")
    harness = f"proc version {{args}} {{return {{{version}}}}}\n"
    harness += "proc open_checkpoint {path} {error ADMITTED_BEFORE_DESIGN_ACCESS}\n"
    harness += "set argv [list " + " ".join("{" + str(v) + "}" for v in args) + "]\n"
    harness += "set argc [llength $argv]\n"
    harness += f"if {{[catch {{source {{{script}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=harness, capture_output=True, text=True,
                          check=False, timeout=10)


@pytest.mark.parametrize("field,value,error", [
    (0, "/nonexistent/probe-source.dcp", "existing checkpoint and new output required"),
    (2, "HEAD", "full revision and checkpoint hash required"),
    (2, "0" * 40, "unknown revision"),
    (3, "0" * 64, "checkpoint SHA256 mismatch"),
    (3, "bad-hash", "full revision and checkpoint hash required"),
    (4, "AltSpreadLogic_high", "unsupported bounded placement policy"),
    (4, "Explore; exit 0", "unsupported bounded placement policy"),
    (4, "", "unsupported bounded placement policy"),
])
def test_invalid_probe_has_no_design_or_output_side_effect(probe, field, value, error):
    result = invoke(probe, field=field, value=value)
    assert result.returncode == 2 and error in result.stderr
    assert "ADMITTED_BEFORE_DESIGN_ACCESS" not in result.stderr
    assert not probe[2].exists()


def test_wrong_tool_rejected_before_creating_output(probe):
    result = invoke(probe, version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not probe[2].exists()


def test_existing_evidence_is_preserved(probe):
    result = invoke(probe, existing=True)
    assert result.returncode == 2 and "existing checkpoint and new output required" in result.stderr
    assert (probe[2] / "retained.txt").read_text() == "keep"
    assert len(list(probe[2].iterdir())) == 1


@pytest.mark.parametrize("directive", ["AltSpreadLogic_medium", "Explore"])
def test_admitted_probe_freezes_script_without_modifying_source(probe, directive):
    before = probe[1].read_bytes()
    result = invoke(probe, field=4, value=directive)
    assert result.returncode == 2 and "ADMITTED_BEFORE_DESIGN_ACCESS" in result.stderr
    assert probe[1].read_bytes() == before
    assert (probe[2] / "probe_source.tcl").read_bytes() == PROBE.read_bytes()


def test_probe_never_changes_constraints_or_runs_synthesis_or_routing():
    source = "\n".join(line for line in PROBE.read_text().splitlines()
                       if not line.lstrip().startswith("#"))
    for command in ("read_xdc", "set_property", "create_clock", "create_generated_clock",
                    "set_max_delay", "set_min_delay", "set_false_path", "set_multicycle_path",
                    "set_clock_groups", "reset_timing", "opt_design", "phys_opt_design",
                    "synth_design", "route_design", "write_bitstream"):
        assert not re.search(rf"\b{command}\b", source), command
    assert "write_checkpoint [file join $output placement_only.dcp]" in source
    assert "source checkpoint changed during probe" in source
    assert "placement_only_child_of_saved_optimized_checkpoint_not_fresh_receiver_qualification" in source
