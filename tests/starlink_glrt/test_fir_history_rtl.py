"""Burst arrivals and repeated history wraps against independent convolution."""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, coefficients, quantize


BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_gap=0,input_support=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg [4:0] input_phase=0;
wire input_accepted,output_valid,output_support,halted;
wire signed [15:0] output_i,output_q;
wire [63:0] output_index;
wire [4:0] output_phase;
wire [1:0] output_clips;
wire [3:0] sticky_fault;
starlink_glrt_fir #(.TAPS(TAP_COUNT),.LANES(LANE_COUNT),
 .DECIMATION(24),.PHASE_MODULUS(24),.COEFFICIENT_FILE("COEFFICIENT")) dut (.*);
integer fd,rc,vi,su,si,sq,ph,accepted=0;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"input missing");
 fd=$fopen(path,"r");
 if(!fd) $fatal(1,"input unreadable");
 repeat(4) @(negedge clk);
 resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %h %d %d %d\n",vi,su,ix,ph,si,sq);
  if(rc!=6) $fatal(1,"bad input");
  input_valid=vi;input_support=su;input_index=ix;
  input_phase=ph;input_i=si;input_q=sq;
  @(posedge clk);
  if(input_accepted) accepted=accepted+1;
  #1;
  if(output_valid) $display("O %h %d %d %d %d %d",output_index,
   output_i,output_q,output_support,output_clips,output_phase);
  @(negedge clk);
 end
 $display("S %d %d %d",accepted,sticky_fault,halted);
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("rate,lanes", [(5_000_000, 4), (10_000_000, 4),
                                        (25_000_000, 4), (60_000_000, 8)])
@pytest.mark.parametrize("offset", [0, 7, 23])
def test_bursts_preserve_history_during_mac_and_repeated_wraps(rate, lanes, offset, tmp_path):
    bank = coefficients(rate)
    taps = len(bank)
    mac_rows = ((taps + 1) // 2 + lanes - 1) // lanes
    source = BENCH.replace("TAP_COUNT", str(taps)).replace("LANE_COUNT", str(lanes))
    source = source.replace('"COEFFICIENT"', f'"{BANK_ROOT / f"ddc_{rate}_q17.mem"}"')
    bench, executable = tmp_path / "tb.sv", tmp_path / "sim"
    bench.write_text(source)
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench), str(BANK_ROOT / "starlink_glrt_fir.v"),
                            str(BANK_ROOT / "starlink_glrt_sample_ring.v")],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr

    rng = np.random.default_rng(21014 + offset)
    count = 8192
    values = rng.integers(-32768, 32768, (count, 2), dtype=np.int16)
    supported = np.ones(count, dtype=bool)
    supported[[0, 257, 1500, 4077]] = False
    idle = "0 0 0 0 0 0"
    records = []
    first = (1 << 48) + offset
    for j, (i, q) in enumerate(values):
        # Each phase-zero word starts a MAC. Send the remaining 23 words on
        # consecutive clocks, then wait only as needed before the next job.
        index = first + j
        phase = index % 24
        records.append(f"1 {int(supported[j])} {index:x} {phase} {i} {q}")
        if phase == 23:
            records.extend([idle] * max(0, mac_rows + 7 - 24))
    records.extend([idle] * (mac_rows + 12))
    path = tmp_path / "input.txt"
    path.write_text("\n".join(records) + "\n")
    process = subprocess.run(["vvp", str(executable), f"+INPUT={path}"],
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    actual, status = [], None
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] == "O":
            actual.append((int(words[1], 16), *map(int, words[2:])))
        elif words[0] == "S":
            status = tuple(map(int, words[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)

    sums = np.column_stack([np.convolve(values[:, c].astype(np.int64), bank)[:count]
                            for c in range(2)])
    result, _ = quantize(sums)
    support_counts = np.convolve(supported.astype(np.int64), np.ones(taps, dtype=np.int64))
    expected = []
    for j in range(count):
        if (first + j) % 24:
            continue
        _, clips = quantize(sums[j])
        expected.append((first + j, *map(int, result[j]),
                         int(support_counts[j] == taps), clips, 0))
    assert status == (count, 0, 0)
    assert actual == expected
