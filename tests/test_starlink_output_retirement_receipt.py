from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
from tests.test_starlink_product_identity_stage import PARENT
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import output_retirement_receipt_experiment_v2 as experiment
import output_retirement_receipt_transform as transform
RTL=experiment.RTL
BANK=RTL/'starlink_pss_output_mailbox_staged_identity.v'

@pytest.mark.parametrize('mutation',['none','recursive'])
def test_auxiliary_campaign_entry_is_acyclic(tmp_path,mutation):
    prepared=tmp_path/'prepared'
    experiment.prepare(prepared,True)
    bench=(prepared/'tb_fft_buffered_forward.sv').read_text()
    if mutation=='recursive':
        before='      run_output_retirement_boundaries;'
        assert bench.count(before)==1
        bench=bench.replace(before,'      run_product_retirement_boundaries;',1)
    bodies=dict(re.findall(r'task automatic (\w+)[^;]*;(.*?)endtask',bench,re.S))
    def visit(name,ancestors):
        assert name not in ancestors, 'recursive auxiliary campaign: '+str(ancestors+[name])
        assert name in bodies
        for child in re.findall(r'\b(run_\w+)\s*;',bodies[name]):
            visit(child,ancestors+[name])
    def check():
        visit('run_buffered_auxiliary',[])
        assert sum(body.count('run_output_retirement_boundaries;') for body in bodies.values())==1
        assert 'run_output_retirement_boundaries;' in bodies['run_private_descriptor_boundaries']
    if mutation=='recursive':
        with pytest.raises(AssertionError,match='recursive auxiliary campaign'):check()
    else:check()

def test_exact_private_only_top_delta():
    old=(RTL/(experiment.base.NEW+'.v')).read_text();new=(RTL/(experiment.NEW+'.v')).read_text()
    assert transform.transform(old)==new and transform.undo(new)==old
    for marker in ['assign output_stage_consume =','assign output_replay_accept =']:
        a=old[old.index(marker):].split(';',1)[0];b=new[new.index(marker):].split(';',1)[0]
        assert a==b

@pytest.mark.parametrize('mutation',['none','unknown_receipt','ignore_ownership'])
def test_retirement_ready_four_state(tmp_path,mutation):
    source=(RTL/(experiment.NEW+'.v')).read_text()
    fragment=source[source.index('  wire output_published_receipt ='):source.index('  starlink_pss_product_identity_split_capacity output_identity_stage')]
    if mutation=='unknown_receipt':fragment=fragment.replace("(output_request ^ output_ack_sync) === 1'b1",'output_request !== output_ack_sync')
    elif mutation=='ignore_ownership':fragment=fragment.replace("&& output_published_receipt)","&& 1'b1)")
    bench='''`timescale 1ns/1ps
module tb;
reg output_request,output_ack_sync,fast_fault,output_stage_last,output_bank_ready;
integer n,checks=0;
function automatic four(input integer n);
case(n%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
'''+fragment+'''
reg expected;
initial begin
 for(n=0;n<1024;n=n+1)begin
  output_request=four(n);output_ack_sync=four(n/4);fast_fault=four(n/16);
  output_stage_last=four(n/64);output_bank_ready=four(n/256);
  expected=0;
  if(fast_fault===0)begin
   if(output_stage_last===0)expected=output_bank_ready===1;
   if(output_stage_last===1)expected=(output_request===0 && output_ack_sync===1) ||
     (output_request===1 && output_ack_sync===0);
  end
  #1;if(output_retire_ready!==expected)$fatal(1,"retirement authority mismatch");checks=checks+1;
 end
 $display("RETIREMENT_FOUR_STATE_PASS checks=%0d",checks);$finish;
end
endmodule
'''
    result=compile_run(tmp_path,bench)
    if mutation=='none':assert result.returncode==0 and 'RETIREMENT_FOUR_STATE_PASS checks=1024' in result.stdout,result.stdout
    else:assert result.returncode!=0 and 'retirement authority mismatch' in result.stdout,result.stdout

