import subprocess

import pytest

from .ddc import BANK_ROOT, RATES


BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam integer RATE_VALUE=(RATE);
reg clk=0,sample_clk=0,resetn=0,sample_reset=1,sample_valid=0,sample_gap=0,flush_pacer=0;
reg signed [15:0] sample_i=0,sample_q=0;
always #5 clk=~clk;
always #(250000000.0/RATE_VALUE) sample_clk=~sample_clk;
wire output_valid,output_gap,source_ready;
wire signed [15:0] output_i,output_q;
wire [63:0] output_index;
wire [4:0] output_phase;
wire [31:0] cdc_dropped_count,pacer_dropped_count;
wire [7:0] cdc_level,cdc_maximum_level;
wire [6:0] pacer_level,pacer_maximum_level;
starlink_glrt_ingress #(.SOURCE_RATE_HZ(RATE_VALUE)) dut(.*);
integer j,count=0;
always @(negedge clk) begin
 if(output_valid) begin
  $display("O %d %d %d %d %d",output_index,output_i,output_q,output_phase,output_gap);
  count=count+1;
 end
end
task send(input integer n);
 begin
  @(negedge sample_clk);
  sample_i=n;sample_q=-n;sample_valid=1;
  @(negedge sample_clk);sample_valid=0;
 end
endtask
initial begin
 repeat(5) @(negedge sample_clk);
 resetn=1;sample_reset=0;
 repeat(20) @(negedge sample_clk);
 for(j=0;j<1100;j=j+1) send(j);
 repeat(100) @(negedge sample_clk);
 if(count!=1100) $fatal(1,"first segment did not drain");
 @(negedge clk);flush_pacer=1;
 repeat(3) @(negedge clk);
 flush_pacer=0;
 // A radio reset/tune creates a gap marker but preserves absolute phase and
 // sample index. The source counter is independent of AD9361's data reset.
 sample_reset=1;
 repeat(10) @(negedge sample_clk);
 sample_reset=0;
 repeat(20) @(negedge sample_clk);
 for(j=1100;j<2200;j=j+1) send(j);
 repeat(100) @(negedge sample_clk);
 $display("S %d %d %d %d %d",count,cdc_dropped_count,pacer_dropped_count,cdc_level,pacer_level);
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("rate", RATES)
def test_native_clock_counter_phase_and_radio_reset(rate, tmp_path):
    bench, executable = tmp_path/"tb.sv", tmp_path/"sim"
    bench.write_text(BENCH.replace("(RATE)", f"({rate})"))
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                           *[str(BANK_ROOT/name) for name in ("starlink_glrt_ingress.v", "starlink_glrt_sample_cdc.v",
                                                            "starlink_glrt_pacer.v")]], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout+built.stderr
    process = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stdout+process.stderr
    output = [tuple(map(int, line.split()[1:])) for line in process.stdout.splitlines() if line.startswith("O ")]
    ratio = rate//2500000
    assert output == [(j, j, -j, j % ratio, int(j in (0, 1100))) for j in range(2200)]
    status = [tuple(map(int, line.split()[1:])) for line in process.stdout.splitlines() if line.startswith("S ")]
    assert status == [(2200, 0, 0, 0, 0)]
