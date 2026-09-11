from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
from tests.test_starlink_product_identity_stage import PARENT,BANK
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import product_retirement_receipt_experiment as experiment
import product_retirement_receipt_transform as transform
RTL=experiment.RTL

def test_exact_private_only_top_delta():
    old=(RTL/(experiment.base.NEW+'.v')).read_text();new=(RTL/(experiment.NEW+'.v')).read_text()
    assert transform.transform(old)==new and transform.undo(new)==old
    for marker in ['wire product_commit_authorized =','assign staged_product_ready =']:
        a=old[old.index(marker):].split(';',1)[0];b=new[new.index(marker):].split(';',1)[0]
        assert a==b

@pytest.mark.parametrize('mutation',['none','unknown_receipt','ignore_ownership'])
def test_retirement_ready_four_state(tmp_path,mutation):
    source=(RTL/(experiment.NEW+'.v')).read_text()
    fragment=source[source.index('  wire product_published_receipt ='):source.index('  starlink_pss_product_identity_parallel_reference product_identity_stage')]
    if mutation=='unknown_receipt':fragment=fragment.replace("(product_owner_request ^ product_owner_ack_sync) === 1'b1",'product_owner_request !== product_owner_ack_sync')
    elif mutation=='ignore_ownership':fragment=fragment.replace("&& product_published_receipt)","&& 1'b1)")
    bench='''`timescale 1ns/1ps
module tb;
reg product_owner_request,product_owner_ack_sync,fast_fault,staged_product_last,product_bank_ready;
integer n,checks=0;
function automatic four(input integer n);
case(n%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
'''+fragment+'''
reg expected;
initial begin
 for(n=0;n<1024;n=n+1)begin
  product_owner_request=four(n);product_owner_ack_sync=four(n/4);fast_fault=four(n/16);
  staged_product_last=four(n/64);product_bank_ready=four(n/256);
  expected=0;
  if(fast_fault===0)begin
   if(staged_product_last===0)expected=product_bank_ready===1;
   if(staged_product_last===1)expected=(product_owner_request===0 && product_owner_ack_sync===1) ||
     (product_owner_request===1 && product_owner_ack_sync===0);
  end
  #1;if(product_retire_ready!==expected)$fatal(1,"retirement authority mismatch");checks=checks+1;
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
    stage=(RTL/'starlink_pss_product_identity_parallel_reference.v').read_text();bank=BANK.read_text()
    bench=(RTL/'tb_product_identity_stage.sv').read_text()
    bench=bench.replace('starlink_pss_product_identity_stage stage(','starlink_pss_product_identity_parallel_reference stage(',1)
    bench=bench.replace('.reference_metadata(reference_metadata),','.reference_metadata(held_metadata),.retiring_metadata(staged_metadata),.reference_select(metadata_load),',1)
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
    elif mutation=='unchecked':stage=stage.replace("(reference_select ? match_retiring : match_held) === 1'b1","1'b1",1)
    elif mutation=='lost_abort':stage=stage.replace("(abort_epoch !== 1'b0)","1'b0",1)
    elif mutation=='no_write_through':bench=bench.replace('.reference_select(metadata_load)',".reference_select(1'b0)",1)
    elif mutation=='bypass_certificate':bank=bank.replace("input_metadata_certified === 1'b1","1'b1",1)
    (tmp_path/'stage.v').write_text(stage);(tmp_path/'bank.v').write_text(bank)
    result=compile_run(tmp_path,bench,[PARENT,tmp_path/'stage.v',tmp_path/'bank.v'])
    if mutation=='none':
        assert result.returncode==0,result.stdout+result.stderr
        assert 'PRODUCT_IDENTITY_COMPONENT_PASS good_blocks=12 bad_metadata=420 bad_framing=6 resets=8 reads=6144' in result.stdout,result.stdout
        assert 'RETIREMENT_MAILBOX_PASS' in result.stdout
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

MAIN='PRODUCT_RETIREMENT_RECEIPT_PASS checks=10000 publications=18 retires=18 extra_holds=18 exact_publication=1 no_post_publication_write=1 receipt_retirement=1\n'
LINES=[f'PRODUCT_RETIREMENT_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(5)]
LINES+=['PRODUCT_RETIREMENT_BOUNDARIES_PASS cases=5 delayed_publication=1 pending_reset=1 checked_receipt=1\n']
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
