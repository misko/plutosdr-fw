set part xc7z010clg400-1
set d /home/mouse9911/gits/plutosdr-fw-tandem-agc-v1/hdl-tandem
create_project -in_memory -part $part
read_verilog $d/tandem_cdc_lib.v
read_verilog $d/tandem_agc_core.v
read_verilog $d/tandem_agc_axi.v
read_xdc $d/tandem_agc_axi.xdc
synth_design -top tandem_agc_axi -part $part -mode out_of_context
opt_design -quiet
report_utilization -file /tmp/axi_util.rpt
report_timing_summary -delay_type max -max_paths 3 -file /tmp/axi_timing.rpt
report_cdc -file /tmp/axi_cdc.rpt
puts "=== AXI SYNTH DONE ==="
