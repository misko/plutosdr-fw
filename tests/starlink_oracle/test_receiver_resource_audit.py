"""Execute audit admission/integrity logic with explicit fake Vivado commands.

These are tooling safety tests, never evidence about real resource utilization.
The real checkpoint inventory and synthesis live in separately pinned reports.
"""

import hashlib
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
AUDIT = HDL / "projects/pluto/audit_pss_receiver_resources.tcl"
SIMULATION = HDL / "library/starlink_pss_acquisition/simulate_transform_fifo_storage.tcl"
BASE = "ced8a17d21e5ea00a134eb075a095d5ecf435955"


@pytest.mark.parametrize("case,expected_error", [
    ("valid", None),
    ("version", "requires Vivado 2022.2"),
    ("hash", "checkpoint SHA256 mismatch"),
    ("commit", "full source revision"),
    ("missing", "checkpoint must exist"),
    ("existing", "audit output must be new"),
    ("part", "wrong receiver part"),
    ("changed", "checkpoint changed during audit"),
])
def test_read_only_audit_checks_identity_and_unchanged_checkpoint(tmp_path, case, expected_error):
    checkpoint = tmp_path / "fake-checkpoint.dcp"
    checkpoint.write_bytes(b"not a real FPGA checkpoint\n")
    original = checkpoint.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    output = tmp_path / "audit"
    if case == "missing":
        checkpoint.unlink()
    if case == "existing":
        output.mkdir()
        (output / "keep").write_text("preserve")
    version = "2020.1" if case == "version" else "2022.2"
    part = "wrong" if case == "part" else "xc7z010clg400-1"
    revision = "bad" if case == "commit" else BASE
    if case == "hash":
        digest = "0" * 64
    tamper = "set f [open $path a]; puts $f changed; close $f" if case == "changed" else ""
    script = f"""
proc version {{args}} {{ return {version} }}
proc open_checkpoint {{path}} {{ puts MOCK_OPENED; {tamper} }}
proc current_design {{}} {{ return mock_design }}
proc get_property {{key object}} {{
  if {{$key eq "PART"}} {{ return {part} }}
  if {{$object eq "memory"}} {{ return RAMB18E1 }}
  return SRL16E
}}
proc get_cells {{args}} {{ return {{memory shift}} }}
proc mock_report {{args}} {{
  set path [lindex $args [expr {{[lsearch -exact $args -file] + 1}}]]
  set f [open $path w]; puts $f MOCK_NOT_RESOURCE_EVIDENCE; close $f
}}
proc report_utilization {{args}} {{ mock_report {{*}}$args }}
proc report_control_sets {{args}} {{ mock_report {{*}}$args }}
proc close_design {{}} {{ puts MOCK_CLOSED }}
set argc 4
set argv [list {{{checkpoint}}} {{{output}}} {revision} {digest}]
if {{[catch [list source {{{AUDIT}}}] message]}} {{ puts stderr $message; exit 2 }}
"""
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                            timeout=10, check=False)
    if expected_error:
        assert result.returncode == 2 and expected_error in result.stderr, result
        assert "RESOURCE_INVENTORY_FINISHED" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "source_association_not_derived_from_checkpoint=1" in (output / "scope.txt").read_text()
        assert "RAMB18E1\tmemory" in (output / "storage.tsv").read_text()
        assert "SRL16E\tshift" in (output / "storage.tsv").read_text()
        assert (output / "audit_source.tcl").read_bytes() == AUDIT.read_bytes()
    if case not in {"missing", "changed"}:
        assert checkpoint.read_bytes() == original
    if case == "existing":
        assert list(output.iterdir()) == [output / "keep"]
        assert (output / "keep").read_text() == "preserve"


@pytest.mark.parametrize("case,error", [
    ("missing", "missing comparison input"),
    ("incomplete", "synthesis comparison incomplete"),
    ("baseline", "baseline source mismatch"),
    ("candidate", "candidate source changed since synthesis"),
    ("netlist", "synthesis receipt does not bind candidate_netlist_sha256"),
])
def test_netlist_simulation_rejects_unbound_inputs_before_vivado(tmp_path, case, error):
    comparison = tmp_path / "comparison"
    comparison.mkdir()
    original = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/starlink_pss_transform_fifo.v",
    ], capture_output=True, check=True, timeout=10).stdout
    candidate = (SIMULATION.parent / "starlink_pss_transform_fifo.v").read_bytes()
    netlist = b"deliberately not a real netlist"
    (comparison / "baseline.v").write_bytes(original if case != "baseline" else b"wrong")
    (comparison / "candidate.v").write_bytes(candidate if case != "candidate" else b"wrong")
    if case != "missing":
        (comparison / "candidate_netlist.v").write_bytes(netlist)
    marker = "FIFO_STORAGE_COMPARISON_FINISHED hardware_qualified=false"
    scope = "\n".join([
        f"baseline_source_sha256={hashlib.sha256(original).hexdigest()}",
        f"candidate_source_sha256={hashlib.sha256(candidate).hexdigest()}",
        "candidate_netlist_sha256=" + "0" * 64,
        marker if case != "incomplete" else "NOT_FINISHED",
    ])
    (comparison / "scope.txt").write_text(scope)
    output = tmp_path / "simulation"
    script = f"""
proc version {{args}} {{ return 2022.2 }}
proc create_project {{args}} {{ error SHOULD_NOT_REACH_VIVADO }}
set argc 2
set argv [list {{{comparison}}} {{{output}}}]
if {{[catch [list source {{{SIMULATION}}}] message]}} {{ puts stderr $message; exit 2 }}
"""
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                            timeout=10, check=False)
    assert result.returncode == 2 and error in result.stderr, result
    assert "SHOULD_NOT_REACH_VIVADO" not in result.stderr
    assert not output.exists()
