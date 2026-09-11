"""Source-index cadence, exact first-sample staging, skipped work and closure."""
from pathlib import Path
import re
import subprocess

import pytest


BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam P=PERIOD,W=WINDOW,N=COUNT;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,source_closed=0,input_valid=0,input_gap=0,engine_arm_ready=1;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
wire engine_arm,engine_input_valid,closed,incomplete_capture,fault;
wire signed [15:0] engine_input_i,engine_input_q;
wire [63:0] engine_input_index;
wire [31:0] opportunities,admitted,skipped;
starlink_glrt_local_cadence #(.PERIOD_SAMPLES(P),.WINDOW_SAMPLES(W)) dut(.*);
integer n,arms=0,captured=0,left=0,completed=0;
reg [63:0] expected=0;
reg previous_valid=0;
reg [95:0] previous_sample=0;
always @(posedge clk) begin
 if(resetn && !flush && !fault) begin
  if(engine_input_valid!==previous_valid) $fatal(1,"staging validity");
  if(engine_input_valid && {engine_input_index,engine_input_q,engine_input_i}!==previous_sample)
    $fatal(1,"staging data/index");
  if(engine_arm) begin
   if(left!=0 || input_index!=64'h20000000000003+arms*P+(arms>=1 ? P : 0))
    $fatal(1,"cadence moved or replaced capture");
   arms=arms+1;left=W;expected=input_index;
  end else if(engine_input_valid && left>0) begin
   if(engine_input_index!=expected) $fatal(1,"window coordinate");
   expected=expected+1;left=left-1;captured=captured+1;
   if(left==0) completed=completed+1;
  end
 end
 previous_valid<=input_valid && resetn && !flush;
 previous_sample<={input_index,input_q,input_i};
end
initial begin
 repeat(3) @(negedge clk);resetn=1;
 for(n=0;n<N;n=n+1) begin
  // Variable source pacing must not move the sample-domain search cadence.
  if(n%97==5) begin input_valid=0;repeat(2) @(negedge clk);end
  input_valid=1;input_index=64'h20000000000003+n;input_i=n;input_q=~n;
  engine_arm_ready=!(n>=P && n<2*P);
  @(negedge clk);
 end
 input_valid=0;source_closed=1;
 repeat(3) @(negedge clk);
 if(fault || !closed || opportunities!=ATTEMPTS || admitted!=ADMITS || skipped!=1 ||
    arms!=ADMITS || captured!=CAPTURED || completed!=COMPLETED || incomplete_capture!=PARTIAL)
  $fatal(1,"closure accounting opp=%d admitted=%d captured=%d completed=%d partial=%d",
    opportunities,admitted,captured,completed,incomplete_capture);
 // A closed visit cannot silently restart when source_closed is deasserted.
 source_closed=0;input_valid=1;input_index=input_index+1;
 @(negedge clk);input_valid=0;
 if(!fault || engine_input_valid || engine_arm) $fatal(1,"post-close data accepted");
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || closed || incomplete_capture || opportunities || admitted || skipped)
  $fatal(1,"flush did not clear visit");
 $display("PASS");$finish;
end
endmodule
'''


def simulate(tmp_path, bench):
    source = Path(__file__).resolve().parents[2] / "hdl/library/starlink_glrt/starlink_glrt_local_cadence.v"
    (tmp_path / "tb.v").write_text(bench)
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(tmp_path / "sim"),
                    str(tmp_path / "tb.v"), str(source)], check=True, capture_output=True, text=True)
    result = subprocess.run(["vvp", str(tmp_path / "sim")], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0 and "PASS" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("period,window", [(19, 7), (250000, 14000)])
@pytest.mark.parametrize("partial", [False, True])
def test_cadence_and_exact_window_staging(tmp_path, period, window, partial):
    count = (2 if partial else 3) * period + window - int(partial)
    admissions = 2 if partial else 3
    replacements = {"PERIOD": period, "WINDOW": window, "COUNT": count,
                    "ATTEMPTS": admissions + 1, "ADMITS": admissions,
                    "CAPTURED": admissions * window - int(partial),
                    "COMPLETED": admissions - int(partial), "PARTIAL": int(partial)}
    bench = BENCH
    for key, value in replacements.items():
        bench = re.sub(rf"\b{key}\b", str(value), bench)
    simulate(tmp_path, bench)


@pytest.mark.parametrize("damage", ["input_gap=1;", "input_index=9;", "source_closed=1;",
    "dut.opportunities=32'hffffffff;dut.remaining=0;",
    "dut.admitted=32'hffffffff;dut.remaining=0;",
    "dut.skipped=32'hffffffff;dut.remaining=0;engine_arm_ready=0;",
    "dut.expected_index=0;input_index=0;"])
def test_faults_fence_admission_and_forwarding(tmp_path, damage):
    bench = r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,source_closed=0,input_valid=0,input_gap=0,engine_arm_ready=1;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
wire engine_arm,engine_input_valid,closed,incomplete_capture,fault;
wire signed [15:0] engine_input_i,engine_input_q;
wire [63:0] engine_input_index;
wire [31:0] opportunities,admitted,skipped;
starlink_glrt_local_cadence dut(.*);
initial begin
 repeat(3) @(negedge clk);resetn=1;input_valid=1;
 @(negedge clk);input_index=1;
 DAMAGE
 #1;if(engine_arm) $fatal(1,"bad source admitted");
 @(negedge clk);input_valid=0;
 if(!fault || engine_input_valid || engine_arm) $fatal(1,"fault not fenced");
 flush=1;@(negedge clk);flush=0;source_closed=0;input_gap=0;input_index=123;
 engine_arm_ready=1;input_valid=1;
 #1;if(!engine_arm) $fatal(1,"restart not admitted");
 @(negedge clk);input_valid=0;
 if(fault || !engine_input_valid || engine_input_index!=123 || admitted!=1 || opportunities!=1)
  $fatal(1,"restart wrong");
 $display("PASS");$finish;
end
endmodule
'''
    simulate(tmp_path, bench.replace("DAMAGE", damage))
