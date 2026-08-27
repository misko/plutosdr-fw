# Routed out-of-context release gate for the complete TAG2 control surface.
# The shell launcher creates and owns the fresh output directory, verifies the
# exact Vivado version and records the source hashes.  Keep every report inside
# that directory so stale shared /tmp reports can never satisfy this gate.

if {$argc != 1} {
  error "usage: axi_ooc.tcl <fresh-output-directory>"
}

set part xc7z010clg400-1
set top tandem_agc_axi
set source_dir [file normalize [file dirname [info script]]]
set output_dir [file normalize [lindex $argv 0]]

if {![file isdirectory $output_dir]} {
  error "output directory does not exist: $output_dir"
}

set rtl_sources [list \
  [file join $source_dir tandem_cdc_lib.v] \
  [file join $source_dir tandem_agc_core.v] \
  [file join $source_dir tandem_agc_axi.v]]
set constraints [file join $source_dir tandem_agc_axi.xdc]
foreach input [concat $rtl_sources [list $constraints]] {
  if {![file isfile $input]} {
    error "required OOC input is missing: $input"
  }
}

# The release gate must exercise the production defaults, not override a
# changed declaration back to the expected values at synthesis time.
set axi_source [open [file join $source_dir tandem_agc_axi.v] r]
set axi_text [read $axi_source]
close $axi_source
# Remove Verilog comments before matching declarations so an exact-looking
# parameter inside a disabled comment cannot mask a changed live default.
regsub -all {(?s)/\*.*?\*/} $axi_text {} axi_code
regsub -all {//[^\r\n]*} $axi_code {} axi_code
foreach {parameter pattern} {
  EVT_AW {^[ \t]*parameter[ \t]+integer[ \t]+EVT_AW[ \t]*=[ \t]*6,[ \t]*$}
  EVT_DW {^[ \t]*parameter[ \t]+integer[ \t]+EVT_DW[ \t]*=[ \t]*128,[ \t]*$}
  EVENTS {^[ \t]*parameter[ \t]+integer[ \t]+EVENTS[ \t]*=[ \t]*1[ \t]*$}
} {
  if {[regexp -all -line -- $pattern $axi_code] != 1} {
    error "production event parameter is not exact: $parameter"
  }
}

create_project -in_memory -part $part
read_verilog {*}$rtl_sources
read_xdc $constraints
synth_design -top $top -part $part -mode out_of_context

set all_clocks [get_clocks]
if {[llength $all_clocks] != 2} {
  error "OOC design must contain exactly two clocks: $all_clocks"
}
set axi_clock [get_clocks s_axi_aclk]
set rx_clock [get_clocks l_clk]
if {[llength $axi_clock] != 1 || [llength $rx_clock] != 1} {
  error "OOC clock names are not exact"
}
if {[expr {abs([get_property PERIOD $axi_clock] - 10.000)}] > 0.000001 ||
    [expr {abs([get_property PERIOD $rx_clock] - 16.276)}] > 0.000001} {
  error "OOC clock periods are not exact"
}

opt_design
place_design
phys_opt_design
route_design

set all_cells [get_cells -hierarchical]
if {[llength $all_cells] == 0} {
  error "OOC design contains no cells"
}
set black_boxes [filter $all_cells {IS_BLACKBOX == 1}]
if {[llength $black_boxes] != 0} {
  error "OOC design contains black boxes: $black_boxes"
}

set setup_path [get_timing_paths -delay_type max -max_paths 1]
set hold_path [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_path] != 1 || [llength $hold_path] != 1} {
  error "OOC design lacks a setup or hold timing path"
}
set setup_slack [get_property SLACK $setup_path]
set hold_slack [get_property SLACK $hold_path]
if {$setup_slack < 0 || $hold_slack < 0} {
  error "OOC design has negative setup or hold slack"
}

report_utilization -file [file join $output_dir utilization.rpt]
report_cdc -no_waiver -file [file join $output_dir cdc-summary.rpt]
report_cdc -details -no_waiver -file [file join $output_dir cdc-details.rpt]
report_clock_interaction -file [file join $output_dir clock_interaction.rpt]
report_route_status -file [file join $output_dir route_status.rpt]
report_drc -ruledeck default -no_waivers -file [file join $output_dir drc.rpt]
report_methodology -no_waivers -file [file join $output_dir methodology.rpt]
report_timing_summary -delay_type min_max -max_paths 50 \
  -report_unconstrained -check_timing_verbose \
  -file [file join $output_dir timing_summary.rpt]
write_checkpoint -force [file join $output_dir tandem_agc_axi_routed.dcp]

set route_file [open [file join $output_dir route_status.rpt] r]
set route_text [read $route_file]
close $route_file
if {![regexp {# of routable nets[^0-9]*([0-9]+)} $route_text _ routable_nets] ||
    ![regexp {# of fully routed nets[^0-9]*([0-9]+)} $route_text _ fully_routed_nets] ||
    ![regexp {# of nets with routing errors[^0-9]*([0-9]+)} $route_text _ route_errors] ||
    $routable_nets == 0 || $fully_routed_nets != $routable_nets ||
    $route_errors != 0} {
  error "OOC route status is not complete and error-free"
}

set all_waivers [get_waivers]
if {[llength $all_waivers] != 0} {
  error "OOC design contains waivers: $all_waivers"
}
if {[get_msg_config -count -severity {CRITICAL WARNING}] != 0 ||
    [get_msg_config -count -severity ERROR] != 0} {
  error "Vivado emitted an error or critical-warning message"
}

puts "=== TANDEM AXI ROUTE COMPLETE ==="
