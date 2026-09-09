from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT
from .pilot import fixed_score

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0, flush=0, correlation_valid=0;
reg [5:0] correlation_symbol=0;
reg [63:0] correlation_epoch=64'h123456789abcdef0;
reg signed [23:0] exact_i=0, exact_q=0, control_i=0, control_q=0;
reg decision_enable=1;
reg [16:0] threshold_q16=19661, margin_q16=9831;
wire ready, result_valid, detected, busy;
wire [63:0] result_epoch;
wire [16:0] exact_score_q16, control_score_q16;
wire [8:0] exact_cfo_bin, control_cfo_bin;
wire [54:0] exact_energy, control_energy;
wire [50:0] exact_peak, control_peak;
wire [4:0] result_block_shift;
wire [1:0] zero_energy, ratio_clamped;
wire [3:0] sticky_fault;
starlink_glrt_score #(.TWIDDLE_FILE("TWIDDLE")) dut (.*);
integer fd, rc, cycle, n, gap, fail_mode;
reg [2047:0] path;
initial begin
 if (!$value$plusargs("INPUT=%s",path)) $fatal(1,"input missing");
 if (!$value$plusargs("GAP=%d",gap)) gap=1;
 if (!$value$plusargs("FAIL=%d",fail_mode)) fail_mode=0;
 fd=$fopen(path,"r");
 repeat(4) @(negedge clk);
 resetn=1;
 for(n=0;n<64;n=n+1) begin
  rc=$fscanf(fd,"%d %d %d %d\n",exact_i,exact_q,control_i,control_q);
  if(rc!=4) $fatal(1,"bad input");
  correlation_valid=1;
  correlation_symbol=n;
  if(fail_mode==1 && n==30) correlation_symbol=31;
  if(fail_mode==2 && n==30) correlation_epoch=7;
  if(fail_mode==3 && n==30) flush=1;
  @(posedge clk); #1; @(negedge clk);
  correlation_valid=0;
  flush=0;
  repeat(gap-1) @(negedge clk);
 end
 if(fail_mode==4) begin
  correlation_valid=1;
  correlation_symbol=0;
  correlation_epoch=7;
  @(posedge clk); #1; @(negedge clk);
  correlation_valid=0;
 end
 cycle=0;
 while(!result_valid && !sticky_fault && cycle<40000) begin
  @(posedge clk); #1;
  cycle=cycle+1;
  @(negedge clk);
 end
 if(fail_mode==0 && !result_valid) $fatal(1,"missing bounded GLRT result");
 if(result_valid) $display("R %h %d %d %d %d %d %d %d %d %d %d %d %d %d",result_epoch,
 exact_score_q16,control_score_q16,exact_cfo_bin,control_cfo_bin,exact_energy,control_energy,
 exact_peak,control_peak,result_block_shift,zero_energy,ratio_clamped,detected,cycle);
 $display("S %d %d",sticky_fault,busy);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def scorer(tmp_path_factory):
    root = tmp_path_factory.mktemp("glrt-score-compile")
    bench = root / "tb.sv"
    bench.write_text(BENCH.replace('"TWIDDLE"', f'"{BANK_ROOT}/glrt_dft512_q15.mem"'))
    executable = root / "sim"
    result = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(bench), str(BANK_ROOT / "starlink_glrt_ratio.v"), str(BANK_ROOT / "starlink_glrt_score.v")],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


def run(scorer, exact, control, tmp_path, *, gap=1, fail=0):
    path = tmp_path / "vectors.txt"
    path.write_text("\n".join(" ".join(str(int(x)) for x in row)
                             for row in np.column_stack((exact, control)))+"\n")
    result = subprocess.run(["vvp", str(scorer), f"+INPUT={path}", f"+GAP={gap}", f"+FAIL={fail}"],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    outputs = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith("R ")]
    statuses = [tuple(map(int, line.split()[1:])) for line in result.stdout.splitlines() if line.startswith("S ")]
    assert len(statuses) == 1
    return outputs, statuses[0]


