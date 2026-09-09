"""Native reference recurrence checked against independent integer polynomials."""
from __future__ import annotations

import math
import random
import subprocess

import pytest

from .ddc import BANK_ROOT

WIDTHS = (12, 13, 14, 15)
SHIFTS = (13, 9, 4, 0)

BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam SEGMENTS = SEGMENT_VALUE;
localparam B = $clog2(SEGMENTS*24);
reg clk=0; always #5 clk=~clk;
reg resetn=0, flush=0, job_valid=0, output_ready=0;
wire job_ready, output_valid, output_last, aborted;
wire signed [27:0] oi,oq;
wire [B-1:0] output_index;
starlink_glrt_cubic_reference #(.SEGMENT_COUNT(SEGMENTS),.TEMPLATE_FILE("BANK_PATH")) dut (
 .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_ready(job_ready),
 .output_valid(output_valid),.output_ready(output_ready),.output_i(oi),.output_q(oq),
 .output_index(output_index),.output_last(output_last),.aborted(aborted));
integer fd,rc;
reg [4095:0] path;
reg stalled=0;
reg [56+B:0] previous_payload;
wire [56+B:0] payload={oi,oq,output_index,output_last};
always @(posedge clk) if(resetn && !flush) begin
 if(stalled && (!output_valid || payload !== previous_payload)) $fatal(1,"stalled reference changed");
 stalled <= output_valid && !output_ready;
 previous_payload <= payload;
 if(output_valid && output_ready) $display("R %d %d %d %d",output_index,oi,oq,output_last);
 if(aborted) $display("A");
end else stalled <= 0;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"missing input");
 fd=$fopen(path,"r");
 repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d\n",resetn,flush,job_valid,output_ready);
  if(rc!=4) $fatal(1,"malformed input");
  @(negedge clk);
 end
 resetn=1; flush=0; job_valid=0; output_ready=1;
 repeat(5) @(negedge clk);
 if(!job_ready) $fatal(1,"unfinished reference job");
 $finish;
end
endmodule
'''


def coefficients(count):
    rng = random.Random(371148)
    rows = [
        [[rng.randrange(-(1 << (width-1)), 1 << (width-1)) for _ in range(2)] for width in WIDTHS]
        for _ in range(count)
    ]
    rows[0] = [[-(1 << (width-1)), (1 << (width-1))-1] for width in WIDTHS]
    return rows


def packed_words(rows):
    result = []
    for segment in rows:
        word, shift = 0, 0
        for order, width in enumerate(WIDTHS):
            for channel in range(2):
                word |= (segment[order][channel] & ((1 << width)-1)) << shift
                shift += width
        result.append(word)
    return result


def expected(rows):
    result = []
    for segment_index, segment in enumerate(rows):
        for n in range(24):
            values = [sum(math.comb(n, order)*segment[order][channel]*(1 << SHIFTS[order]) for order in range(4)) for channel in range(2)]
            index = 24*segment_index+n
            result.append([index, *values, int(index == len(rows)*24-1)])
    return result


def simulate(tmp_path, segments, cycles):
    bank, bench, trace, executable = [tmp_path / name for name in ("bank.mem", "tb.sv", "input.txt", "sim")]
    bank.write_text("".join(f"{word:027x}\n" for word in packed_words(segments)))
    bench.write_text(BENCH.replace("SEGMENT_VALUE", str(len(segments))).replace("BANK_PATH", str(bank)))
    trace.write_text("".join(f"{reset} {flush} {start} {ready}\n" for reset,flush,start,ready in cycles))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench), str(BANK_ROOT / "starlink_glrt_cubic_reference.v")], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={trace}"], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout+run.stderr
    lines = run.stdout.splitlines()
    return [list(map(int, line.split()[1:])) for line in lines if line.startswith("R ")], lines.count("A")


@pytest.mark.parametrize("count", [1, 3, 3302, 4096])
def test_all_native_samples_match_closed_form_with_signed_corners_and_backpressure(tmp_path, count):
    segments = coefficients(count)
    # Pattern includes stalls at segment boundaries; capacity is still >60 MS/s.
    cycles = [(1,0,1,0)] + [(1,0,0,int(cycle % 5 < 3)) for cycle in range(count*24*5//3+40)]
    result, aborted = simulate(tmp_path, segments, cycles)
    assert result == expected(segments)
    assert aborted == 0


def test_two_jobs_restart_the_rom_prefetch_and_native_index(tmp_path):
    segments = coefficients(3)
    job = [(1,0,1,0)] + [(1,0,0,1)]*80
    result, aborted = simulate(tmp_path, segments, job+job)
    assert result == expected(segments)*2
    assert aborted == 0


@pytest.mark.parametrize("reset", [False, True])
def test_flush_or_reset_aborts_partial_reference_without_polluting_a_new_job(tmp_path, reset):
    segments = coefficients(3)
    cycles = [(1,0,1,0)] + [(1,0,0,1)]*14
    cycles += [(0,0,0,0) if reset else (1,1,0,0), (1,0,0,0)]
    cycles += [(1,0,1,0)] + [(1,0,0,1)]*80
    result, aborted = simulate(tmp_path, segments, cycles)
    truth = expected(segments)
    assert result[-len(truth):] == truth
    assert result[:-len(truth)] == truth[:12]
    assert aborted == int(not reset)
