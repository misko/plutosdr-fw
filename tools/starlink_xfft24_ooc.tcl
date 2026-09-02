# Vivado 2022.2 resource/timing gate for one 24-bit acquisition XFFT core.
# Usage: vivado -mode batch -source starlink_xfft24_ooc.tcl -tclargs OUTPUT

if {$argc != 1} {
  error "expected one absolute output directory"
}
if {[version -short] ne "2022.2"} {
  error "this evidence gate requires Vivado 2022.2, got [version -short]"
}

set output_dir [file normalize [lindex $argv 0]]
file mkdir $output_dir
create_project -force starlink_xfft24_ooc $output_dir -part xc7z010clg400-1
create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 \
  -module_name starlink_pss_fft512_bfp24
set_property -dict [list \
  CONFIG.channels {1} \
  CONFIG.transform_length {512} \
  CONFIG.target_clock_frequency {100} \
  CONFIG.implementation_options {automatically_select} \
  CONFIG.target_data_throughput {20} \
  CONFIG.run_time_configurable_transform_length {false} \
  CONFIG.data_format {fixed_point} \
  CONFIG.input_width {24} \
  CONFIG.phase_factor_width {16} \
  CONFIG.scaling_options {block_floating_point} \
  CONFIG.rounding_modes {convergent_rounding} \
  CONFIG.aresetn {true} \
  CONFIG.xk_index {true} \
  CONFIG.throttle_scheme {nonrealtime} \
  CONFIG.output_ordering {natural_order} \
  CONFIG.cyclic_prefix_insertion {false} \
  CONFIG.memory_options_data {block_ram} \
  CONFIG.memory_options_phase_factors {block_ram} \
  CONFIG.memory_options_reorder {block_ram} \
  CONFIG.complex_mult_type {use_mults_resources} \
  CONFIG.butterfly_type {use_luts} \
] [get_ips starlink_pss_fft512_bfp24]
generate_target all [get_ips starlink_pss_fft512_bfp24]

set wrappers [glob -nocomplain \
  [file join $output_dir starlink_xfft24_ooc.gen sources_1 ip \
    starlink_pss_fft512_bfp24 synth starlink_pss_fft512_bfp24.vhd]]
if {[llength $wrappers] != 1} {
  error "could not locate generated XFFT synthesis wrapper"
}
set wrapper_file [open [lindex $wrappers 0] r]
set wrapper_text [read $wrapper_file]
close $wrapper_file
if {![regexp {C_ARCH => 1,} $wrapper_text]} {
  error "20 MS/s automatic selection did not choose radix-4 burst C_ARCH=1"
}

create_ip_run [get_ips starlink_pss_fft512_bfp24]
launch_runs starlink_pss_fft512_bfp24_synth_1 -jobs 4
wait_on_run starlink_pss_fft512_bfp24_synth_1
if {[get_property STATUS [get_runs starlink_pss_fft512_bfp24_synth_1]] \
    ne "synth_design Complete!"} {
  error "XFFT synthesis did not complete"
}
open_run starlink_pss_fft512_bfp24_synth_1

set utilization_report [report_utilization -return_string]
set timing_report [report_timing_summary \
  -delay_type min_max -max_paths 20 -return_string]
foreach {name contents} [list \
    starlink_xfft24_utilization_synth.rpt $utilization_report \
    starlink_xfft24_timing_synth.rpt $timing_report] {
  set report_file [open [file join $output_dir $name] w]
  puts -nonewline $report_file $contents
  close $report_file
}
report_property [get_ips starlink_pss_fft512_bfp24] \
  -file [file join $output_dir starlink_xfft24_properties.rpt]

foreach {label pattern} {
  total_luts {\| Slice LUTs\* +\| +([0-9]+) +\|}
  total_ffs {\| Slice Registers +\| +([0-9]+) +\|}
} {
  if {![regexp $pattern $utilization_report unused value]} {
    error "could not parse $label from utilization"
  }
  set $label $value
}
set ramb36_count [llength \
  [get_cells -quiet -hier -filter {REF_NAME == RAMB36E1}]]
set ramb18_count [llength \
  [get_cells -quiet -hier -filter {REF_NAME == RAMB18E1}]]
set dsp_count [llength \
  [get_cells -quiet -hier -filter {REF_NAME == DSP48E1}]]
if {$total_luts > 2500 || $total_ffs > 4300} {
  error "XFFT logic budget exceeded: LUT=$total_luts FF=$total_ffs"
}
if {$ramb36_count != 0 || $ramb18_count != 11 || $dsp_count != 9} {
  error "expected RAMB36/RAMB18/DSP 0/11/9, got $ramb36_count/$ramb18_count/$dsp_count"
}

set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_path] != 1 || [llength $hold_path] != 1} {
  error "constrained XFFT setup and hold paths are required"
}
set setup_wns [get_property SLACK $setup_path]
set hold_whs [get_property SLACK $hold_path]
if {$setup_wns < 0.0 || $hold_whs < 0.0} {
  error "100 MHz XFFT synthesis timing failed: setup=$setup_wns hold=$hold_whs"
}

set summary [open [file join $output_dir starlink_xfft24_ooc_summary.txt] w]
puts $summary "vivado_version=[version -short]"
puts $summary "xfft_version=9.1"
puts $summary "part=xc7z010clg400-1"
puts $summary "architecture=radix_4_burst"
puts $summary "data_bits=24"
puts $summary "phase_factor_bits=16"
puts $summary "scaling=block_floating_point"
puts $summary "rounding=convergent"
puts $summary "transform_samples=512"
puts $summary "target_clock_mhz=100"
puts $summary "target_throughput_msps=20"
puts $summary "timing_scope=post_synthesis_unplaced"
puts $summary "setup_wns_ns=$setup_wns"
puts $summary "hold_whs_ns=$hold_whs"
puts $summary "total_luts=$total_luts"
puts $summary "total_ffs=$total_ffs"
puts $summary "ramb36e1=$ramb36_count"
puts $summary "ramb18e1=$ramb18_count"
puts $summary "dsp48e1=$dsp_count"
close $summary

puts "STARLINK_XFFT24_OOC_PASS setup_wns_ns=$setup_wns hold_whs_ns=$hold_whs total_luts=$total_luts total_ffs=$total_ffs ramb18e1=$ramb18_count dsp48e1=$dsp_count"
close_design
close_project
