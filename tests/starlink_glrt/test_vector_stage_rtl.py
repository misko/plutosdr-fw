"""Complete-vector staging is lossless under a busy scorer; partial tails retire."""
import subprocess

import pytest

from .ddc import BANK_ROOT


BENCH = r'''
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,reserve=0,abort_partial=0,input_valid=0,score_ready=0;
reg [5:0] input_symbol=0;
reg [63:0] input_epoch=0;
reg signed [23:0] input_exact_i=0,input_exact_q=0,input_control_i=0,input_control_q=0;
wire ready,busy,output_valid,complete_valid,sticky_fault;
wire [5:0] output_symbol;
wire [63:0] output_epoch;
wire signed [23:0] output_exact_i,output_exact_q,output_control_i,output_control_q;
starlink_glrt_vector_stage dut(.*);
integer complete_count=0,output_count=0,n,mode;
always @(posedge clk) begin
 #1;
 if(complete_valid) complete_count=complete_count+1;
 if(output_valid) begin
  $display("O %d %d %d %d %d %d",output_symbol,output_epoch,
   output_exact_i,output_exact_q,output_control_i,output_control_q);
  output_count=output_count+1;
 end
end
task tick;
 begin @(posedge clk);#2;@(negedge clk);end
endtask
task start_job;
 begin if(!ready) $fatal(1,"reservation while unavailable");reserve=1;tick();reserve=0;end
endtask
task symbol_word;
 input integer k;
 begin
  input_valid=1;input_symbol=k;input_epoch=64'h1000000000000007;
  input_exact_i=k*15003-8388608;input_exact_q=8388607-k*991;
  input_control_i=-k*1701;input_control_q=k*771;
  tick();input_valid=0;
 end
endtask
initial begin
 if(!$value$plusargs("MODE=%d",mode)) mode=0;
 repeat(4) tick();resetn=1;tick();start_job();
 if(mode==1) begin symbol_word(1);tick();if(!sticky_fault) $fatal(1,"order failure unreported");end
 else if(mode==2) begin
  for(n=0;n<17;n=n+1) symbol_word(n);
  abort_partial=1;tick();abort_partial=0;tick();
  if(!ready || busy || complete_count!=0 || output_count!=0 || sticky_fault) $fatal(1,"partial did not retire");
  start_job();for(n=0;n<64;n=n+1) symbol_word(n);
 end else for(n=0;n<64;n=n+1) symbol_word(n);
 if(mode!=1) begin
  repeat(100) tick();
  if(ready || !busy || output_count!=0 || complete_count!=1 || sticky_fault) $fatal(1,"busy scorer changed vector");
  score_ready=1;tick();score_ready=0;
  repeat(70) tick();
  if(!ready || busy || output_count!=64 || complete_count!=1 || sticky_fault) $fatal(1,"vector drain failed");
 end
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_stage_busy_reservation_complete_delivery_and_partial_abort(mode, tmp_path):
    bench, executable = tmp_path / "tb.sv", tmp_path / "sim"
    bench.write_text(BENCH)
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                               str(bench), str(BANK_ROOT / "starlink_glrt_vector_stage.v")],
                              capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = subprocess.run(["vvp", str(executable), f"+MODE={mode}"], capture_output=True,
                         text=True, timeout=10)
    assert run.returncode == 0, run.stdout + run.stderr
    words = [tuple(map(int, line.split()[1:])) for line in run.stdout.splitlines() if line.startswith("O ")]
    expected = [] if mode == 1 else [(k, 0x1000000000000007, k * 15003 - 8388608,
                                     8388607 - k * 991, -k * 1701, k * 771) for k in range(64)]
    assert words == expected
