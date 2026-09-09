"""Executable audit-failure contracts over fake Vivado objects, not CDC proof."""

import hashlib
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
AUDIT = HDL / "projects/pluto/audit_descriptor_bram.tcl"
REVISION = "653a3205bc7bd158a7267a9288beba63aebe12cf"


@pytest.mark.parametrize("broken,error", [
    ("", None),
    ("distributed", "not block RAM"),
    ("missing_bank", "bank count"),
    ("mixed", "retains distributed"),
    ("missing_sync", "three bits per stage"),
    ("unmarked", "unmarked descriptor"),
    ("stage_clock", "different destination clocks"),
    ("waived_sync", "not fully timed"),
    ("sync_bound", "unexpected second-stage"),
    ("bram_clock", "does not match pointer ownership"),
    ("latency", "unexpected port/latency"),
    ("second_register", "unexpected port/latency"),
    ("port_width", "unexpected port/latency"),
    ("extra_port", "unexpected port/latency"),
    ("fusion_profile", "global register-fusion profile"),
    ("waived_read", "lacks its normal timed path"),
    ("waived_register", "fused register enable lacks its normal timed path"),
    ("register_bound", "fused register enable lacks its normal timed path"),
    ("register_source", "no exact-reducer source"),
])
def test_actual_audit_logic_rejects_missing_or_weakened_structure(tmp_path, broken, error):
    checkpoint = tmp_path / "fake.dcp"
    checkpoint.write_bytes(b"MOCK CHECKPOINT NOT REAL FPGA EVIDENCE")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    output = tmp_path / "audit"
    script = r'''
set broken {@BROKEN@}
proc version {args} { return 2022.2 }
proc open_checkpoint {args} {}
proc current_design {} { return design }
proc close_design {} {}
proc report_cdc {args} {}
proc report_exceptions {args} {}
proc report_property {args} {}
proc get_cells {args} {
  set selector [lindex $args end]
  if {[string first {REF_NAME == RAMB18E1} $selector] >= 0} {
    if {$::broken eq "distributed"} { return {} }
    if {$::broken eq "missing_bank"} { return {bram0 bram1} }
    return {bram0 bram1 bram2}
  }
  if {[string first {REF_NAME !~ RAMB*} $selector] >= 0} {
    if {$::broken eq "mixed"} { return lutram }
    return {}
  }
  set found {}
  foreach prefix {read_gray_write write_gray_read} {
    foreach stage {1 2} {
      foreach bit {0 1 2} {
        set name [format {x/i_capture_bridge/i_descriptor_fifo/%s_sync_%s_reg[%s]} $prefix $stage $bit]
        if {[regexp $selector $name] && !($::broken eq "missing_sync" && $bit == 2)} {
          lappend found $name
        }
      }
    }
  }
  return $found
}
proc get_pins {args} {
  set objects [lindex $args [expr {[lsearch -exact $args -of_objects] + 1}]]
  if {[string match bram* $objects]} {
    set filter [lindex $args end]
    if {[string first CLKARDCLK $filter] >= 0} { return ${objects}.read_clock }
    if {[string first CLKBWRCLK $filter] >= 0} { return ${objects}.write_clock }
    if {[string first REGCEAREGCE $filter] >= 0} { return ${objects}.register_enable }
    return ${objects}.read_controls
  }
  return $objects
}
proc get_clocks {args} {
  set object [lindex [lindex $args end] 0]
  if {[string match bram*.write_clock $object]} {
    return [expr {$::broken eq "bram_clock" ? "clk_read" : "clk_write"}]
  }
  if {[string match bram*.read_clock $object] || [string first write_gray_read $object] >= 0} {
    if {$::broken eq "stage_clock" && [string first _sync_2_ $object] >= 0} { return clk_write }
    return clk_read
  }
  return clk_write
}
proc get_property {property object} {
  switch -- $property {
    PART { return xc7z010clg400-1 }
    ASYNC_REG { return [expr {$::broken ne "unmarked"}] }
    PERIOD { return [expr {$object eq "clk_read" ? 10.0 : 16.27}] }
    REQUIREMENT { return [lindex [split $object :] 0] }
    READ_WIDTH_A - WRITE_WIDTH_B {
      if {$::broken eq "port_width"} { return 18 }
      return [expr {$object eq "bram2" && $::broken ne "fusion_profile" ? 36 : 72}]
    }
    READ_WIDTH_B - WRITE_WIDTH_A { return [expr {$::broken eq "extra_port" ? 18 : 0}] }
    DOA_REG - DOB_REG {
      set normal [expr {$object ne "bram2" || $::broken eq "fusion_profile"}]
      if {$::broken eq "latency" || ($::broken eq "second_register" && $property eq "DOB_REG")} {
        return [expr {!$normal}]
      }
      return $normal
    }
    REF_NAME { return [expr {$object eq "bram2" && $::broken ne "fusion_profile" ? "RAMB18E1" : "RAMB36E1"}] }
    default { error "unmodeled property $property" }
  }
}
proc get_timing_paths {args} {
  set destination [lindex $args [expr {[lsearch -exact $args -to] + 1}]]
  if {[string match bram*.register_enable $destination]} {
    if {$::broken eq "waived_register"} { return {} }
    return [expr {$::broken eq "register_bound" ? "20.0:0" : "10.0:0"}]
  }
  if {[string match bram* $destination]} {
    if {$::broken eq "waived_read"} { return {} }
    return 10.0:0
  }
  if {$::broken eq "waived_sync"} { return {} }
  set period [expr {[string first write_gray_read $destination] >= 0 ? 10.0 : 16.27}]
  if {$::broken eq "sync_bound"} { set period 99.0 }
  return [list ${period}:0 ${period}:1 ${period}:2]
}
proc all_fanin {args} {
  if {$::broken eq "register_source"} { return other/FSM/C }
  return x/g_slice_exact_reducer.i_exact_reducer/current_is_better_reg/C
}
set argc 4
set argv [list {@CHECKPOINT@} {@OUTPUT@} @REVISION@ @HASH@]
if {[catch {source {@AUDIT@}} message]} { puts stderr $message; exit 2 }
'''
    for key, value in {"BROKEN": broken, "CHECKPOINT": checkpoint, "OUTPUT": output,
                       "REVISION": REVISION, "HASH": digest, "AUDIT": AUDIT}.items():
        script = script.replace(f"@{key}@", str(value))
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            timeout=10, check=False)
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == digest
    if error:
        assert result.returncode == 2 and error in result.stderr, result
        assert "DESCRIPTOR_BRAM_STRUCTURE_VERIFIED" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "DESCRIPTOR_BRAM_STRUCTURE_VERIFIED" in result.stdout
        assert "physical_timing_CDC_RF_hardware_qualified=false" in (output / "scope.txt").read_text()
