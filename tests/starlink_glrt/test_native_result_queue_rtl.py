"""Atomic native result publication, backpressure, wrap and generation fencing."""
from __future__ import annotations

import subprocess

import pytest

from .ddc import BANK_ROOT

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg resetn=0,reserve=0,write_valid=0,write_last=0,read_request=0,pop=0;
reg [31:0] write_data=0;
reg [4:0] read_word=0;
wire space,reserved,write_ready,head_valid,read_valid,fault;
wire [31:0] read_data,committed,popped;
wire [2:0] count,high_water;
starlink_glrt_native_result_queue #(.DEPTH_BITS(2)) dut (
 .clk(clk),.resetn(resetn),.reserve(reserve),.space(space),.reserved(reserved),
 .write_valid(write_valid),.write_data(write_data),.write_last(write_last),
 .write_ready(write_ready),.read_request(read_request),.read_word(read_word),
 .read_valid(read_valid),.read_data(read_data),.pop(pop),.head_valid(head_valid),
 .count(count),.high_water(high_water),.committed(committed),.popped(popped),.fault(fault));
integer seen=0;
function [31:0] value(input integer frame,input integer word_index);
 value=32'h9e3779b9*frame ^ (32'hdeadbeef+word_index*32'h10204081);
endfunction
task claim;
 begin
  while(!space) @(negedge clk);
  reserve=1; @(negedge clk); reserve=0;
  if(!reserved || !write_ready) $fatal(1,"slot not reserved");
 end
endtask
task put_frame(input integer frame);
 integer k;
 begin
  claim;
  for(k=0;k<32;k=k+1) begin
   // Producer stalls must not publish a partial record.
   if(k%7==0) begin write_valid=0; repeat(2) @(negedge clk); end
   write_valid=1; write_data=value(frame,k); write_last=k==31;
   @(negedge clk);
  end
  write_valid=0; write_last=0;
  if(reserved) $fatal(1,"complete record retained reservation");
 end
endtask
task inspect(input integer frame);
 integer k;
 begin
  if(!head_valid) $fatal(1,"complete head missing");
  // Reverse reads prove random word access; read the head again before POP.
  for(k=31;k>=0;k=k-1) begin
   read_request=1; read_word=k;
   @(negedge clk);
   if(!read_valid || read_data!==value(frame,k))
    $fatal(1,"head torn/overwritten frame=%d word=%d got=%h",frame,k,read_data);
  end
  read_request=0; @(negedge clk);
  if(read_valid) $fatal(1,"read valid survived without request");
 end
endtask
task consume(input integer frame);
 begin
  while(!head_valid) @(negedge clk);
  inspect(frame);
  pop=1; @(negedge clk); pop=0; seen=seen+1;
 end
endtask
task clean;
 begin
  resetn=0; reserve=0;write_valid=0;write_last=0;read_request=0;pop=0;
  repeat(2) @(negedge clk); resetn=1; @(negedge clk);
  if(head_valid || reserved || count || committed || popped || fault || read_valid)
   $fatal(1,"reset leaked prior generation");
 end
endtask
integer frame,k;
initial begin
 clean;
 BODY
 $display("PASS"); $finish;
end
initial begin #2000000; $fatal(1,"queue test hung"); end
endmodule
'''


def simulate(tmp_path, body):
    bench, executable = tmp_path / "tb.sv", tmp_path / "sim"
    bench.write_text(BENCH.replace("BODY", body))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench), str(BANK_ROOT / "starlink_glrt_native_result_queue.v")],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout+run.stderr


def test_full_queue_retains_heads_while_writer_and_reader_wrap_independently(tmp_path):
    simulate(tmp_path, r'''
 for(frame=0;frame<4;frame=frame+1) put_frame(frame);
 if(space || count!=4 || high_water!=4) $fatal(1,"full queue admission");
 repeat(40) @(negedge clk);
 inspect(0); inspect(0);
 fork
  begin for(integer p=4;p<40;p=p+1) put_frame(p); end
  begin
   for(integer r=0;r<40;r=r+1) begin
    repeat((r%5)*11) @(negedge clk);
    consume(r);
   end
  end
 join
 if(count || reserved || fault || committed!=40 || popped!=40 || seen!=40)
  $fatal(1,"record conservation failed");
 ''')


def test_partial_record_is_invisible_and_reset_discards_only_old_generation(tmp_path):
    simulate(tmp_path, r'''
 claim;
 for(k=0;k<31;k=k+1) begin
  write_valid=1; write_data=value(99,k); @(negedge clk);
  if(head_valid || count || committed) $fatal(1,"partial record published");
 end
 write_valid=0; read_request=1;
 repeat(3) @(negedge clk);
 if(read_valid) $fatal(1,"uncommitted record readable");
 clean;
 put_frame(7); consume(7);
 if(committed!=1 || popped!=1 || count || fault) $fatal(1,"fresh generation failed");
 ''')


@pytest.mark.parametrize("violation", [
    "write_valid=1;",  # no reserved slot
    "claim; reserve=1;",  # second reservation
    "claim; write_valid=1; write_last=1;",  # early end of record
    "claim; for(k=0;k<32;k=k+1) begin write_valid=1; @(negedge clk); end",  # missing end
])
def test_protocol_fault_preserves_previously_committed_head(tmp_path, violation):
    simulate(tmp_path, "put_frame(17);\n" + violation + r'''
 @(negedge clk); reserve=0; write_valid=0; write_last=0;
 if(!fault || space || write_ready || count!=1 || committed!=1)
  $fatal(1,"malformed producer not fenced");
 inspect(17); consume(17);
 if(count || popped!=1) $fatal(1,"fault prevented head drain");
 clean; put_frame(23); consume(23);
 ''')


def test_empty_pop_and_counter_exhaustion_never_wrap(tmp_path):
    simulate(tmp_path, r'''
 pop=1; @(negedge clk); pop=0;
 if(!fault || popped || count) $fatal(1,"empty pop changed accounting");
 clean;
 dut.committed=32'hfffffffe; dut.popped=32'hfffffffe;
 put_frame(27); consume(27);
 if(committed!=32'hffffffff || popped!=32'hffffffff || space || fault)
  $fatal(1,"exhausted sequence wrapped");
 ''')