@pytest.mark.parametrize("kind", ["zero", "exact_zero", "control_zero", "one", "tone", "offgrid", "real_tie", "noise", "extreme"])
@pytest.mark.parametrize("gap", [1, 11])
def test_all_score_fields_bit_exact_and_bounded(kind, gap, scorer, tmp_path):
    rng = np.random.default_rng(83879)
    control = rng.integers(-50000, 50001, (64, 2), dtype=np.int64)
    if kind in ("zero", "exact_zero"):
        exact = np.zeros((64, 2), dtype=np.int64)
        if kind == "zero":
            control[:] = 0
    elif kind == "control_zero":
        exact = np.full((64, 2), 500000, dtype=np.int64)
        control[:] = 0
    elif kind == "one":
        exact = np.ones((64, 2), dtype=np.int64)
        control = rng.integers(-1, 2, (64, 2), dtype=np.int64)
    elif kind in ("tone", "offgrid"):
        signal = 750000*np.exp(2j*np.pi*(421 if kind == "tone" else 95.3)*np.arange(64)/512)
        exact = np.rint(np.column_stack((signal.real, signal.imag))).astype(np.int64)
    elif kind == "real_tie":
        # Real bin-200 tone has exactly equal peaks at bins 200 and 312.
        # Paired visitation reaches 312 first; the legacy winner must be 200.
        signal = 750000*np.cos(2*np.pi*200*np.arange(64)/512)
        exact = np.rint(np.column_stack((signal, np.zeros(64)))).astype(np.int64)
    elif kind == "noise":
        exact = rng.integers(-50000, 50001, (64, 2), dtype=np.int64)
    else:
        exact = rng.choice([-8388608, 8388607], (64, 2))
        control = rng.integers(-8388608, 8388608, (64, 2), dtype=np.int64)
    expected = fixed_score(exact, control)
    output, status = run(scorer, exact, control, tmp_path, gap=gap)
    assert status[0] == 0 and len(output) == 1
    row = output[0]
    assert int(row[0], 16) == 0x123456789abcdef0
    e, c = expected["exact"], expected["control"]
    detected = e["zero"] == 0 and e["score"] >= 19661 and e["score"]-c["score"] >= 9831
    fields = [e["score"], c["score"], e["bin"], c["bin"], e["energy"], c["energy"], e["peak"], c["peak"],
              expected["block_shift"], e["zero"] | (c["zero"] << 1), e["clamped"] | (c["clamped"] << 1), int(detected)]
    assert list(map(int, row[1:-1])) == fields
    # The native history deadline requires paired-bin service under 200 us.
    assert int(row[-1]) < 20000
    if kind in ("tone", "offgrid", "real_tie", "one", "control_zero"):
        assert detected
    if kind == "real_tie":
        assert e["bin"] == int(row[3]) == 200
    if kind in ("noise", "zero", "exact_zero", "extreme"):
        assert not detected


@pytest.mark.parametrize("fail", [1, 2, 3, 4])
def test_partial_or_mixed_epoch_cannot_make_glrt_result(fail, scorer, tmp_path):
    values = np.ones((64, 2), dtype=np.int64)*500000
    output, status = run(scorer, values, values, tmp_path, fail=fail)
    assert not output and status[0] == 1


def test_frozen_twiddles_have_exact_signed_halfturn_negation():
    # Paired DFT products require this exact integer identity, not an assumed
    # floating-point trigonometric symmetry or an approximate unit circle.
    words = [int(line, 16) for line in (BANK_ROOT / "glrt_dft512_q15.mem").read_text().split()]
    def signed17(word):
        return word-(1 << 17) if word & (1 << 16) else word
    twiddles = [(signed17(word & 0x1ffff), signed17(word >> 17)) for word in words]
    assert len(twiddles) == 512
    assert all(twiddles[index+256] == (-twiddles[index][0], -twiddles[index][1]) for index in range(256))
    assert max(abs(component) for twiddle in twiddles for component in twiddle) <= 1 << 15
    # Signed CI24 times two bounded Q15 components, across 64 signed terms,
    # fits a signed 48-bit accumulator even without exploiting sin/cos bounds.
    assert 64 * 2 * (1 << 23) * (1 << 15) < 1 << 47
