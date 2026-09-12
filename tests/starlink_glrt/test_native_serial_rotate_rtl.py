"""Shared rotation: exact pipeline equivalence, cadence and generation fences."""
from __future__ import annotations

import random
import subprocess

import pytest

from .ddc import BANK_ROOT
from .test_native_products_rtl import BENCH, products, rotate, simulate

SERIAL_BENCH = BENCH.replace(
    ".METADATA_WIDTH(64)", ".METADATA_WIDTH(64),.SERIAL(1)"
).replace(
    "starlink_glrt_native_products products",
    "starlink_glrt_native_products #(.SERIAL_ROTATE(1)) products",
)


def test_serial_random_samples_and_full_scale_corners(tmp_path, monkeypatch):
    # Keep the independent direct-product/integer-rotation oracle and both
    # original 18/22-register completion/cancellation expectations.
    from . import test_native_products_rtl as original

    monkeypatch.setattr(original, "BENCH", SERIAL_BENCH)
    rng = random.Random(938147)
    edges = (-32768, -32767, -1, 0, 1, 32767)
    phases = [(quadrant * 2**30 + offset) % 2**32
              for quadrant in range(4) for offset in (-16384, -1, 0, 1, 16384)]
    samples = [(len(phases)*(6*i+j)+p, a, b, phase, a, b, b, a, p % 16)
               for i, a in enumerate(edges) for j, b in enumerate(edges)
               for p, phase in enumerate(phases)]
    samples += [(2**63+n, *[rng.randrange(-32768, 32768) for _ in range(2)],
                 rng.randrange(2**32), *[rng.randrange(-32768, 32768) for _ in range(4)], n % 16)
                for n in range(6000)]
    cycles = []
    for sample in samples:
        cycles += [(1, 0, sample)] + [(1, 0, None)]*(rng.choice((18, 19, 40, 43))-1)
    simulate(tmp_path, cycles)


@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("offset", range(1, 24))
def test_serial_cancellation_at_every_rotation_and_product_stage(tmp_path, monkeypatch, reset, offset):
    from . import test_native_products_rtl as original

    monkeypatch.setattr(original, "BENCH", SERIAL_BENCH)
    sample = (23, -32768, 32767, 2**31-3, 123, -789, 321, -543, 9)
    fresh = (2**63+7, 1719, -9381, 2**30+331, 32767, -32768, -891, 733, 0)
    cycles = [(1, 0, sample)] + [(1, 0, None)]*(offset-1)
    cycles += [(0, 0, None) if reset else (1, 1, None)]
    cycles += [(1, 0, fresh)]
    assert simulate(tmp_path, cycles)["P"][-1] == products(fresh)


ROTATION_BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg resetn=0,flush=0,iv=0;
reg signed [15:0] ii=0,iq=0;
reg [31:0] phase=0;
reg [63:0] tag=0;
wire sv,pv,sf,pf;
wire signed [17:0] si,sq,pi,pq;
wire [63:0] st,pt;
starlink_glrt_native_rotate #(.METADATA_WIDTH(64),.SERIAL(1)) serial (
 .clk(clk),.resetn(resetn),.flush(flush),.input_valid(iv),.input_i(ii),.input_q(iq),
 .input_phase(phase),.input_metadata(tag),.output_valid(sv),.output_i(si),.output_q(sq),
 .output_metadata(st),.fault(sf));
starlink_glrt_native_rotate #(.METADATA_WIDTH(64)) parallel (
 .clk(clk),.resetn(resetn),.flush(flush),.input_valid(iv),.input_i(ii),.input_q(iq),
 .input_phase(phase),.input_metadata(tag),.output_valid(pv),.output_i(pi),.output_q(pq),
 .output_metadata(pt),.fault(pf));
integer n,offset,seen=0;
reg compare=1;
always @(posedge clk) if(resetn && !flush) begin
 if(pf) $fatal(1,"parallel fault");
 if(compare && (sv !== pv || sf)) $fatal(1,"latency or cadence differs");
 if(compare && sv && {si,sq,st} !== {pi,pq,pt}) $fatal(1,"rotation differs");
 if(sv) begin seen=seen+1; if(!compare) $display("R %h %d %d",st,si,sq); end
end
initial begin
 repeat(3) @(negedge clk); resetn=1;
 BODY
 $finish;
end
endmodule
'''


def run_rotation(tmp_path, body):
    bench = tmp_path/"tb.sv"
    bench.write_text(ROTATION_BENCH.replace("BODY", body))
    executable = tmp_path/"sim"
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench), str(BANK_ROOT/"starlink_glrt_native_rotate.v")],
                           capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=180, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    return run.stdout


def test_every_q18_phase_matches_parallel_value_metadata_and_clock(tmp_path):
    run_rotation(tmp_path, r'''
     for(n=0;n<262144;n=n+1) begin
      // Exercise every phase, including all folding and narrowing boundaries.
      phase=-(n<<14); tag=64'h8000000000000000+n;
      ii=n[0] ? -32768 : 32767; iq=n[1] ? -32768 : 32767;
      iv=1; @(negedge clk); iv=0; repeat(17) @(negedge clk);
     end
     repeat(24) @(negedge clk);
     if(seen!=262144) $fatal(1,"missing phase results");
    ''')


@pytest.mark.parametrize("offset", range(1, 18))
@pytest.mark.parametrize("reset", [False, True])
def test_collision_discards_pending_rotation_and_requires_clear(tmp_path, offset, reset):
    clear = "resetn=0;" if reset else "flush=1;"
    output = run_rotation(tmp_path, f'''
     compare=0; iv=1; ii=-32768; iq=32767; phase=32'h80000000; tag=1;
     @(negedge clk); iv=0; repeat({offset-1}) @(negedge clk);
     iv=1; tag=2; @(negedge clk); iv=0;
     if(!sf || sv) $fatal(1,"collision not fenced");
     repeat(45) @(negedge clk);
     iv=1; tag=3; @(negedge clk); iv=0;
     repeat(25) @(negedge clk);
     if(!sf || seen!=0) $fatal(1,"collision was not sticky");
     {clear} @(negedge clk); resetn=1; flush=0;
     if(sf) $fatal(1,"clear failed");
     iv=1; tag=4; @(negedge clk); iv=0;
     repeat(25) @(negedge clk);
     if(sf || seen!=1) $fatal(1,"new generation failed");
    ''')
    records = [line.split() for line in output.splitlines() if line.startswith("R ")]
    assert records == [["R", "0000000000000004", *map(str, rotate(-32768, 32767, 2**31))]]
