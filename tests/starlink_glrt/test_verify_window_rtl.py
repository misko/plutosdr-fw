"""Complete buffered fine-grid scores versus independent integer arithmetic."""

import math
from pathlib import Path
import subprocess

import numpy as np
import pytest


BENCH = r'''
`timescale 1ns/1ps
module tb;
parameter integer LANES=3;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,input_valid=0,input_gap=0,job_valid=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg [11:0] job_epoch=0;
reg signed [12:0] job_cfo_units=0;
reg job_step_500=0;
reg [8:0] job_frequency_count=1;
reg [1:0] job_subset=0;
reg output_ready=1;
wire busy,job_ready,window_loaded,done,fault,output_valid;
wire [63:0] window_first_index;
wire [8:0] output_frequency;
wire [16:0] output_score;
wire [2:0] output_support;
wire [31:0] rejected_arms;
starlink_glrt_verify_window3 #(.LANES(LANES),.PILOT_FILE("PILOT"),.ENERGY_FILE("ENERGY"),
 .OSCILLATOR_FILE("WAVE")) dut(.external_ready(1'b0),.external_valid(1'b0),
 .external_first_index(64'd0),.external_offset(14'd0),.external_data(32'd0),
 .sample_read_enable(),.sample_read_address(),.*);
integer fd,jobs,rc,si,sq,n=0,waits=0,job=0,invalid=0;
reg [4095:0] path;
reg held=0;
reg [28:0] previous;
always @(posedge clk) begin
 if(resetn && !flush) begin
  if(held && (!output_valid || {output_frequency,output_score,output_support}!==previous))
   $fatal(1,"unstable backpressure result");
  held<=output_valid && !output_ready;
  previous<={output_frequency,output_score,output_support};
  if(output_valid && output_ready) $display("R %d %d %d %d",job,output_frequency,output_score,output_support);
 end else held<=0;
end
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");
 if(!$value$plusargs("JOBS=%s",path)) $fatal;
 jobs=$fopen(path,"r");
 repeat(3) @(negedge clk);resetn=1;arm=1;@(negedge clk);arm=0;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d\n",si,sq);if(rc!=2) $fatal;
  input_valid=1;input_i=si;input_q=sq;input_index=64'h10000000000001+n;
  @(negedge clk);n=n+1;
  if(n%7==0) begin input_valid=0;@(negedge clk);end
 end
 input_valid=0;
 if(n!=14000 || !window_loaded || !job_ready || busy) $fatal(1,"load failed");
 if($value$plusargs("INVALID=%d",invalid) && invalid!=0) begin
  rc=$fscanf(jobs,"%d %d %d %d %d\n",job_epoch,job_cfo_units,job_step_500,job_frequency_count,job_subset);
  if(rc!=5) $fatal;
  job_valid=1;@(negedge clk);job_valid=0;
  repeat(60) begin
   @(negedge clk);
   if(dut.state==dut.ISSUE || output_valid) $fatal(1,"malformed job issued samples/results");
  end
  if(!fault || window_loaded || busy || output_valid) $fatal(1,"malformed job not fenced");
  $display("INVALID_PASS");$finish;
 end
 while(!$feof(jobs)) begin
  rc=$fscanf(jobs,"%d %d %d %d %d\n",job_epoch,job_cfo_units,job_step_500,job_frequency_count,job_subset);
  if(rc!=5) $fatal;
  job_valid=1;@(negedge clk);job_valid=0;
  // Rejected overwrite must preserve the in-flight window and count admission.
  arm=1;@(negedge clk);arm=0;
  waits=0;
  while(!done && !fault && waits<1500000*((3+LANES-1)/LANES)) begin
   output_ready=waits%7!=0;@(negedge clk);waits=waits+1;
  end
  if(!done || fault || !window_loaded || !job_ready || rejected_arms!=job+1 ||
      window_first_index!=64'h10000000000001) $fatal(1,"job closure %d fault %d",job,fault);
  $display("CYCLES %d %d",job,waits);
  job=job+1;
 end
 // An interrupted correlation must not leak a late score or reuse old samples.
 job_frequency_count=1;job_cfo_units=0;job_valid=1;@(negedge clk);job_valid=0;
 repeat(220) @(negedge clk);flush=1;@(negedge clk);flush=0;
 repeat(100) @(negedge clk);
 if(fault || busy || window_loaded || job_ready || output_valid) $fatal(1,"flush failed");
 // Reload with explicit gap, then with an implicit sample-index discontinuity.
 arm=1;@(negedge clk);arm=0;input_valid=1;input_gap=1;
 @(negedge clk);input_valid=0;input_gap=0;
 if(!fault || window_loaded || output_valid) $fatal(1,"gap not fenced");
 flush=1;@(negedge clk);flush=0;arm=1;@(negedge clk);arm=0;input_valid=1;input_index=42;
 @(negedge clk);input_index=44;@(negedge clk);input_valid=0;
 if(!fault || window_loaded || output_valid) $fatal(1,"index discontinuity not fenced");
 $display("PASS");$finish;
end
endmodule
'''


def write_roms(path, pilot):
    wave = np.array([(round(math.cos(2*math.pi*k/1024)*1024),
                      round(math.sin(2*math.pi*k/1024)*1024)) for k in range(1024)], dtype=np.int64)
    for name, values in (("pilot.mem", pilot), ("wave.mem", wave)):
        (path/name).write_text("".join(f"{(int(i)&4095)|((int(q)&4095)<<12):06x}\n" for i,q in values))
    subsets = [(np.arange(start,302,2)[:,None]*11+np.arange(11)).ravel() for start in (2,3)]
    energies = [int(np.sum(pilot[indexes]**2)) for indexes in
                (subsets[0], subsets[1], np.arange(3333), 4096+subsets[1])]
    (path/"energy.mem").write_text("".join(f"{e:09x}\n" for e in energies))
    return wave, subsets


