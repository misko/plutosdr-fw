"""Autonomous fabric acquisition -> native GLRT alongside continuous IQ export.

There is no candidate timing input in this bench. Synthetic observation truth
is used only after simulation to assess what the receiver independently found.
This does not constitute independent-host or live RF qualification.
"""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, Ddc, RATES
from .pilot import fixed_score, frame, symbol_correlations, waveforms
from .test_ddc_rtl import records

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_gap=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg [4:0] input_phase=0;
wire decision_enable=1;
wire [16:0] acquisition_threshold_q16=15729,glrt_threshold_q16=19661,glrt_margin_q16=9831;
wire iq_valid,iq_support,export_halted,result_valid,detected,detector_halted;
wire signed [15:0] iq_i,iq_q;
wire [63:0] iq_index,export_accepted_count,export_emitted_count,result_epoch;
wire [63:0] acquisition_sample_count,acquisition_tested_count,proposal_count;
wire [63:0] admitted_candidates,busy_rejections,result_count;
wire [31:0] export_clipping_count;
wire [8:0] export_fault,exact_cfo_bin,control_cfo_bin;
wire [21:0] detector_fault;
wire [63:0] selected_candidates,merged_proposals;
wire selection_pending;
wire [16:0] exact_score_q16,control_score_q16;
wire [54:0] exact_energy,control_energy;
wire [50:0] exact_peak,control_peak;
wire [4:0] result_block_shift;
wire [1:0] zero_energy,ratio_clamped;
starlink_glrt_receiver #(.SOURCE_RATE_HZ(RATE),
 .NATIVE_TEMPLATE_FILE("NATIVE"),.ACQUISITION_TEMPLATE_FILE("ACQUISITION"),
 .FIRST_COEFFICIENT_FILE("FIRST"),.FINAL_COEFFICIENT_FILE("FINAL"),
 .TWIDDLE_FILE("TWIDDLE")) dut (.*);
integer fd,rc,vi,ga,fl,ph,si,sq;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"input missing");
 fd=$fopen(path,"r");
 if(!fd) $fatal(1,"input unreadable");
 repeat(4) @(negedge clk);
 resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %d %d %d\n",vi,ga,fl,ix,ph,si,sq);
  if(rc!=7) $fatal(1,"bad input");
  input_valid=vi;input_gap=ga;flush=fl;input_index=ix;
  input_phase=ph;input_i=si;input_q=sq;
  @(posedge clk);#1;
  if(iq_valid) $display("O %h %d %d %d",iq_index,iq_i,iq_q,iq_support);
  if(dut.proposal_valid) $display("P %h",dut.proposal_epoch);
  if(dut.selected_valid) $display("C %h %d %d",dut.selected_epoch,dut.admit,dut.reject_busy);
  if(result_valid) $display("G %h %d %d %d %d %d %d %d %d %d %d %d %d",
   result_epoch,detected,exact_score_q16,control_score_q16,exact_cfo_bin,control_cfo_bin,
   exact_energy,control_energy,exact_peak,control_peak,result_block_shift,zero_energy,ratio_clamped);
  @(negedge clk);
 end
 $display("S %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",
  export_accepted_count,export_emitted_count,export_clipping_count,export_fault,export_halted,
  acquisition_sample_count,acquisition_tested_count,proposal_count,admitted_candidates,
  busy_rejections,result_count,detector_fault,detector_halted,dut.native_busy,dut.score_busy,
  selected_candidates,merged_proposals,selection_pending);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def receivers(tmp_path_factory):
    root = tmp_path_factory.mktemp("receiver-compile")
    cache = {}
    def get(rate, edge="upper"):
        key = rate, edge
        if key not in cache:
            source = BENCH.replace("(RATE)", f"({rate})")
            for label, filename in {
                "NATIVE": f"pilot_{rate}_{edge}_q7.mem",
                "ACQUISITION": f"pilot_2500000_{edge}_q7.mem",
                "FIRST": f"ddc_{rate}_q17.mem", "FINAL": "ddc_5000000_q17.mem",
                "TWIDDLE": "glrt_dft512_q15.mem",
            }.items():
                source = source.replace(f'"{label}"', f'"{BANK_ROOT / filename}"')
            bench = root / f"tb_{rate}_{edge}.sv"
            bench.write_text(source)
            executable = root / f"sim_{rate}_{edge}"
            built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                                    *map(str, sorted(BANK_ROOT.glob("*.v")))], capture_output=True, text=True)
            assert built.returncode == 0, built.stdout + built.stderr
            cache[key] = executable
        return cache[key]
    return get


