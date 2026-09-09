"""Reset an occupied ingress while the ADC clock is stopped.

This exercises the source-clock acknowledgement behind the reported reset CDC
reconvergence. RTL cannot model analog metastability or minimum pulse widths.
"""
import subprocess

import pytest

from .ddc import BANK_ROOT


BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam integer RATE_VALUE=RATE;
localparam integer RADIO_ONLY=RADIO;
reg clk=0,sample_clk=0,cpu_enable=1,adc_enable=1;
reg resetn=0,sample_reset=1,sample_valid=0,sample_gap=0,flush_pacer=0;
reg signed [15:0] sample_i=0,sample_q=0;
always #5 if(cpu_enable) clk=~clk;
always #(250000000.0/RATE_VALUE) if(adc_enable) sample_clk=~sample_clk;
wire output_valid,output_gap,source_ready;
wire signed [15:0] output_i,output_q;
wire [63:0] output_index;
wire [4:0] output_phase;
wire [31:0] cdc_dropped_count,pacer_dropped_count;
wire [7:0] cdc_level,cdc_maximum_level;
wire [6:0] pacer_level,pacer_maximum_level;
starlink_glrt_ingress #(.SOURCE_RATE_HZ(RATE_VALUE)) dut(.*);
integer j,count=0,check_new_epoch=0;
always @(negedge clk) begin
 if(check_new_epoch && output_valid) begin
  if(output_i<10000) $fatal(1,"old queued payload escaped after reset");
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
 @(negedge clk); cpu_enable=0;
 for(j=0;j<20;j=j+1) send(j);
 @(negedge sample_clk); adc_enable=0;
 if(dut.cdc.source_pointer_binary!=20) $fatal(1,"fixture did not queue old words");
 #OFFSET;
 if(RADIO_ONLY) begin sample_reset=1;flush_pacer=1; end
 else resetn=0;
 cpu_enable=1;
 repeat(5) @(negedge clk);
 if(source_ready) $fatal(1,"source still ready under reset");
 check_new_epoch=1;
 if(RADIO_ONLY) begin sample_reset=0;flush_pacer=0; end
 else resetn=1;
 repeat(30) begin
  @(negedge clk);
  if(source_ready || output_valid) $fatal(1,"release occurred without ADC clock acknowledgement");
 end
 adc_enable=1;
 repeat(30) @(negedge sample_clk);
 if(!source_ready) $fatal(1,"source did not become ready after clock resumed");
 for(j=0;j<100;j=j+1) send(10000+j);
 repeat(100) @(negedge sample_clk);
 if(count!=100 || cdc_dropped_count || pacer_dropped_count) $fatal(1,"new epoch did not drain exactly");
 $display("PASS %d %d",RATE_VALUE,RADIO_ONLY);
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("rate", [2_500_000, 60_000_000])
@pytest.mark.parametrize("radio_only", [False, True])
@pytest.mark.parametrize("offset", [1, 4, 7, 11])
def test_stopped_adc_requires_clock_ack_and_purges_occupied_fifo(rate, radio_only, offset, tmp_path):
    bench, executable = tmp_path/"tb.sv", tmp_path/"sim"
    bench.write_text(BENCH.replace("RATE;", f"{rate};").replace("RADIO;", f"{int(radio_only)};").replace("#OFFSET;", f"#{offset};"))
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                            *[str(BANK_ROOT/name) for name in ("starlink_glrt_ingress.v", "starlink_glrt_sample_cdc.v", "starlink_glrt_pacer.v")]],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stdout+built.stderr
    process = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stdout+process.stderr
    output = [tuple(map(int, row.split()[1:])) for row in process.stdout.splitlines() if row.startswith("O ")]
    first = 20 if radio_only else 0
    assert output == [(first+j, 10000+j, -10000-j, (first+j) % (rate//2_500_000), int(j==0)) for j in range(100)]
