"""Exact native reduction, loss fences and 750 Hz scheduling of this block alone."""
from __future__ import annotations

import subprocess

import pytest

from .ddc import BANK_ROOT


BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam N = COUNT;
localparam C = $clog2(N+1), S = 33+$clog2(N), T = S+$clog2(N), E = 33+$clog2(N);
reg clk=0; always #5 clk=~clk;
reg resetn=0, flush=0, job_valid=0, input_valid=0, input_gap=0, products_closed=0, result_ready=1;
reg [63:0] job_start=0, input_index=0;
reg signed [32:0] pri=0, prq=0, pdi=0, pdq=0;
reg [32:0] power=0;
wire job_ready, active, result_valid;
wire [63:0] result_start;
wire [C-1:0] result_count;
wire [3:0] result_fault;
wire signed [S-1:0] ri,rq,di,dq;
wire signed [T-1:0] ti,tq;
wire [E-1:0] energy;
starlink_glrt_local_moments #(.SAMPLE_COUNT(N)) dut (
 .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_ready(job_ready),.job_start(job_start),
 .input_valid(input_valid),.input_gap(input_gap),.products_closed(products_closed),.input_index(input_index),
 .reference_product_i(pri),.reference_product_q(prq),.delay_product_i(pdi),.delay_product_q(pdq),.sample_power(power),
 .active(active),.result_valid(result_valid),.result_ready(result_ready),.result_start(result_start),
 .result_count(result_count),.result_fault(result_fault),.reference_sum_i(ri),.reference_sum_q(rq),
 .delay_sum_i(di),.delay_sum_q(dq),.reference_prefix_integral_i(ti),.reference_prefix_integral_q(tq),.observed_energy(energy));
integer fd,rc;
reg [4095:0] path;
localparam PAYLOAD = 64+C+4+4*S+2*T+E;
wire [PAYLOAD-1:0] payload = {result_start,result_count,result_fault,ri,rq,di,dq,ti,tq,energy};
reg stalled=0;
reg [PAYLOAD-1:0] previous_payload;
always @(posedge clk) if(resetn) begin
 if(stalled && (!result_valid || payload !== previous_payload)) $fatal(1,"backpressured result changed");
 if(result_valid && job_ready) $fatal(1,"pending result admitted a new job");
 stalled <= result_valid && !result_ready;
 previous_payload <= payload;
 if(result_valid && result_ready)
   $display("R %h %d %d %d %d %d %d %d %d %d",result_start,result_count,result_fault,ri,rq,di,dq,ti,tq,energy);
end else stalled <= 0;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"missing input");
 fd=$fopen(path,"r");
 repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
   rc=$fscanf(fd,"%d %d %d %h %d %d %d %d %h %d %d %d %d %h\n",resetn,flush,job_valid,job_start,input_valid,input_gap,products_closed,result_ready,input_index,pri,prq,pdi,pdq,power);
   if(rc!=14) $fatal(1,"malformed input %d",rc);
   @(negedge clk);
 end
 resetn=1; flush=0; job_valid=0; input_valid=0; input_gap=0; products_closed=0; result_ready=1;
 repeat(8) @(negedge clk);
 if(active || result_valid) $fatal(1,"undrained reduction");
 $finish;
