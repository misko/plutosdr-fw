"""Execute the real constraint gate against a bounded named-endpoint model.

These tests qualify gate admission and failure behavior, not physical timing.
Actual implementation still has to provide every checked endpoint/path.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl")))
GATE = HDL / "projects/pluto/shared_xfft_impl_gate.tcl"
XDC = HDL / "library/starlink_pss_acquisition/starlink_pss_shared_xfft_constr.xdc"


def gate_probe(tmp_path, *, mode=1, boundary=0, broken=""):
    # Use Vivado's dot-joined generate hierarchy, not a fabricated slash-join.
    prefix = "receiver/acquisition/shared_transform.iq_to_score.realtime_transform.transform_service/"
    script = r'''
set ::env(STARLINK_PSS_SHARED_XFFT) 1
set ::env(STARLINK_PSS_REALTIME_XFFT) MODE
set ::env(STARLINK_PSS_RATE_MSPS) 15
set ::env(STARLINK_PSS_PROFILE) paired-pilot
set ::env(STARLINK_PSS_BOUNDARY_STOP) @BOUNDARY@
set prefix {PREFIX}
set broken {BROKEN}
set endpoints [list ${prefix}shared_xfft receiver/starlink_pss_tracker/inst \
  receiver/starlink_pilot_capture/inst receiver/starlink_pilot_dma/inst]
array set periods {}
if {$broken eq "serial_reducer"} {
  lappend endpoints receiver/starlink_pss_tracker/inst/i_core/g_slice_exact_reducer.i_exact_reducer
}
if {$::env(STARLINK_PSS_BOUNDARY_STOP) || $broken eq "unexpected_stop"} {
  foreach {role suffix} {
    stop_controller phase_map_control/stop_active_reg
    stop_map_fence acquisition/phase_map/stop_pending_reg
  } {
    set name receiver/starlink_pss_acquisition/inst/$suffix
    if {$broken ne $role} {lappend endpoints $name}
    set periods($name) [expr {$broken eq "stop_clock" ? 5.0 : 10.0}]
  }
}
foreach box {input_mailbox output_mailbox} {
  foreach suffix {request_toggle_reg acknowledge_toggle_reg request_sync_reg[0] acknowledge_sync_reg[0] metadata_in_hold_reg[0] metadata_out_hold_reg[0]} {
    set name ${prefix}${box}/${suffix}
    lappend endpoints $name
    set producer [expr {$box eq "input_mailbox" ? 10.0 : 5.0}]
    set consumer [expr {$box eq "input_mailbox" ? 5.0 : 10.0}]
    set periods($name) [expr {[string match request_toggle* $suffix] ||
      [string match acknowledge_sync* $suffix] || [string match metadata_in* $suffix] ? $producer : $consumer}]
  }
}
foreach chain {slow_reset_fast_sync fast_reset_fast_sync slow_reset_slow_sync fast_reset_slow_sync} {
  foreach bit {0 1} { lappend endpoints [format {%s%s_reg[%s]} $prefix $chain $bit] }
}
foreach {name period} {fast_fault_reg 5.0 fast_fault_sync_reg[0] 10.0} {
  lappend endpoints ${prefix}${name}
  set periods(${prefix}${name}) $period
}
if {$::env(STARLINK_PSS_REALTIME_XFFT)} {
  foreach {name period} {input_mailbox/input_fault_reg 10.0 input_fault_fast_sync_reg[0] 5.0 input_fault_fast_sync_reg[1] 5.0} {
    if {$broken ne $name} { lappend endpoints ${prefix}${name} }
    set periods(${prefix}${name}) $period
  }
}
proc get_cells {args} {
  if {[lsearch -exact $args -filter] >= 0} {
    if {[string first g_dsp_exact_reducer [lindex $args end]] >= 0} {
      set count 10
      if {$::broken eq "missing_reducer_dsp"} {set count 9}
      if {$::broken eq "extra_reducer_dsp"} {set count 11}
      set result {}
      for {set n 0} {$n < $count} {incr n} {lappend result reducer_dsp_$n}
      return $result
    }
    if {[string first pilot_pacer [lindex $args end]] >= 0 ||
        [string first pacer_memory [lindex $args end]] >= 0} {return pacer}
    return ${::prefix}shared_xfft
  }
  set result {}
  foreach name $::endpoints {
    if {[regexp [lindex $args end] $name]} { lappend result $name }
  }
  return $result
}
proc get_pins {args} {return [lindex $args 1]}
proc get_clocks {args} {
  set found {}
  foreach name [lindex $args end] { lappend found $::periods($name) }
  return [lsort -unique $found]
}
proc get_property {property objects} {
  switch -- $property {
    PERIOD {return $objects}
    REF_NAME - ORIG_REF_NAME {
      if {$objects eq "pacer"} {return RAMB18E1}
      if {$::env(STARLINK_PSS_REALTIME_XFFT) && $::broken ne "wrong_core"} {
        return starlink_pss_fft512_bfp18_rt_candidate
      }
      return starlink_pss_fft512_bfp18
    }
    REQUIREMENT {return [string range $objects 5 end]}
    ASYNC_REG {return [expr {$::broken ne "unmarked_sync"}]}
  }
  error "unexpected property $property"
}
proc get_timing_paths {args} {
  set source [lindex [lindex $args [expr {[lsearch -exact $args -from] + 1}]] 0]
  set destination [lindex [lindex $args [expr {[lsearch -exact $args -to] + 1}]] 0]
  if {$::broken eq "waived_fault" && [string first input_fault_fast_sync $destination] >= 0} {return {}}
  set requirement $::periods($destination)
  if {[string first metadata_out_hold $destination] >= 0} {set requirement [expr {2*$requirement}]}
  if {$::broken eq "wrong_fault_bound" && [string first input_mailbox/input_fault $source] >= 0} {set requirement 10.0}
  if {$::broken eq "waived_second_stage" && [string first input_fault_fast_sync $source] >= 0} {set requirement 10.0}
  return path_$requirement
}
proc report_clocks {args} {}
proc report_cdc {args} {}
proc report_exceptions {args} {}
if {[catch {source {GATE}} message]} {puts stderr $message; exit 2}
'''
    for key, value in {"PREFIX": prefix, "MODE": str(mode), "@BOUNDARY@": str(boundary),
                       "BROKEN": broken, "GATE": str(GATE)}.items():
        script = script.replace(key, value)
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          cwd=tmp_path, timeout=10, check=False)


@pytest.mark.parametrize("mode", [0, 1])
@pytest.mark.parametrize("boundary", [0, 1])
def test_real_gate_accepts_only_complete_matching_named_inventory(tmp_path, mode, boundary):
    result = gate_probe(tmp_path, mode=mode, boundary=boundary)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SHARED_XFFT_INIT_GATE_PASS" in result.stdout
    report = (tmp_path / "shared_xfft_init_gate.txt").read_text()
    assert f"realtime_xfft={mode}" in report
    assert "tracker_exact_reducer_dsp48e1=10 serial_reducer_present=0" in report
    assert f"stop_controller boundary_stop={boundary} surviving_registers={boundary}" in report
    assert f"stop_map_fence boundary_stop={boundary} surviving_registers={boundary}" in report
    assert ("input_fault_fast_sync/second_stage requirement_ns=5.0" in report) == bool(mode)


@pytest.mark.parametrize("mode", [0, 1])
@pytest.mark.parametrize("broken", ["stop_controller", "stop_map_fence", "stop_clock"])
def test_enabled_stop_requires_both_synthesized_halves_at_actual_slow_clock(tmp_path, mode, broken):
    result = gate_probe(tmp_path, mode=mode, boundary=1, broken=broken)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "SHARED_XFFT_INIT_GATE_PASS" not in result.stdout


def test_disabled_stop_rejects_unexpected_synthesized_feature(tmp_path):
    result = gate_probe(tmp_path, boundary=0, broken="unexpected_stop")
    assert result.returncode == 2 and "boundary-stop disabled" in result.stderr


@pytest.mark.parametrize("broken", ["missing_reducer_dsp", "extra_reducer_dsp", "serial_reducer"])
def test_shared_image_requires_the_actual_exact_dsp_reducer(tmp_path, broken):
    result = gate_probe(tmp_path, broken=broken)
    assert result.returncode == 2 and "exact ten-DSP tracker reducer" in result.stderr
    assert "SHARED_XFFT_INIT_GATE_PASS" not in result.stdout


@pytest.mark.parametrize("broken", ["input_mailbox/input_fault_reg", "input_fault_fast_sync_reg[0]",
                                    "input_fault_fast_sync_reg[1]", "wrong_core", "unmarked_sync",
                                    "waived_fault", "wrong_fault_bound", "waived_second_stage"])
def test_real_gate_rejects_missing_or_waived_realtime_fault_contract(tmp_path, broken):
    result = gate_probe(tmp_path, broken=broken)
    assert result.returncode == 2 and "SHARED_XFFT_INIT_GATE_PASS" not in result.stdout


def test_fault_xdc_matches_real_dot_joined_generate_hierarchy(tmp_path):
    script = r'''
set matched {}
proc get_cells {args} {
  set pattern [lindex $args end]
  set result {}
  foreach name {
    receiver/acquisition/shared_transform.iq_to_score.realtime_transform.transform_service/input_mailbox/input_fault_reg
    receiver/acquisition/shared_transform.iq_to_score.realtime_transform.transform_service/input_fault_fast_sync_reg[0]
  } {if {[regexp $pattern $name]} {lappend result $name}}
  return $result
}
proc get_pins {args} {return {}}
proc set_false_path {args} {}
proc set_max_delay {args} {
  set start [lindex $args [expr {[lsearch -exact $args -from] + 1}]]
  set stop [lindex $args [expr {[lsearch -exact $args -to] + 1}]]
  if {[llength $start] && [llength $stop]} {
    if {[lindex $args 2] ne "5.000"} {error "wrong sticky fault bound"}
    incr ::matched
  }
}
set matched 0
if {[catch {
  source {XDC}
  if {$matched != 1} {error "sticky source fault constraint matched $matched paths"}
} message]} {puts stderr $message; exit 2}
puts REALTIME_FAULT_XDC_MATCH_PASS
'''.replace("{XDC}", "{" + str(XDC) + "}")
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            cwd=tmp_path, timeout=10, check=False)
    assert result.returncode == 0 and "REALTIME_FAULT_XDC_MATCH_PASS" in result.stdout, result.stderr
