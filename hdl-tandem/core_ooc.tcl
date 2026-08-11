set part xc7z010clg400-1
set d /home/mouse9911/gits/plutosdr-fw-tandem-agc-v1/hdl-tandem
create_project -in_memory -part $part
read_verilog $d/tandem_agc_core.v
read_verilog $d/tandem_agc_regs.v
read_verilog $d/tandem_agc_wrap.v
read_xdc /tmp/claude-1000/-home-mouse9911-gits-plutosdr-fw/454bf768-c15a-453e-a6f3-d9d08693d7ca/scratchpad/canary_clk.xdc
synth_design -top tandem_agc_wrap -part $part -mode out_of_context
opt_design -quiet
report_utilization -file /tmp/core_util.rpt
report_timing_summary -delay_type max -max_paths 3 -file /tmp/core_timing.rpt
puts "=== CORE SYNTH DONE ==="