def run(simulator, rows, tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("\n".join(rows)+"\n")
    process = subprocess.run(["vvp", str(simulator), f"+INPUT={path}"],
                             capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stdout+process.stderr
    streams = {"O": [], "P": [], "C": [], "G": [], "S": []}
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] in streams:
            streams[words[0]].append(tuple(int(word, 16 if j == 0 and words[0] != "S" else 10)
                                                for j, word in enumerate(words[1:])))
        elif "$finish called at" not in line:
            pytest.fail(line)
    assert len(streams["S"]) == 1
    return streams


def observation(rate, kind, cfo=42000):
    ratio = rate//2500000
    epoch, first, count = 513*ratio, (1 << 45)+87, rate//500
    rng = np.random.default_rng(514009)
    values = 1500*(rng.normal(size=count)+1j*rng.normal(size=count))
    if kind in ("positive", "rolled", "scrambled"):
        pilot = frame(rate, "upper", roll=17 if kind == "rolled" else 0)
        if kind == "scrambled":
            n = 11*ratio
            pilot[2*n:302*n] = waveforms(rate, "upper")[rng.permutation(300)].reshape(-1)
        length = min(len(pilot), count-epoch)
        values[epoch:epoch+length] += 6000*pilot[:length]
    elif kind == "tone":
        values += 6000*np.exp(2j*np.pi*350000*np.arange(count)/rate)
    values *= np.exp(2j*np.pi*cfo*np.arange(count)/rate)
    raw = np.rint(np.column_stack((values.real, values.imag)))
    assert np.all(raw >= -32768) and np.all(raw <= 32767)
    return raw.astype(np.int16), epoch, first


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("kind", ["positive", "noise", "tone", "scrambled", "rolled"])
def test_blind_native_detection_and_identical_continuous_iq(rate, kind, receivers, tmp_path):
    raw, epoch, first = observation(rate, kind)
    rows = records(raw, rate, first)+["0 0 0 0 0 0 0"]*75000
    streams = run(receivers(rate), rows, tmp_path)
    status = streams["S"][0]
    reference = Ddc(rate).process(raw, first)
    expected_iq = [(int(index), int(i), int(q), int(support)) for index, (i, q), support in
                   zip(reference.indexes, reference.iq, reference.supported)]
    assert streams["O"] == expected_iq
    assert status[:5] == (len(raw), len(expected_iq), reference.clips, 0, 0)
    assert status[5:8] == (len(expected_iq), max(0, int(reference.supported.sum())-175), len(streams["P"]))
    assert status[8:11] == (sum(row[1] for row in streams["C"]), sum(row[2] for row in streams["C"]), len(streams["G"]))
    assert status[11:15] == (0, 0, 0, 0), (status, streams["P"], streams["G"])
    assert status[15] == len(streams["C"]) and status[17] == 0
    assert status[7] == status[15]+status[16]
    assert status[15] == status[8]+status[9] and status[8] == status[10]
    assert [row[0] for row in streams["G"]] == [row[0] for row in streams["C"] if row[1]]
    for result in streams["G"]:
        result_epoch = result[0]-first
        oracle = fixed_score(symbol_correlations(raw, rate, "upper", result_epoch),
                             symbol_correlations(raw, rate, "upper", result_epoch, 17))
        e, c = oracle["exact"], oracle["control"]
        decision = int(e["score"] >= 19661 and e["score"] >= c["score"]+9831 and not e["zero"])
        assert result[1:] == (decision, e["score"], c["score"], e["bin"], c["bin"], e["energy"],
                              c["energy"], e["peak"], c["peak"], oracle["block_shift"],
                              e["zero"]+2*c["zero"], e["clamped"]+2*c["clamped"])
    detections = [row for row in streams["G"] if row[1]]
    if kind == "positive":
        expected_epoch = first+epoch
        assert any(abs(row[0]-expected_epoch) <= rate//2500000 for row in detections), (streams["P"], streams["G"])
    elif kind == "rolled":
        # Acquisition can rediscover the cyclically rolled code at a shifted
        # epoch. The single scorer may already be occupied by an earlier
        # unrelated proposal: preserve this explicit busy miss, not a negative
        # classification or an assertion that the detector recovered it.
        expected_epoch = first+epoch+187*(rate//2500000)
        assert any(abs(row[0]-expected_epoch) <= rate//2500000 for row in streams["P"])
        if not any(abs(row[0]-expected_epoch) <= rate//2500000 for row in detections):
            assert any(abs(row[0]-expected_epoch) <= rate//2500000 and row[2] for row in streams["C"]), streams
    else:
        assert not detections
