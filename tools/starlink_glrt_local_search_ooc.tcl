# Complete local acquisition component, including both buffers and decisions.
if {$argc ni {2 3} || [version -short] ne "2022.2"} {
  error "requires Vivado 2022.2, fresh output, ROM directory, optional --control-netlist"
}
set control_netlist [expr {$argc==3}]
if {$control_netlist && [lindex $argv 2] ne "--control-netlist"} { error "unknown output mode" }
set output [file normalize [lindex $argv 0]]
set roms [file normalize [lindex $argv 1]]
if {[file exists $output]} { error "output exists" }
file mkdir $output
set repo [file dirname [file dirname [file normalize [info script]]]]
set sources [list]
foreach name {local_search coarse_search coarse_window coarse_mac6 coarse_norm coarse_peaks verify_control verify_window3 verify_mac3 verify_rotate3} {
  lappend sources $repo/hdl/library/starlink_glrt/starlink_glrt_$name.v
}
if {$control_netlist} {
  lappend sources $repo/hdl/library/starlink_glrt/starlink_glrt_local_control.v
  lappend sources $repo/hdl/library/starlink_glrt/starlink_glrt_local_cadence.v
  set top starlink_glrt_local_control
} else {
  lappend sources $repo/tools/starlink_glrt_local_search_ooc_wrapper.v
  set top starlink_glrt_local_search_ooc_wrapper
}
set tracked [concat $sources [list [file normalize [info script]] $roms/manifest.json \
    $roms/coarse_upper_q9.mem $roms/coarse_upper_energy.mem $roms/verify_upper_pilot_q9.mem \
    $roms/verify_upper_energy.mem $roms/verify_oscillator_q10.mem]]
file mkdir $output/source-snapshot
foreach path $tracked {
  set hashes($path) [lindex [exec sha256sum $path] 0]
  file copy $path $output/source-snapshot/[file tail $path]
}
set fd [open $output/build-environment.txt {WRONLY CREAT EXCL}]
puts $fd "vivado=[version -short]\nos=[exec uname -a]\nuserspace=[exec cat /etc/os-release]"
foreach key {LD_PRELOAD LD_LIBRARY_PATH TMPDIR} {
  if {[info exists ::env($key)]} { puts $fd "$key=$::env($key)" }
}
close $fd
set_param general.maxThreads 1
cd $roms
set netlists [list]
set stubs [list]
# Give the two normalizer specializations distinct private module names so
# their structural netlists cannot collide when linked. Only names change.
foreach {name tag_width original} {coarse_mac6 5 coarse_mac6 verify_mac3 1 verify_mac3 verify_rotate3 34 verify_rotate3 coarse_norm4 4 coarse_norm verify_norm 2 verify_norm} {
  set module starlink_glrt_$name
  set path $repo/hdl/library/starlink_glrt/starlink_glrt_$original.v
  if {$original eq "verify_norm"} { set path $repo/hdl/library/starlink_glrt/starlink_glrt_coarse_norm.v }
  set fd [open $path r];set content [read $fd];close $fd
  if {$original eq "coarse_norm"} {
    set content [string map [list starlink_glrt_coarse_norm $module \
        starlink_glrt_unsigned_sqrt_pipe starlink_glrt_unsigned_sqrt_pipe_$tag_width] $content]
  }
  set source $output/source-snapshot/$module.v
  set fd [open $source w];puts -nonewline $fd $content;close $fd
  set netlist $output/$module.edf
  set script $output/${module}_synthesize.tcl
  set fd [open $script {WRONLY CREAT EXCL}]
  puts $fd [list set_param general.maxThreads 1]
  puts $fd [list create_project -in_memory -part xc7z010clg400-1]
  puts $fd [list set_msg_config -id {Synth 8-311} -new_severity ERROR]
  puts $fd [list cd $roms]
  puts $fd [list read_verilog -sv $source]
  puts $fd [list synth_design -top $module -mode out_of_context -generic TAG_WIDTH=$tag_width \
      -flatten_hierarchy rebuilt -directive AreaOptimized_high]
  puts $fd [list report_utilization -hierarchical -file $output/${module}_synthesis.rpt]
  puts $fd [list write_edif $netlist]
  puts $fd exit
  close $fd
  exec /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch -nojournal -log $output/${module}.log \
      -source $script > $output/${module}.console.log 2>@1
  lappend netlists $netlist
  set start [string first "module $module" $content]
  set finish [string first "\n);" $content $start]
  if {$start<0 || $finish<0} { error "cannot extract arithmetic interface" }
  set header [string range $content $start [expr {$finish+2}]]
  regsub {TAG_WIDTH=[0-9]+} $header TAG_WIDTH=$tag_width header
  set stub $output/${module}_stub.v
  set fd [open $stub {WRONLY CREAT EXCL}];puts $fd "(* black_box=\"yes\" *) $header\nendmodule";close $fd
  lappend stubs $stub
}
set shell_sources [list]
set shell_names {local_search coarse_search coarse_window coarse_peaks verify_control verify_window3}
if {$control_netlist} { lappend shell_names local_control local_cadence }
foreach name $shell_names {
  set path $repo/hdl/library/starlink_glrt/starlink_glrt_$name.v
  set fd [open $path r];set content [read $fd];close $fd
  if {$name eq "coarse_window"} { set content [string map {starlink_glrt_coarse_norm starlink_glrt_coarse_norm4} $content] }
  set copied $output/source-snapshot/starlink_glrt_${name}_linked.v
  set fd [open $copied w];puts -nonewline $fd $content;close $fd
  lappend shell_sources $copied
}
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
if {!$control_netlist} { lappend shell_sources [lindex $sources end] }
read_verilog -sv [concat $shell_sources $stubs]
synth_design -top $top -mode out_of_context \
  -flatten_hierarchy none -directive Default
