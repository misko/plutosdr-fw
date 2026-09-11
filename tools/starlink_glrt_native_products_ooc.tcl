# Native derotation and exact products, isolated from the complete receiver.
# Usage: vivado -mode batch -source THIS -tclargs OUTPUT ?TEMPLATE_BANK? ?RATE?
if {$argc < 1 || $argc > 3} { error "expected output, optional engine bank and rate" }
if {[version -short] ne "2022.2"} { error "requires Vivado 2022.2" }
set output [file normalize [lindex $argv 0]]
set repo [file dirname [file dirname [file normalize [info script]]]]
set rtl [file join $repo hdl library starlink_glrt starlink_glrt_native_products.v]
set rotation [file join $repo hdl library starlink_glrt starlink_glrt_native_rotate.v]
set cordic [file join $repo hdl library common ad_dds_cordic_pipe.v]
set wrapper [file join $repo tools starlink_glrt_native_products_ooc_wrapper.v]
set script [file normalize [info script]]
set names {rtl rotation cordic wrapper script}
set sources [list $cordic $rotation $rtl]
set top starlink_glrt_native_products_ooc_wrapper
set generics {}
set mode products
set rate 60000000
if {$argc == 3} {
  set rate [lindex $argv 2]
  if {$rate ni {2500000 15000000 30000000 60000000}} { error "unsupported tracking rate" }
}
set stride [expr {60000000/$rate}]
set synthesis_directive Default
if {[info exists ::env(STARLINK_GLRT_OOC_SYNTH_DIRECTIVE)]} {
  set synthesis_directive $::env(STARLINK_GLRT_OOC_SYNTH_DIRECTIVE)
  if {$synthesis_directive ni {Default AreaOptimized_high}} {
    error "unsupported OOC synthesis directive"
  }
}
set lut_budget 1800
set ff_budget 3500
set bram_half_tile_budget 0
if {$argc >= 2} {
  set mode engine
  set bank [file normalize [lindex $argv 1]]
  set reference [file join $repo hdl library starlink_glrt starlink_glrt_cubic_reference.v]
  set coefficients [file join $repo hdl library starlink_glrt starlink_glrt_cubic_coefficients.v]
  set direct [file join $repo hdl library starlink_glrt starlink_glrt_direct_coefficients.v]
  set moments [file join $repo hdl library starlink_glrt starlink_glrt_local_moments.v]
  set engine [file join $repo hdl library starlink_glrt starlink_glrt_native_engine.v]
  set wrapper [file join $repo tools starlink_glrt_native_engine_ooc_wrapper.v]
  set top starlink_glrt_native_engine_ooc_wrapper
  set generics [list TEMPLATE_FILE=$bank REFERENCE_STRIDE=$stride]
  if {$rate == 2500000} { lappend generics DIRECT_COEFFICIENT_FILE=$bank }
  lappend sources $reference $coefficients $direct $moments $engine
  lappend names bank reference coefficients direct moments engine
  set lut_budget 3659
  set ff_budget 5500
  set bram_half_tile_budget 24
  set fd [open $bank r]
  set words [split [string trim [read $fd]] \n]
  close $fd
  set expected_words [expr {$rate == 2500000 ? 3300 : 3302}]
  set word_pattern [expr {$rate == 2500000 ? {^[0-9a-fA-F]{16}$} : {^[0-9a-fA-F]{27}$}}]
  if {[llength $words] != $expected_words} { error "tracking engine template length differs" }
  foreach word $words {
    if {![regexp $word_pattern $word]} { error "invalid rate-specific template word" }
  }
}
lappend sources $wrapper
if {[file exists [file join $output summary.txt]]} { error "output already completed" }
file mkdir $output
foreach name $names { set digest($name) [lindex [exec sha256sum [set $name]] 0] }
create_project -in_memory -part xc7z010clg400-1
set_msg_config -id {Synth 8-311} -new_severity ERROR
read_verilog $sources
synth_design -top $top -mode out_of_context -flatten_hierarchy none -generic $generics -directive $synthesis_directive
create_clock -name arithmetic_clk -period 10.0 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks arithmetic_clk]
# These exclusions end at fixture registers; every DUT path is constrained.
set_false_path -from [lsearch -all -inline -not -exact [all_inputs] [get_ports clk]]
set_false_path -to [all_outputs]
opt_design
place_design
phys_opt_design
route_design
report_utilization -file [file join $output utilization.rpt]
report_utilization -cells [get_cells dut] -file [file join $output dut_utilization.rpt]
report_utilization -hierarchical -file [file join $output hierarchy.rpt]
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
  error "native products have an error or critical DRC warning"
}
write_checkpoint [file join $output routed.dcp]
set lut [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ LUT*}]]
set srl [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ SRL*}]]
set ff [llength [get_cells -quiet -hier -filter {NAME =~ dut/* && REF_NAME =~ FD*}]]
set dsp [llength [get_cells -quiet -hier -filter {REF_NAME == DSP48E1}]]
set bram36 [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB36E1}]]
set bram18 [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB18E1}]]
set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_path] != 1 || [llength $hold_path] != 1} { error "missing setup/hold path" }
set setup [get_property SLACK $setup_path]
set hold [get_property SLACK $hold_path]
if {$lut+$srl > $lut_budget || $ff > $ff_budget || $dsp != 8 || 2*$bram36+$bram18 > $bram_half_tile_budget} {
  error "native arithmetic budget exceeded: LUT=$lut SRL=$srl FF=$ff DSP=$dsp BRAM36=$bram36 BRAM18=$bram18"
}
set minimum_rom_half_tiles [expr {$rate == 2500000 ? 12 : 20}]
if {$mode eq "engine" && 2*$bram36+$bram18 < $minimum_rom_half_tiles} {
  error "native reference ROM is missing from the synthesized engine"
}
if {$setup < 0 || $hold < 0} { error "native products timing failed: setup=$setup hold=$hold" }
foreach name $names {
  if {[lindex [exec sha256sum [set $name]] 0] ne $digest($name)} { error "$name changed during build" }
}
set fd [open [file join $output summary.txt] {WRONLY CREAT EXCL}]
puts $fd "scope=out_of_context_native_${mode}_with_registered_boundaries"
puts $fd "vivado=2022.2"
puts $fd "synthesis_directive=$synthesis_directive"
puts $fd "part=xc7z010clg400-1"
puts $fd "clock_mhz=100"
puts $fd "source_rate_hz=$rate"
puts $fd "reference_stride=$stride"
set direct_mode [expr {$mode eq "engine" && $rate == 2500000}]
puts $fd "direct_coefficients=$direct_mode"
puts $fd "clock_source_site=BUFGCTRL_X0Y0"
puts $fd "clock_uncertainty_ns=0.1"
puts $fd "external_fixture_io_timing=excluded"
puts $fd "logic_lut_cells=$lut"
puts $fd "srl_lut_cells=$srl"
puts $fd "total_lut_primitive_cells=[expr {$lut+$srl}]"
puts $fd "ff_cells=$ff"
puts $fd "dsp48e1=$dsp"
puts $fd "ramb36e1=$bram36"
puts $fd "ramb18e1=$bram18"
puts $fd "setup_wns_ns=$setup"
puts $fd "hold_whs_ns=$hold"
puts $fd "complete_receiver_qualified=false"
foreach name $names { puts $fd "${name}_sha256=$digest($name)" }
close $fd
puts "STARLINK_NATIVE_PRODUCTS_OOC_PASS LUT=$lut SRL=$srl FF=$ff DSP=$dsp setup=$setup hold=$hold"
close_design
close_project
