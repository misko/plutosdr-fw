import hashlib
import shutil
import subprocess

import numpy as np
import pytest

from tools import starlink_coarse25 as base
from tools import starlink_coarse25_fixed as fixed


@pytest.mark.parametrize('kind',['random','recorded','gap'])
def test_mac_and_normalizer_composition(tmp_path,kind):
    assert shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required'
    rng=np.random.default_rng(33917)
    if kind=='recorded':
        fixture=base.ROOT/'tests/fixtures/coarse25_positive_ci16.mem'
        words=[int(s,16) for s in fixture.read_text().split()]
        assert len(words)==2048
        payload=b''.join(word.to_bytes(4,'little') for word in words)
        assert hashlib.sha256(payload).hexdigest() == 'fe50c3d29fd476d11049f3533c4aea703026080cf79a0156bbb3753c49c52db4'
        x=np.frombuffer(payload,dtype='<i2').reshape(-1,2)
    else:
        x=rng.integers(-32768,32768,size=(512,2),dtype=np.int16)
        x[:32]=-32768
    words=[((int(q)&65535)<<16)|(int(i)&65535) for i,q in x]
    (tmp_path/'input.mem').write_text('\n'.join(f'{w:08x}' for w in words)+'\n')
    shutil.copyfile(base.ROOT/'hdl/library/starlink_coarse25/coarse25_q15.mem',tmp_path/'coarse25_q15.mem')
    gap_at=256 if kind=='gap' else len(x)
    tb=r'''
module tb;
 reg clk=0; always #5 clk=~clk;
 reg reset=1, valid=0;
 reg signed [15:0] xi=0,xq=0;
 reg [63:0] idx=0;
 wire sv,dz,gap,mo,so;
 wire [7:0] score;
 wire [63:0] first;
 reg [31:0] samples [0:COUNT-1];
 integer n;
 starlink_coarse25_datapath dut(.clk(clk),.reset(reset),.sample_valid(valid),
  .sample_i(xi),.sample_q(xq),.sample_index(idx),.score_valid(sv),.score(score),
  .score_first_index(first),.denominator_zero(dz),.gap(gap),.mac_overrun(mo),.score_overrun(so));
 always @(posedge clk) begin
  #1;
  if(sv) $display("SCORE %0d %0d",first,score);
  if(gap) $display("GAP");
  if(mo || so) $fatal(1,"unexpected datapath overrun");
 end
 initial begin
  $readmemh("input.mem",samples);
  repeat(3) @(negedge clk);
  reset=0;
  for(n=0;n<COUNT;n=n+1) begin
   {xq,xi}=samples[n]; idx=n+(n>=GAP_AT ? 7 : 0); valid=1;
   @(negedge clk); valid=0;
   repeat(39) @(negedge clk);
  end
  repeat(50) @(negedge clk);
  $finish;
 end
endmodule
'''.replace('COUNT',str(len(x))).replace('GAP_AT',str(gap_at))
    (tmp_path/'tb.sv').write_text(tb)
    lib=base.ROOT/'hdl/library/starlink_coarse25'
    sources=[lib/name for name in ('starlink_coarse25_mac.v','starlink_coarse25_score.v',
                                  'starlink_coarse25_datapath.v')]
    sources.append(base.ROOT/'hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v')
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
                    *map(str,sources),str(tmp_path/'tb.sv')],capture_output=True,check=True)
    run=subprocess.run(['vvp',str(tmp_path/'sim')],cwd=tmp_path,capture_output=True,
                       text=True,check=True,timeout=60)
    actual=[(int(s.split()[1]),int(s.split()[2])) for s in run.stdout.splitlines()
            if s.startswith('SCORE ')]
    if kind=='gap':
        expected=list(enumerate(map(int,fixed.scores(x[:256]))))
        expected += [(256+7+k,int(s)) for k,s in enumerate(fixed.scores(x[256:]))]
    else:
        expected=list(enumerate(map(int,fixed.scores(x))))
    assert actual==expected
    assert sum(line=='GAP' for line in run.stdout.splitlines())==(kind=='gap')
