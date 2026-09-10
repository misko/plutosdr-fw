# Measure the narrow result RAM and every internal path with registered I/O.
if {$argc != 1 || [version -short] ne "2022.2"} { error "requires Vivado 2022.2 and fresh output path" }
set output [file normalize [lindex $argv 0]]
if {[file exists $output]} { error "output exists" }
file mkdir $output
set repo [file dirname [file dirname [file normalize [info script]]]]
set rtl $repo/hdl/library/starlink_glrt/starlink_glrt_native_result_queue.v
set wrapper $repo/tools/starlink_glrt_native_queue_ooc_wrapper.v
set sources [list $rtl $wrapper [file normalize [info script]]]
foreach path $sources { set hashes($path) [lindex [exec sha256sum $path] 0] }
set_param general.maxThreads 4
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
read_verilog [list $rtl $wrapper]
synth_design -top starlink_glrt_native_queue_ooc_wrapper -mode out_of_context \
  -flatten_hierarchy none -directive AreaOptimized_high
create_clock -name queue_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks queue_clk]
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
  error "queue DRC failed"
}
set lut [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME == RAMB18E1}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$lut>600 || $ff>250 || 2*$ram36+$ram18!=4 || $dsp!=0 || $setup<0 || $hold<0} {
  error "queue resource/timing gate: LUT=$lut FF=$ff RAM36=$ram36 RAM18=$ram18 DSP=$dsp setup=$setup hold=$hold"
}
foreach path $sources {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
}
write_checkpoint $output/routed.dcp
set fd [open $output/summary.txt {WRONLY CREAT EXCL}]
puts $fd "scope=registered_queue_component_not_complete_board"
puts $fd "clock_mhz=100\nclock_uncertainty_ns=0.1\nexternal_fixture_io_timing=excluded"
puts $fd "lut=$lut\nff=$ff\nramb36=$ram36\nramb18=$ram18\ndsp=$dsp\nsetup_ns=$setup\nhold_ns=$hold"
foreach path $sources { puts $fd "$path=$hashes($path)" }
close $fd
puts "NATIVE_QUEUE_OOC_PASS"
close_project
exit
