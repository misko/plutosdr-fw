from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, RATES
from .pilot import symbol_correlations, symbol_samples

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0, flush=0, input_valid=0, input_gap=0, candidate_valid=0;
reg signed [15:0] input_i=0, input_q=0;
reg [63:0] input_index=0, candidate_epoch=0;
wire candidate_ready, candidate_rejected, correlation_valid, busy, halted;
wire [31:0] rejected_count;
wire [5:0] correlation_symbol;
wire signed [23:0] exact_i, exact_q, control_i, control_q;
wire [63:0] correlation_epoch;
wire [4:0] sticky_fault;
starlink_glrt_correlator #(.SOURCE_RATE_HZ(RATE), .TEMPLATE_FILE("TEMPLATE")) dut (.*);
integer fd, rc, vi, ga, fl, si, sq, cv;
reg [63:0] ix, ep;
reg [2047:0] path;
initial begin
 if (!$value$plusargs("INPUT=%s", path)) $fatal(1,"input missing");
 fd=$fopen(path,"r");
 if (!fd) $fatal(1,"input unreadable");
 repeat(4) @(negedge clk);
 resetn=1;
 while (!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %d %d %d %h\n",vi,ga,fl,ix,si,sq,cv,ep);
  if (rc != 8) $fatal(1,"bad input");
  input_valid=vi; input_gap=ga; flush=fl; input_index=ix;
  input_i=si; input_q=sq; candidate_valid=cv; candidate_epoch=ep;
  @(posedge clk); #1;
  if (correlation_valid) $display("C %h %d %d %d %d %d",correlation_epoch,correlation_symbol,exact_i,exact_q,control_i,control_q);
  if (candidate_rejected) $display("R");
  @(negedge clk);
 end
 $display("S %d %d %d %d",rejected_count,sticky_fault,halted,busy);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def correlators(tmp_path_factory):
    root = tmp_path_factory.mktemp("glrt-correlator-compile")
    cache = {}
    def get(rate, edge):
        key = (rate, edge)
        if key not in cache:
            bench = root / f"tb_{rate}_{edge}.sv"
            bench.write_text(BENCH.replace("(RATE)", f"({rate})").replace(
                '"TEMPLATE"', f'"{BANK_ROOT}/pilot_{rate}_{edge}_q7.mem"'))
            executable = root / f"sim_{rate}_{edge}"
            process = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                str(bench), str(BANK_ROOT / "starlink_glrt_correlator.v")], text=True, capture_output=True)
            assert process.returncode == 0, process.stdout + process.stderr
            cache[key] = executable
        return cache[key]
    return get


def records(values, rate, first=0, candidates=()):
    count = (len(values)*100_000_000+rate-1)//rate
    rows = [[0, 0, 0, 0, 0, 0, 0, 0] for _ in range(count+100)]
    for j, (i, q) in enumerate(values):
        cycle = j*100_000_000//rate
        rows[cycle][:6] = [1, 0, 0, first+j, int(i), int(q)]
    for cycle, epoch in candidates:
        rows[cycle][6:] = [1, epoch]
    return rows


def run(simulator, rows, tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("\n".join(f"{v} {g} {f} {idx:x} {i} {q} {c} {epoch:x}"
                             for v, g, f, idx, i, q, c, epoch in rows)+"\n")
    process = subprocess.run(["vvp", str(simulator), f"+INPUT={path}"],
                             capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    result, status, rejected = [], None, 0
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] == "C":
            result.append((int(words[1], 16), *map(int, words[2:])))
        elif words[0] == "S":
            status = tuple(map(int, words[1:]))
        elif words[0] == "R":
            rejected += 1
        elif "$finish called at" not in line:
            pytest.fail(f"unexpected simulator output: {line}")
    assert status is not None
    return result, status, rejected


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_native_exact_control_bit_exact(rate, edge, correlators, tmp_path):
    n = symbol_samples(rate)
    epoch = 4000
    first = (1 << 48) + 951
    rng = np.random.default_rng(7511)
    values = rng.integers(-32768, 32768, (epoch + 70*n, 2), dtype=np.int16)
    command_cycle = (epoch + 18*n)*100_000_000//rate
    rows = records(values, rate, first, [(command_cycle, first+epoch)])
    result, status, rejected = run(correlators(rate, edge), rows, tmp_path)
    exact = symbol_correlations(values, rate, edge, epoch)
    control = symbol_correlations(values, rate, edge, epoch, 17)
    expected = [(first+epoch, symbol, *map(int, e), *map(int, c))
                for symbol, (e, c) in enumerate(zip(exact, control))]
    assert result == expected
    assert status == (0, 0, 0, 0)
    assert rejected == 0


@pytest.mark.parametrize("rate", RATES)
def test_busy_candidate_is_accounted_without_changing_active_result(rate, correlators, tmp_path):
    n = symbol_samples(rate)
    rng = np.random.default_rng(11432)
    values = rng.integers(-10000, 10001, (72*n, 2), dtype=np.int16)
    cycle = 18*n*100_000_000//rate
    rows = records(values, rate, candidates=[(cycle, 0), (cycle+1, 1)])
    result, status, rejected = run(correlators(rate, "upper"), rows, tmp_path)
    assert len(result) == 64 and all(r[0] == 0 for r in result)
    assert status == (1, 0, 0, 0)
    assert rejected == 1


@pytest.mark.parametrize("rate", RATES)
def test_source_gap_invalidates_partial_native_result(rate, correlators, tmp_path):
    n = symbol_samples(rate)
    values = np.ones((72*n, 2), dtype=np.int16)
    cycle = 18*n*100_000_000//rate
    rows = records(values, rate, candidates=[(cycle, 0)])
    fault_cycle = 35*n*100_000_000//rate
    rows[fault_cycle][1] = 1
    rows[fault_cycle+50][2] = 1
    result, status, _ = run(correlators(rate, "upper"), rows, tmp_path)
    assert 0 < len(result) < 64
    assert status[1] & 2 and status[2] == 1 and status[3] == 0


@pytest.mark.parametrize("rate", RATES)
def test_missing_history_candidate_fails_closed(rate, correlators, tmp_path):
    n = symbol_samples(rate)
    values = np.ones((5000+72*n, 2), dtype=np.int16)
    cycle = (5000+18*n)*100_000_000//rate
    rows = records(values, rate, first=1000, candidates=[(cycle, 0)])
    result, status, rejected = run(correlators(rate, "upper"), rows, tmp_path)
    assert not result and rejected == 1
    assert status[:3] == (1, 1, 1)
