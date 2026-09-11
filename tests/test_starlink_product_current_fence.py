from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import product_current_fence_experiment as experiment
import product_current_fence_transform as transform

def test_exact_current_fence_delta():
    old=(experiment.RTL/(experiment.base.NEW+'.v')).read_text()
    new=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    assert len(transform.CHANGES)==2 and transform.transform(old)==new and transform.undo(new)==old

@pytest.mark.parametrize('mutation',[False,True])
def test_actual_gate_four_state_truth_table(tmp_path,mutation):
    text=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    start=text.index('  wire product_commit_authorized =')
    expression=text[start:text.index(';',start)+1]
    if mutation:expression=expression.replace(" &&\n    (guard_offered_local_fault === 2'b00)",'')
    bench='''`timescale 1ns/1ps
module tb;
reg forward_committed,external_fault_now,result_fault;
reg [1:0] guard_offered_local_fault;
reg expected;
integer a,b,c,g0,g1,checks=0;
function automatic bit4(input integer n);
case(n)0:bit4=0;1:bit4=1;2:bit4=1'bx;3:bit4=1'bz;endcase
endfunction
'''+expression+'''
initial begin
  for(a=0;a<2;a=a+1)for(b=0;b<2;b=b+1)for(c=0;c<2;c=c+1)
    for(g0=0;g0<4;g0=g0+1)for(g1=0;g1<4;g1=g1+1)begin
      forward_committed=a;external_fault_now=b;result_fault=c;
      guard_offered_local_fault={bit4(g1),bit4(g0)};
      expected=(a==1 && b==0 && c==0 && g0==0 && g1==0);#1;
      if(product_commit_authorized!==expected)$fatal(1,"product gate truth table");
      checks=checks+1;
    end
  if(checks!=128)$fatal(1,"vacuous gate table");
  $display("PRODUCT_GATE_PASS checks=128");$finish;
end
endmodule
'''
    (tmp_path/'bench.sv').write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'bench.sv')],capture_output=True,text=True,timeout=15)
    (tmp_path/'compile.log').write_text(build.stdout+build.stderr);assert build.returncode==0,build.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=15)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr)
    if mutation:assert result.returncode!=0 and 'product gate truth table' in result.stdout
    else:assert result.returncode==0 and 'PRODUCT_GATE_PASS checks=128' in result.stdout

MAIN='LOCAL_FAULT_PASS checks=10000 delayed_edges=0 pending_checks=0 exact_sources=1 bounded_abort=1 publication_fenced=1\n'
LOCAL=MAIN.replace('delayed_edges=0','delayed_edges=6').replace('pending_checks=0','pending_checks=6')
LOCAL+=''.join(f'LOCAL_FAULT_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6))
LOCAL+='LOCAL_FAULT_BOUNDARIES_PASS cases=6 delayed_fault_exercised=1 fresh_recovery=1\n'
LINES=[f'PRODUCT_CURRENT_FENCE_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6)]
LINES+=['PRODUCT_CURRENT_FENCE_BOUNDARIES_PASS cases=6 current_fault_fenced=1 pending_reset=1 fresh_recovery=1\n']
AUX=LOCAL+''.join(LINES)
def test_main_witness():assert experiment.witness(MAIN)['additional_boundaries']==0
def test_auxiliary_witness():assert experiment.witness(AUX,True)['additional_boundaries']==6

@pytest.mark.parametrize('line',range(7))
def test_each_boundary_required(line):
    lines=LINES.copy();del lines[line]
    with pytest.raises(ValueError):experiment.witness(LOCAL+''.join(lines),True)

@pytest.mark.parametrize('log',[AUX+AUX,AUX+'FATAL\n',AUX.replace('new_publications=0','new_publications=1'),
    AUX.replace('fresh_reads=512','fresh_reads=511'),AUX.replace('current_fault_fenced=1','current_fault_fenced=0'),
    AUX.replace('pending_reset=1','pending_reset=0')])
def test_changed_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log,True)
