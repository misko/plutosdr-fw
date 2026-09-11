# Observe real register endpoints without changing checkpoint or constraints.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected ROUTED_DCP SHA NEW_OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "unapproved checkpoint or existing output"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output endpoints.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
foreach {label pattern} {
  occupancy *product_identity_stage/full_reg/D
  identity *product_identity_stage/output_identity_good_reg/D
} {
  set pins [get_pins -quiet -hierarchical -filter "NAME =~ $pattern"]
  if {[llength $pins] != 1} {error "missing or ambiguous $label endpoint"}
  set paths [get_timing_paths -to $pins -delay_type max -max_paths 1]
  if {[llength $paths] != 1} {error "missing $label timing path"}
  puts $f "$label.slack=[get_property SLACK $paths]"
  puts $f "$label.start=[get_property STARTPOINT_PIN $paths]"
  puts $f "$label.end=[get_property ENDPOINT_PIN $paths]"
  report_timing -to $pins -delay_type max -max_paths 20 -file [file join $output $label.rpt]
}
close $f
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed during observation"}
puts PRODUCT_RETIREMENT_ENDPOINTS_OBSERVED_NOT_FULL_SIGNOFF
