"""Native derotation, exact direct complex products and reset-generation fences."""
from __future__ import annotations

import cmath
import math
import random
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from .ddc import BANK_ROOT

ANGLE_STEPS = tuple(round(math.atan(2**-stage)*2**18/(2*math.pi)) for stage in range(16))
CORDIC_GAIN = math.prod(math.sqrt(1+2**(-2*stage)) for stage in range(16))

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0;
reg [63:0] input_index=0;
reg signed [15:0] ii=0,iq=0,ri=0,rq=0,di=0,dq=0;
reg [31:0] phase=0;
reg [3:0] clipped=0;
wire nv,pv;
wire [63:0] ni,pi;
wire signed [17:0] oi,oq;
wire signed [34:0] pri,prq,pdi,pdq;
wire [35:0] power;
wire [3:0] pc;
starlink_glrt_native_rotate #(.METADATA_WIDTH(64)) rotate (
 .clk(clk),.resetn(resetn),.flush(flush),.input_valid(input_valid),.input_i(ii),.input_q(iq),
 .input_phase(phase),.input_metadata(input_index),.output_valid(nv),.output_i(oi),.output_q(oq),.output_metadata(ni));
starlink_glrt_native_products products (
 .clk(clk),.resetn(resetn),.flush(flush),.input_valid(input_valid),.input_index(input_index),
 .input_i(ii),.input_q(iq),.input_phase(phase),.reference_i(ri),.reference_q(rq),
 .derivative_i(di),.derivative_q(dq),.input_clipped(clipped),.output_valid(pv),
 .output_index(pi),.output_clipped(pc),.reference_product_i(pri),.reference_product_q(prq),
 .delay_product_i(pdi),.delay_product_q(pdq),.sample_power(power));
integer fd,rc;
reg [4095:0] path;
always @(posedge clk) begin
 if((!resetn || flush) && (nv || pv)) $fatal(1,"reset/flush leaked valid samples");
 if(nv) $display("N %h %d %d",ni,oi,oq);
 if(pv) $display("P %h %d %d %d %d %d %d",pi,pri,prq,pdi,pdq,power,pc);
end
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"missing input");
 fd=$fopen(path,"r");
 repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %d %d %h %d %d %d %d %h\n",resetn,flush,input_valid,
    input_index,ii,iq,phase,ri,rq,di,dq,clipped);
  if(rc!=12) $fatal(1,"malformed input");
  @(negedge clk);
 end
 resetn=1;flush=0;input_valid=0;
 repeat(40) @(negedge clk);
 if(nv || pv) $fatal(1,"undrained native products");
 $finish;
