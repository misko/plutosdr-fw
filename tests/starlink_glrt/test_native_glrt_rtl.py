"""Wired native-correlator -> FPGA-GLRT test, with explicit synthetic epochs.

This exercises real native IQ and fabric decisions. The testbench supplies a
known candidate solely to isolate the scoring chain; it is not blind acquisition
or live RF qualification, and never labels the candidate FPGA-acquired.
"""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, RATES, group_delay
from .pilot import fixed_score, frame, symbol_correlations, symbol_samples
from .test_correlator_rtl import BENCH, records

SCORER = r'''
wire score_ready, result_valid, detected, score_busy;
wire [63:0] result_epoch;
wire [16:0] exact_score_q16, control_score_q16;
wire [8:0] exact_cfo_bin, control_cfo_bin;
wire [54:0] exact_energy, control_energy;
wire [50:0] exact_peak, control_peak;
wire [4:0] result_block_shift;
wire [1:0] zero_energy, ratio_clamped;
wire [3:0] score_fault;
starlink_glrt_score #(.TWIDDLE_FILE("TWIDDLE")) scorer (
 .clk(clk),.resetn(resetn),.flush(flush || halted),
 .correlation_valid(correlation_valid),.correlation_symbol(correlation_symbol),
 .correlation_epoch(correlation_epoch),.exact_i(exact_i),.exact_q(exact_q),
 .control_i(control_i),.control_q(control_q),
 .decision_enable(1'b1),.threshold_q16(17'd19661),.margin_q16(17'd9831),
 .ready(score_ready),.result_valid(result_valid),.detected(detected),
 .result_epoch(result_epoch),.exact_score_q16(exact_score_q16),
 .control_score_q16(control_score_q16),.exact_cfo_bin(exact_cfo_bin),
 .control_cfo_bin(control_cfo_bin),.exact_energy(exact_energy),.control_energy(control_energy),
 .exact_peak(exact_peak),.control_peak(control_peak),.result_block_shift(result_block_shift),
 .zero_energy(zero_energy),.ratio_clamped(ratio_clamped),.sticky_fault(score_fault),.busy(score_busy)
);
'''


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("kind", ["positive", "noise", "rolled"])
def test_same_clock_native_iq_through_fabric_glrt(rate, kind, tmp_path):
    bench_text = BENCH.replace("integer fd", SCORER+"\ninteger fd").replace(
        '  if (correlation_valid)',
        '  if (result_valid) $display("G %h %d %d %d %d %d", result_epoch, exact_score_q16, control_score_q16, exact_cfo_bin, control_cfo_bin, detected);\n  if (correlation_valid)')
    bench_text = bench_text.replace(' $display("S %d %d %d %d",',
        ' $display("T %d %d", score_fault, score_busy);\n $display("S %d %d %d %d",')
    bench_text = bench_text.replace("(RATE)", f"({rate})").replace(
        '"TEMPLATE"', f'"{BANK_ROOT}/pilot_{rate}_upper_q7.mem"').replace(
        '"TWIDDLE"', f'"{BANK_ROOT}/glrt_dft512_q15.mem"')
    bench = tmp_path / "tb.sv"
    bench.write_text(bench_text)
    executable = tmp_path / "sim"
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
        *[str(BANK_ROOT / name) for name in ("starlink_glrt_sample_ring.v", "starlink_glrt_correlator.v",
                                            "starlink_glrt_ratio.v", "starlink_glrt_score.v")]],
        capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    epoch, first = 513, (1 << 45)+131
    n = symbol_samples(rate)
    count = epoch+rate//1000
    rng = np.random.default_rng(15887)
    values = 1500*(rng.normal(size=count)+1j*rng.normal(size=count))
    if kind != "noise":
        pilot = frame(rate, "upper", roll=17 if kind == "rolled" else 0)
        length = min(len(pilot), len(values)-epoch)
        values[epoch:epoch+length] += 6000*pilot[:length]
    values *= np.exp(2j*np.pi*42000*np.arange(count)/rate)
    raw = np.rint(np.column_stack((values.real, values.imag)))
    assert np.all(raw >= -32768) and np.all(raw <= 32767)
    raw = raw.astype(np.int16)
    candidate_cycle = (epoch+18*n+group_delay(rate))*100_000_000//rate
    rows = records(raw, rate, first, [(candidate_cycle, first+epoch)])
    path = tmp_path / "input.txt"
    path.write_text("\n".join(f"{v} {g} {f} {idx:x} {i} {q} {c} {ep:x}"
                             for v, g, f, idx, i, q, c, ep in rows)+"\n")
    run = subprocess.run(["vvp", str(executable), f"+INPUT={path}"], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    lines = run.stdout.splitlines()
    primary = [line.split()[1:] for line in lines if line.startswith("G ")]
    assert len(primary) == 1
    assert [line.split()[1:] for line in lines if line.startswith("S ")] == [["0", "0", "0", "0"]]
    assert [line.split()[1:] for line in lines if line.startswith("T ")] == [["0", "0"]]
    reference = fixed_score(symbol_correlations(raw, rate, "upper", epoch),
                            symbol_correlations(raw, rate, "upper", epoch, 17))
    e, c = reference["exact"], reference["control"]
    assert int(primary[0][0], 16) == first+epoch
    assert list(map(int, primary[0][1:])) == [e["score"], c["score"], e["bin"], c["bin"], int(kind == "positive")]
