import shutil
import subprocess

import numpy as np
import pytest

from tools import starlink_coarse25 as base


def expected_map(scores, first):
    phase=3*np.arange(len(scores))%10000
    summed=np.bincount(phase,weights=scores,minlength=10000).astype(np.int64)
    folded=np.roll(summed,1)+summed+np.roll(summed,-1)
    peak=int(np.argmax(folded))
    distance=base.circular_distance(np.arange(10000),peak,10000)
    background=folded[distance>150]
    total=sum(map(int,background))
    squares=sum(int(x)**2 for x in background)
    n=len(background)
    delta=int(folded[peak])*n-total
    detected=int(delta>0 and delta*delta>=64*(n*squares-total*total))
    return (first,peak,int(folded[peak]),total,squares,n,detected)


@pytest.mark.parametrize('kind',['zero','peak_wrap','noise','two_banks','gap_recovery','overrun_recovery','flush_scan'])
def test_exact_phase_maps_moments_and_gate(tmp_path,kind):
    assert shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required'
    groups=2
    count=groups*10000
    rng=np.random.default_rng(77013)
    tiles=3 if kind=='two_banks' else 1
    scores=rng.integers(1,30,size=count*tiles,dtype=np.uint8)
    if kind=='zero': scores[:]=0
    if kind in ('peak_wrap','two_banks'):
        for tile in range(tiles):
            target=(9999+tile*3500)%10000
            phase=3*np.arange(count)%10000
            scores[tile*count:(tile+1)*count][base.circular_distance(phase,target,10000)<=1]=220
    expected=[expected_map(scores[t*count:(t+1)*count],1000+t*count) for t in range(tiles)]
    (tmp_path/'scores.mem').write_text('\n'.join(f'{int(x):02x}' for x in scores)+'\n')
    tb=r'''
module tb;
 reg clk=0; always #5 clk=~clk;
 reg reset=1,flush=0,valid=0;
 reg [7:0] score=0;
 reg [63:0] idx=0;
 wire initializing,fault,cv,detected;
 wire [63:0] first;
 wire [13:0] phase,n;
 wire [14:0] peak;
 wire [27:0] sum;
 wire [42:0] sumsq;
 reg [7:0] scores [0:COUNT-1];
 integer k;
 starlink_coarse25_fold #(.GROUPS(GROUP_COUNT)) dut(
  .clk(clk),.reset(reset),.flush(flush),.score_valid(valid),.score(score),
  .score_first_index(idx),.initializing(initializing),.fault(fault),
  .candidate_valid(cv),.detected(detected),.candidate_map_first_index(first),
  .candidate_phase(phase),.candidate_peak(peak),.candidate_background_sum(sum),
  .candidate_background_sumsq(sumsq),.candidate_background_count(n));
 always @(posedge clk) begin
  #1;
  if(fault) $display("FAULT");
  if(cv) $display("MAP %0d %0d %0d %0d %0d %0d %0d",first,phase,peak,sum,sumsq,n,detected);
 end
 initial begin
  $readmemh("scores.mem",scores);
  repeat(3) @(negedge clk); reset=0;
  wait(initializing==0); @(negedge clk);
  PRELUDE
  for(k=0;k<COUNT;k=k+1) begin
   score=scores[k]; idx=1000+k; valid=1;
   @(negedge clk); valid=0;
   repeat(3) @(negedge clk);
  end
  repeat(40000) @(negedge clk);
  $finish;
 end
endmodule
'''.replace('GROUP_COUNT',str(groups)).replace('COUNT',str(len(scores)))
    prelude=''
    if kind=='gap_recovery':
        prelude='''valid=1; score=9; idx=10; @(negedge clk); valid=0;
          repeat(3) @(negedge clk); valid=1; idx=12; @(negedge clk); valid=0;
          wait(initializing==1); wait(initializing==0); @(negedge clk);'''
    elif kind=='overrun_recovery':
        prelude='''valid=1; score=9; idx=10; @(negedge clk); idx=11;
          @(negedge clk); valid=0;
          wait(initializing==1); wait(initializing==0); @(negedge clk);'''
    elif kind=='flush_scan':
        prelude=f'''for(k=0;k<{count};k=k+1) begin
          score=scores[k]; idx=50000+k; valid=1;
          @(negedge clk); valid=0; repeat(3) @(negedge clk);
          end
          repeat(100) @(negedge clk); flush=1;
          @(negedge clk); flush=0;
          wait(initializing==0); @(negedge clk);'''
    tb=tb.replace('PRELUDE',prelude)
    (tmp_path/'tb.sv').write_text(tb)
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
                    str(base.ROOT/'hdl/library/starlink_coarse25/starlink_coarse25_fold.v'),
                    str(tmp_path/'tb.sv')],check=True,capture_output=True)
    result=subprocess.run(['vvp',str(tmp_path/'sim')],cwd=tmp_path,check=True,
                          capture_output=True,text=True,timeout=60)
    actual=[tuple(map(int,s.split()[1:])) for s in result.stdout.splitlines() if s.startswith('MAP ')]
    assert actual==expected
    assert sum(line=='FAULT' for line in result.stdout.splitlines())==int(kind in ('gap_recovery','overrun_recovery'))
