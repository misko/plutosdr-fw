# Query the measured handoff and product-position cones; no constraints change.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
foreach {label source_pattern destination_pattern} {
  handoff_ack {^owners\[1\]\.result_guard/return_exponent_reg.*$} {^owners\[0\]\.result_guard/awaiting_ack_reg/D$}
  handoff_active {^owners\[1\]\.result_guard/return_exponent_reg.*$} {^owners\[0\]\.result_guard/active_private_reg/D$}
  position_active {^product_identity_stage/output_position_reg.*$} {^owners\[0\]\.result_guard/active_private_reg/D$}
  handoff_fault {^owners\[1\]\.result_guard/return_exponent_reg.*$} {^fast_fault_reg/D$}
} {
  set cells [get_cells -hier -regexp $source_pattern]
  set from [get_pins -of_objects $cells -filter {REF_PIN_NAME == C}]
  set to [get_pins -hier -regexp $destination_pattern]
  if {[llength $from]<1 || [llength $to]!=1} {error "missing source or destination $label"}
  puts $f "$label.source_cells=[lsort $cells]\n$label.source_count=[llength $cells]"
  set paths [get_timing_paths -quiet -from $from -to $to -max_paths 1 -delay_type max]
  puts $f "$label.path_count=[llength $paths]"
  if {[llength $paths]==1} {
    set p [lindex $paths 0]
    puts $f "$label.start=[get_property STARTPOINT_PIN $p]\n$label.end=[get_property ENDPOINT_PIN $p]\n$label.slack_ns=[get_property SLACK $p]"
    report_timing -from $from -to $to -max_paths 1 -delay_type max -file [file join $output ${label}.rpt]
  }
}
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "constraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts FORWARD_FINAL_PATHS_RECORDED_NOT_PHYSICAL_SIGNOFF
