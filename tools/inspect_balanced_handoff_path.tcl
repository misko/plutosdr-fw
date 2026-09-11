# Compare the previous critical endpoint pair without changing constraints.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set from [get_pins -hier -regexp {^owners\[0\]\.result_guard/return_exponent_reg\[2\]/C$}]
set to [get_pins -hier -regexp {^output_bank/request_toggle_reg/D$}]
if {[llength $from]!=1 || [llength $to]!=1} {error "expected original endpoint pair"}
set paths [get_timing_paths -from $from -to $to -max_paths 1 -delay_type max]
if {[llength $paths]!=1} {error "missing original endpoint path"}
report_timing -from $from -to $to -max_paths 1 -delay_type max -file [file join $output original_pair.rpt]
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected"
puts $f "script_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "from=$from\nto=$to\nslack_ns=[get_property SLACK [lindex $paths 0]]"
puts $f "constraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
puts BALANCED_HANDOFF_PATH_RECORDED_NOT_DEPLOYMENT_PROOF
