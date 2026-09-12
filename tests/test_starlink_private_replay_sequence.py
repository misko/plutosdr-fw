"""Exact bank contract plus private replay offer confinement."""
from pathlib import Path
import sys
import re
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
from tests.test_starlink_private_forward_capture import REFERENCE_INSTANCE
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import private_replay_sequence_transform as transform
import private_replay_sequence_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
OLD='starlink_pss_forward_return_private_descriptor'
BANK='starlink_pss_forward_return_private_replay'
TOP='starlink_pss_fft_private_replay_sequence_impl'

@pytest.mark.parametrize('old,new,changes',[
    (OLD,BANK,transform.BANK_CHANGES),
    ('starlink_pss_fft_output_retirement_receipt_impl',TOP,transform.TOP_CHANGES)])
def test_exact_additive_delta(old,new,changes):
    a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

def reference():
    observer=REFERENCE_INSTANCE
    start=observer.index('      if(dut.write_count!==')
    end=observer.index('      equivalence_checks=',start)
    observer=observer[:start]+'''
      if({dut.state,dut.fault_q,dut.replay_valid,dut.write_count,dut.read_count,dut.descriptor,dut.exponent,dut.output_position} !==
         {original.state,original.fault_q,original.replay_valid,original.write_count,original.read_count,original.descriptor,original.exponent,original.output_position})
        $fatal(1,"private offer changed existing bank state");
      if(dut.private_replay_valid===1'b1 && output_valid!==1'b1 && fault!==1'b1)
        $fatal(1,"private-only offer without current fault");
      if(output_valid===1'b1 && dut.private_replay_valid!==1'b1)
        $fatal(1,"public replay lacks private offer");
'''+observer[end:]
    return observer

def run(tmp_path,bench,case=None):
    (tmp_path/'reference.v').write_text((RTL/(OLD+'.v')).read_text().replace('module '+OLD+' #(','module bank_reference #(',1))
    return compile_run(tmp_path,bench,[RTL/(BANK+'.v'),tmp_path/'reference.v'],case)

@pytest.mark.parametrize('case',range(21))
def test_existing_bank_contract_unchanged(tmp_path,case):
    bench=(RTL/'tb_forward_return_bank.sv').read_text().replace('starlink_pss_forward_return_bank dut(',BANK+' dut(',1)
    bench=bench.replace('module tb;','module tb;\nwire private_fault,private_replay_valid;',1)
    bench=bench.replace('\nendmodule','\n'+reference()+'\nendmodule',1)
    result=run(tmp_path,bench,case)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'private_differences=0 current_exact=1 valid_payload_exact=1' in result.stdout

