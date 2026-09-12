from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, Ddc, COMPONENT_RATES as RATES

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk = 0;
always #5 clk = ~clk;
reg resetn = 0, flush = 0, input_valid = 0, input_gap = 0;
reg signed [15:0] input_i = 0, input_q = 0;
reg [63:0] input_index = 0;
reg [4:0] input_phase = 0;
wire output_valid, output_support, halted;
wire signed [15:0] output_i, output_q;
wire [63:0] output_index, accepted_count, emitted_count;
wire [31:0] clipping_count;
wire [8:0] sticky_fault;
starlink_glrt_ddc #(.SOURCE_RATE_HZ(RATE),
 .FIRST_COEFFICIENT_FILE("FIRST_FILE"), .FINAL_COEFFICIENT_FILE("FINAL_FILE")) dut (.*);
integer fd, rc, vi, ga, fl, ph, si, sq;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if (!$value$plusargs("INPUT=%s", path)) $fatal(1, "input missing");
 fd = $fopen(path, "r");
 if (!fd) $fatal(1, "input unreadable");
 repeat (4) @(negedge clk);
 resetn = 1;
 while (!$feof(fd)) begin
  rc = $fscanf(fd, "%d %d %d %h %d %d %d\n", vi, ga, fl, ix, ph, si, sq);
  if (rc != 7) $fatal(1, "bad input record");
  input_valid = vi; input_gap = ga; flush = fl; input_index = ix;
  input_phase = ph; input_i = si; input_q = sq;
  @(posedge clk); #1;
  if (output_valid) $display("O %h %d %d %d", output_index, output_i, output_q, output_support);
  @(negedge clk);
 end
 $display("S %d %d %d %d %d", accepted_count, emitted_count, clipping_count, sticky_fault, halted);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def simulators(tmp_path_factory):
    root = tmp_path_factory.mktemp("glrt-ddc-compile")
    cache = {}

    def get(rate):
        if rate not in cache:
            bench = root / f"tb_{rate}.sv"
            bench.write_text(BENCH.replace("(RATE)", f"({rate})").replace(
                "FIRST_FILE", str(BANK_ROOT / f"ddc_{rate}_q17.mem")).replace(
                "FINAL_FILE", str(BANK_ROOT / "ddc_5000000_q17.mem")))
            executable = root / f"sim_{rate}"
            built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                str(bench), str(BANK_ROOT / "starlink_glrt_fir.v"),
                str(BANK_ROOT / "starlink_glrt_sample_ring.v"),
                str(BANK_ROOT / "starlink_glrt_ddc.v")], capture_output=True, text=True)
            assert built.returncode == 0, built.stdout + built.stderr
            cache[rate] = executable
        return cache[rate]
    return get


def records(values, rate, first=0):
    count = (len(values) * 100_000_000 + rate-1) // rate
    rows = ["0 0 0 0 0 0 0"] * (count + 70)
    ratio = rate // 2_500_000
    for j, (i, q) in enumerate(values):
        cycle = j * 100_000_000 // rate
        index = first + j
        rows[cycle] = f"1 0 0 {index:x} {index % ratio} {i} {q}"
    return rows


def run(simulator, rows, tmp_path):
    path = tmp_path / "samples.txt"
    path.write_text("\n".join(rows) + "\n")
    process = subprocess.run(["vvp", str(simulator), f"+INPUT={path}"],
                             capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    output = []
    status = None
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] == "O":
            output.append((int(words[1], 16), *map(int, words[2:])))
        elif words[0] == "S":
            status = tuple(map(int, words[1:]))
        elif "$finish called at" in line:
            continue
        else:
            pytest.fail(f"unexpected simulator output: {line}")
    assert status is not None
    return output, status


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("first", [0, 7, (1 << 48) + 53])
def test_exact_stream_at_native_pacing(rate, first, simulators, tmp_path):
    rng = np.random.default_rng(99318)
    values = rng.integers(-32768, 32768, (9000, 2), dtype=np.int16)
    reference = Ddc(rate).process(values, first)
    output, status = run(simulators(rate), records(values, rate, first), tmp_path)
    expected = [(int(index), int(i), int(q), int(support)) for index, (i, q), support in
                zip(reference.indexes, reference.iq, reference.supported)]
    assert output == expected
    assert status == (len(values), len(expected), reference.clips, 0, 0)


@pytest.mark.parametrize("rate", RATES)
def test_gap_fault_persists_across_flush(rate, simulators, tmp_path):
    values = np.full((4000, 2), 3000, dtype=np.int16)
    rows = records(values, rate)
    rows += ["0 1 0 0 0 0 0", "0 0 1 0 0 0 0"]
    rows += records(values, rate, 4000)
    output, status = run(simulators(rate), rows, tmp_path)
    assert status[0] == len(values)
    assert status[3] & 0x88
    assert status[4] == 1
    assert all(row[0] < 4000 for row in output)


@pytest.mark.parametrize("rate", RATES)
def test_wrong_phase_and_source_gap_fail_closed(rate, simulators, tmp_path):
    rows = records(np.ones((40, 2), dtype=np.int16), rate)
    ratio = rate // 2_500_000
    rows += [f"1 0 0 {1000:x} {ratio} 3 4"] + ["0 0 0 0 0 0 0"] * 80
    _, status = run(simulators(rate), rows, tmp_path)
    assert status[0] == 40  # Rejected source words are never counted as accepted.
    assert status[3] & (0x33)
    assert status[4] == 1


@pytest.mark.parametrize("rate", RATES)
def test_source_counter_wrap_cannot_append_to_session(rate, simulators, tmp_path):
    values = np.ones((64, 2), dtype=np.int16)
    rows = records(values, rate, (1 << 64)-64)
    rows += ["1 0 0 0 0 1 1"] + ["0 0 0 0 0 0 0"]*80
    _, status = run(simulators(rate), rows, tmp_path)
    assert status[0] == 64
    assert status[3] & 0x11 and status[4] == 1


@pytest.mark.parametrize("rate", RATES)
def test_clean_flush_preserves_absolute_phase_and_telemetry(rate, simulators, tmp_path):
    rng = np.random.default_rng(9801)
    before = rng.integers(-10000, 10001, (3000, 2), dtype=np.int16)
    after = rng.integers(-10000, 10001, (4000, 2), dtype=np.int16)
    rows = records(before, rate, 53) + ["0 0 1 0 0 0 0"] + records(after, rate, 3053)
    output, status = run(simulators(rate), rows, tmp_path)
    references = [Ddc(rate).process(before, 53), Ddc(rate).process(after, 3053)]
    expected = [(int(index), int(i), int(q), int(support)) for ref in references
                for index, (i, q), support in zip(ref.indexes, ref.iq, ref.supported)]
    assert output == expected
    assert status == (7000, len(expected), sum(ref.clips for ref in references), 0, 0)


@pytest.mark.parametrize("rate", RATES[1:])
def test_overrun_is_visible(rate, simulators, tmp_path):
    ratio = rate // 2_500_000
    rows = [f"1 0 0 {j:x} {j % ratio} 6000 -5000" for j in range(9000)]
    rows += ["0 0 0 0 0 0 0"] * 80
    _, status = run(simulators(rate), rows, tmp_path)
    assert status[3] & 0x44
    assert status[4] == 1
