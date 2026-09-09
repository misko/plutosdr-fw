# One fixed physical retry of an existing implementation. No XDC edits.
# Usage: vivado -mode batch -source ... -tclargs COPIED_PROJECT_XPR OUTPUT_ROOT
if {$argc != 2} { error "expected COPIED_PROJECT_XPR OUTPUT_ROOT" }
set project [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set impl [file join [file dirname $project] pluto.runs impl_1]
set sdk [file join [file dirname $project] pluto.sdk]
set_param general.maxThreads 4
open_project $project
open_run impl_1
write_xdc -force $out/constraints_before.xdc
report_clocks -file $out/clocks_before.rpt
report_exceptions -coverage -file $out/exceptions_before.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $out/timing_before.rpt

# The original flow already ran AggressiveExplore. Use alternate replication,
# additional global routing iterations, then one final aggressive physical pass.
phys_opt_design -directive AlternateReplication
report_timing_summary -delay_type min_max -file $out/timing_alternate_replication.rpt
route_design -directive MoreGlobalIterations -tns_cleanup
report_timing_summary -delay_type min_max -file $out/timing_rerouted.rpt
phys_opt_design -directive AggressiveExplore

# open_run and the full-audit script must reopen this exact final checkpoint.
write_checkpoint -force $impl/system_top_postroute_physopt.dcp
write_xdc -force $out/constraints_after.xdc
report_clocks -file $out/clocks_after.rpt
report_exceptions -coverage -file $out/exceptions_after.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $out/timing_after.rpt
report_route_status -file $out/route_after.rpt
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1} { error "missing timing paths" }
set setup_slack [get_property SLACK $setup]
set hold_slack [get_property SLACK $hold]
set f [open $out/retry_result.tsv w]
puts $f "setup_slack_ns\t$setup_slack"
puts $f "hold_slack_ns\t$hold_slack"
puts $f "sequence\tAlternateReplication;MoreGlobalIterations+tns_cleanup;AggressiveExplore"
puts $f "constraints_modified_by_recipe\t0"
close $f
if {$setup_slack < 0 || $hold_slack < 0} { error "physical retry did not close setup and hold timing" }
write_bitstream -force $impl/system_top.bit
write_hw_platform -fixed -include_bit -force -file $sdk/system_top.xsa
close_project
exit
