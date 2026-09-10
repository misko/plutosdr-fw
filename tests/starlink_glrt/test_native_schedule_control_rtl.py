"""Shared manual/scheduled engine ownership and coherent GLS1 control reads."""
from __future__ import annotations

import subprocess

import pytest

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_engine_rtl import bank_for, expected, sample
from .test_native_queued_engine_rtl import signed

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,wr=0,swr=0,srr=0,good=1,gap=0;
reg [7:0] wa=0,ra=0,sra=0;
reg [31:0] wd=0,cdc=0,pacer=0;
reg [3:0] strobe=15;
reg [63:0] index=0;
wire signed [15:0] ii=(index*31)%65536-32768,iq=(index*173)%65536-32768;
wire [31:0] rd,srd,cd;
wire ack,owner,reserved,cv;
starlink_glrt_native_control #(.SAMPLE_COUNT(96),.ENABLE_SCHEDULE(1),.TEMPLATE_FILE("BANK_PATH")) dut (
 .clk(clk),.resetn(resetn),.write_request(wr),.write_address(wa),.read_address(ra),
 .write_data(wd),.write_strobe(strobe),.read_data(rd),.base_idle(1'b1),.base_ready(1'b1),
 .fifo_empty(1'b1),.capture_ready(1'b1),.capture_pop(1'b0),.capture_owner(owner),.reserved(reserved),
 .capture_valid(cv),.capture_data(cd),.source_good(good),.cdc_dropped_count(cdc),.pacer_dropped_count(pacer),
 .latest_index(index),.input_valid(1'b1),.input_gap(gap),.input_clipped(1'b0),
 .input_index(index),.input_i(ii),.input_q(iq),
 .schedule_write_request(swr),.schedule_read_request(srr),.schedule_write_address(wa),
 .schedule_read_address(sra),.schedule_read_ack(ack),.schedule_read_data(srd));
always @(posedge clk) if(resetn) begin
 index<=index+1'b1;
 if(dut.admit && dut.schedule_job_valid) $fatal(1,"engine admitted two owners");
 if(cv || owner) $fatal(1,"capture-off scheduled work claimed IQ DMA");
end
task write_reg(input integer scheduled,input [7:0] address,input [31:0] data);
 begin
  wa=address;wd=data;wr=!scheduled;swr=scheduled;
  @(negedge clk);wr=0;swr=0;@(negedge clk);
 end
endtask
task sr(input [7:0] address);
 integer waited;
 begin
  sra=address;srr=1;@(negedge clk);srr=0;waited=0;
  while(!ack) begin @(negedge clk);waited=waited+1; if(waited>3) $fatal(1,"read not acknowledged");end
  if(address[7:5]==4 && waited!=1) $fatal(1,"head read bypassed synchronous RAM");
  $display("S %h %h",address,srd);
  @(negedge clk);if(ack) $fatal(1,"duplicate read acknowledgement");
 end
endtask
task mr(input [7:0] address);
 begin ra=address;@(negedge clk);$display("M %h %h",address,rd);end