@pytest.mark.parametrize('mutation',['none','early_retire','unchecked','lost_abort','no_write_through','bypass_certificate'])
def test_actual_mailbox_receipt_retirement(tmp_path,mutation):
    stage=(RTL/'starlink_pss_product_identity_split_capacity.v').read_text();bank=BANK.read_text()
    bench=(RTL/'tb_product_identity_stage.sv').read_text()
    bench=bench.replace('starlink_pss_product_identity_stage stage(','starlink_pss_product_identity_split_capacity stage(',1)
    bench=bench.replace('starlink_pss_product_mailbox_staged_identity','starlink_pss_output_mailbox_staged_identity',1)
    bench=bench.replace('.output_valid(staged_valid),','.refill_capacity(bank_ready && allow_write),.output_valid(staged_valid),',1)
    old="assign staged_ready=bank_ready && allow_write && ((staged_last===1'b0) || bank_commit);"
    assert bench.count(old)==1
    new="assign staged_ready=((staged_last===1'b0) && bank_ready && allow_write) || ((staged_last===1'b1) && ((request ^ ack)===1'b1));"
    bench=bench.replace(old,new,1)
    observer='''
  integer receipt_holds=0,receipt_retires=0;
  always @(posedge clk)if(resetn && !stage_fault && staged_valid && staged_last)begin
    if(request!==ack)begin
      if(bank_ready || !staged_ready || input_ready)$fatal(1,"receipt retirement contract");
      receipt_retires=receipt_retires+1;
    end else if(bank_commit && bank_ready)begin
      if(staged_ready)$fatal(1,"early private final retirement");
      receipt_holds=receipt_holds+1;
    end
  end
  final begin
    if(receipt_holds<12 || receipt_retires<12)$fatal(1,"vacuous receipt delta");
    $display("RETIREMENT_MAILBOX_PASS holds=%0d retires=%0d",receipt_holds,receipt_retires);
  end
'''
    bench=bench.replace('\nendmodule','\n'+observer+'\nendmodule',1)
    if mutation=='early_retire':bench=bench.replace(new,old,1)
    elif mutation=='unchecked':stage=stage.replace("(input_metadata == reference_metadata) === 1'b1","1'b1",1)
    elif mutation=='lost_abort':stage=stage.replace("(abort_epoch !== 1'b0)","1'b0",1)
    elif mutation=='no_write_through':bench=bench.replace('metadata_load ? staged_metadata : held_metadata','held_metadata',1)
    elif mutation=='bypass_certificate':bank=bank.replace("input_metadata_certified === 1'b1","1'b1",1)
    (tmp_path/'stage.v').write_text(stage);(tmp_path/'bank.v').write_text(bank)
    result=compile_run(tmp_path,bench,[PARENT,tmp_path/'stage.v',tmp_path/'bank.v'])
    if mutation=='none':
        assert result.returncode==0,result.stdout+result.stderr
        assert 'PRODUCT_IDENTITY_COMPONENT_PASS good_blocks=12 bad_metadata=420 bad_framing=6 resets=8 reads=6144' in result.stdout,result.stdout
        assert 'RETIREMENT_MAILBOX_PASS' in result.stdout
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

MAIN='OUTPUT_RETIREMENT_RECEIPT_PASS checks=10000 publications=18 retires=18 extra_holds=18 exact_publication=1 no_post_publication_write=1 receipt_retirement=1\n'
LINES=[f'OUTPUT_RETIREMENT_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(5)]
LINES+=['OUTPUT_RETIREMENT_BOUNDARIES_PASS cases=5 delayed_publication=1 pending_reset=1 checked_receipt=1\n']
AUX=MAIN+''.join(LINES)
def test_main_witness():assert experiment.witness(MAIN)['retires']==18
def test_aux_witness():assert experiment.witness(AUX,True)['publications']==18
@pytest.mark.parametrize('line',range(6))
def test_missing_boundary_rejected(line):
    lines=LINES.copy();del lines[line]
    with pytest.raises(ValueError):experiment.witness(MAIN+''.join(lines),True)
@pytest.mark.parametrize('log',[MAIN+MAIN,MAIN+'FATAL\n',MAIN.replace('retires=18','retires=17'),
    MAIN.replace('extra_holds=18','extra_holds=17'),MAIN.replace('publications=18','publications=19'),
    MAIN.replace('exact_publication=1','exact_publication=0'),MAIN.replace('no_post_publication_write=1','no_post_publication_write=0'),
    MAIN.replace('receipt_retirement=1','receipt_retirement=0')])
def test_invalid_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log)
