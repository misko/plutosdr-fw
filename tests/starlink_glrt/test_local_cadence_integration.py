"""Actual GLRT engine with automatic sample-domain admission and visit closure."""
from pathlib import Path
import subprocess

import numpy as np
import pytest

from .test_local_search_rtl import local_engine, reference  # noqa: F401


BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,source_closed=0,input_valid=0,input_gap=0,output_ready=1;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
wire arm,arm_ready,engine_input_valid,closed,incomplete_capture,cadence_fault;
wire signed [15:0] engine_input_i,engine_input_q;
wire [63:0] engine_input_index;
wire [31:0] opportunities,admitted,skipped;
starlink_glrt_local_cadence #(.PERIOD_SAMPLES(50000)) cadence (
 .clk(clk),.resetn(resetn),.flush(flush),.source_closed(source_closed),
 .input_valid(input_valid),.input_gap(input_gap),.input_i(input_i),.input_q(input_q),.input_index(input_index),
 .engine_arm_ready(arm_ready),.engine_arm(arm),.engine_input_valid(engine_input_valid),
 .engine_input_i(engine_input_i),.engine_input_q(engine_input_q),.engine_input_index(engine_input_index),
 .closed(closed),.incomplete_capture(incomplete_capture),.fault(cadence_fault),
 .opportunities(opportunities),.admitted(admitted),.skipped(skipped));
