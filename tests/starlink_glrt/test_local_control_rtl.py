"""GLA1 queue/ownership tests with an explicitly controlled numerical engine."""
import subprocess
from pathlib import Path

import pytest

SIGNALS = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,clear=0,enabled=0,source_closed=0,source_abort=0,input_valid=0,input_gap=0;
reg [31:0] visit_id=123,write_data=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg write_request=0;
reg [7:0] write_address=0,read_address=0;
reg [3:0] write_strobe=15;
wire [31:0] read_data;
wire reserved,records_pending,halted,settled;
starlink_glrt_local_control #(.PERIOD_SAMPLES(14000)) dut(.*);
integer n,w,r,mode=0;
task tick;begin @(negedge clk);end endtask
task command(input [31:0] value);begin
 tick;
 write_request=1;write_address=4;write_data=value;tick;write_request=0;
end endtask
task check(input [7:0] address,input [31:0] expected);begin
 read_address=address;#1;if(read_data!==expected)
  $fatal(1,"register %h actual %h expected %h",address,read_data,expected);
end endtask
task capture(input integer count);begin
 for(n=0;n<count;n=n+1) begin
  input_valid=1;input_index=64'h20000000000003+n;input_i=n;input_q=~n;tick;
 end
 input_valid=0;
end endtask
task offer(input integer record_number);begin
 dut.engine.test_first=64'h20000000000003+(record_number/9)*14000;
 dut.engine.test_decision=record_number%9==8;
 dut.engine.test_reasons=record_number==17 ? 4 : 0;
 dut.engine.test_rank=record_number%9==8 ? 0 : record_number%9;
 dut.engine.test_valid=1;
end endtask
task read_record(input integer record_number);begin
 for(w=0;w<16;w=w+1) begin
  read_address=32+w;#1;$display("WORD %d %d %h",record_number,w,read_data);tick;
 end
end endtask
'''

STUB = r'''
 reg test_valid=0,test_decision=0,test_busy=0,test_ready=1,test_fault=0;
 reg [4:0] test_reasons=0;
 reg [2:0] test_rank=0;
 reg [63:0] test_first=0;
 assign busy=test_busy;
 assign arm_ready=resetn && !flush && test_ready;
 assign output_valid=test_valid && resetn && !flush;
 assign done=output_valid && output_ready && output_decision;
 assign output_decision=test_decision;
 assign output_reasons=test_reasons;
 assign output_rank=test_rank;
 assign output_support=3;
 assign output_epoch=17;
 assign output_coarse_frequency=4;
 assign output_coarse_score=65000;
 assign output_acquire=10000;
 assign output_verify=9000;
 assign output_control=1000;
 assign output_conditioned=11000;
 assign output_cfo_units=-13'sd1234;
 always_comb begin fault=test_fault;rejected_arms=0;window_first_index=test_first;end
 always @(posedge clk) begin
  if(!resetn || flush) test_busy<=0;
  else if(arm) test_busy<=1;
  else if(done) test_busy<=0;
 end
endmodule
'''


def simulate(tmp_path, body):
    root = Path(__file__).resolve().parents[2] / "hdl/library/starlink_glrt"
    source = (root / "starlink_glrt_local_search.v").read_text()
    start = source.index("module starlink_glrt_local_search")
    end = source.index("\n);", start) + 3
    (tmp_path / "stub.v").write_text(source[start:end] + STUB)
    (tmp_path / "tb.v").write_text(SIGNALS + body)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(tmp_path / "sim"),
        str(tmp_path / "tb.v"), str(tmp_path / "stub.v"), str(root / "starlink_glrt_local_control.v"),
        str(root / "starlink_glrt_local_cadence.v")], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run(["vvp", str(tmp_path / "sim")], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "simulation.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout + run.stderr
    return run.stdout


def test_queue_snapshot_simultaneous_pop_push_wrap_and_complete_accounting(tmp_path):
    output = simulate(tmp_path, r'''
