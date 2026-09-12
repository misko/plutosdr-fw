# Compare exact direct-reference storage components, not a receiver image.
if {$argc!=3 || [version -short] ne "2022.2"} { error "expected PACKED BANK NEW_OUTPUT on Vivado 2022.2" }
set packed [lindex $argv 0]
if {$packed ni {0 1}} { error "invalid storage selection" }
set bank [file normalize [lindex $argv 1]]
set out [file normalize [lindex $argv 2]]
if {[file exists $out]} { error "output exists" }
file mkdir $out
set repo [file dirname [file dirname [file normalize [info script]]]]
set sources [list $repo/hdl/library/starlink_glrt/starlink_glrt_direct_coefficients.v \
  $repo/hdl/library/starlink_glrt/starlink_glrt_packed_direct_coefficients.v \
  $repo/tools/glrt_direct_rom_ooc_wrapper.v]
foreach path [concat $sources [list $bank [file normalize [info script]]]] {
  set hashes($path) [lindex [exec sha256sum $path] 0]
}
file mkdir $out/source-snapshot
set copied_sources {}
foreach path $sources {
  set copied $out/source-snapshot/[file tail $path]
  file copy $path $copied
  lappend copied_sources $copied
}
file copy $bank $out/source-snapshot/[file tail $bank]
file copy [info script] $out/source-snapshot/[file tail [info script]]
set_param general.maxThreads 4
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
read_verilog $copied_sources
synth_design -top glrt_direct_rom_ooc_wrapper -mode out_of_context -flatten_hierarchy none \
  -directive AreaOptimized_high -generic [list PACKED=$packed TEMPLATE_FILE=$out/source-snapshot/[file tail $bank]]
create_clock -name reference_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks reference_clk]
set_false_path -from [get_ports stimulus*]
set_false_path -to [all_outputs]
opt_design
report_utilization -hierarchical -file $out/synth_utilization.rpt
write_checkpoint $out/synth.dcp
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file $out/utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file $out/timing.rpt
report_route_status -file $out/route_status.rpt
report_drc -file $out/drc.rpt
check_timing -verbose -file $out/check_timing.rpt
set f [open $out/check_timing.rpt r];set checks [read $f];close $f
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
  error "reference DRC failed"
}
set lut [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
set ff [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME == RAMB18E1}]]
set dsp [llength [get_cells -hier -filter {REF_NAME == DSP48E1}]]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
foreach path [array names hashes] {
  if {[lindex [exec sha256sum $path] 0] ne $hashes($path)} { error "source changed" }
}
write_checkpoint $out/routed.dcp
set f [open $out/summary.txt {WRONLY CREAT EXCL}]
puts $f "scope=registered_reference_component_not_receiver"
puts $f "packed=$packed\nlut=$lut\nff=$ff\nramb36=$ram36\nramb18=$ram18\ndsp=$dsp\nsetup_ns=$setup\nhold_ns=$hold"
foreach path [array names hashes] { puts $f "$path=$hashes($path)" }
close $f
if {$setup<0 || $hold<0 || $dsp!=0} { error "reference timing or multiplier gate failed" }
puts "DIRECT_REFERENCE_OOC_PASS"
close_project
exit
