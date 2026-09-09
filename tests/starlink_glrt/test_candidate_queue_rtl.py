"""Isolate queue admission from DSP latency to exercise simultaneous boundaries."""
import subprocess

import pytest

from .ddc import BANK_ROOT


BENCH = r'''
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,source_closed=0,propose=0,resources=0;
reg [63:0] start=1000,newest=1100;
integer mode;
starlink_glrt_receiver #(.NATIVE_TEMPLATE_FILE("NATIVE"),.ACQUISITION_TEMPLATE_FILE("NATIVE"),
 .TWIDDLE_FILE("TWIDDLE")) dut(.clk(clk),.resetn(resetn),.flush(1'b0),.source_closed(source_closed),
 .input_valid(1'b0),.input_gap(1'b0),.input_i(16'd0),.input_q(16'd0),.input_index(64'd0),
 .input_phase(5'd0),.decision_enable(1'b0),.acquisition_threshold_q16(17'd0),
 .glrt_threshold_q16(17'd0),.glrt_margin_q16(17'd0));
task tick;begin @(posedge clk);#1;@(negedge clk);end endtask
initial begin
 if(!$value$plusargs("MODE=%d",mode)) mode=0;
 repeat(4) tick();resetn=1;tick();
 // Only this admission test replaces the already-tested arithmetic workers.
 // The actual queue, expiry comparison and accounting always blocks execute.
 force dut.converted_valid=propose;force dut.converted_start=start;
 force dut.native_ready=resources;force dut.stage_ready=resources;
 force dut.latest_source_index=newest;
 force dut.native_fault=0;force dut.native_rejected=0;force dut.stage_fault=0;
 propose=1;tick();propose=0;
 if(!dut.waiting_valid || dut.admitted_candidates!=0) $fatal(1,"waiting candidate missing");
 if(mode==0 || mode==1) begin
  if(mode==1) dut.selected_close_rejections=64'hfffffffffffffffe;
  propose=1;start=1200;source_closed=1;tick();propose=0;
  if(mode==0) begin
   if(dut.selected_close_rejections!=2 || dut.waiting_valid || dut.detector_halted) $fatal(1,"two close rejections lost");
  end else if(dut.selected_close_rejections!=64'hfffffffffffffffe || !dut.detector_halted)
   $fatal(1,"two-candidate close wrapped counter");
 end else if(mode==2) begin
  propose=1;start=1200;resources=1;tick();propose=0;resources=0;
  if(!dut.waiting_valid || dut.waiting_start!=1200 || dut.admitted_candidates!=1) $fatal(1,"handoff lost incoming selection");
  tick();resources=1;tick();
  if(dut.waiting_valid || dut.admitted_candidates!=2 || dut.busy_rejections!=0 || dut.detector_halted)
   $fatal(1,"handoff did not preserve both selections");
 end else if(mode==3) begin
  newest=2023;tick();
  if(dut.waiting_valid || dut.expired_candidates!=1 || dut.busy_rejections!=1 || dut.admitted_candidates!=0 || dut.detector_halted)
   $fatal(1,"expired history reached reader or disappeared");
 end else begin
  propose=1;start=1200;#1;
  if(dut.selected_start!=1200 || dut.native.candidate_start!=1000 || dut.admit)
   $fatal(1,"rejected overflow changed the native admission head");
  tick();propose=0;
  if(!dut.waiting_valid || dut.waiting_start!=1000 || dut.busy_rejections!=1) $fatal(1,"full queue replaced waiting work");
  resources=1;tick();
  if(dut.waiting_valid || dut.admitted_candidates!=1 || dut.detector_halted) $fatal(1,"waiting work did not recover");
 end
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("mode", range(5))
def test_bounded_epoch_queue_close_handoff_expiry_and_counter_exhaustion(mode, tmp_path):
    source = BENCH.replace('"NATIVE"', f'"{BANK_ROOT}/pilot_2500000_upper_q7.mem"')
    source = source.replace('"TWIDDLE"', f'"{BANK_ROOT}/glrt_dft512_q15.mem"')
    bench, executable = tmp_path / "tb.sv", tmp_path / "sim"
    bench.write_text(source)
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                               *map(str, sorted(BANK_ROOT.glob("*.v")))], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = subprocess.run(["vvp", str(executable), f"+MODE={mode}"], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stdout + run.stderr
