# Read-only audit of a completed GLRT board implementation, including failures.
# Usage: vivado -mode batch -source ... -tclargs PROJECT_XPR NEW_REPORT_DIRECTORY
if {$argc != 2} { error "expected PROJECT_XPR NEW_REPORT_DIRECTORY" }
set project [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} { error "report directory already exists: $out" }
file mkdir $out
set_param general.maxThreads 4
open_project $project
open_run impl_1
report_utilization -hierarchical -file $out/utilization_hierarchical.rpt
report_utilization -file $out/utilization.rpt
report_route_status -file $out/route_status.rpt
report_timing_summary -delay_type min_max -report_unconstrained \
  -check_timing_verbose -max_paths 20 -file $out/timing_summary.rpt
report_timing -delay_type max -max_paths 100 -nworst 2 \
  -path_type full_clock_expanded -input_pins -file $out/setup_paths.rpt
report_timing -delay_type min -max_paths 100 -nworst 2 \
  -path_type full_clock_expanded -input_pins -file $out/hold_paths.rpt
report_cdc -details -file $out/cdc.rpt
report_clock_interaction -file $out/clock_interaction.rpt
report_clocks -file $out/clocks.rpt
report_bus_skew -file $out/bus_skew.rpt
report_exceptions -ignored -file $out/ignored_exceptions.rpt
report_exceptions -coverage -file $out/exception_coverage.rpt
report_drc -file $out/drc.rpt
report_methodology -file $out/methodology.rpt
report_io -file $out/io.rpt
set f [open $out/cells.tsv w]
puts $f "name\tref_name\torig_ref_name"
set forbidden {}
set native_dma {}
set glrt {}
set glrt_dma {}
set native_engines {}
set native_schedules {}
set native_result_queues {}
set legacy_correlators {}
set legacy_scorers {}
set legacy_vector_stages {}
set local_controls {}
set local_engines {}
set local_cadences {}
set tracking_controls {}
set acquisition_engines {}
foreach cell [get_cells -hierarchical] {
  set name [get_property NAME $cell]
  set ref [get_property REF_NAME $cell]
  set orig [get_property ORIG_REF_NAME $cell]
  puts $f "$name\t$ref\t$orig"
  if {[regexp -nocase {pss} "$name $ref $orig"]} { lappend forbidden $name }
  if {[string match *axi_ad9361_adc_dma* $name]} { lappend native_dma $name }
  if {[string match *axi_starlink_glrt* $ref] || [string match *axi_starlink_glrt* $orig]} { lappend glrt $name }
  if {[string match */starlink_glrt_dma $name]} { lappend glrt_dma $name }
  if {[string match starlink_glrt_native_engine* $ref] || [string match starlink_glrt_native_engine* $orig]} {
    lappend native_engines $name
  }
  foreach {base destination} {starlink_glrt_native_schedule_control native_schedules starlink_glrt_native_result_queue native_result_queues} {
    if {[string match ${base}* $ref] || [string match ${base}* $orig]} { lappend $destination $name }
  }
  foreach {base destination} {starlink_glrt_correlator legacy_correlators starlink_glrt_score legacy_scorers starlink_glrt_vector_stage legacy_vector_stages} {
    if {[string match ${base}* $ref] || [string match ${base}* $orig]} {
      lappend $destination $name
    }
  }
  foreach {base destination} {starlink_glrt_local_control local_controls starlink_glrt_local_search local_engines starlink_glrt_local_cadence local_cadences} {
    if {[string match ${base}* $ref] || [string match ${base}* $orig]} { lappend $destination $name }
  }
  foreach {base destination} {starlink_glrt_tracking_control tracking_controls starlink_glrt_acquisition acquisition_engines} {
    if {[string match ${base}* $ref] || [string match ${base}* $orig]} { lappend $destination $name }
  }
}
close $f
set maxpath [get_timing_paths -delay_type max -max_paths 1]
set minpath [get_timing_paths -delay_type min -max_paths 1]
if {[llength $maxpath] != 1 || [llength $minpath] != 1} { error "missing timing paths" }
set f [open $out/audit.tsv w]
puts $f "project\t$project"
puts $f "part\t[get_property PART [current_project]]"
puts $f "setup_slack_ns\t[get_property SLACK $maxpath]"
puts $f "hold_slack_ns\t[get_property SLACK $minpath]"
puts $f "pss_cells\t[llength $forbidden]"
puts $f "native_dma_cells\t[llength $native_dma]"
puts $f "glrt_ip_cells\t[llength $glrt]"
puts $f "glrt_dma_cells\t[llength $glrt_dma]"
puts $f "native_refinement_engines\t[llength $native_engines]"
puts $f "native_schedule_controls\t[llength $native_schedules]"
puts $f "native_result_queues\t[llength $native_result_queues]"
puts $f "legacy_correlators\t[llength $legacy_correlators]"
puts $f "legacy_scorers\t[llength $legacy_scorers]"
puts $f "legacy_vector_stages\t[llength $legacy_vector_stages]"
puts $f "local_search_controls\t[llength $local_controls]"
puts $f "local_search_engines\t[llength $local_engines]"
puts $f "local_search_cadences\t[llength $local_cadences]"
puts $f "tracking_controls\t[llength $tracking_controls]"
puts $f "acquisition_engines\t[llength $acquisition_engines]"
puts $f "hardware_eligible\t0"
puts $f "qualification\tTiming, CDC, I/O and exception reports require review; audit alone grants no deployment."
close $f
if {[llength $forbidden] || [llength $native_dma] || ![llength $glrt] || [llength $glrt_dma] != 1} {
  error "GLRT-only implemented-netlist gate failed; inspect audit.tsv and cells.tsv"
}
close_project
exit
