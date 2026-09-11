# Query all replicas; an absent path from the original cell is not a cut.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set cells [get_cells -hier -regexp {^epoch_barrier/fast_release_reg.*$}]
if {[llength $cells]<2} {error "expected original and replicated release registers"}
set from [get_pins -of_objects $cells -filter {REF_PIN_NAME == C}]
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
puts $f "source_cells=[lsort $cells]\nsource_count=[llength $cells]"
foreach {label destination_pattern} {
  release_fault {^fast_fault_reg/D$}
  release_rom {^joiner/kernel_rom/output_valid_reg/D$}
  release_request {^output_bank/request_toggle_reg/D$}
  release_protocol {^joiner/kernel_rom/protocol_fault_reg/D$}
} {
  set to [get_pins -hier -regexp $destination_pattern]
  if {[llength $to]!=1} {error "missing destination $label"}
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
puts RELEASE_REPLICAS_INSPECTED_NO_PATH_REMOVAL_CLAIM
