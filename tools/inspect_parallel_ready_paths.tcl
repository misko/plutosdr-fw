# Read-only queries of the previously failing reset-release cone.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
foreach {label source_pattern destination_pattern} {
  release_fault {^epoch_barrier/fast_release_reg/C$} {^fast_fault_reg/D$}
  release_rom {^epoch_barrier/fast_release_reg/C$} {^joiner/kernel_rom/output_valid_reg/D$}
  release_request {^epoch_barrier/fast_release_reg/C$} {^output_bank/request_toggle_reg/D$}
  metadata_fault {^product_bank/metadata_out_hold_reg\[34\]/C$} {^fast_fault_reg/D$}
} {
  set from [get_pins -hier -regexp $source_pattern]
  set to [get_pins -hier -regexp $destination_pattern]
  if {[llength $from]!=1 || [llength $to]!=1} {error "original endpoints missing: $label"}
  set paths [get_timing_paths -quiet -from $from -to $to -max_paths 1 -delay_type max]
  puts $f "$label.source=$from\n$label.destination=$to\n$label.path_count=[llength $paths]"
  if {[llength $paths]==1} {
    puts $f "$label.slack_ns=[get_property SLACK [lindex $paths 0]]"
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
puts PARALLEL_READY_PATHS_RECORDED_NOT_DEPLOYMENT_PROOF
