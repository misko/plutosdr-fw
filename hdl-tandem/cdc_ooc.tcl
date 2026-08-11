set part xc7z010clg400-1
create_project -in_memory -part $part
read_verilog /home/mouse9911/gits/plutosdr-fw-tandem-agc-v1/hdl-tandem/tandem_cdc_lib.v
synth_design -top tandem_async_fifo -part $part -mode out_of_context
report_utilization -file /tmp/fifo_util.rpt
puts "=== FIFO SYNTH DONE ==="
