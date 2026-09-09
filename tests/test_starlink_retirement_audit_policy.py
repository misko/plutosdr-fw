"""Execute read-only audit guards/inventory with an explicit mocked netlist.

These tests do not establish synthesis behavior; real DCP audits do that.
"""

from pathlib import Path
import subprocess

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/audit_shared_input_retirement.tcl"


def _run(checkpoint, output, *, tool="2022.2", missing=False, dependent=False):
    script = f"proc version {{args}} {{return {{{tool}}}}}\n"
    script += f"set argc 2\nset argv [list {{{checkpoint}}} {{{output}}}]\n"
    script += f"set missing {int(missing)}\nset dependent {int(dependent)}\n"
    script += r"""
proc open_checkpoint {path} {}
proc current_design {} {return receiver}
proc close_design {} {}
proc get_property {property objects} {
    if {$property eq "PART"} {return xc7z010clg400-1}
    if {$property eq "NAME"} {return $objects}
    error "unexpected property"
}
proc get_cells {args} {
    if {$::missing} {return {}}
    set cells {}
    for {set i 0} {$i < 9} {incr i} {lappend cells "position$i"}
    return $cells
}
proc get_pins {args} {
    if {[string match *ENARDEN* [lindex $args end]]} {return memory_enable}
    set pins {}
    for {set i 0} {$i < 18} {incr i} {lappend pins "address$i"}
    return $pins
}
proc all_fanin {args} {
    if {$::dependent && [lindex $args end] eq "memory_enable"} {
        return {core_ready position4 position7}
    }
    return {core_ready reset_released address8}
}
proc report_timing {args} {
    set fd [open [lindex $args end] w]
    puts $fd "MOCKED TIMING NOT PHYSICAL EVIDENCE"
    close $fd
}
"""
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("case,error", [
    ("missing", "missing input checkpoint"),
    ("existing", "refusing to overwrite retirement evidence"),
    ("tool", "requires Vivado 2022.2"),
])
def test_admission_preserves_files_and_requires_actual_tool(tmp_path, case, error):
    checkpoint = tmp_path / "input.dcp"
    output = tmp_path / "evidence"
    if case != "missing":
        checkpoint.write_bytes(b"frozen checkpoint")
    if case == "existing":
        output.mkdir()
        (output / "retained").write_bytes(b"prior evidence")
    result = _run(checkpoint, output, tool="2023.1" if case == "tool" else "2022.2")
    assert result.returncode == 2 and error in result.stderr
    assert output.exists() == (case == "existing")
    if case == "existing":
        assert list(output.iterdir()) == [output / "retained"]
        assert (output / "retained").read_bytes() == b"prior evidence"


def test_missing_expected_endpoint_cannot_masquerade_as_cut(tmp_path):
    checkpoint = tmp_path / "input.dcp"
    checkpoint.touch()
    output = tmp_path / "evidence"
    result = _run(checkpoint, output, missing=True)
    assert result.returncode == 2 and "do not infer isolation" in result.stderr
    assert not (output / "fanin.txt").exists()


@pytest.mark.parametrize("dependent", [False, True])
def test_actual_inventory_logic_reports_both_outcomes_without_timing_claim(tmp_path, dependent):
    checkpoint = tmp_path / "input.dcp"
    checkpoint.write_bytes(b"unchanged checkpoint")
    output = tmp_path / "evidence"
    result = _run(checkpoint, output, dependent=dependent)
    assert result.returncode == 0, result.stderr
    report = (output / "fanin.txt").read_text()
    assert f"input_position_dependent_endpoints={int(dependent)}" in report
    assert "address_control_pins=18" in report and "memory_enable_pins=1" in report
    assert "hardware_qualified=false" in report
    assert "not_path_sensitization_or_timing_closure" in report
    assert (output / "audit_source.tcl").read_bytes() == RUNNER.read_bytes()
    assert checkpoint.read_bytes() == b"unchanged checkpoint"


def test_runner_cannot_modify_design_or_timing_constraints():
    source = RUNNER.read_text()
    for forbidden in ("set_property", "read_xdc", "create_clock", "set_false_path",
                      "set_multicycle_path", "set_max_delay", "set_clock_groups",
                      "place_design", "route_design", "phys_opt_design", "write_checkpoint"):
        assert forbidden not in source
