"""The verifier rejects lost/misassociated responses from its shared IQ owner."""
import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT
from .test_verify_window_rtl import BENCH, write_roms


@pytest.mark.parametrize("failure", ["missing", "offset", "ready", "unsolicited", "unready_arm"])
@pytest.mark.parametrize("lanes", [3, 2, 1])
def test_shared_sample_port_fences_and_flush_recovers(tmp_path, failure, lanes):
    write_roms(tmp_path, np.zeros((8192, 2), dtype=np.int64))
    bench = BENCH[:BENCH.index("integer fd,jobs")]
    bench = bench.replace("parameter integer LANES=3", f"parameter integer LANES={lanes}")
    bench = bench.replace('.PILOT_FILE("PILOT")', '.EXTERNAL_WINDOW(1),.PILOT_FILE("pilot.mem")')
    bench = bench.replace('"ENERGY"', '"energy.mem"').replace('"WAVE"', '"wave.mem"')
    begin = bench.index(" dut(.external_ready")
    bench = bench[:begin] + ''' dut(.external_ready(external_ready),.external_valid(external_valid),
 .external_first_index(64'h10000000000001),.external_offset(external_offset),
 .external_data(32'd0),.sample_read_enable(sample_read_enable),
 .sample_read_address(sample_read_address),.*);
reg external_ready=1,external_valid=0;
reg [13:0] external_offset=0;
wire sample_read_enable;
wire [13:0] sample_read_address;
integer corruption=0,cycles=0,outputs=0;
always @(posedge clk) begin
 cycles<=cycles+1;
 if(cycles>16000) $fatal(1,"shared port timeout");
 external_valid<=resetn && !flush && (corruption==4 || (sample_read_enable && corruption!=1));
 if(sample_read_enable) external_offset<=sample_read_address+(corruption==2);
 if(output_valid && output_ready) outputs<=outputs+1;
end
initial begin
 repeat(3) @(negedge clk);resetn=1;
 if(FAILURE==5) external_ready=0;
 arm=1;@(negedge clk);arm=0;#1;
 if(FAILURE!=5) begin
  if(!window_loaded || !job_ready) $fatal(1,"shared window not admitted");
  job_subset=2;job_epoch=0;job_cfo_units=0;job_frequency_count=1;
  job_valid=1;@(negedge clk);job_valid=0;
  if(FAILURE!=4) begin wait(sample_read_enable);@(negedge clk);end
  corruption=FAILURE;
  if(FAILURE==3) external_ready=0;
 end
 repeat(4) @(negedge clk);
 if(!fault || window_loaded || output_valid || busy || outputs) $fatal(1,"bad shared reply escaped fence");
 flush=1;corruption=0;external_ready=1;@(negedge clk);flush=0;
 repeat(3) @(negedge clk);
 if(fault || busy || window_loaded || output_valid) $fatal(1,"flush did not clear ownership");
 arm=1;@(negedge clk);arm=0;#1;
 job_subset=2;job_epoch=0;job_cfo_units=0;job_frequency_count=1;
 job_valid=1;@(negedge clk);job_valid=0;
 wait(done || fault);@(negedge clk);
 if(fault || outputs!=1 || busy || !job_ready || output_score!=0 || output_support!=4)
  $fatal(1,"fresh shared window failed");
 $display("PASS");$finish;
end
endmodule
'''
    bench = bench.replace("FAILURE", str({"missing": 1, "offset": 2, "ready": 3,
                                          "unsolicited": 4, "unready_arm": 5}[failure]))
    (tmp_path/"tb.sv").write_text(bench)
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in
               ("verify_window3", "verify_rotate3", "verify_mac3", "coarse_norm")]
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", "sim", "tb.sv", *map(str, sources)],
        cwd=tmp_path, capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", "sim"], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == 0 and "PASS" in run.stdout, run.stdout+run.stderr