set shell_edif $output/$top.edf
if {$control_netlist} {
  file mkdir $output/shell
  set shell_edif $output/shell/$top.edf
}
write_edif $shell_edif
close_project
create_project -in_memory -part xc7z010clg400-1
read_edif $netlists
read_edif $shell_edif
link_design -top $top -part xc7z010clg400-1 -mode out_of_context
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} { error "unresolved arithmetic black box" }
if {$control_netlist} {
  # An unplaced complete component for the board implementation. No fixture
  # registers or false paths are exported; the board must time every port.
  write_edif $output/starlink_glrt_local_control.edf
  report_utilization -hierarchical -file $output/synthesis_utilization.rpt
  set source $repo/hdl/library/starlink_glrt/starlink_glrt_local_control.v
  set fd [open $source r];set content [read $fd];close $fd
  set start [string first "module starlink_glrt_local_control" $content]
  set finish [string first "\n);" $content $start]
  if {$start<0 || $finish<0} { error "cannot extract local control interface" }
  set fd [open $output/starlink_glrt_local_control_stub.v {WRONLY CREAT EXCL}]
  puts $fd "(* black_box=\"yes\" *) [string range $content $start [expr {$finish+2}]]\nendmodule"
  close $fd
  set fd [open $output/source-hashes.txt {WRONLY CREAT EXCL}]
  foreach path $tracked {
    if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
    puts $fd "$hashes($path)  $path"
  }
  close $fd
  set fd [open $output/outputs.sha256 {WRONLY CREAT EXCL}]
  foreach name {starlink_glrt_local_control.edf starlink_glrt_local_control_stub.v source-hashes.txt} {
    puts $fd "[lindex [exec sha256sum $output/$name] 0]  $name"
  }
  close $fd
  puts "LOCAL_CONTROL_NETLIST_READY_NOT_BOARD_TIMING_VERIFIED"
  close_project
  exit
}
create_clock -name local_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks local_clk]
set_false_path -from [get_ports stimulus*]
set_false_path -to [all_outputs]
report_utilization -hierarchical -file $output/synthesis_utilization.rpt
write_checkpoint $output/synthesized.dcp
opt_design
place_design
phys_opt_design
route_design
phys_opt_design -directive AggressiveExplore
route_design
report_utilization -hierarchical -file $output/utilization.rpt
report_utilization -cells [get_cells dut] -file $output/dut_utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $output/timing.rpt
report_timing -delay_type max -max_paths 20 -nworst 1 -file $output/critical_paths.rpt
report_drc -file $output/drc.rpt
check_timing -verbose -file $output/check_timing.rpt
set fd [open $output/check_timing.rpt r];set checks [read $fd];close $fd
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
  error "local acquisition DRC failed"
}
set fd [open $output/dut_utilization.rpt r];set utilization [read $fd];close $fd
# Include distributed RAM and shift-register LUTs in the resource gate.
if {![regexp -line {^\|\s*Slice LUTs\*?\s*\|\s*([0-9]+)\s*\|} $utilization unused lut]} {
  error "cannot read total DUT LUT utilization"
}
set ff [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME == RAMB18E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set fd [open $output/summary.txt {WRONLY CREAT EXCL}]
puts $fd "scope=autonomous_local_glrt_component_not_complete_radio_board"
puts $fd "clock_mhz=100\nlut=$lut\nff=$ff\ndsp=$dsp\nram36=$ram36\nram18=$ram18\nsetup_ns=$setup\nhold_ns=$hold"
foreach path $tracked {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
  puts $fd "$path=$hashes($path)"
}
close $fd
write_checkpoint $output/routed.dcp
if {$lut>15000 || $dsp>80 || $ram36*2+$ram18>100 || $setup<0 || $hold<0} {
  error "local acquisition feasibility gate: LUT=$lut DSP=$dsp RAM36=$ram36 RAM18=$ram18 setup=$setup hold=$hold"
}
puts "LOCAL_SEARCH_OOC_PASS"
close_project
exit
