# Read-only, replica-inclusive descriptor -> private write progress queries.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source expected output
if {[file exists $output] || [lindex [exec sha256sum $source] 0] ne $expected} {error "fresh output/source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source
set descriptors {};set counters {}
foreach cell [get_cells -hier -regexp {^descriptor_reg.*$}] {
  if {[string match "FD*" [get_property REF_NAME $cell]]} {lappend descriptors $cell}
}
foreach cell [get_cells -hier -regexp {^write_count_reg.*$}] {
  if {[string match "FD*" [get_property REF_NAME $cell]]} {lappend counters $cell}
}
if {[llength $descriptors]<70 || [llength $counters]<10} {error "missing descriptor or counter register inventory"}
set starts [get_pins -of_objects $descriptors -filter {REF_PIN_NAME == C}]
set ends [get_pins -of_objects $counters -filter {REF_PIN_NAME == D || REF_PIN_NAME == CE || REF_PIN_NAME == R || REF_PIN_NAME == CLR}]
if {[llength $starts]!=[llength $descriptors] || [llength $ends]<[llength $counters]} {error "incomplete register pins"}
set paths [get_timing_paths -quiet -from $starts -to $ends -max_paths 1 -delay_type max]
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
puts $f "descriptor_cells=[lsort $descriptors]\ncounter_cells=[lsort $counters]\npath_count=[llength $paths]"
if {[llength $paths]==1} {
  set p [lindex $paths 0]
  puts $f "start=[get_property STARTPOINT_PIN $p]\nend=[get_property ENDPOINT_PIN $p]\nslack_ns=[get_property SLACK $p]"
  report_timing -from $starts -to $ends -max_paths 1 -delay_type max -file [file join $output descriptor_capture.rpt]
}
close $f
close_design
if {[lindex [exec sha256sum $source] 0] ne $expected} {error "DCP changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "constraints_changed=false\nreceiver_integration=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts PRIVATE_CAPTURE_PATHS_RECORDED_NOT_INTEGRATION_SIGNOFF
