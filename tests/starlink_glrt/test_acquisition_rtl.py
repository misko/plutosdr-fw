from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT
from .pilot import acquisition_fixed, frame

BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_gap=0,input_support=1;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg [16:0] threshold_q16=15729;
wire candidate_valid,score_valid,score_support,halted;
wire [63:0] candidate_epoch,accepted_count,tested_count,candidate_count,score_index;
wire [50:0] candidate_numerator,score_numerator;
wire [40:0] candidate_energy,score_energy;
wire [9:0] sticky_fault;
starlink_glrt_acquisition #(.INDEX_STRIDE(STRIDE),.GROUP_DELAY(DELAY),.TEMPLATE_FILE("TEMPLATE")) dut (.*);
integer fd,rc,vi,ga,fl,su,si,sq;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"input missing");
 fd=$fopen(path,"r");
 repeat(4) @(negedge clk);
 resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d %h %d %d\n",vi,ga,fl,su,ix,si,sq);
  if(rc!=7) $fatal(1,"bad input");
  input_valid=vi;input_gap=ga;flush=fl;input_support=su;
  input_index=ix;input_i=si;input_q=sq;
  @(posedge clk);#1;
  if(score_valid) $display("S %h %d %d %d",score_index,score_numerator,score_energy,score_support);
  if(candidate_valid) $display("C %h %d %d",candidate_epoch,candidate_numerator,candidate_energy);
  @(negedge clk);
 end
 $display("T %d %d %d %d %d",accepted_count,tested_count,candidate_count,sticky_fault,halted);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def acquisitions(tmp_path_factory):
    root=tmp_path_factory.mktemp("acquisition-compile")
    cache={}
    def get(stride,delay,edge):
        key=(stride,delay,edge)
        if key not in cache:
            bench=root/f"tb_{stride}_{delay}_{edge}.sv"
            bench.write_text(BENCH.replace("(STRIDE)",f"({stride})").replace("(DELAY)",f"({delay})").replace(
                '"TEMPLATE"',f'"{BANK_ROOT}/pilot_2500000_{edge}_q7.mem"'))
            executable=root/f"sim_{stride}_{delay}_{edge}"
            files=["starlink_glrt_pilot_bank.v","starlink_glrt_window_energy.v",
                   "starlink_glrt_pilot_power.v","starlink_glrt_acquisition.v"]
            built=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(executable),str(bench),
                *[str(BANK_ROOT/name) for name in files]],capture_output=True,text=True)
            assert built.returncode==0,built.stdout+built.stderr
            cache[key]=executable
        return cache[key]
    return get


def records(values,stride,first,spacing=40):
    rows=[]
    for j,(i,q) in enumerate(values):
        rows.append(f"1 0 0 1 {first+j*stride:x} {i} {q}")
        rows.extend(["0 0 0 1 0 0 0"]*(spacing-1))
    return rows+["0 0 0 1 0 0 0"]*80


def run(simulator,rows,tmp_path):
    path=tmp_path/"input.txt"
    path.write_text("\n".join(rows)+"\n")
    result=subprocess.run(["vvp",str(simulator),f"+INPUT={path}"],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    scores,candidates,status=[],[],None
    for line in result.stdout.splitlines():
        words=line.split()
        if words[0] in ("S","C"):
            target=scores if words[0]=="S" else candidates
            target.append((int(words[1],16),*map(int,words[2:])))
        elif words[0]=="T":
            status=tuple(map(int,words[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)
    assert status is not None
    return scores,candidates,status


@pytest.mark.parametrize("stride,delay",[(1,0),(2,100),(4,212),(10,530),(24,1272)])
@pytest.mark.parametrize("spacing",[39,40])
def test_every_window_numerator_energy_counter_and_peak(stride,delay,spacing,acquisitions,tmp_path):
    rng=np.random.default_rng(28933)
    values=rng.integers(-32768,32768,(700,2),dtype=np.int16)
    first=(1<<45)+87
    scores,candidates,status=run(acquisitions(stride,delay,"upper"),records(values,stride,first,spacing),tmp_path)
    padded=np.concatenate((np.zeros((175,2),dtype=np.int16),values))
    numerator,energy=acquisition_fixed(padded,"upper")
    expected=[(first+j*stride,int(n),int(e),int(j>=175)) for j,(n,e) in enumerate(zip(numerator,energy))]
    assert scores==expected
    expected_candidates=[]
    for j in range(176,len(values)-1):
        if (numerator[j]>numerator[j-1] and numerator[j]>=numerator[j+1]
                and energy[j]!=0 and int(numerator[j])*(1<<16)>=44*int(energy[j])*15729):
            expected_candidates.append((first+(j-197)*stride-delay,int(numerator[j]),int(energy[j])))
    assert candidates==expected_candidates
    assert status==(700,525,len(candidates),0,0)


@pytest.mark.parametrize("edge",["upper","lower"])
@pytest.mark.parametrize("kind",["positive","rolled","noise","tone"])
def test_blind_epoch_without_candidate_seed(edge,kind,acquisitions,tmp_path):
    rng=np.random.default_rng(3011)
    count=5000
    values=1500*(rng.normal(size=count)+1j*rng.normal(size=count))
    epoch=513
    if kind in ("positive","rolled"):
        pilot=frame(2500000,edge,roll=17 if kind=="rolled" else 0)
        values[epoch:epoch+len(pilot)]+=6000*pilot
    elif kind=="tone":
        values+=6000*np.exp(2j*np.pi*.14*np.arange(count))
    values*=np.exp(2j*np.pi*42000*np.arange(count)/2500000)
    iq=np.rint(np.column_stack((values.real,values.imag))).astype(np.int16)
    _,candidates,status=run(acquisitions(1,0,edge),records(iq,1,0),tmp_path)
    assert status[3:]==(0,0)
    if kind in ("positive","rolled"):
        strongest=max(candidates,key=lambda c:c[1]/c[2])
        # Rolled pilot is an ambiguous shifted positive under blind search.
        assert strongest[0]==epoch+(187 if kind=="rolled" else 0)
    else:
        assert not candidates


@pytest.mark.parametrize("spacing",[1,38])
def test_overspeed_fault_preserves_evidence(spacing,acquisitions,tmp_path):
    values=np.ones((300,2),dtype=np.int16)
    rows=records(values,1,0,spacing)+["0 0 1 1 0 0 0"]+records(values,1,300)
    _,candidates,status=run(acquisitions(1,0,"upper"),rows,tmp_path)
    assert not candidates and status[3]&2 and status[4]==1
