# Bounded full-pilot reduction alone; this is not complete-receiver timing proof.
# Usage: vivado -mode batch -source THIS -tclargs FRESH_OUTPUT_DIRECTORY
if {$argc != 1} { error "expected one absolute output directory" }
if {[version -short] ne "2022.2"} { error "requires Vivado 2022.2" }
set output_dir [file normalize [lindex $argv 0]]
set repo [file dirname [file dirname [file normalize [info script]]]]
set source_file [file join $repo hdl library starlink_glrt starlink_glrt_local_moments.v]
set wrapper_file [file join $repo tools starlink_glrt_local_moments_ooc_wrapper.v]
if {[file exists [file join $output_dir summary.txt]]} { error "output already completed" }
file mkdir $output_dir
set source_digest [lindex [exec sha256sum $source_file] 0]
set wrapper_digest [lindex [exec sha256sum $wrapper_file] 0]
create_project -in_memory -part xc7z010clg400-1
read_verilog $source_file
read_verilog $wrapper_file
synth_design -top starlink_glrt_local_moments_ooc_wrapper -mode out_of_context -flatten_hierarchy none
create_clock -name moment_clk -period 10.0 [get_ports clk]
# Match the FCLK0 buffer site in the retained full-receiver routed checkpoint.
# OOC clock delay/skew is otherwise explicitly unqualified by Vivado 38-242.
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks moment_clk]
set data_inputs [lsearch -all -inline -not -exact [all_inputs] [get_ports clk]]
# Only the fixture's external ports are excluded. Every DUT input is driven by
# a real launch FF and every DUT output terminates in a real capture FF; all
# those boundary and internal paths retain the same 10 ns setup/hold checks.
set_false_path -from $data_inputs
set_false_path -to [all_outputs]
opt_design
place_design
phys_opt_design
route_design
report_utilization -file [file join $output_dir utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output_dir timing_summary.rpt]
report_drc -file [file join $output_dir drc.rpt]
check_timing -verbose -file [file join $output_dir check_timing.rpt]
set checks_file [open [file join $output_dir check_timing.rpt] r]
set checks_text [read $checks_file]
close $checks_file
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks_text]} {
    error "local moment timing coverage failed: $check"
  }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]] != 0} {
  error "local moment route has an error or critical DRC warning"
}
write_checkpoint [file join $output_dir routed.dcp]
report_utilization -cells [get_cells dut] -file [file join $output_dir dut_utilization.rpt]
set lut_count [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff_count [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp_count [llength [get_cells -quiet -hier -filter {REF_NAME == DSP48E1}]]
set bram_count [llength [get_cells -quiet -hier -filter {REF_NAME =~ RAMB*}]]
set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_path] != 1 || [llength $hold_path] != 1} {
  error "missing constrained setup or hold path"
}
set setup [get_property SLACK $setup_path]
set hold [get_property SLACK $hold_path]
if {$lut_count > 1000 || $ff_count > 1250 || $dsp_count != 0 || $bram_count != 0} {
  error "local moment budget exceeded: LUT=$lut_count FF=$ff_count DSP=$dsp_count BRAM=$bram_count"
}
if {$setup < 0 || $hold < 0} { error "100 MHz local moment timing failed: setup=$setup hold=$hold" }
if {[lindex [exec sha256sum $source_file] 0] ne $source_digest} { error "source changed during build" }
if {[lindex [exec sha256sum $wrapper_file] 0] ne $wrapper_digest} { error "wrapper changed during build" }
set report [open [file join $output_dir summary.txt] {WRONLY CREAT EXCL}]
puts $report "scope=out_of_context_routed_local_moment_reduction_with_registered_boundaries"
puts $report "part=xc7z010clg400-1"
puts $report "vivado=2022.2"
puts $report "source_sha256=$source_digest"
puts $report "wrapper_sha256=$wrapper_digest"
puts $report "sample_count=79200"
puts $report "clock_mhz=100"
puts $report "clock_source_site=BUFGCTRL_X0Y0"
puts $report "external_fixture_io_timing=excluded"
puts $report "dut_port_timing=real_same_clock_launch_and_capture_registers"
puts $report "clock_uncertainty_ns=0.1"
puts $report "lut_cells=$lut_count"
puts $report "ff_cells=$ff_count"
puts $report "dsp48e1=$dsp_count"
puts $report "bram_cells=$bram_count"
puts $report "setup_wns_ns=$setup"
puts $report "hold_whs_ns=$hold"
puts $report "complete_receiver_qualified=false"
close $report
puts "STARLINK_LOCAL_MOMENTS_OOC_PASS LUT=$lut_count FF=$ff_count setup=$setup hold=$hold"
close_design
close_project
