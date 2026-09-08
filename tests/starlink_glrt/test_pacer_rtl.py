from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, Ddc, RATES

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,input_valid=0,input_gap=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg [4:0] input_phase=0;
wire output_valid,output_gap;
wire signed [15:0] output_i,output_q;
wire [63:0] output_index;
wire [4:0] output_phase;
wire [31:0] dropped_count;
wire [6:0] maximum_level,level;
starlink_glrt_pacer #(.SOURCE_RATE_HZ(RATE)) dut(.*);
wire iq_valid,iq_support,halted;
wire signed [15:0] iq_i,iq_q;
wire [63:0] iq_index,accepted_count,emitted_count;
wire [31:0] clipping_count;
wire [8:0] sticky_fault;
starlink_glrt_ddc #(.SOURCE_RATE_HZ(RATE),.FIRST_COEFFICIENT_FILE("FIRST"),
 .FINAL_COEFFICIENT_FILE("FINAL")) ddc (
 .clk(clk),.resetn(resetn),.flush(1'b0),.input_valid(output_valid),.input_gap(output_valid && output_gap),
 .input_i(output_i),.input_q(output_q),.input_index(output_index),.input_phase(output_phase),
 .output_valid(iq_valid),.output_support(iq_support),.output_i(iq_i),.output_q(iq_q),.output_index(iq_index),
 .accepted_count(accepted_count),.emitted_count(emitted_count),.clipping_count(clipping_count),
 .sticky_fault(sticky_fault),.halted(halted)
);
integer fd,rc,vi,ga,ph,si,sq,cycle;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");
 repeat(4) @(negedge clk);
 resetn=1;cycle=0;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %h %d %d %d\n",vi,ga,ix,ph,si,sq);
  if(rc!=6) $fatal;
  input_valid=vi;input_gap=ga;input_index=ix;input_phase=ph;input_i=si;input_q=sq;
  @(posedge clk);#1;
  if(output_valid) $display("P %d %h %d %d %d %d",cycle,output_index,output_i,output_q,output_phase,output_gap);
  if(iq_valid) $display("O %d %h %d %d %d",cycle,iq_index,iq_i,iq_q,iq_support);
  @(negedge clk);cycle=cycle+1;
 end
 $display("S %d %d %d %d %d %d %d",dropped_count,maximum_level,level,accepted_count,emitted_count,clipping_count,sticky_fault);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def pacers(tmp_path_factory):
    root = tmp_path_factory.mktemp("pacer-compile")
    cache = {}
    def get(rate):
        if rate not in cache:
            source = BENCH.replace("(RATE)", f"({rate})").replace(
                '"FIRST"', f'"{BANK_ROOT}/ddc_{rate}_q17.mem"').replace(
                '"FINAL"', f'"{BANK_ROOT}/ddc_5000000_q17.mem"')
            bench, executable = root/f"tb_{rate}.sv", root/f"sim_{rate}"
            bench.write_text(source)
            built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                *[str(BANK_ROOT/name) for name in ("starlink_glrt_pacer.v", "starlink_glrt_fir.v", "starlink_glrt_ddc.v")]],
                capture_output=True, text=True)
            assert built.returncode == 0, built.stdout+built.stderr
            cache[rate] = executable
        return cache[rate]
    return get


def run(simulator, rows, tmp_path):
    path = tmp_path/"samples.txt"
    path.write_text("\n".join(" ".join(map(str, row[:2]))+f" {row[2]:x} "+" ".join(map(str, row[3:]))
                             for row in rows)+"\n")
    process = subprocess.run(["vvp", str(simulator), f"+INPUT={path}"], capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout+process.stderr
    outputs = {"P": [], "O": [], "S": []}
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] in outputs:
            outputs[words[0]].append(tuple(int(word, 16 if j == 1 and words[0] != "S" else 10)
                                           for j, word in enumerate(words[1:])))
        elif "$finish called at" not in line:
            pytest.fail(line)
    return outputs


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("speed_percent", [99, 100, 101])
def test_jitter_pacing_rate_headroom_and_exact_ddc(rate, speed_percent, pacers, tmp_path):
    rng = np.random.default_rng(733100)
    raw = rng.integers(-12000, 12001, (8000, 2), dtype=np.int16)
    ratio, first = rate//2500000, (1 << 49)+53
    cycles = np.arange(len(raw))*10_000_000_000//(rate*speed_percent)
    cycles += rng.integers(0, 7, len(raw))
    for j in range(1, len(raw)):
        cycles[j] = max(cycles[j], cycles[j-1]+1)
    rows = [(0, 0, 0, 0, 0, 0)]*(int(cycles[-1])+3000)
    for j, (i, q) in enumerate(raw):
        rows[int(cycles[j])] = (1, 0, first+j, (first+j) % ratio, int(i), int(q))
    outputs = run(pacers(rate), rows, tmp_path)
    assert [row[1:] for row in outputs["P"]] == [(first+j, int(i), int(q), (first+j) % ratio, 0)
                                                for j, (i, q) in enumerate(raw)]
    times = np.array([row[0] for row in outputs["P"]])
    assert np.all(times[ratio:]-times[:-ratio] >= 39)
    reference = Ddc(rate).process(raw, first)
    assert [row[1:] for row in outputs["O"]] == [(int(index), int(i), int(q), int(support)) for index, (i, q), support in
                                                 zip(reference.indexes, reference.iq, reference.supported)]
    output_times = np.array([row[0] for row in outputs["O"]])
    assert np.all(np.diff(output_times) >= 39)
    status = outputs["S"][0]
    assert status[0] == 0 and 0 < status[1] < 64 and status[2] == 0
    assert status[3:] == (len(raw), len(reference.iq), reference.clips, 0)


@pytest.mark.parametrize("rate", RATES)
def test_every_dropped_word_counted_and_first_reaccepted_word_gap_tagged(rate, pacers, tmp_path):
    ratio = rate//2500000
    rows = [(1, 0, j, j % ratio, j, -j) for j in range(700)]
    rows += [(0, 0, 0, 0, 0, 0)]*3000
    rows += [(1, 0, 700, 700 % ratio, 700, -700)]+[(0, 0, 0, 0, 0, 0)]*100
    outputs = run(pacers(rate), rows, tmp_path)
    status = outputs["S"][0]
    assert status[0] == 701-len(outputs["P"]) > 0
    assert status[1:3] == (64, 0)
    previous = -1
    for _, index, i, q, phase, gap in outputs["P"]:
        assert (i, q, phase, gap) == (index, -index, index % ratio, int(index != previous+1))
        previous = index
    assert status[-1] != 0  # Exporter refuses to correlate/filter across loss.