wire engine_flush=flush || cadence_fault || incomplete_capture;
wire busy,done,fault,output_valid,output_decision;
wire [31:0] rejected_arms;
wire [63:0] window_first_index;
wire [4:0] output_reasons;
wire [2:0] output_rank,output_support;
wire [11:0] output_epoch;
wire [3:0] output_coarse_frequency;
wire [16:0] output_coarse_score,output_acquire,output_verify,output_control,output_conditioned;
wire signed [12:0] output_cfo_units;
starlink_glrt_local_search #(.EPOCH_COUNT(64),.COEFFICIENT_FILE("COARSE"),
 .COARSE_ENERGY_FILE("COARSE_ENERGY"),.PILOT_FILE("PILOT"),
 .VERIFY_ENERGY_FILE("ENERGY"),.OSCILLATOR_FILE("WAVE")) dut (
 .clk(clk),.resetn(resetn),.flush(engine_flush),.arm(arm),.input_valid(engine_input_valid),.input_gap(1'b0),
 .input_i(engine_input_i),.input_q(engine_input_q),.input_index(engine_input_index),
 .busy(busy),.arm_ready(arm_ready),.done(done),.fault(fault),.rejected_arms(rejected_arms),
 .output_valid(output_valid),.output_ready(output_ready),.window_first_index(window_first_index),
 .output_decision(output_decision),.output_reasons(output_reasons),.output_rank(output_rank),
 .output_support(output_support),.output_epoch(output_epoch),.output_coarse_frequency(output_coarse_frequency),
 .output_coarse_score(output_coarse_score),.output_acquire(output_acquire),.output_verify(output_verify),
 .output_control(output_control),.output_conditioned(output_conditioned),.output_cfo_units(output_cfo_units));
reg [31:0] samples[0:27999];reg [4095:0] path;
integer cycles=0,n,decisions=0,mode=0,overlapped=0;
always @(posedge clk) begin
 cycles<=cycles+1;
 if(cycles>30000000) $fatal(1,"timeout");
 if(arm && admitted!=0 && busy) overlapped=1;
 if(output_valid && output_ready && !engine_flush) begin
  $display("R %d %d %d %d %d %d %d %d %d %d %d %d %d",window_first_index,
   output_decision,output_reasons,output_rank,output_epoch,output_coarse_frequency,output_coarse_score,
   output_cfo_units,output_acquire,output_verify,output_control,output_conditioned,output_support);
  if(output_decision) decisions<=decisions+1;
 end
end
always @(negedge clk) output_ready=cycles%11<7;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 if($value$plusargs("MODE=%d",mode)) begin end
 $readmemh(path,samples);repeat(3) @(negedge clk);resetn=1;
 for(n=0;n<(mode==2 ? 63999 : 64000);n=n+1) begin
  input_valid=1;input_index=64'h20000000000003+n;input_gap=(mode==1 && n==60000);
  if(n<14000) {input_q,input_i}=samples[n];
  else if(n>=50000) {input_q,input_i}=samples[14000+n-50000];
  else begin input_i=0;input_q=0;end
  @(negedge clk);input_valid=0;input_gap=0;repeat(39) @(negedge clk);
 end
 source_closed=1;repeat(4) @(negedge clk);
 if(mode==0) begin
  wait(decisions==2);@(negedge clk);
  while(busy && !fault) @(negedge clk);
  if(fault || cadence_fault || incomplete_capture || !closed || opportunities!=2 ||
     admitted!=2 || skipped || rejected_arms || !overlapped) $fatal(1,"normal closure");
 end else begin
  if(decisions || output_valid || busy || (mode==1 && !cadence_fault) ||
     (mode==2 && (!incomplete_capture || !closed || admitted!=2))) $fatal(1,"abort closure");
 end
 flush=1;@(negedge clk);flush=0;source_closed=0;repeat(3) @(negedge clk);
 if(fault || cadence_fault || incomplete_capture || busy || output_valid || opportunities || admitted || skipped)
  $fatal(1,"flush recovery");
 $display("PASS");$finish;
end
endmodule
'''


@pytest.fixture(scope="module")
def scheduled_engine(request, tmp_path_factory):
    roms, coefficients, pilot, wave, subsets = request.getfixturevalue("local_engine")
    output = tmp_path_factory.mktemp("scheduled-local-engine")
    bench = BENCH
    for key, name in (("COARSE", "coarse.mem"), ("COARSE_ENERGY", "coarse_energy.mem"),
                      ("PILOT", "pilot.mem"), ("ENERGY", "energy.mem"), ("WAVE", "wave.mem")):
        bench = bench.replace(f'"{key}"', f'"{roms / name}"')
    (output / "tb.sv").write_text(bench)
    root = Path(__file__).resolve().parents[2] / "hdl/library/starlink_glrt"
    sources = [root / f"starlink_glrt_{name}.v" for name in (
        "local_cadence", "local_search", "coarse_search", "coarse_window", "coarse_mac6", "coarse_norm",
        "coarse_peaks", "verify_control", "verify_window3", "verify_mac3", "verify_rotate3")]
    build = subprocess.run(["verilator", "--binary", "--timing", "--top-module", "tb", "-Wno-fatal",
        "--Mdir", str(output / "obj"), "-o", "sim", "-j", "4", str(output / "tb.sv"), *map(str, sources)],
        capture_output=True, text=True, timeout=120)
    (output / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stdout + build.stderr
    return output, coefficients, pilot, wave, subsets


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_automatic_admission_and_close(tmp_path, scheduled_engine, mode):
    output, coefficients, pilot, wave, subsets = scheduled_engine
    rng = np.random.default_rng(21300)
    windows = []
    for epoch, cfo in ((17, 123400), (31, -218700)):
        samples = np.zeros(14000, dtype=np.complex128)
        template = pilot[:3333, 0] + 1j * pilot[:3333, 1]
        for offset in (0, 3333, 6667, 10000, 13333):
            count = min(3333, 14000 - offset - epoch)
            if count > 0:
                samples[offset + epoch:offset + epoch + count] = template[:count]
        samples *= 8 * np.exp(2j * np.pi * np.arange(14000) * cfo / 2500000)
        windows.append(np.rint(np.column_stack((samples.real, samples.imag)) +
            rng.normal(0, 20, (14000, 2))).astype(np.int16))
    stimulus = tmp_path / "iq.mem"
    stimulus.write_text("".join(f"{(int(i)&65535)|((int(q)&65535)<<16):08x}\n" for iq in windows for i, q in iq))
    run = subprocess.run([str(output / "obj/sim"), f"+INPUT={stimulus}", f"+MODE={mode}"],
        capture_output=True, text=True, timeout=90)
    (tmp_path / "simulation.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout + run.stderr
    actual = [list(map(int, line.split()[1:])) for line in run.stdout.splitlines() if line.startswith("R ")]
    if mode == 0:
        expected = [[0x20000000000003 + index * 50000, *row] for index, iq in enumerate(windows)
                    for row in reference(iq, coefficients, pilot, wave, subsets)]
        assert actual == expected
        assert all(row[2] == 0 for row in actual if row[1] == 1)
    else:
        assert not any(row[1] for row in actual)