endtask
task snapshot;
 begin write_reg(1,2,8);for(integer k=0;k<20;k=k+1) sr(8'h40+k);end
endtask
task head;
 begin for(integer k=0;k<32;k=k+1) sr(8'h80+k);end
endtask
task configure_schedule(input [31:0] tag,input [31:0] start,input [31:0] period,input [7:0] repeats);
 begin
  write_reg(1,5,tag);write_reg(1,6,start);write_reg(1,7,0);write_reg(1,8,0);
  write_reg(1,9,period<<16);write_reg(1,10,period>>16);
  write_reg(1,11,32'd4096<<16);write_reg(1,12,0);
  write_reg(1,13,0);write_reg(1,14,0);write_reg(1,15,17);
  write_reg(1,16,repeats);write_reg(1,17,20000);write_reg(1,18,0);
 end
endtask
initial begin
 repeat(3) @(negedge clk);resetn=1;@(negedge clk);
 BODY
 $display("PASS");$finish;
end
initial begin #300000;$fatal(1,"control test hung");end
endmodule
'''


def simulate(tmp_path, body):
    bank = bank_for(96)
    bank_path, bench, executable = [tmp_path/name for name in ("bank.mem", "tb.sv", "sim")]
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    bench.write_text(BENCH.replace("BANK_PATH", str(bank_path)).replace("BODY", body))
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "cubic_reference", "cubic_coefficients", "native_rotate", "native_products", "local_moments",
        "native_engine", "native_control", "native_schedule", "native_scheduled_results",
        "native_result_queue", "native_schedule_control")]
    sources.append(BANK_ROOT.parent/"common/ad_dds_cordic_pipe.v")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench), *map(str, sources)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout+run.stderr
    return [(words[0], int(words[1], 16), int(words[2], 16))
            for line in run.stdout.splitlines() if (words := line.split()) and words[0] in ("S", "M")]


def groups(reads, kind, begin, count):
    rows = [(address, value) for owner, address, value in reads if owner == kind]
    return [[value for _address, value in rows[n:n+count]] for n, (address, _) in enumerate(rows)
            if address == begin and [a for a, _ in rows[n:n+count]] == list(range(begin, begin+count))]


def check_moments(record, start):
    bank = bank_for(96)
    oracle = expected((start, 17, 4096), [sample(start+n) for n in range(96)],
                      coefficient_oracle(bank, 24, 96))
    assert record[3:9] == [start, 0, 17, 4096, 96, 0]
    assert [signed(record[k:k+2]) for k in (9, 11, 13, 15)] == oracle[5:9]
    assert [signed(record[k:k+3]) for k in (17, 20)] == oracle[9:11]
    assert record[23]+(record[24] << 32) == oracle[11]


def test_manual_conflicts_cannot_corrupt_scheduled_heads_and_engine_returns_to_manual(tmp_path):
    reads = simulate(tmp_path, r'''
 sr(0);sr(1);sr(8'h80);write_reg(1,2,16);configure_schedule(23,1000,1000,2);write_reg(1,2,1);
 while(index<2500) @(negedge clk);
 // No manual result or completion may refer to the scheduled engine output.
 mr(12);mr(13);mr(14);mr(8'h80);
 write_reg(0,2,1);write_reg(0,2,4);mr(4);
 head;head;write_reg(1,2,32);head;write_reg(1,2,32);snapshot;
 write_reg(0,2,4);write_reg(0,5,29);write_reg(0,6,8000);write_reg(0,7,0);
 write_reg(0,8,17);write_reg(0,9,4096);write_reg(0,10,0);write_reg(0,2,1);
 while(index<8400) @(negedge clk);
 for(integer k=0;k<32;k=k+1) mr(8'h80+k);
 write_reg(0,2,8);repeat(5) @(negedge clk);write_reg(0,2,4);
 mr(4);if(reserved) $fatal(1,"shared engine ownership leaked");
 ''')
    assert reads[:3] == [("S", 0, 0x474c5331), ("S", 1, 0x10000), ("S", 0x80, 0)]
    heads = groups(reads, "S", 0x80, 32)
    assert len(heads) == 3 and heads[0] == heads[1]
    for frame, head in enumerate((heads[0], heads[2])):
        assert head[:3] == [0x474c5331, frame, 23]
        assert head[27:] == [frame, 0, 0, 0, 0]
        check_moments(head, 1000+1000*frame)
    snapshot = groups(reads, "S", 0x40, 20)[0]
    assert snapshot[6:18] == [0, 2, 2, 0, 0, 0, 0, 0, 2, 2, 0, 2]
    manual = [(a, v) for t, a, v in reads if t == "M"]
    assert manual[:5] == [(12, 0), (13, 0), (14, 0), (0x80, 0), (4, 1)]
    manual_head = groups(reads, "M", 0x80, 32)[0]
    assert manual_head[:3] == [0x474c4e31, 0, 29]
    check_moments(manual_head, 8000)
    assert manual[-1] == (4, 0)


@pytest.mark.parametrize("failure", ["cdc=1;", "pacer=1;", "good=0;", "gap=1;"])
def test_source_epoch_change_between_pilots_fences_future_work_and_rebase_requires_drain(tmp_path, failure):
    reads = simulate(tmp_path, r'''
 write_reg(1,2,16);configure_schedule(31,1000,3000,3);write_reg(1,2,1);
 while(index<2200) @(negedge clk);
 ''' + failure + r'''
 repeat(5) @(negedge clk);good=1;gap=0;
 write_reg(1,2,16);head;snapshot;
 // Snapshot remains coherent as the live native counter advances.
 sr(8'h43);repeat(100) @(negedge clk);sr(8'h43);
 write_reg(1,2,32);write_reg(1,2,4);repeat(3) @(negedge clk);
 write_reg(1,2,16);sr(19);sr(4);snapshot;
 if(reserved) $fatal(1,"invalidated predictions retained ownership");
 ''')
    head = groups(reads, "S", 0x80, 32)[0]
    check_moments(head, 1000)
    before, after = groups(reads, "S", 0x40, 20)
    assert before[2] == 1 and before[6] == 9  # source fence plus forbidden rebase
    assert before[7:17] == [3, 1, 0, 0, 2, 0, 0, 1, 0, 1]
    assert after[2] == 2 and after[6:18] == [0]*12
    frozen = [v for t, a, v in reads if t == "S" and a == 0x43]
    assert frozen[0] == frozen[1] == frozen[2]


def test_invalid_strobes_config_and_unbased_submit_are_explicit(tmp_path):
    reads = simulate(tmp_path, r'''
 write_reg(1,2,1);sr(4);write_reg(1,2,4);repeat(3) @(negedge clk);
 strobe=3;write_reg(1,5,17);strobe=15;sr(5);sr(4);
 write_reg(1,2,4);repeat(3) @(negedge clk);write_reg(1,8,65536);sr(8);sr(4);
 write_reg(1,2,4);repeat(3) @(negedge clk);write_reg(1,2,16);
 configure_schedule(17,1000,1000,2);write_reg(1,5,0);write_reg(1,2,1);
 repeat(3) @(negedge clk);sr(4);snapshot;
 ''')
    assert [(a, v) for t, a, v in reads[:7]] == [(4, 1), (5, 0), (4, 1), (8, 0), (4, 1), (4, 2), (0x40, 0x474c5331)]
    snapshot = groups(reads, "S", 0x40, 20)[0]
    assert snapshot[7:18] == [0]*11


@pytest.mark.parametrize("termination", ["complete", "source", "cancel"])
def test_stale_manual_descriptor_cannot_affect_scheduled_admission_or_abort(tmp_path, termination):
    action = {"complete":"", "source":"pacer=1;", "cancel":"write_reg(1,2,2);"}[termination]
    reads = simulate(tmp_path, r'''
 // Deliberately incompatible manual start/phase stays staged while the other
 // owner prepares and admits (or cancels) its finite prediction.
 write_reg(0,5,42);write_reg(0,6,32'hffffffff);write_reg(0,7,32'hffffffff);
 write_reg(0,8,32'hdeadbeef);write_reg(0,9,32'hffffffff);write_reg(0,10,0);
 write_reg(1,2,16);configure_schedule(23,1000,1000,1);write_reg(1,2,1);
 while(index<488) @(negedge clk);
 '''+action+r'''
 while(index<1500) @(negedge clk);
 head;snapshot;
 if(dut.scheduled.control.head_valid) write_reg(1,2,32);
 write_reg(1,2,4);repeat(4) @(negedge clk);
 // The retained manual descriptor must still produce its own explicit range
 // error when ownership returns, without any of the scheduled phase/start.
 write_reg(0,2,1);repeat(100) @(negedge clk);
 for(integer k=0;k<32;k=k+1) mr(8'h80+k);
 write_reg(0,2,8);repeat(5) @(negedge clk);write_reg(0,2,4);
 if(reserved) $fatal(1,"ownership leaked after range-error result");
 ''')
    head = groups(reads,"S",0x80,32)[0]
    snapshot = groups(reads,"S",0x40,20)[0]
    if termination == "complete":
        check_moments(head,1000)
        assert snapshot[7:17] == [1,1,0,0,0,0,0,1,0,1]
    else:
        assert head == [0]*32
        assert snapshot[7:17] == [1,0,0,0,int(termination=="source"),0,
                                  int(termination=="cancel"),0,0,0]
    manual = groups(reads,"M",0x80,32)[0]
    assert manual[:9] == [0x474c4e31,0,42,0xffffffff,0xffffffff,0xdeadbeef,0xffffffff,0,4]
    assert manual[9:25] == [0]*16
