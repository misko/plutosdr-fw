"""Real numerical search through the public GLA1 queue, including backpressure."""
import subprocess
from pathlib import Path

import numpy as np
import pytest

from .test_local_search_rtl import local_engine, reference  # noqa: F401

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,clear=0,enabled=0,source_closed=0,source_abort=0,input_valid=0,input_gap=0;
reg [31:0] visit_id=517,write_data=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg write_request=0;
reg [7:0] write_address=0,read_address=0;
reg [3:0] write_strobe=15;
wire [31:0] read_data;
wire reserved,records_pending,halted,settled;
starlink_glrt_local_control #(.EPOCH_COUNT(64),.PERIOD_SAMPLES(50000),
 .COEFFICIENT_FILE("COARSE"),.COARSE_ENERGY_FILE("COARSE_ENERGY"),.PILOT_FILE("PILOT"),
 .VERIFY_ENERGY_FILE("ENERGY"),.OSCILLATOR_FILE("WAVE")) dut(.*);
reg [31:0] samples[0:27999];reg [4095:0] path;
integer cycles=0,n,w,record_count=0,require_full=0;
always @(posedge clk) begin
 cycles<=cycles+1;
 if(cycles>30000000) $fatal(1,"timeout");
 if(resetn && halted) $fatal(1,"local controller fault");
end
task check(input [7:0] address,input [31:0] expected);begin
 read_address=address;#1;if(read_data!==expected)
  $fatal(1,"register %h actual %h expected %h",address,read_data,expected);
end endtask
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 if($value$plusargs("FULL=%d",require_full)) begin end
 $readmemh(path,samples);repeat(3) @(negedge clk);resetn=1;enabled=1;
 fork
  begin
   for(n=0;n<64000;n=n+1) begin
    input_valid=1;input_index=64'h20000000000003+n;
    if(n<14000) {input_q,input_i}=samples[n];
    else if(n>=50000) {input_q,input_i}=samples[14000+n-50000];
    else begin input_i=0;input_q=0;end
    @(negedge clk);input_valid=0;repeat(39) @(negedge clk);
   end
   source_closed=1;
  end
  begin
   // Hold the host reader off long enough to fill the 16-record queue.
   // The numerical engine must hold its next result, with no dropped record.
   repeat(15000000) @(negedge clk);
   if(require_full) begin check(8,16);check(9,16);end
   while(!settled || records_pending) begin
    if(records_pending) begin
     for(w=0;w<16;w=w+1) begin
      read_address=32+w;#1;$display("W %d %d %h",record_count,w,read_data);@(negedge clk);
     end
     write_request=1;write_address=4;write_data=1;
     @(negedge clk);write_request=0;record_count=record_count+1;
    end else @(negedge clk);
   end
  end
 join
 check(3,0);check(8,0);check(11,record_count);check(12,record_count);check(13,2);check(14,2);
 check(15,0);check(16,2);check(18,0);check(19,0);check(2,32'h113);
 if(reserved || !settled) $fatal(1,"unsettled after complete drain");
 $display("PASS");$finish;
end
endmodule
'''


@pytest.fixture(scope="module")
def control_engine(request, tmp_path_factory):
    roms, coefficients, pilot, wave, subsets = request.getfixturevalue("local_engine")
    output = tmp_path_factory.mktemp("local-control-engine")
    bench = BENCH
    for key, name in (("COARSE", "coarse.mem"), ("COARSE_ENERGY", "coarse_energy.mem"),
                      ("PILOT", "pilot.mem"), ("ENERGY", "energy.mem"), ("WAVE", "wave.mem")):
        bench = bench.replace(f'"{key}"', f'"{roms / name}"')
    (output / "tb.sv").write_text(bench)
    root = Path(__file__).resolve().parents[2] / "hdl/library/starlink_glrt"
    sources = [root / f"starlink_glrt_{name}.v" for name in (
        "local_control", "local_cadence", "local_search", "coarse_search", "coarse_window", "coarse_mac6", "coarse_norm",
        "coarse_peaks", "verify_control", "verify_window3", "verify_mac3", "verify_rotate3")]
    build = subprocess.run(["verilator", "--binary", "--timing", "--top-module", "tb", "-Wno-fatal",
        "--Mdir", str(output / "obj"), "-o", "sim", "-j", "4", str(output / "tb.sv"), *map(str, sources)],
        capture_output=True, text=True, timeout=120, check=False)
    (output / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stdout + build.stderr
    return output, coefficients, pilot, wave, subsets


def encode_expected(records, first_index, sequence=0, visit=517):
    result = []
    for row in records:
        decision, reasons, rank, epoch, frequency, coarse, cfo, acquire, verify, control, conditioned, support = row
        flags = (epoch << 16) | (frequency << 12) | (rank << 9) | (support << 6) | (reasons << 1) | decision
        result.append([0x474C4131, visit, sequence, first_index & 0xFFFFFFFF, first_index >> 32,
                       flags, cfo & 0xFFFFFFFF, coarse, acquire, verify, control, conditioned, 14000, 0, 0, 0])
        sequence += 1
    return result


@pytest.mark.parametrize("kind", ["pilot", "zero"])
def test_complete_numerical_records_survive_queue_pressure(tmp_path, control_engine, kind):
    output, coefficients, pilot, wave, subsets = control_engine
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
        iq = np.rint(np.column_stack((samples.real, samples.imag)) + rng.normal(0, 20, (14000, 2))).astype(np.int16)
        if kind == "zero":
            iq[:] = 0
        windows.append(iq)
    stimulus = tmp_path / "iq.mem"
    stimulus.write_text("".join(f"{(int(i)&65535)|((int(q)&65535)<<16):08x}\n" for iq in windows for i, q in iq))
    run = subprocess.run([str(output / "obj/sim"), f"+INPUT={stimulus}", f"+FULL={int(kind == 'pilot')}"],
        capture_output=True, text=True, timeout=90, check=False)
    (tmp_path / "simulation.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout + run.stderr
    words = [int(line.split()[3], 16) for line in run.stdout.splitlines() if line.startswith("W ")]
    expected = []
    for index, iq in enumerate(windows):
        expected.extend(encode_expected(reference(iq, coefficients, pilot, wave, subsets),
                                       0x20000000000003 + index * 50000, len(expected)))
    assert words == [word for record in expected for word in record]
