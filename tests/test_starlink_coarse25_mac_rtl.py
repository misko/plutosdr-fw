"""Exact full-width MAC comparison, no FPGA/route/transport claims."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from tools import starlink_coarse25 as base

RTL = base.ROOT / 'hdl/library/starlink_coarse25/starlink_coarse25_mac.v'


def test_tracked_coefficient_rom_matches_frozen_template():
    h, _ = base.template(0)
    coefficients = np.rint(np.column_stack((h.real, h.imag)) * 32767).astype(int)
    expected = [((int(q) & 65535) << 16) | (int(i) & 65535) for i, q in coefficients]
    actual = [int(line, 16) for line in (RTL.parent / 'coarse25_q15.mem').read_text().splitlines()]
    assert actual == expected


def run_case(tmp_path, samples, coefficients):
    compiler, runner = shutil.which('iverilog'), shutil.which('vvp')
    assert compiler and runner, 'Icarus is required; do not skip RTL verification'
    # samples: (reset, valid, I, Q, index), one entry per calculation clock.
    stimuli = []
    for reset, valid, i, q, index in samples:
        packed = reset << 97 | valid << 96 | (i & 65535) << 80 | (q & 65535) << 64 | index
        stimuli.append(f'{packed:025x}\n')
    (tmp_path / 'stim.mem').write_text(''.join(stimuli))
    (tmp_path / 'coeff.mem').write_text(''.join(
        f'{((int(q) & 65535) << 16) | (int(i) & 65535):08x}\n' for i, q in coefficients))
    tb = r'''
module tb;
 reg clk=0; always #5 clk=~clk;
 reg reset=1, valid=0;
 reg signed [15:0] xi=0, xq=0;
 reg [63:0] idx=0;
 wire rv, gap, overrun;
 wire signed [36:0] re, im;
 wire [35:0] energy;
 wire [63:0] first;
 reg [97:0] stimulus [0:COUNT-1];
 integer cycle;
 starlink_coarse25_mac #(.COEFFICIENT_FILE("coeff.mem")) dut(
 .clk(clk), .reset(reset), .sample_valid(valid), .sample_i(xi), .sample_q(xq),
 .sample_index(idx), .result_valid(rv), .result_re(re), .result_im(im),
 .result_energy(energy), .result_first_index(first), .gap(gap), .overrun(overrun));
 initial begin
  $readmemh("stim.mem", stimulus);
  for (cycle=0; cycle<COUNT; cycle=cycle+1) begin
   @(negedge clk); {reset,valid,xi,xq,idx}=stimulus[cycle];
   @(posedge clk); #1;
   if (gap || overrun) $display("FAULT %0d %0d %0d",cycle,gap,overrun);
   if (rv) $display("RESULT %0d %0d %0d %0d %0d",cycle,first,re,im,energy);
  end
  $finish;
 end
endmodule
'''.replace('COUNT', str(len(samples)))
    (tmp_path / 'tb.sv').write_text(tb)
    subprocess.run([compiler, '-g2012', '-s', 'tb', '-o', str(tmp_path / 'sim'),
                    str(RTL), str(tmp_path / 'tb.sv')], check=True, capture_output=True)
    result = subprocess.run([runner, str(tmp_path / 'sim')], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, check=True)
    actual = [tuple(line.split()) for line in result.stdout.splitlines()
              if line.startswith(('RESULT ', 'FAULT '))]
    # Independent oracle evaluates the entire chronological window at launch;
    # it does not imitate the tap-by-tap multiply/accumulate implementation.
    expected, history = [], []
    last, pending, due = None, None, None
    for cycle, (reset, valid, i, q, index) in enumerate(samples):
        if reset:
            history, last, pending, due = [], None, None, None
        elif valid:
            gap = last is not None and index != (last + 1) % 2**64
            overrun = pending is not None
            last = index
            if gap or overrun:
                expected.append(tuple(map(str, ('FAULT', cycle, int(gap), int(overrun)))))
                history, pending, due = [], None, None
            history = (history + [(i, q)])[-16:]
            if len(history) == 16:
                re = sum(xi * int(hi) + xq * int(hq)
                         for (xi, xq), (hi, hq) in zip(history, coefficients, strict=True))
                im = sum(xq * int(hi) - xi * int(hq)
                         for (xi, xq), (hi, hq) in zip(history, coefficients, strict=True))
                energy = sum(xi*xi + xq*xq for xi, xq in history)
                pending = ((index - 15) % 2**64, re, im, energy)
                due = cycle + 19
        elif pending is not None and cycle == due:
            expected.append(tuple(map(str, ('RESULT', cycle, *pending))))
            pending, due = None, None
    assert actual == expected, (actual[:5], expected[:5], result.stderr)
    return actual


@pytest.mark.parametrize('spacing', [20, 40])
def test_full_width_random_and_endpoint_arithmetic(tmp_path, spacing):
    rng = np.random.default_rng(6012)
    coefficients = rng.integers(-32768, 32768, size=(16, 2))
    coefficients[0] = [-32768, -32768]
    data = rng.integers(-32768, 32768, size=(200, 2))
    data[:20] = [-32768, -32768]
    samples = [(1, 0, 0, 0, 0)]
    for index, (i, q) in enumerate(data):
        samples.append((0, 1, int(i), int(q), index))
        samples.extend([(0, 0, 0, 0, 0)] * (spacing - 1))
    samples.extend([(0, 0, 0, 0, 0)] * 20)
    actual = run_case(tmp_path, samples, coefficients)
    assert len(actual) == len(data) - 15


def test_gap_overrun_and_reset_expire_pending_results(tmp_path):
    h, _ = base.template(0)
    coefficients = np.rint(np.column_stack((h.real, h.imag)) * 32767).astype(int)
    samples = [(1, 0, 0, 0, 0)]
    index = 1000
    for n in range(100):
        if n == 40:
            index += 7
        samples.append((0, 1, n*11, -n*17, index))
        index += 1
        # Two deliberately overloaded arrivals; one reset during arithmetic.
        if n == 75:
            samples.extend([(0, 0, 0, 0, 0)] * 3)
            samples.append((1, 0, 0, 0, 0))
        samples.extend([(0, 0, 0, 0, 0)] * (3 if n in (20, 60) else 39))
    samples.extend([(0, 0, 0, 0, 0)] * 20)
    actual = run_case(tmp_path, samples, coefficients)
    assert sum(line[0] == 'FAULT' for line in actual) == 3
    assert any(line[0] == 'RESULT' for line in actual)
