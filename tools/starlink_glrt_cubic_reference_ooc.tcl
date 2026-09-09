# Scope: native reference generator with real registered data boundaries.
# The full receiver still requires routing under its unchanged constraints.
# Usage: vivado -mode batch -source THIS -tclargs FRESH_OUTPUT TEMPLATE_BANK ?coefficients?
if {$argc < 2 || $argc > 3} { error "expected output directory, 3302-word template bank and optional coefficients mode" }
if {[version -short] ne "2022.2"} { error "requires Vivado 2022.2" }
set output [file normalize [lindex $argv 0]]
set bank [file normalize [lindex $argv 1]]
set repo [file dirname [file dirname [file normalize [info script]]]]
set rtl [file join $repo hdl library starlink_glrt starlink_glrt_cubic_reference.v]
set wrapper [file join $repo tools starlink_glrt_cubic_reference_ooc_wrapper.v]
set mode reference
if {$argc == 3} {
  if {[lindex $argv 2] ne "coefficients"} { error "unknown native reference mode" }
  set mode coefficients
}
set top starlink_glrt_cubic_reference_ooc_wrapper
set sources [list $rtl]
set digest_names {rtl wrapper bank}
set lut_budget 600
set ff_budget 600
if {$mode eq "coefficients"} {
  set coefficients_rtl [file join $repo hdl library starlink_glrt starlink_glrt_cubic_coefficients.v]
  set wrapper [file join $repo tools starlink_glrt_cubic_coefficients_ooc_wrapper.v]
  set top starlink_glrt_cubic_coefficients_ooc_wrapper
  lappend sources $coefficients_rtl
  lappend digest_names coefficients_rtl
  set lut_budget 1200
  set ff_budget 1200
}
lappend sources $wrapper
if {[file exists [file join $output summary.txt]]} { error "output already completed" }
file mkdir $output
set fd [open $bank r]
set words [split [string trim [read $fd]] \n]
close $fd
if {[llength $words] != 3302} { error "native reference bank must contain exactly 3302 words" }
foreach word $words {
  if {![regexp {^[0-9a-fA-F]{27}$} $word]} { error "invalid 108-bit native reference word" }
}
foreach name $digest_names {
  set digest($name) [lindex [exec sha256sum [set $name]] 0]
}
create_project -in_memory -part xc7z010clg400-1
read_verilog $sources
synth_design -top $top -mode out_of_context \
  -flatten_hierarchy none -generic TEMPLATE_FILE=$bank
create_clock -name reference_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks reference_clk]
# Exclude the fixture's external I/O only. All actual DUT boundaries and
# internal paths are launched/captured by real FFs on the same 100 MHz clock.
set_false_path -from [lsearch -all -inline -not -exact [all_inputs] [get_ports clk]]
set_false_path -to [all_outputs]
opt_design
place_design
phys_opt_design
route_design
report_utilization -file [file join $output utilization.rpt]
report_utilization -cells [get_cells dut] -file [file join $output dut_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output timing_summary.rpt]
report_drc -file [file join $output drc.rpt]
check_timing -verbose -file [file join $output check_timing.rpt]
set fd [open [file join $output check_timing.rpt] r]
set checks [read $fd]
close $fd
foreach check {no_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
  if {![regexp [format {checking %s \(0\)} $check] $checks]} { error "timing coverage failed: $check" }
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]] != 0} {
  error "native reference route has an error or critical DRC warning"
}
write_checkpoint [file join $output routed.dcp]
set lut [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set ff [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -quiet -hier -filter {REF_NAME == DSP48E1}]]
set ramb36 [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB36E1}]]
set ramb18 [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB18E1}]]
set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_path] != 1 || [llength $hold_path] != 1} { error "missing setup/hold path" }
set setup [get_property SLACK $setup_path]
set hold [get_property SLACK $hold_path]
if {$lut > $lut_budget || $ff > $ff_budget || $dsp != 0 || 2*$ramb36+$ramb18 > 24} {
  error "native reference budget exceeded: LUT=$lut FF=$ff DSP=$dsp RAMB36=$ramb36 RAMB18=$ramb18"
}
if {$setup < 0 || $hold < 0} { error "native reference timing failed: setup=$setup hold=$hold" }
foreach name $digest_names {
  if {[lindex [exec sha256sum [set $name]] 0] ne $digest($name)} { error "$name changed during build" }
}
set fd [open [file join $output summary.txt] {WRONLY CREAT EXCL}]
puts $fd "scope=out_of_context_native_${mode}_with_registered_boundaries"
puts $fd "vivado=2022.2"
puts $fd "part=xc7z010clg400-1"
puts $fd "clock_mhz=100"
puts $fd "clock_source_site=BUFGCTRL_X0Y0"
puts $fd "clock_uncertainty_ns=0.1"
puts $fd "external_fixture_io_timing=excluded"
puts $fd "segments=3302"
puts $fd "native_samples=79248"
if {$mode eq "coefficients"} { puts $fd "output_coefficients=79200" }
puts $fd "lut_cells=$lut"
puts $fd "ff_cells=$ff"
puts $fd "dsp48e1=$dsp"
puts $fd "ramb36e1=$ramb36"
puts $fd "ramb18e1=$ramb18"
puts $fd "setup_wns_ns=$setup"
puts $fd "hold_whs_ns=$hold"
puts $fd "complete_receiver_qualified=false"
foreach name $digest_names { puts $fd "${name}_sha256=$digest($name)" }
close $fd
puts "STARLINK_CUBIC_REFERENCE_OOC_PASS LUT=$lut FF=$ff RAMB36=$ramb36 RAMB18=$ramb18 setup=$setup hold=$hold"
close_design
close_project
