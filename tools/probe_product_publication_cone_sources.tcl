# Source-specific endpoint measurements; no exceptions or checkpoint mutations.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected CHECKPOINT SHA OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint/output identity"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output endpoints.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
foreach {label source_pattern destination_pattern} {
 handoff_publication *product_bank/metadata_out_hold_reg*/C *product_bank/request_toggle_reg*/D
 capture_kernel *registered_scheduling.engine_metadata_reg*/C *joiner/kernel_rom/expected_next_block_start_reg*/CE
 capture_publication *registered_scheduling.engine_metadata_reg*/C *product_bank/request_toggle_reg*/D
} {
 set sources [get_pins -quiet -hierarchical -filter "NAME =~ $source_pattern"]
 set pins [get_pins -quiet -hierarchical -filter "NAME =~ $destination_pattern"]
 if {![llength $sources] || ![llength $pins]} {error "missing $label source/endpoint"}
 puts $f "$label.sources=[llength $sources]"
 puts $f "$label.pins=[llength $pins]"
 set paths [get_timing_paths -from $sources -to $pins -delay_type max -max_paths 1]
 if {[llength $paths]!=1} {error "missing $label path"}
 puts $f "$label.slack=[get_property SLACK $paths]"
 puts $f "$label.start=[get_property STARTPOINT_PIN $paths]"
 puts $f "$label.end=[get_property ENDPOINT_PIN $paths]"
 report_timing -from $sources -to $pins -delay_type max -max_paths 20 -file [file join $output $label.rpt]
}
close $f
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed"}
puts PUBLICATION_SOURCES_OBSERVED_NOT_FULL_SIGNOFF