initial begin
 repeat(3) tick;resetn=1;enabled=1;capture(28000);source_closed=1;repeat(4) tick;
 check(0,32'h474c4131);check(1,32'h00010000);check(5,14000);check(6,14000);check(7,16);
 check(13,2);check(14,2);check(15,0);check(19,2);
 tick;for(r=0;r<16;r=r+1) begin offer(r);tick;end
 offer(16);repeat(5) tick;
 if(dut.output_ready || !records_pending || !reserved || halted) $fatal(1,"full queue did not stall");
 check(8,16);check(9,16);check(11,16);check(12,0);check(16,1);check(17,1);check(19,1);
 command(2);check(10,1);check(66,16);check(68,16);check(69,0);check(70,2);check(71,2);
 check(72,0);check(73,1);check(74,1);check(75,0);check(76,1);check(77,123);
 // A multiword read must not advance the queue. Pop and push replace a full
 // slot on the same edge without changing its capacity or the unread head.
 read_record(0);command(1);dut.engine.test_valid=0;
 check(8,16);check(11,17);check(12,1);check(68,16);check(69,0);
 offer(17);read_record(1);command(1);dut.engine.test_valid=0;
 check(8,16);check(11,18);check(12,2);check(16,2);check(17,1);check(18,0);check(19,0);
 for(r=2;r<18;r=r+1) begin read_record(r);command(1);end
 check(8,0);check(11,18);check(12,18);check(2,32'h113);
 if(!settled || reserved || records_pending || halted) $fatal(1,"drain not settled");
 for(w=0;w<16;w=w+1) check(32+w,0);
 command(2);check(10,2);check(66,0);check(68,18);check(69,18);check(73,2);check(76,0);
 tick;clear=1;tick;clear=0;enabled=0;source_closed=0;repeat(2) tick;
 check(3,0);check(8,0);check(10,0);check(11,0);check(14,0);check(16,0);check(18,0);
 $display("PASS");$finish;
end
endmodule
''')
    words = [line.split() for line in output.splitlines() if line.startswith("WORD ")]
    assert len(words) == 18 * 16
    for sequence in range(18):
        first = 0x20000000000003 + (sequence // 9) * 14000
        rank = 0 if sequence % 9 == 8 else sequence % 9
        reasons = 4 if sequence == 17 else 0
        flags = (17 << 16) | (4 << 12) | (rank << 9) | (3 << 6) | (reasons << 1) | int(sequence % 9 == 8)
        expected = [0x474C4131, 123, sequence, first & 0xFFFFFFFF, first >> 32, flags,
                    (-1234) & 0xFFFFFFFF, 65000, 10000, 9000, 1000, 11000, 14000, 0, 0, 0]
        actual = [int(row[3], 16) for row in words if int(row[1]) == sequence]
        assert actual == expected


@pytest.mark.parametrize("damage,expected_faults,partial", [
    ("source_closed=1;", 0, True),
    ("source_abort=1;source_closed=1;", 4, False),
    ("dut.engine.test_fault=1;source_closed=1;", 2, False),
    ("input_valid=1;input_gap=1;tick;input_valid=0;input_gap=0;source_closed=1;", 1, False),
    ("input_valid=1;input_index=99;tick;input_valid=0;source_closed=1;", 1, False),
    ("command(1);source_closed=1;", 8, False),
    ("write_strobe=1;command(2);source_closed=1;", 8, False),
    ("dut.buffered=32'hffffffff;offer(0);source_closed=1;", 16, False),
])
def test_abort_fences_unfinished_decisions_and_preserves_counts(tmp_path, damage, expected_faults, partial):
    simulate(tmp_path, r'''
initial begin
 repeat(3) tick;resetn=1;enabled=1;capture(3);
 DAMAGE
 repeat(8) tick;
 check(3,FAULTS);check(14,1);check(16,0);check(18,1);check(19,0);check(8,0);
 if(!settled || reserved || !dut.aborted_visit) $fatal(1,"abort not settled");
 if(PARTIAL && !dut.incomplete_capture) $fatal(1,"partial tail not explicit");
 // The engine cannot resume when the original error disappears.
 dut.engine.test_fault=0;source_abort=0;dut.engine.test_valid=0;
 repeat(5) tick;check(18,1);check(19,0);
 tick;clear=1;tick;clear=0;enabled=0;source_closed=0;repeat(2) tick;
 check(3,0);check(14,0);check(18,0);
 $display("PASS");$finish;
end
endmodule
'''.replace("DAMAGE", damage).replace("FAULTS", str(expected_faults)).replace("PARTIAL", str(int(partial))))


def test_skipped_cadence_and_explicit_abort_after_complete_capture(tmp_path):
    simulate(tmp_path, r'''
initial begin
 repeat(3) tick;resetn=1;enabled=1;capture(14000);
 dut.engine.test_ready=0;input_valid=1;input_index=input_index+1;tick;input_valid=0;
 source_closed=1;repeat(4) tick;
 check(13,2);check(14,1);check(15,1);check(18,0);check(19,1);
 if(dut.incomplete_capture || settled) $fatal(1,"complete buffer aborted prematurely");
 command(4);repeat(4) tick;
 check(3,0);check(18,1);check(19,0);
 if(!settled || reserved) $fatal(1,"explicit abort not settled");
 $display("PASS");$finish;
end
endmodule
''')
