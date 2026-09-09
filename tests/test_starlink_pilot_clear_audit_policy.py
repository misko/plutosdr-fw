"""Exercise read-only CLEAR audit admission against an explicit mock netlist.

Only the separately retained real Vivado DCP audits establish synthesized cones.
"""
import hashlib
from pathlib import Path
import subprocess

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/audit_pilot_clear_fanin.tcl"


def _run(checkpoint, output, *, mode="registered", tool="2022.2", revision="d" * 40,
         wrong_hash=False, missing=False, residual=False, wrong_clear=False,
         source_mismatch=False, sequential=True, part="xc7z010clg400-1"):
    digest = hashlib.sha256(checkpoint.read_bytes() if checkpoint.exists() else b"").hexdigest()
    if wrong_hash:
        digest = "0" * 64
    script = f"proc version {{args}} {{return {{{tool}}}}}\n"
    script += f"set argc 5\nset argv [list {{{checkpoint}}} {{{output}}} {{{revision}}} {digest} {{{mode}}}]\n"
    for key, value in {"missing": missing, "residual": residual, "wrong_clear": wrong_clear,
                       "source_mismatch": source_mismatch, "sequential": sequential}.items():
        script += f"set {key} {int(value)}\n"
    script += f"set mode {{{mode}}}\nset part {{{part}}}\n"
    script += r"""
rename exec system_exec
proc exec {args} {
    if {[lindex $args 0] ne "git"} {return [system_exec {*}$args]}
    if {[lindex $args 3] eq "rev-parse"} {return [string range [lindex $args 4] 0 39]}
    if {$::source_mismatch} {return "not the requested source"}
    if {$::mode eq "registered"} {return "reg clear_ok;\nclear_ok <= clear_admit;"}
    return "wire clear_ok = clear_request && !active && empty;"
}
proc open_checkpoint {path} {}
proc current_design {} {return receiver}
proc close_design {} {}
proc get_property {property objects} {
    if {$property eq "PART"} {return $::part}
    if {$property eq "NAME"} {return $objects}
    if {$property eq "IS_SEQUENTIAL"} {return $::sequential}
    error "unexpected property"
}
proc get_cells {args} {
    if {$::missing} {return {}}
    if {[string first clear_ok [lindex $args end]] >= 0} {
        if {($::mode eq "registered") != $::wrong_clear} {return clear_token}
        return {}
    }
    return {fifo0 fifo1 fifo2 fifo3 fifo4 fifo5}
}
proc get_pins {args} {
    set pins {}
    for {set i 0} {$i < 128} {incr i} {lappend pins "pin$i"}
    return $pins
}
proc all_fanin {args} {
    if {[lindex $args end] eq "pin0"} {
        if {$::mode eq "old"} {return {fifo0 fifo4 source_ready}}
        if {$::residual} {return {clear_token fifo3 source_ready}}
        return {clear_token source_ready}
    }
    return {source_ready job_index}
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
    ("existing", "refusing to overwrite pilot CLEAR evidence"),
    ("tool", "requires Vivado 2022.2"),
    ("mode", "CLEAR mode must be old or registered"),
    ("revision", "full immutable commit"),
    ("hash", "checkpoint SHA256 mismatch"),
    ("source", "source commit does not contain"),
])
def test_admission_is_pinned_and_invalid_input_has_no_output_side_effects(tmp_path, case, error):
    checkpoint, output = tmp_path / "input.dcp", tmp_path / "evidence"
    if case != "missing":
        checkpoint.write_bytes(b"frozen checkpoint")
    if case == "existing":
        output.mkdir()
        (output / "retained").write_bytes(b"prior evidence")
    result = _run(checkpoint, output, mode="typo" if case == "mode" else "registered",
                  tool="2023.1" if case == "tool" else "2022.2",
                  revision="main" if case == "revision" else "d" * 40,
                  wrong_hash=case == "hash", source_mismatch=case == "source")
    assert result.returncode == 2 and error in result.stderr
    assert output.exists() == (case == "existing")
    if case == "existing":
        assert list(output.iterdir()) == [output / "retained"]
        assert (output / "retained").read_bytes() == b"prior evidence"


@pytest.mark.parametrize("option,error", [
    ("missing", "do not infer isolation"),
    ("wrong_clear", "source inventory does not match"),
    ("sequential", "expected sequential source"),
    ("part", "requires the complete xc7z010 receiver"),
])
def test_missing_or_incompatible_netlist_cannot_masquerade_as_a_cut(tmp_path, option, error):
    checkpoint, output = tmp_path / "input.dcp", tmp_path / "evidence"
    checkpoint.write_bytes(b"unchanged checkpoint")
    value = False if option == "sequential" else "other_part" if option == "part" else True
    result = _run(checkpoint, output, **{option: value})
    assert result.returncode == 2 and error in result.stderr
    assert not (output / "fanin.txt").exists()


@pytest.mark.parametrize("mode", ["old", "registered"])
def test_both_pinned_structural_outcomes_retain_inventory_without_timing_claim(tmp_path, mode):
    checkpoint, output = tmp_path / "input.dcp", tmp_path / "evidence"
    checkpoint.write_bytes(b"unchanged checkpoint")
    result = _run(checkpoint, output, mode=mode)
    assert result.returncode == 0, result.stderr
    report = (output / "fanin.txt").read_text()
    assert f"fifo_count_dependent_endpoints={int(mode == 'old')}" in report
    assert f"registered_clear_dependent_endpoints={int(mode == 'registered')}" in report
    assert "job_index_control_pins=128" in report and "fifo_count_registers=6" in report
    assert "hardware_qualified=false" in report
    assert "not_path_sensitization_or_timing_closure" in report
    assert "caller_attested_build_provenance_not_derived_from_checkpoint" in report
    assert (output / "audit_source.tcl").read_bytes() == RUNNER.read_bytes()
    assert checkpoint.read_bytes() == b"unchanged checkpoint"


def test_residual_fifo_dependency_fails_with_retained_diagnostic(tmp_path):
    checkpoint, output = tmp_path / "input.dcp", tmp_path / "evidence"
    checkpoint.write_bytes(b"unchanged checkpoint")
    result = _run(checkpoint, output, residual=True)
    assert result.returncode == 2 and "cut was not established" in result.stderr
    assert "fifo_count_dependent_endpoints=1" in (output / "fanin.txt").read_text()


def test_runner_cannot_modify_design_or_timing_constraints():
    source = RUNNER.read_text()
    for forbidden in ("set_property", "read_xdc", "create_clock", "set_false_path",
                      "set_multicycle_path", "set_max_delay", "set_clock_groups",
                      "place_design", "route_design", "phys_opt_design", "write_checkpoint"):
        assert forbidden not in source