end
endmodule
'''


def row(*, reset=1, flush=0, job=None, sample=None, gap=0, closed=0, ready=1):
    index, ri, rq, di, dq, power = sample or (0, 0, 0, 0, 0, 0)
    return f"{reset} {flush} {int(job is not None)} {job or 0:x} {int(sample is not None)} {gap} {closed} {ready} {index:x} {ri} {rq} {di} {dq} {power:x}\n"


def simulate(tmp_path, count, rows):
    bench, input_path, executable = tmp_path / "tb.sv", tmp_path / "input.txt", tmp_path / "sim"
    bench.write_text(BENCH.replace("= COUNT;", f"= {count};"))
    with input_path.open("w") as file:
        file.writelines(rows)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench), str(BANK_ROOT / "starlink_glrt_local_moments.v")], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={input_path}"], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    return [[int(words[1], 16), *map(int, words[2:])] for line in run.stdout.splitlines() if (words := line.split()) and words[0] == "R"]


def expected(start, samples, fault=0):
    # Python unbounded integer sums are independent of the RTL prefix recurrence.
    n = len(samples)
    sums = [sum(s[k] for s in samples) for k in range(1, 5)]
    prefix = [sum((n-1-i)*s[k] for i, s in enumerate(samples)) for k in (1, 2)]
    return [start, n, fault, *sums, *prefix, sum(s[5] for s in samples)]


def test_full_native_moments_run_on_every_750_hz_repeat_with_integer_corner_values(tmp_path):
    count, base = 79_200, 2**55+71
    corner = [(2**32-1, -2**32, -2**32, 2**32-1, 2**33-1), (-2**32, 2**32-1, 17, -31, 2**32)]
    wanted = []
    for frame in range(3):
        start = base+frame*80_000
        products = corner[frame % 2]
        wanted.append(expected(start, [(start+n, *products) for n in range(count)]))

    def inputs():
        yield row(job=base)
        native_index = 0
        for cycle in range(400_000):  # 4 ms at 100 MHz = three 750 Hz repeat periods.
            if (cycle+1)*3//5 == cycle*3//5:
                yield row()
                continue
            frame, offset = divmod(native_index, 80_000)
            sample = (base+native_index, *corner[frame % 2]) if offset < count else None
            job = base+native_index+1 if offset == 79_999 and frame < 2 else None
            yield row(sample=sample, job=job)
            native_index += 1

    assert simulate(tmp_path, count, inputs()) == wanted


@pytest.mark.parametrize("failure,fault", [("index", 1), ("gap", 1), ("close", 2), ("flush", 8)])
def test_loss_or_flush_keeps_only_preceding_valid_support_and_can_start_again(tmp_path, failure, fault):
    first, second, count = 2**54+73, 2**54+1001, 32
    prefix = [(first+i, i-19, 7-i, 3*i, -2*i, i*i) for i in range(17)]
    rows = [row(job=first), *[row(sample=s) for s in prefix]]
    rows.append(row(sample=(first+19, 1, 2, 3, 4, 5)) if failure == "index" else row(**{failure if failure != "close" else "closed": 1}))
    rows.extend([row(), row(), row(job=second)])
    fresh = [(second+i, -2, 3, -5, 7, 19) for i in range(count)]
    rows.extend(row(sample=s) for s in fresh)
    assert simulate(tmp_path, count, rows) == [expected(first, prefix, fault), expected(second, fresh)]


def test_last_product_and_close_complete_together_and_result_survives_backpressure(tmp_path):
    start, count = 37, 32
    samples = [(start+i, i-10, 5-i, -i, i, i*3) for i in range(count)]
    rows = [row(job=start), *[row(sample=s) for s in samples[:-1]], row(sample=samples[-1], closed=1, ready=0)]
    rows.extend(row(job=999, ready=0) for _ in range(20))
    rows.extend([row(ready=1), row()])
    assert simulate(tmp_path, count, rows) == [expected(start, samples)]


def test_out_of_range_job_is_rejected_without_wrapping_the_sample_axis(tmp_path):
    start = 2**64-16
    assert simulate(tmp_path, 32, [row(job=start)]) == [expected(start, [], 4)]


def test_reset_discards_old_generation_before_a_fresh_complete_frame(tmp_path):
    count, first, second = 32, 73, 1011
    fresh = [(second+i, -9, 13, 21, -7, 83) for i in range(count)]
    rows = [row(job=first), row(sample=(first, 200, 100, 50, 25, 30)), row(reset=0), row(), row(job=second)]
    rows.extend(row(sample=s) for s in fresh)
    assert simulate(tmp_path, count, rows) == [expected(second, fresh)]