end
endmodule
'''


def rotate(i, q, phase):
    """Unbounded integer oracle; no wrapping intermediate arithmetic is allowed."""
    angle = ((-phase) % 2**32) >> 14
    x, y = i*16, q*16
    if ((angle >> 17) ^ (angle >> 16)) & 1:
        x, y = -x, -y
        angle ^= 2**17
    z = angle if angle < 2**17 else angle-2**18
    for stage, step in enumerate(ANGLE_STEPS):
        direction = 1 if z >= 0 else -1
        x, y, z = x-direction*(y >> stage), y+direction*(x >> stage), z-direction*step
        assert -2**21 <= x < 2**21 and -2**21 <= y < 2**21
        assert -2**17 <= z < 2**17
    return round(Fraction(x, 16)), round(Fraction(y, 16))


def products(sample):
    index, i, q, phase, ri, rq, di, dq, clipped = sample
    a, b = rotate(i, q, phase)
    # Direct four-multiplier mathematical form, independent of the RTL's
    # three-multiplier factorization. Delay basis is minus the derivative.
    return [index, a*ri+b*rq, b*ri-a*rq, -a*di-b*dq, a*dq-b*di, a*a+b*b, clipped]


def surviving_samples(cycles, latency):
    pending = {}
    output = []
    for cycle, (reset, flush, sample) in enumerate(cycles+[(1,0,None)]*40):
        if not reset or flush:
            pending.clear()
            continue
        if cycle in pending:
            output.append(pending.pop(cycle))
        if sample is not None:
            pending[cycle+latency] = sample
    assert not pending
    return output


def simulate(tmp_path, cycles):
    bench, trace, executable = [tmp_path/name for name in ("tb.sv", "input.txt", "sim")]
    bench.write_text(BENCH)
    with trace.open("w") as file:
        for reset, flush, sample in cycles:
            index,i,q,phase,ri,rq,di,dq,clipped = sample or (0,)*9
            file.write(f"{reset} {flush} {int(sample is not None)} {index:x} {i} {q} {phase:x} {ri} {rq} {di} {dq} {clipped:x}\n")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
        str(BANK_ROOT/"starlink_glrt_native_rotate.v"), str(BANK_ROOT/"starlink_glrt_native_products.v"),
        str(BANK_ROOT.parent/"common/ad_dds_cordic_pipe.v")], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={trace}"], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout+run.stderr
    output = {"N": [], "P": []}
    for line in run.stdout.splitlines():
        words = line.split()
        if words and words[0] in output:
            output[words[0]].append([int(words[1], 16), *map(int, words[2:])])
    ns = surviving_samples(cycles, 18)
    ps = surviving_samples(cycles, 22)
    assert output["N"] == [[s[0], *rotate(s[1], s[2], s[3])] for s in ns]
    assert output["P"] == [products(s) for s in ps]
    return output


def test_quadrant_edges_signed_iq_and_coefficient_corners(tmp_path):
    edges = (-32768, -32767, -1, 0, 1, 32767)
    phases = [((quadrant << 30)+offset) % 2**32 for quadrant in range(4) for offset in (-1, 0, 1, 8192, 16384)]
    samples = []
    for i in edges:
        for q in edges:
            for phase in phases:
                k = len(samples)
                samples.append((2**63+k,i,q,phase,edges[k % 6],edges[(k+1) % 6],edges[(k+2) % 6],edges[(k+3) % 6],k % 16))
    simulate(tmp_path, [(1,0,s) for s in samples])


def test_random_phase_rotation_error_and_native_sample_enable_holes(tmp_path):
    rng = random.Random(196591)
    samples = [(2**55+n, *[rng.randrange(-32768,32768) for _ in range(2)], rng.randrange(2**32),
        *[rng.randrange(-32768,32768) for _ in range(4)], n % 16) for n in range(6000)]
    cycles = []
    for sample in samples:
        cycles.append((1,0,sample))
        cycles.extend([(1,0,None)]*rng.randrange(3))
    output = simulate(tmp_path, cycles)
    errors = []
    for sample, (_, i, q) in zip(samples, output["N"], strict=True):
        ideal = CORDIC_GAIN*complex(sample[1],sample[2])*cmath.exp(-2j*math.pi*sample[3]/2**32)
        errors.append(complex(i,q)-ideal)
    # Frozen arithmetic budget in original ADC-count units; retain CORDIC gain.
    assert max(abs(value.real) for value in errors) <= 24
    assert max(abs(value.imag) for value in errors) <= 24
    assert math.sqrt(sum(abs(value)**2 for value in errors)/len(errors)) <= 6


@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("offset", [1, 8, 17, 18, 21, 22, 30])
def test_cancellation_fences_both_pipeline_latencies_and_a_fresh_generation(tmp_path, reset, offset):
    sample = (23,-32768,32767,2**31-3,123,-789,321,-543,9)
    fresh = (2**63+7,1719,-9381,2**30+331,32767,-32768,-891,733,0)
    cycles = [(1,0,sample)] + [(1,0,None)]*(offset-1)
    cycles += [(0,0,None) if reset else (1,1,None)]
    cycles += [(1,0,fresh), (1,0,None)]
    output = simulate(tmp_path, cycles)
    assert output["P"][-1] == products(fresh)


@pytest.mark.parametrize("rate", [-4000, 4000])
def test_full_native_pilot_preserves_small_residual_cfo_and_frequency_rate(tmp_path, rate):
    fs, count = 60_000_000, 79_200
    times = (np.arange(count)-(count-1)/2)/fs
    actual_cfo, predicted_cfo = 100371.123, 100194.123
    values = np.rint(11000*np.exp(2j*np.pi*(actual_cfo*times+0.5*rate*times**2)).real).astype(int)
    quadrature = np.rint(11000*np.exp(2j*np.pi*(actual_cfo*times+0.5*rate*times**2)).imag).astype(int)
    step = round(predicted_cfo/fs*2**32)
    phase0 = 2**32-9141
    cycles = []
    for n, (i, q) in enumerate(zip(values, quadrature, strict=True)):
        if n % 3 != 0:
            cycles.append((1,0,None))
        cycles.append((1,0,(2**54+n,int(i),int(q),(phase0+n*step) % 2**32,2048,701,-2073,19,0)))
    output = simulate(tmp_path, cycles)
    observed = np.asarray([complex(row[1],row[2]) for row in output["N"]])
    phase = np.unwrap(np.angle(observed))
    # Normalize time for conditioning, then convert the polynomial back to Hz.
    fit = np.polynomial.polynomial.polyfit(times*1000, phase/(2*np.pi), 2)
    cfo_estimate, rate_estimate = fit[1]*1000, 2*fit[2]*1e6
    assert abs(cfo_estimate-(actual_cfo-step*fs/2**32)) <= 0.02
    assert abs(rate_estimate-rate) <= 5
