if {$argc != 3} {
  error "usage: vivado -source synth_ooc.tcl -tclargs source rate output_dir"
}

set source_file [file normalize [lindex $argv 0]]
set rate_msps [lindex $argv 1]
set output_dir [file normalize [lindex $argv 2]]

if {$rate_msps ni {15 30 60}} {
  error "rate must be exactly 15, 30, or 60"
}
if {[file exists $output_dir]} {
  error "output_dir must not already exist"
}

file mkdir $output_dir
read_verilog $source_file
synth_design -mode out_of_context -flatten_hierarchy rebuilt \
  -top starlink_pss_delay_candidate -part xc7z010clg400-1 \
  -generic RATE_MSPS=$rate_msps
create_clock -name sample_clk -period 16.666 [get_ports clk]
report_utilization -hierarchical \
  -file [file join $output_dir utilization.rpt]
report_timing_summary -delay_type max -max_paths 10 \
  -file [file join $output_dir timing_synth.rpt]
write_checkpoint [file join $output_dir synthesized.dcp]
