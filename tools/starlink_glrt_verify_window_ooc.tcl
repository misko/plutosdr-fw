# Full-pilot verification feasibility with the actual upper-edge pilot ROM.
if {$argc!=2 || [version -short] ne "2022.2"} { error "requires Vivado 2022.2, fresh output, ROM directory" }
set output [file normalize [lindex $argv 0]]
set roms [file normalize [lindex $argv 1]]
if {[file exists $output]} { error "output exists" }
file mkdir $output
set repo [file dirname [file dirname [file normalize [info script]]]]
set sources [list]
foreach name {verify_window3 verify_mac3 verify_rotate3 coarse_norm} {
  lappend sources $repo/hdl/library/starlink_glrt/starlink_glrt_$name.v
}
lappend sources $repo/tools/starlink_glrt_verify_window_ooc_wrapper.v
set tracked [concat $sources [list [file normalize [info script]] \
    $roms/verify_upper_pilot_q9.mem $roms/verify_upper_energy.mem \
    $roms/verify_oscillator_q10.mem $roms/manifest.json]]
file mkdir $output/source-snapshot
foreach path $tracked {
  set hashes($path) [lindex [exec sha256sum $path] 0]
  file copy $path $output/source-snapshot/[file tail $path]
}
set fd [open $output/build-environment.txt {WRONLY CREAT EXCL}]
puts $fd "vivado=[version -short]\nos=[exec uname -a]"
puts $fd "userspace=[exec cat /etc/os-release]"
foreach key {LD_PRELOAD LD_LIBRARY_PATH TMPDIR} {
  if {[info exists ::env($key)]} { puts $fd "$key=$::env($key)" }
}
if {[info exists ::env(LD_PRELOAD)] && [file isfile $::env(LD_PRELOAD)]} {
  puts $fd "allocator_sha256=[lindex [exec sha256sum $::env(LD_PRELOAD)] 0]"
}
close $fd
set_param general.maxThreads 1
cd $roms
set netlists [list]
set stubs [list]
# Synthesize arithmetic partitions separately, then link their structural
# netlists. This avoids the reproducible 2022.2 monolithic mapper crash without
# excluding any arithmetic from the final placement or timing analysis.
foreach {name tag_width} {verify_mac3 1 verify_rotate3 34 coarse_norm 2} {
  set module starlink_glrt_$name
  set source $repo/hdl/library/starlink_glrt/$module.v
  set netlist $output/$module.edf
  # Each synthesis gets its own process: reusing one Vivado process across
  # projects also triggers stale Tcl collection destruction in 2022.2.
  set component_script $output/${module}_synthesize.tcl
  set fd [open $component_script {WRONLY CREAT EXCL}]
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
  exec /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch -nojournal \
    -log $output/${module}.log -source $component_script > $output/${module}.console.log 2>@1
  lappend netlists $netlist
  set fd [open $source r];set content [read $fd];close $fd
  set start [string first "module $module" $content]
  set finish [string first "\n);" $content $start]
  if {$start<0 || $finish<0} { error "cannot extract component header" }
  set header [string range $content $start [expr {$finish+2}]]
  regsub {TAG_WIDTH=[0-9]+} $header TAG_WIDTH=$tag_width header
  set stub $output/${module}_stub.v
  set fd [open $stub {WRONLY CREAT EXCL}]
  puts $fd "(* black_box=\"yes\" *) $header\nendmodule"
  close $fd
  lappend stubs $stub
}
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
read_verilog -sv [concat [list [lindex $sources 0] [lindex $sources end]] $stubs]
synth_design -top starlink_glrt_verify_window_ooc_wrapper -mode out_of_context \
  -flatten_hierarchy none -directive Default
set shell_edif $output/starlink_glrt_verify_window_ooc_wrapper.edf
write_edif $shell_edif
close_project
create_project -in_memory -part xc7z010clg400-1
read_edif $netlists
read_edif $shell_edif
link_design -top starlink_glrt_verify_window_ooc_wrapper -part xc7z010clg400-1 -mode out_of_context
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} { error "unresolved verification blackbox" }
create_clock -name verify_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks verify_clk]
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
report_timing_summary -delay_type min_max -report_unconstrained -file $output/timing.rpt
report_drc -file $output/drc.rpt
check_timing -verbose -file $output/check_timing.rpt
set fd [open $output/check_timing.rpt r];set checks [read $fd];close $fd
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
  error "verification window DRC failed"
}
set lut [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff [llength [get_cells -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME == RAMB18E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set fd [open $output/summary.txt {WRONLY CREAT EXCL}]
puts $fd "scope=buffered_full_pilot_verification_component_not_complete_board"
puts $fd "clock_mhz=100\nlut=$lut\nff=$ff\ndsp=$dsp\nram36=$ram36\nram18=$ram18\nsetup_ns=$setup\nhold_ns=$hold"
foreach path $tracked {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
  puts $fd "$path=$hashes($path)"
}
close $fd
write_checkpoint $output/routed.dcp
if {$lut>7500 || $dsp>42 || $ram36*2+$ram18>56 || $setup<0 || $hold<0} {
  error "verification feasibility gate: LUT=$lut DSP=$dsp RAM36=$ram36 RAM18=$ram18 setup=$setup hold=$hold"
}
puts "VERIFY_WINDOW_OOC_PASS"
close_project
exit
