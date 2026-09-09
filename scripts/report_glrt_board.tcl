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
puts $f "hardware_eligible\t0"
puts $f "qualification\tTiming, CDC, I/O and exception reports require review; audit alone grants no deployment."
close $f
if {[llength $forbidden] || [llength $native_dma] || ![llength $glrt] || [llength $glrt_dma] != 1} {
  error "GLRT-only implemented-netlist gate failed; inspect audit.tsv and cells.tsv"
}
close_project
exit
