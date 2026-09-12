"""Tracking register capabilities, immutable queued evidence and epoch recovery."""
import subprocess

import pytest

from tools.starlink_glrt_tracking_abi import TrackingResult, TrackingSnapshot

from . import test_tracking_snapshots
from .ddc import BANK_ROOT
from .test_tracking_schedule import RATES

transport = test_tracking_snapshots.transport

BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam RATE=RATE_VALUE,N=RATE*33/25000,PHASES=RATE==2500000 ? 4 : 1;
localparam PB=PHASES==4 ? 2 : 1,C=$clog2(N+1),S=35+$clog2(N),T=S+$clog2(N),E=36+$clog2(N);
reg clk=0;always #5 clk=~clk;
reg resetn=0,wr=0,rr=0,good=1,gap=0;
reg [7:0] wa=0,ra=0;
reg [31:0] wd=0,cdc=0,pacer=0;
reg [63:0] index=0;
wire ack,reserved,job,flush,engine_gap,ready;
wire [31:0] rd,seed,step;
wire [63:0] start;
wire [PB-1:0] phase;
reg result=0;
reg [63:0] result_start=0;
reg [31:0] result_seed=0,result_step=0;
reg [PB-1:0] result_phase=0;
starlink_glrt_native_schedule_control #(.TRACKING(1),.SOURCE_RATE(RATE),.SAMPLE_COUNT(N)) dut (
 .clk(clk),.resetn(resetn),.write_request(wr),.read_request(rr),.write_address(wa),.read_address(ra),
 .write_data(wd),.write_strobe(4'hf),.read_ack(ack),.read_data(rd),.manual_idle(1'b1),.base_ready(1'b1),
 .source_good(good),.input_gap(gap),.cdc_dropped_count(cdc),.pacer_dropped_count(pacer),
 .latest_index(index),.reserved(reserved),.engine_ready(!result),.job_valid(job),.job_start(start),
 .job_phase_seed(seed),.job_phase_step(step),.job_reference_phase(phase),.engine_flush(flush),
 .engine_gap(engine_gap),.engine_result(result),.engine_result_ready(ready),.result_start(result_start),
 .result_seed(result_seed),.result_step(result_step),.result_reference_phase(result_phase),
 .result_count(C'(N)),.result_fault(8'd0),.ri(S'(0)),.rq(S'(0)),.di(S'(0)),.dq(S'(0)),
 .ti(T'(0)),.tq(T'(0)),.energy(E'(0)));
// A bounded engine stub isolates control/epoch semantics. Full-rate arithmetic
// and 750 Hz scheduling are tested with the real engine in queued-engine tests.
always @(posedge clk) if(resetn) begin
 if(job) begin
  result<=1;result_start<=start;result_seed<=seed;result_step<=step;result_phase<=phase;
 end
 if(result && ready) result<=0;
end
task write_reg(input [7:0] address,input [31:0] data);
 begin wa=address;wd=data;wr=1;@(negedge clk);wr=0;@(negedge clk);end
endtask
task read_reg(input [7:0] address);
 integer waited;
 begin
  ra=address;rr=1;@(negedge clk);rr=0;waited=0;
  while(!ack) begin @(negedge clk);waited++;if(waited>3) $fatal(1,"read timed out");end
  if(address[7:5]==4 && waited!=1) $fatal(1,"head bypassed RAM latency");
  $display("R %h %h",address,rd);@(negedge clk);
 end
endtask
task snapshot;
 begin write_reg(2,8);for(integer k=0;k<24;k++) read_reg(64+k);end
endtask
task head;
 begin for(integer k=0;k<32;k++) read_reg(128+k);end
endtask
initial begin
 repeat(3) @(negedge clk);resetn=1;@(negedge clk);
 read_reg(0);read_reg(1);for(integer k=0;k<7;k++) read_reg(32+k);
 write_reg(2,16);
 write_reg(5,17);write_reg(6,1000000);write_reg(7,0);write_reg(8,24576);
 write_reg(9,32'(PERIOD_VALUE));write_reg(10,32'(48'dPERIOD_VALUE>>32));
 write_reg(11,4096<<16);write_reg(12,0);write_reg(13,0);write_reg(14,0);
 write_reg(15,19);write_reg(16,3);write_reg(17,2000000);write_reg(18,0);
 write_reg(2,1);repeat(10) @(negedge clk);
 index=1000000-((512+60000000/RATE-1)/(60000000/RATE));
 repeat(100) @(negedge clk);head;
 FAILURE_ACTION
 repeat(10) @(negedge clk);good=1;gap=0;
 // Queued evidence prevents both destructive CLEAR and a new epoch.
 write_reg(2,4);write_reg(2,16);snapshot;head;
 write_reg(2,32);write_reg(2,4);repeat(4) @(negedge clk);
 write_reg(2,16);snapshot;
 if(reserved) $fatal(1,"ownership leaked after recovery");
 $finish;
end
initial begin #100000; $fatal(1,"tracking control hung");end
endmodule
'''


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("failure", ["cdc=1;", "pacer=1;", "good=0;", "gap=1;"])
def test_source_change_fences_predictions_and_preserves_head_until_ack(tmp_path, transport, rate, failure):
    bench, executable = tmp_path/"tb.sv", tmp_path/"sim"
    period = round(rate*65536/750)
    bench.write_text(BENCH.replace("RATE_VALUE", str(rate)).replace("PERIOD_VALUE", str(period))
                     .replace("FAILURE_ACTION", failure))
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "native_schedule", "native_result_queue", "native_scheduled_results", "native_schedule_control")]
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(bench), *map(str, sources)], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=10, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    rows = [tuple(int(w, 16) for w in line.split()[1:]) for line in run.stdout.splitlines()
            if line.startswith("R ")]
    bank = 0xdc509401 if rate == 2500000 else 0xb04a2fab
    assert rows[:9] == list(zip([0, 1, *range(32, 39)],
        [0x474c5431, 0x10000, rate*33//25000, rate, 64, bank, 1, 4 if rate == 2500000 else 1, 24],
        strict=True))
    heads, snapshots = [], []
    for n, (address, _) in enumerate(rows):
        if address == 128: heads.append([v for _, v in rows[n:n+32]])
        if address == 64: snapshots.append([v for _, v in rows[n:n+24]])
    assert len(heads) == len(snapshots) == 2 and heads[0] == heads[1]
    head = TrackingResult.from_sysfs("GLT1 00010000 00000001 "+" ".join(f"{v:08x}" for v in heads[0]))
    assert (head.rate, head.reference_phase, head.start) == (rate, 2 if rate == 2500000 else 0, 1000000)
    before, after = [TrackingSnapshot.from_sysfs("GLT1SNAP 00010000 "+" ".join(f"{v:08x}" for v in w))
                     for w in snapshots]
    for n, words in enumerate(snapshots):
        rc, decoded = test_tracking_snapshots.parse(transport, test_tracking_snapshots.text(words))
        assert rc == 0 and list(decoded) == words
        assert transport.glrt_tracking_snapshot_drained(decoded) == n
    assert before.epoch == 1 and before.faults == 9 and before.queued == 1
    assert (before.configured, before.admitted, before.unavailable, before.committed, before.popped) == (3, 1, 2, 1, 0)
    with pytest.raises(ValueError): before.require_drained()
    assert after.epoch == 2 and after.faults == 0 and after.configured == 0
    after.require_drained()
