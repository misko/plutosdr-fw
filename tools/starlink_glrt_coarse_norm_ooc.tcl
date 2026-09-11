# Registered component feasibility only; not a complete-board timing claim.
if {$argc != 1 || [version -short] ne "2022.2"} { error "requires Vivado 2022.2 and fresh output path" }
set output [file normalize [lindex $argv 0]]
if {[file exists $output]} { error "output exists" }
file mkdir $output
set repo [file dirname [file dirname [file normalize [info script]]]]
set rtl $repo/hdl/library/starlink_glrt/starlink_glrt_coarse_norm.v
set wrapper $repo/tools/starlink_glrt_coarse_norm_ooc_wrapper.v
set sources [list $rtl $wrapper [file normalize [info script]]]
foreach path $sources { set hashes($path) [lindex [exec sha256sum $path] 0] }
set_param general.maxThreads 4
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
read_verilog -sv [list $rtl $wrapper]
synth_design -top starlink_glrt_coarse_norm_ooc_wrapper -mode out_of_context \
  -flatten_hierarchy none -directive AreaOptimized_high
create_clock -name coarse_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks coarse_clk]
set_false_path -from [get_ports stimulus*]
set_false_path -to [all_outputs]
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file $output/utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $output/timing.rpt
report_drc -file $output/drc.rpt
check_timing -verbose -file $output/check_timing.rpt
set fd [open $output/check_timing.rpt r]; set checks [read $fd]; close $fd
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
  error "normalization DRC failed"
}
set lut [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set fd [open $output/summary.txt {WRONLY CREAT EXCL}]
puts $fd "scope=registered_coarse_normalization_component_not_complete_board"
puts $fd "latency_clocks=48\ninitiation_interval_clocks=1\nclock_mhz=100"
puts $fd "lut=$lut\nff=$ff\ndsp=$dsp\nsetup_ns=$setup\nhold_ns=$hold"
foreach path $sources {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
  puts $fd "$path=$hashes($path)"
}
close $fd
write_checkpoint $output/routed.dcp
if {$lut>5000 || $ff>8000 || $dsp!=0 || $setup<0 || $hold<0} {
  error "normalization resource/timing gate: LUT=$lut FF=$ff DSP=$dsp setup=$setup hold=$hold"
}
puts "COARSE_NORM_OOC_PASS"
close_project
exit