def test_replay_four_state_controls_and_recovery(tmp_path):
    bench='''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,abort_epoch=0,reserve_valid=0,capture_valid=0,seal_valid=0,output_ready=0;
reg [69:0] reserve_descriptor=70'h12345,capture_descriptor=70'h12345;
reg [35:0] capture_data=0;
reg [8:0] capture_position=0;
reg capture_last=0;
reg [4:0] capture_exponent=7;
wire reserve_ready,capture_ready,output_valid,output_last,done_pulse,busy,fault,private_fault,private_replay_valid;
wire [35:0] output_data;wire [8:0] output_position;
wire [4:0] output_exponent;wire [69:0] output_descriptor;
'''+BANK+''' #(.ADDRESS_WIDTH(2)) dut(.*);
integer n,k,j,divergences=0,reads=0;
function automatic four(input integer d);
case(d%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
task tick;begin #1;clk=1;#1;clk=0;#1;end endtask
task prime;begin
  resetn=0;abort_epoch=0;reserve_valid=0;capture_valid=0;seal_valid=0;output_ready=0;tick;
  resetn=1;tick;reserve_valid=1;tick;reserve_valid=0;
  for(k=0;k<4;k=k+1)begin capture_valid=1;capture_data=100+k;capture_position=k;capture_last=k==3;tick;end
  capture_valid=0;seal_valid=1;tick;seal_valid=0;tick;
  if(output_valid!==1 || private_replay_valid!==1)$fatal(1,"missing sealed private offer");
end endtask
initial begin
  for(n=0;n<1024;n=n+1)begin
    prime;
    reserve_valid=four(n);capture_valid=four(n/4);seal_valid=four(n/16);
    abort_epoch=four(n/64);output_ready=four(n/256);#1;
    if(private_replay_valid===1 && output_valid!==1)begin
      if(fault!==1)$fatal(1,"unfenced private-only offer");
      divergences=divergences+1;
    end
    tick;
    if(fault===1 && private_replay_valid!==0)$fatal(1,"private replay persisted after fault edge");
    prime;output_ready=1;reads=0;
    for(j=0;j<10 && reads<4;j=j+1)begin
      if(output_valid)begin
        if(output_data!==36'(100+reads) || output_position!==9'(reads))$fatal(1,"fresh replay mismatch");
        reads=reads+1;
      end
      tick;
    end
    if(reads!=4 || fault)$fatal(1,"fresh replay recovery missing");
  end
  if(divergences<1)$fatal(1,"private delta not exercised");
  $display("PRIVATE_REPLAY_GRID_PASS cases=1024 fresh_reads=4096 divergences=%0d",divergences);$finish;
end
'''+reference().replace('bank_reference original(','bank_reference #(.ADDRESS_WIDTH(2)) original(',1)+'\nendmodule\n'
    result=run(tmp_path,bench)
    assert result.returncode==0 and 'PRIVATE_REPLAY_GRID_PASS cases=1024 fresh_reads=4096' in result.stdout,result.stdout+result.stderr

MAIN='PRIVATE_REPLAY_SEQUENCE_PASS checks=10000 takes=9216 private_only=0 final_only=0 quarantined_differences=0 public_exact=1 receipt_fenced=1\n'
AUX=MAIN.replace('private_only=0','private_only=11').replace('final_only=0','final_only=5').replace('quarantined_differences=0','quarantined_differences=11')+''.join(
    f'PRIVATE_REPLAY_SEQUENCE_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(11))+ 'PRIVATE_REPLAY_SEQUENCE_BOUNDARIES_PASS cases=11 first_mid_last=1 current_veto=1 both_resets=1\n'

def test_actual_witnesses():
    assert experiment.witness(MAIN)['private_only']==0
    assert experiment.witness(AUX,True)['final_only']==5

@pytest.mark.parametrize('log,aux',[(MAIN+MAIN,False),(MAIN+'FATAL',False),(MAIN.replace('10000','9999'),False),
    (MAIN.replace('9216','9215'),False),(MAIN.replace('private_only=0','private_only=1'),False),
    (AUX.replace('final_only=5','final_only=0'),True),(AUX.replace('boundary=10','boundary=9'),True),
    (AUX.replace('fresh_reads=512','fresh_reads=511'),True),(AUX.replace('cases=11','cases=10'),True),
    (AUX.replace('public_exact=1','public_exact=0'),True)])
def test_incomplete_witness_rejected(log,aux):
    with pytest.raises(ValueError):experiment.witness(log,aux)

def test_preparation_selects_exact_candidate_and_public_vetoes():
    assert experiment.NEW==TOP and experiment.BANK==BANK
    helper=Path(experiment.__file__).read_text()
    assert 'product_publication_cone' not in helper
    assert 'private_replay_sequence_observer.svh' in helper and 'runtime_modules=41' in helper
    source=(RTL/(TOP+'.v')).read_text()
    assert '.input_valid(forward_buffer_valid && !fast_fault && product_bank_ready)' in source
    assert '(forward_buffer_fault === 1\'b0)' in source
    assert 'auxiliary_active=1;run_private_replay_sequence_boundaries;' in (ROOT/'tools/private_replay_sequence_smoke.py').read_text()
