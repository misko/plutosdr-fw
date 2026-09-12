from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from tools import starlink_coarse25 as base
from tools.starlink_coarse25_fixed import round_score


def simulate(tmp_path, samples, template_energy):
    assert shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required'
    packed = []
    for reset, flush, valid, re, im, energy, index in samples:
        value = reset << 176 | flush << 175 | valid << 174 | (re & (2**37-1)) << 137
        value |= (im & (2**37-1)) << 100 | energy << 64 | index
        packed.append(f'{value:045x}\n')
    (tmp_path / 'stim.mem').write_text(''.join(packed))
    tb = r'''
module tb;
 reg clk=0; always #5 clk=~clk;
 reg reset=1, flush=0, valid=0;
 reg signed [36:0] re=0, im=0;
 reg [35:0] energy=0;
 reg [63:0] idx=0;
 wire sv, dz, overrun;
 wire [7:0] score;
 wire [63:0] first;
 reg [176:0] stimulus [0:COUNT-1];
 integer cycle;
 starlink_coarse25_score #(.COEFFICIENT_ENERGY(36'dENERGY_VALUE)) dut(
 .clk(clk), .reset(reset), .flush(flush), .input_valid(valid), .input_re(re),
 .input_im(im), .input_energy(energy), .input_first_index(idx),
 .score_valid(sv), .score(score), .score_first_index(first),
 .denominator_zero(dz), .overrun(overrun));
 initial begin
  $readmemh("stim.mem",stimulus);
  for(cycle=0;cycle<COUNT;cycle=cycle+1) begin
   @(negedge clk); {reset,flush,valid,re,im,energy,idx}=stimulus[cycle];
   @(posedge clk); #1;
   if(overrun) $display("OVERRUN %0d",cycle);
   if(sv) $display("SCORE %0d %0d %0d %0d",cycle,first,score,dz);
  end
  $finish;
 end
endmodule
'''.replace('COUNT',str(len(samples))).replace('ENERGY_VALUE',str(template_energy))
    (tmp_path / 'tb.sv').write_text(tb)
    sources = [base.ROOT / 'hdl/library/starlink_coarse25/starlink_coarse25_score.v',
               base.ROOT / 'hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v']
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
                    *map(str,sources),str(tmp_path/'tb.sv')],check=True,capture_output=True)
    result = subprocess.run(['vvp',str(tmp_path/'sim')],cwd=tmp_path,check=True,
                            capture_output=True,text=True,timeout=60)
    return [tuple(line.split()) for line in result.stdout.splitlines()
            if line.startswith(('SCORE ','OVERRUN '))]


@pytest.mark.parametrize('template_energy',[2,1073660387,2**36-1])
def test_exact_rounding_width_and_latency(tmp_path,template_energy):
    rng=np.random.default_rng(2048)
    cases=[(1,0,1),(1,0,3),(0,0,0),(-2**36,-2**36,2**36-1),
           (2**36-1,-2**36,0),(0,0,2**36-1)]
    cases += [(int(r),int(i),int(e)) for r,i,e in
              zip(rng.integers(-2**27,2**27,100),rng.integers(-2**27,2**27,100),
                  rng.integers(1,2**36,100))]
    samples=[(1,0,0,0,0,0,0)]
    expected=[]
    for index,(re,im,energy) in enumerate(cases):
        start=len(samples)
        samples.append((0,0,1,re,im,energy,index))
        samples.extend([(0,0,0,0,0,0,0)]*19)
        expected.append(tuple(map(str,('SCORE',start+11,index,
                                       round_score(re,im,energy,template_energy),int(energy==0)))))
    actual=simulate(tmp_path,samples,template_energy)
    assert actual==expected


@pytest.mark.parametrize('abort_cycle',range(1,12))
def test_flush_cancels_each_pipeline_stage(tmp_path,abort_cycle):
    samples=[(1,0,0,0,0,0,0),(0,0,1,3,4,10,100)]
    samples.extend([(0,0,0,0,0,0,0)]*40)
    samples[1+abort_cycle]=(0,1,0,0,0,0,0)
    samples[25]=(0,0,1,3,4,10,101)
    assert simulate(tmp_path,samples,2)==[('SCORE','36','101','255','0')]


def test_overrun_discards_old_epoch_and_recovers(tmp_path):
    samples=[(1,0,0,0,0,0,0)]
    samples.extend((0,0,1,3,4,10,k) for k in range(12))
    samples.extend([(0,0,0,0,0,0,0)]*50)
    samples[40]=(0,0,1,1,0,3,900)
    actual=simulate(tmp_path,samples,2)
    assert any(row[0]=='OVERRUN' for row in actual)
    assert [row for row in actual if row[0]=='SCORE']==[('SCORE','51','900','42','0')]
