set part xc7z010clg400-1
create_project -in_memory -part $part
read_verilog /home/mouse9911/gits/plutosdr-fw-tandem-agc-v1/hdl-tandem/tandem_agc_canary.v
read_xdc /tmp/claude-1000/-home-mouse9911-gits-plutosdr-fw/454bf768-c15a-453e-a6f3-d9d08693d7ca/scratchpad/canary_clk.xdc
synth_design -top tandem_agc_canary -part $part -mode out_of_context
opt_design -quiet
report_utilization -file /tmp/canary_util.rpt
report_timing_summary -delay_type max -max_paths 5 -file /tmp/canary_timing.rpt
puts "=== OOC SYNTH DONE ==="
