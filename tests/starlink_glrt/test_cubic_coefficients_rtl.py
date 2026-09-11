"""Q11 reference/derivative hardware against independent exact rational math."""
from __future__ import annotations

import subprocess
from fractions import Fraction

import pytest

from .ddc import BANK_ROOT
from .test_cubic_reference_rtl import SHIFTS, coefficients, packed_words
from .test_cubic_reference_rtl import expected as raw_expected

BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam SEGMENTS=SEGMENT_VALUE, FIRST=FIRST_VALUE, N=COUNT_VALUE;
localparam B=N<=1 ? 1 : $clog2(N);
reg clk=0; always #5 clk=~clk;
reg resetn=0,flush=0,job_valid=0,output_ready=0;
wire job_ready,output_valid,output_last,aborted;
wire signed [15:0] ri,rq,di,dq;
wire [B-1:0] output_index;
wire [3:0] clipped;
starlink_glrt_cubic_coefficients #(.SEGMENT_COUNT(SEGMENTS),
 .TEMPLATE_FILE("BANK_PATH"),.FIRST_SAMPLE(FIRST),.SAMPLE_COUNT(N),.OUTPUT_STRIDE(STRIDE_VALUE)) dut (
 .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_ready(job_ready),
 .output_valid(output_valid),.output_ready(output_ready),.reference_i(ri),.reference_q(rq),
 .derivative_i(di),.derivative_q(dq),.output_index(output_index),.output_last(output_last),
 .output_clipped(clipped),.aborted(aborted));
integer fd,rc;
reg [4095:0] path;
localparam PAYLOAD=64+B+1+4;
wire [PAYLOAD-1:0] payload={ri,rq,di,dq,output_index,output_last,clipped};
reg stalled=0;
reg [PAYLOAD-1:0] previous_payload;
always @(posedge clk) if(resetn && !flush) begin
 if(stalled && (!output_valid || payload !== previous_payload)) $fatal(1,"stalled coefficient changed");
 if(job_valid && !job_ready) $fatal(1,"job not admitted in scheduled opportunity");
 stalled <= output_valid && !output_ready;
 previous_payload <= payload;
 if(output_valid && output_ready)
  $display("R %d %d %d %d %d %d %d",output_index,ri,rq,di,dq,output_last,clipped);
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
 resetn=1;flush=0;job_valid=0;output_ready=1;
 repeat(12) @(negedge clk);
 if(!job_ready || output_valid) $fatal(1,"unfinished coefficient job");
 $finish;
end
endmodule
'''


def expected(segments, first, count, stride=1):
    raw = raw_expected(segments)
    result = []
    for offset in range(count):
        index = first+offset*stride
        values = raw[index][1:3] + [30*(raw[index+1][k]-raw[index-1][k]) for k in (1, 2)]
        if stride != 1:
            phase = index % 24
            weights = (0, 60, 60*phase-30, 30*phase*phase-60*phase+20)
            values[2:] = [sum(weights[k]*segments[index//24][k][channel]*(1 << SHIFTS[k])
                              for k in range(4)) for channel in range(2)]
        rounded = [round(Fraction(value, 2048)) for value in values]
        clipped = sum(int(value < -32768 or value > 32767) << k for k, value in enumerate(rounded))
        result.append([offset, *[max(-32768, min(32767, value)) for value in rounded], int(offset == count-1), clipped])
    return result


def simulate(tmp_path, segments, first, count, cycles, stride=1):
    bank, bench, trace, executable = [tmp_path/name for name in ("bank.mem", "tb.sv", "input.txt", "sim")]
    bank.write_text("".join(f"{word:027x}\n" for word in packed_words(segments)))
    source = BENCH.replace("SEGMENT_VALUE", str(len(segments))).replace("FIRST_VALUE", str(first))
    bench.write_text(source.replace("COUNT_VALUE", str(count)).replace("BANK_PATH", str(bank))
                    .replace("STRIDE_VALUE", str(stride)))
    with trace.open("w") as file:
        file.writelines(f"{reset} {flush} {start} {ready}\n" for reset,flush,start,ready in cycles)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
        str(BANK_ROOT/"starlink_glrt_cubic_reference.v"), str(BANK_ROOT/"starlink_glrt_cubic_coefficients.v")], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={trace}"], capture_output=True, text=True, timeout=90, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    lines = run.stdout.splitlines()
    return [list(map(int, line.split()[1:])) for line in lines if line.startswith("R ")], lines.count("A")


@pytest.mark.parametrize("first,count", [(1, 1), (1, 22), (22, 27), (24, 46)])
def test_guard_geometry_segment_crossings_signed_corners_and_clipping(tmp_path, first, count):
    segments = coefficients(3)
    cycles = [(1,0,1,0)] + [(1,0,0,int(cycle % 7 < 3)) for cycle in range(240)]
    result, aborted = simulate(tmp_path, segments, first, count, cycles)
    assert result == expected(segments, first, count)
    assert aborted == 0


def test_positive_and_negative_half_ties_round_to_even(tmp_path):
    segments = [[[0,0],[2,-2],[0,0],[0,0]]]
    cycles = [(1,0,1,0)] + [(1,0,0,1)]*50
    result, aborted = simulate(tmp_path, segments, 1, 22, cycles)
    assert result == expected(segments, 1, 22)
    assert result[0][1:5] == [0, 0, 30, -30]
    assert result[2][1:5] == [2, -2, 30, -30]
    assert aborted == 0


@pytest.mark.parametrize("stride", [2, 4, 24])
@pytest.mark.parametrize("reset", [False, True])
def test_multirate_polynomial_derivative_stalls_and_restart(tmp_path, stride, reset):
    segments = coefficients(8)
    first, count = 23, 6
    cycles = [(1,0,1,0)] + [(1,0,0,int(n % 11 < 2)) for n in range(85)]
    cycles += [(0,0,0,0) if reset else (1,1,0,0), (1,0,0,0), (1,0,1,0)]
    cycles += [(1,0,0,int(n % 13 < 3)) for n in range(500)]
    result, _ = simulate(tmp_path, segments, first, count, cycles, stride)
    truth = expected(segments, first, count, stride)
    assert result[-count:] == truth
    assert result[:-count] == truth[:len(result)-count]


def test_full_79200_sample_coefficients_on_three_750_hz_opportunities(tmp_path):
    segments = coefficients(3302)
    def cycles():
        for cycle in range(400_000):
            yield 1, 0, int(cycle in (0, 133333, 266667)), int((cycle+1)*3//5 != cycle*3//5)
    result, aborted = simulate(tmp_path, segments, 24, 79200, cycles())
    assert result == expected(segments, 24, 79200)*3
    assert aborted == 0


@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("pause", [16, 68, 110])
def test_cancel_during_pipeline_or_pending_last_output_then_restart(tmp_path, reset, pause):
    segments = coefficients(3)
    # Hold the output so cancellation also exercises an occupied elastic pipe.
    cycles = [(1,0,1,0)] + [(1,0,0,int(cycle < pause-8)) for cycle in range(pause)]
    cycles += [(0,0,0,0) if reset else (1,1,0,0), (1,0,0,0)]
    cycles += [(1,0,1,0)] + [(1,0,0,1)]*100
    result, aborted = simulate(tmp_path, segments, 1, 70, cycles)
    truth = expected(segments, 1, 70)
    assert result[-len(truth):] == truth
    assert result[:-len(truth)] == truth[:len(result)-len(truth)]
    # The largest pause permits the whole job to complete before flush.
    assert aborted == int(not reset and pause < 110)
