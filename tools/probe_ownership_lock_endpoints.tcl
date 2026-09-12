# Same checkpoint, no clock or timing-exception changes.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected ROUTED_DCP SHA NEW_OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "unapproved checkpoint or existing output"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output endpoints.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
puts $f "design=[current_design]"
foreach {label pattern minimum maximum} {
 guard_reasons *result_guard/fault_reasons_reg*/D 16 17
 admission_snapshot_valid *admission_gate/snapshot_valid_reg/D 1 1
 admission_snapshot_good_d *admission_gate/*snapshot_good_reg*/D 1 36
 admission_snapshot_good_ce *admission_gate/*snapshot_good_reg*/CE 1 36
 guard_active *result_guard/active_private_reg/D 2 2
 admission_consumed *admission_gate/consumed_reg/D 1 1
 fast_fault *fast_fault_reg/D 1 1
} {
 set pins [get_pins -quiet -hierarchical -filter "NAME =~ $pattern"]
 if {[llength $pins] < $minimum || [llength $pins] > $maximum} {error "missing or ambiguous $label endpoint"}
 if {$label eq "guard_reasons"} {
  set original_pins [get_pins -quiet -hierarchical -filter {NAME =~ *result_guard/fault_reasons_reg*/D && NAME !~ *_replica*}]
  if {[llength $original_pins] != 16} {error "expected all sixteen original guard diagnostic registers"}
 }
 puts $f "$label.pins=[llength $pins]"
 foreach p [lsort $pins] {puts $f "$label.pin=$p"}
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
puts RETRY_ADMISSION_ENDPOINTS_OBSERVED_NOT_FULL_SIGNOFF
