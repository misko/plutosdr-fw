# Component feasibility, including real coefficient ROMs and IQ sample RAM.
if {$argc ni {2 3} || [version -short] ne "2022.2"} { error "requires Vivado 2022.2, fresh output, ROM directory, optional grid/search" }
set mode grid
if {$argc==3} { set mode [lindex $argv 2] }
if {$mode ni {grid search}} { error "invalid mode" }
set output [file normalize [lindex $argv 0]]
set roms [file normalize [lindex $argv 1]]
if {[file exists $output]} { error "output exists" }
file mkdir $output
set repo [file dirname [file dirname [file normalize [info script]]]]
set sources [list]
set modules {window mac6 norm}
set wrapper_name window
set ram_limit 36
set lut_limit 7500
if {$mode eq "search"} {
  lappend modules peaks search
  set wrapper_name search
  set ram_limit 40
  set lut_limit 8500
}
foreach name $modules {
  lappend sources $repo/hdl/library/starlink_glrt/starlink_glrt_coarse_$name.v
}
lappend sources $repo/tools/starlink_glrt_coarse_${wrapper_name}_ooc_wrapper.v
set tracked [concat $sources [list [file normalize [info script]] \
    $roms/coarse_upper_q9.mem $roms/coarse_upper_energy.mem $roms/manifest.json]]
foreach path $tracked { set hashes($path) [lindex [exec sha256sum $path] 0] }
file mkdir $output/source-snapshot
foreach path $tracked { file copy $path $output/source-snapshot/[file tail $path] }
set fd [open $output/build-environment.txt {WRONLY CREAT EXCL}]
puts $fd "vivado=[version -short]\nos=[exec uname -a]"
foreach key {LD_PRELOAD LD_LIBRARY_PATH TMPDIR} {
  if {[info exists ::env($key)]} { puts $fd "$key=$::env($key)" }
}
if {[info exists ::env(LD_PRELOAD)] && [file isfile $::env(LD_PRELOAD)]} {
  puts $fd "allocator_sha256=[lindex [exec sha256sum $::env(LD_PRELOAD)] 0]"
}
close $fd
set_param general.maxThreads 1
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
cd $roms
read_verilog -sv $sources
synth_design -top starlink_glrt_coarse_${wrapper_name}_ooc_wrapper -mode out_of_context \
  -flatten_hierarchy rebuilt -directive Default
create_clock -name coarse_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks coarse_clk]
set_false_path -from [get_ports stimulus*]
set_false_path -to [all_outputs]
report_utilization -hierarchical -file $output/synthesis_utilization.rpt
write_checkpoint $output/synthesized.dcp
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file $output/utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $output/timing.rpt
report_drc -file $output/drc.rpt
check_timing -verbose -file $output/check_timing.rpt
set fd [open $output/check_timing.rpt r];set checks [read $fd];close $fd
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
  error "coarse window DRC failed"
}
set lut [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME == RAMB18E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set fd [open $output/summary.txt {WRONLY CREAT EXCL}]
puts $fd "scope=buffered_coarse_${mode}_component_not_complete_board"
puts $fd "clock_mhz=100\nlut=$lut\nff=$ff\ndsp=$dsp\nram36=$ram36\nram18=$ram18\nsetup_ns=$setup\nhold_ns=$hold"
foreach path $tracked {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
  puts $fd "$path=$hashes($path)"
}
close $fd
write_checkpoint $output/routed.dcp
if {$lut>$lut_limit || $dsp>50 || $ram36*2+$ram18>$ram_limit || $setup<0 || $hold<0} {
  error "coarse window feasibility gate: LUT=$lut DSP=$dsp RAM36=$ram36 RAM18=$ram18 setup=$setup hold=$hold"
}
puts "COARSE_WINDOW_OOC_PASS"
close_project
exit
