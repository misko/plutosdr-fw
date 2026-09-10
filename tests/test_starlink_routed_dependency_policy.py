"""Execute the exact audit helper with Tcl query doubles, not a physical proof.

Real Vivado replay must separately establish endpoint counts, structural fanin
and saved timing. These tests ensure missing/excluded paths cannot be relabeled
as passing timing and that connected paths still use the original strict audit.
"""
import subprocess
from pathlib import Path

import pytest

from tests.test_starlink_realtime_routed_audit_policy import AUDIT


@pytest.mark.parametrize("case,expected", [
    ("absent", "NO_DEPENDENCY_RECORDED"),
    ("connected", "STRICT_TIMING_REQUIRED"),
    ("excluded", "untimed structural dependency"),
    ("empty_sources", "empty dependency endpoint inventory"),
    ("empty_destinations", "empty dependency endpoint inventory"),
    ("empty_fanin", "empty structural fanin"),
    ("query_failure", "STRUCTURAL_QUERY_FAILED"),
])
def test_dependency_classification_executes_real_helper(tmp_path: Path, case, expected):
    source = AUDIT.read_text()
    helper = source.split("# AUDIT_DEPENDENCY_BEGIN\n", 1)[1].split(
        "# AUDIT_DEPENDENCY_END", 1)[0]
    script = tmp_path / "dependency.tcl"
    script.write_text(r'''
set case [lindex $argv 0]
set report [open summary.txt w]
proc get_timing_paths {args} {
  if {$args ne {-quiet -delay_type max -from {metadata0 metadata1} -to {job/D job/CE} -max_paths 1}} {
    error "wrong timing query: $args"
  }
  if {$::case eq "connected"} {return {actual_path}}
  return {}
}
proc all_fanin {args} {
  if {$args ne {-flat -startpoints_only -only_cells -trace_arcs all -to {job/D job/CE}}} {
    error "all arcs and exact destination pins are mandatory: $args"
  }
  if {$::case eq "query_failure"} {error "STRUCTURAL_QUERY_FAILED"}
  if {$::case eq "empty_fanin"} {return {}}
  if {$::case eq "excluded"} {return {unrelated metadata1}}
  return {unrelated registered_fault}
}
proc get_property {name objects} {
  if {$name ne "NAME"} {error "unexpected property $name"}
  return $objects
}
proc audit_paths {label sources destinations period} {
  if {$label ne "dependency" || $sources ne {metadata0 metadata1} ||
      $destinations ne {job/D job/CE} || $period ne "5.0"} {
    error "strict timing audit arguments changed"
  }
  error "STRICT_TIMING_REQUIRED"
}
''' + helper + r'''
set sources {metadata0 metadata1}
set destinations {job/D job/CE}
if {$case eq "empty_sources"} {set sources {}}
if {$case eq "empty_destinations"} {set destinations {}}
if {[catch {audit_dependency dependency $sources $destinations 5.0} message]} {
  puts stderr $message
  close $report
  exit 2
}
close $report
puts "NO_DEPENDENCY_RECORDED"
''')
    result = subprocess.run(["tclsh", str(script), case], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10, check=False)
    assert expected in result.stdout + result.stderr
    assert result.returncode == (0 if case == "absent" else 2)
    evidence = tmp_path / "dependency_structural_fanin.txt"
    if case == "absent":
        assert "no_combinational_dependency_not_timing_pass" in (
            tmp_path / "summary.txt").read_text()
        assert "all_arc_startpoints=unrelated registered_fault" in evidence.read_text()
        assert "queried_sources=metadata0 metadata1" in evidence.read_text()
    else:
        assert not evidence.exists()


def test_dependency_exception_is_narrow_and_destination_timing_still_required():
    source = AUDIT.read_text()
    assert source.count("audit_dependency output_metadata_job_start ") == 1
    assert "expected all 75 output metadata registers" in source
    assert "expected job start D and CE pins" in source
    assert "audit_period $output_metadata 5.0" in source
    assert "audit_period $job_start 5.0" in source
    assert "audit_paths job_start_all_sources {} $job_start_pins 5.0" in source
    assert "audit_paths sticky_fault_crossing $fault_source $fault_first 5.0" in source
