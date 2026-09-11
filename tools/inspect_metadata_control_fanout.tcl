# Read-only control-fanout diagnosis of the same routed checkpoint.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set f [open [file join $output control_fanout.txt] {WRONLY CREAT EXCL}]
foreach bank {source_bank output_bank} {
  foreach name {request_sync acknowledge_sync} {
    set stage0 [get_cells -hier -regexp [format {^%s/%s_reg\[0\]$} $bank $name]]
    set stage1 [get_cells -hier -regexp [format {^%s/%s_reg\[1\]$} $bank $name]]
    if {[llength $stage0]!=1 || [llength $stage1]!=1} {error "missing synchronizer stage"}
    set q [get_pins -of_objects $stage0 -filter {REF_PIN_NAME == Q}]
    set endpoints [all_fanout -flat -endpoints_only -from $q]
    puts $f "$bank.$name.stage0=$stage0"
    puts $f "$bank.$name.stage1=$stage1"
    puts $f "$bank.$name.stage0_async_reg=[get_property ASYNC_REG $stage0]"
    puts $f "$bank.$name.stage1_async_reg=[get_property ASYNC_REG $stage1]"
    puts $f "$bank.$name.endpoints=[lsort $endpoints]"
    report_timing -from $q -max_paths 30 -file [file join $output ${bank}_${name}_fanout.rpt]
  }
}
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected"
puts $f "script_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "constraints_changed=false\nruntime_changed=false\nphysical_signoff=false"
close $f
puts CONTROL_FANOUT_INSPECTION_PASS_NO_CONSTRAINT_CHANGE
