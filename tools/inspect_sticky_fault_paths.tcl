# Same queries on scalar parent and distributed candidate, read-only.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set fault_cells {}
foreach cell [get_cells -hier -regexp {^((sticky_fault_causes\[[0-9]+\]\.)?sticky_fault_latched_reg.*|fast_fault_reg.*)$}] {
  if {[string match "FD*" [get_property REF_NAME $cell]]} {lappend fault_cells $cell}
}
if {[llength $fault_cells]<1} {error "missing scalar or generated fault capture cells"}
set fault_d [get_pins -of_objects $fault_cells -filter {REF_PIN_NAME == D}]
set fault_c [get_pins -of_objects $fault_cells -filter {REF_PIN_NAME == C}]
set fft_source [get_pins -hier -regexp {^shared_xfft/U0/i_synth/axi_wrapper/flushing_reg/C$}]
if {[llength $fault_cells]<1 || [llength $fault_c]!=[llength $fault_cells] || [llength $fault_d]!=[llength $fault_cells] || [llength $fft_source]!=1} {error "complete fault-register inventory required"}
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
puts $f "fault_cells=[lsort $fault_cells]\nfault_count=[llength $fault_cells]"
foreach {label from to} [list fft_to_fault $fft_source $fault_d fault_to_island $fault_c [get_clocks island_175]] {
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
puts STICKY_FAULT_PATHS_RECORDED_NOT_PHYSICAL_SIGNOFF