def expected_scores(iq, pilot, wave, subsets, jobs):
    rows=[]
    for job,(epoch,units,step500,count,subset) in enumerate(jobs):
        indexes = np.arange(3333) if subset==2 else subsets[subset%2]
        base = pilot[indexes+(4096 if subset==3 else 0)]
        energy = int(np.sum(base*base))
        frames=[iq[epoch+offset+indexes].astype(np.int64) for offset in (0,3333,6667,10000)
                if epoch+offset+indexes[-1]<14000]
        for frequency in range(count):
            cfo=(units+frequency*(5 if step500 else 1))*100
            # Python integer rounding expressed as rational arithmetic.
            increment=(abs(cfo)*2**32+1250000)//2500000
            if cfo<0: increment=-increment
            angles=wave[((indexes*increment)&0xffffffff)>>22]
            ci=(base[:,0]*angles[:,0]-base[:,1]*angles[:,1]+512)>>10
            cq=(base[:,0]*angles[:,1]+base[:,1]*angles[:,0]+512)>>10
            total=0
            for samples in frames:
                real=int(np.sum(samples[:,0]*ci+samples[:,1]*cq))>>8
                imag=int(np.sum(samples[:,1]*ci-samples[:,0]*cq))>>8
                denominator=math.isqrt((int(np.sum(samples*samples))*energy)>>16)
                total+=min(65536,(math.isqrt(real*real+imag*imag)<<16)//denominator) if denominator else 0
            rows.append([job,frequency,total//len(frames),len(frames)])
    return rows


@pytest.fixture(scope="module", params=[3, 2, 1], ids=["three-cfo", "two-cfo", "serial-cfo"])
def compiled_window(tmp_path_factory, request):
    path=tmp_path_factory.mktemp("verify-window")
    rng=np.random.default_rng(33331024)
    pilot=np.zeros((8192,2),dtype=np.int64)
    pilot[22:3322]=rng.integers(-600,601,(3300,2))
    pilot[4096+22:4096+3322]=np.roll(pilot[22:3322].reshape(300,11,2),71,axis=0).reshape(3300,2)
    wave,subsets=write_roms(path,pilot)
    bench=BENCH.replace('"PILOT"',f'"{path}/pilot.mem"').replace('"ENERGY"',f'"{path}/energy.mem"').replace('"WAVE"',f'"{path}/wave.mem"')
    (path/"tb.sv").write_text(bench)
    root=Path(__file__).parents[2]/"hdl/library/starlink_glrt"
    build=subprocess.run(["verilator","--binary","--timing","--top-module","tb","-Wno-fatal",
        f"-GLANES={request.param}",
        "--Mdir",str(path/"obj"),"-o","sim","-j","4",str(path/"tb.sv"),
        *[str(root/f"starlink_glrt_{name}.v") for name in
          ("verify_window3","verify_rotate3","verify_mac3","coarse_norm")]],capture_output=True,text=True,timeout=120)
    (path/"build.log").write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stdout+build.stderr
    return path,pilot,wave,subsets


@pytest.mark.parametrize("kind",["noise","pilot","rails","zero"])
def test_complete_fine_grid_support_rounding_and_window_fences(tmp_path,compiled_window,kind):
    path,pilot,wave,subsets=compiled_window
    rng=np.random.default_rng(140003)
    iq=rng.integers(-1000,1001,(14000,2),dtype=np.int16)
    if kind=="zero":iq[:]=0
    if kind=="rails":iq[:]=(-32768,32767)
    if kind=="pilot":
        for offset in (0,3333,6667,10000):
            iq[offset:offset+3333]+=pilot[:3333].astype(np.int16)*8
    jobs=[(0,-4000,True,7,0),(687,-1234,False,5,1),(688,3997,False,4,2),
          (3332,0,True,1,3),(678,0,False,2,1),(679,0,False,1,1),
          (667,0,False,1,2),(668,0,False,1,2),
          (689,0,False,1,0),(690,0,False,1,0)]
    if kind=="pilot":jobs.append((0,-800,True,321,0))
    (tmp_path/"iq.txt").write_text("".join(f"{i} {q}\n" for i,q in iq))
    (tmp_path/"jobs.txt").write_text("".join(" ".join(str(int(x)) for x in job)+"\n" for job in jobs))
    result=subprocess.run([str(path/"obj/sim"),f"+INPUT={tmp_path}/iq.txt",f"+JOBS={tmp_path}/jobs.txt"],
                          capture_output=True,text=True,timeout=60)
    (tmp_path/"simulation.log").write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    actual=[list(map(int,line.split()[1:])) for line in result.stdout.splitlines() if line.startswith("R ")]
    assert actual==expected_scores(iq,pilot,wave,subsets,jobs)
    assert "PASS" in result.stdout


@pytest.mark.parametrize("job",[(3333,0,0,1,0),(0,0,0,0,0),(0,0,0,322,0),
                              (0,-4001,0,1,0),(0,4001,0,1,0),(0,4000,0,2,0),
                              (0,3996,1,2,0)])
def test_invalid_grid_requests_fence_loaded_window(tmp_path,compiled_window,job):
    path,*_=compiled_window
    (tmp_path/"iq.txt").write_text("0 0\n"*14000)
    (tmp_path/"jobs.txt").write_text(" ".join(map(str,job))+"\n")
    result=subprocess.run([str(path/"obj/sim"),f"+INPUT={tmp_path}/iq.txt",
        f"+JOBS={tmp_path}/jobs.txt","+INVALID=1"],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert "INVALID_PASS" in result.stdout
    assert not any(line.startswith("R ") for line in result.stdout.splitlines())
