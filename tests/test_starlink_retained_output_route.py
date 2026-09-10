"""Small Tcl admission/report-order checks; no DCP/Vivado execution."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT/'hdl/library/starlink_pss_acquisition/retained_output_actual/route_retained_output.tcl'


def execute(tmp_path, mode):
    source=tmp_path/'NOT_A_REAL_DCP';source.write_text('OFFLINE_STUB_NOT_A_DCP\n')
    expected=hashlib.sha256(source.read_bytes()).hexdigest()
    output=tmp_path/'output'
    if mode=='bad_hash':expected='0'*64
    elif mode=='overwrite':output.mkdir()
    elif mode=='relative':source=Path('relative')
    elif mode=='symlink':
        alias=tmp_path/'alias';alias.symlink_to(source);source=alias
    script=tmp_path/'stub.tcl'
    script.write_text('''# OFFLINE_TCL_STUB_ONLY: no checkpoint parser or vendor process.
proc version args {return 2022.2}
proc set_param {name value} {if {$name ne "general.maxThreads" || $value!=2} {error THREADS}}
set sequence {}
proc open_checkpoint args {global sequence;lappend sequence open}
proc get_cells args {return {}}
proc get_clocks args {return [lindex $args end]}
proc get_property {name object} {
  if {$name eq "PERIOD"} {if {$object eq "source_100"} {return 10.0};return 5.714}
  if {$name eq "SLACK"} {return -1.492}
  return $name
}
foreach command {opt_design place_design phys_opt_design route_design} {
  proc $command {} [format {global sequence;lappend sequence %s} $command]
}
proc write_checkpoint {path} {
  global sequence
  if {$sequence ne {open opt_design place_design phys_opt_design route_design}} {error WRONG_IMPLEMENTATION_SEQUENCE}
  lappend sequence checkpoint
  set f [open $path w];puts $f OFFLINE_STUB_NOT_A_ROUTED_DCP;close $f
}
proc report_route_status args {
  global sequence mode source_dcp
  if {[lindex $sequence end] ne "checkpoint"} {error REPORT_BEFORE_CHECKPOINT}
  if {$mode eq "report_source_mutation"} {set f [open $source_dcp a];puts $f MUTATED;close $f}
  if {$mode in {report_failure report_source_mutation}} {error OFFLINE_EXPECTED_REPORT_FAILURE}
}
foreach command {report_utilization report_clocks write_xdc report_clock_interaction report_exceptions report_timing_summary check_timing report_cdc} {proc $command args {}}
set reported_pairs {}
proc get_timing_paths args {return path0}
proc report_timing args {
  global reported_pairs
  set from [lindex $args [expr {[lsearch -exact $args -from]+1}]]
  set to [lindex $args [expr {[lsearch -exact $args -to]+1}]]
  set kind [lindex $args [expr {[lsearch -exact $args -delay_type]+1}]]
  if {[lindex $args [expr {[lsearch -exact $args -max_paths]+1}]]!=20} {error PATH_COUNT}
  lappend reported_pairs $from.$to.$kind
}
proc close_design {} {
  global reported_pairs
  if {[lsort -unique $reported_pairs] ne [lsort {source_100.source_100.max source_100.source_100.min source_100.island_175.max source_100.island_175.min island_175.source_100.max island_175.source_100.min island_175.island_175.max island_175.island_175.min}]} {error CLOCK_PAIR_INVENTORY}
}
'''+f'set mode {mode}\nset argc 3\nset argv [list {{{source}}} {expected} {{{output}}}]\nsource {{{RUNNER}}}\n')
    run=subprocess.run(['tclsh',str(script)],capture_output=True,text=True,timeout=10)
    (tmp_path/'stub.log').write_text(run.stdout+run.stderr)
    return run,output


@pytest.mark.parametrize('mode',['bad_hash','overwrite','relative','symlink'])
def test_route_admission_before_stub_checkpoint(tmp_path,mode):
    run,output=execute(tmp_path,mode)
    assert run.returncode != 0
    assert not (output/'retained_output_routed.dcp').exists()


@pytest.mark.parametrize('mode',['healthy_stub','report_failure','report_source_mutation'])
def test_routed_checkpoint_preserved_before_observations(tmp_path,mode):
    run,output=execute(tmp_path,mode)
    assert (output/'retained_output_routed.dcp').read_text()=='OFFLINE_STUB_NOT_A_ROUTED_DCP\n'
    receipt=(output/'run_outcome.txt').read_text()
    assert f'run_status={0 if mode=="healthy_stub" else 1}\n' in receipt
    assert f'after_status={1 if mode=="report_source_mutation" else 0}\n' in receipt
    if mode=='healthy_stub':
        assert run.returncode==0 and 'NOT_A_PHYSICAL_RELEASE_PASS' in run.stdout
        paths=(output/'paths.txt').read_text()
        assert paths.count('.reported_paths=1')==8 and paths.count('.slack=-1.492')==8
        assert 'timing_qualified=false' in paths
    else:
        assert run.returncode!=0 and 'OFFLINE_EXPECTED_REPORT_FAILURE' in run.stderr
        assert 'RETAINED_OUTPUT_ROUTE_OBSERVATIONS_RECORDED' not in run.stdout


def test_only_original_implementation_sequence_and_no_waiver():
    text=RUNNER.read_text()
    sequence='  opt_design\n  place_design\n  phys_opt_design\n  route_design\n'
    assert text.count(sequence)==1
    assert all(token not in text for token in ('set_false_path','set_clock_groups','set_multicycle_path','create_clock','read_xdc'))
    assert text.index('write_checkpoint $routed')<text.index('report_route_status -file')
    assert 'report_clock_interaction -file' in text and 'report_exceptions -file' in text
