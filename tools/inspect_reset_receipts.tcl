# Read-only structural gate after actual FFT and unchanged-constraint routing.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set f [open [file join $output controls.txt] {WRONLY CREAT EXCL}]
foreach bank {source_bank output_bank} {
  foreach name {request_sync acknowledge_sync} {
    set stage0 [get_cells -hier -regexp [format {^%s/%s_reg\[0\]$} $bank $name]]
    set stage1 [get_cells -hier -regexp [format {^%s/%s_reg\[1\]$} $bank $name]]
    if {[llength $stage0]!=1 || [llength $stage1]!=1} {error "missing synchronizer stage"}
    foreach cell [list $stage0 $stage1] {
      if {[get_property ASYNC_REG $cell] ne "1"} {error "missing ASYNC_REG"}
    }
    set q [get_pins -of_objects $stage0 -filter {REF_PIN_NAME == Q}]
    set endpoints [lsort [all_fanout -flat -endpoints_only -from $q]]
    set required [get_pins -of_objects $stage1 -filter {REF_PIN_NAME == D}]
    puts $f "$bank.$name.endpoints=$endpoints"
    if {[llength $endpoints]!=1 || [lindex $endpoints 0] ne $required} {error "first stage has non-synchronizer fanout"}
  }
}
set flag [get_cells -hier -regexp {^epoch_barrier/slow_purged_reg$}]
set sync0 [get_cells -hier -regexp {^epoch_barrier/slow_purge_fast_reg\[0\]$}]
set sync1 [get_cells -hier -regexp {^epoch_barrier/slow_purge_fast_reg\[1\]$}]
if {[llength $flag]!=1 || [llength $sync0]!=1 || [llength $sync1]!=1} {error "missing registered purge crossing"}
set starts [all_fanin -flat -startpoints_only -only_cells -to [get_pins -of_objects $sync0 -filter {REF_PIN_NAME == D}]]
if {[llength $starts]!=1 || [lindex $starts 0] ne $flag} {error "purge source is not the single registered flag"}
set source_net [get_nets -of_objects [get_pins -of_objects $flag -filter {REF_PIN_NAME == Q}]]
set dest_net [get_nets -of_objects [get_pins -of_objects $sync0 -filter {REF_PIN_NAME == D}]]
if {$source_net ne $dest_net} {error "combinational logic on purge crossing"}
foreach cell [list $sync0 $sync1] {
  if {[get_property ASYNC_REG $cell] ne "1"} {error "purge synchronizer attribute"}
}
puts $f "purge.source=$flag"
puts $f "purge.destination=$sync0"
puts $f "purge.direct_net=$source_net"
close $f
report_cdc -details -file [file join $output cdc.rpt]
report_exceptions -file [file join $output exceptions.rpt]
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected"
puts $f "script_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "first_stage_fanout_clean=true\npurge_source_registered=true\nconstraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts RESET_RECEIPT_STRUCTURE_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE
