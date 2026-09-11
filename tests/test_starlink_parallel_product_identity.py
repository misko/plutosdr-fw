from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
from tests.test_starlink_product_identity_stage import PARENT, BANK
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import parallel_product_identity_transform as transform
import parallel_product_identity_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
STAGE='starlink_pss_product_identity_parallel_reference'
TOP='starlink_pss_fft_parallel_product_identity_impl'

@pytest.mark.parametrize('old,new,changes',[
    ('starlink_pss_product_identity_split_capacity',STAGE,transform.BANK_CHANGES),
    ('starlink_pss_fft_forward_private_status_impl',TOP,transform.TOP_CHANGES)])
def test_exact_combinational_delta(old,new,changes):
    a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

@pytest.mark.parametrize('mutation',['none','swap_select','omit_retiring','unchecked'])
def test_four_state_reference_selection(tmp_path,mutation):
    source=(RTL/(STAGE+'.v')).read_text()
    fragment=source[source.index('  (* keep = "true" *) wire match_held'):source.index('  always @(posedge')]
    if mutation=='swap_select':fragment=fragment.replace('reference_select ? match_retiring : match_held','reference_select ? match_held : match_retiring')
    elif mutation=='omit_retiring':fragment=fragment.replace('input_metadata == retiring_metadata','input_metadata == reference_metadata')
    elif mutation=='unchecked':fragment=fragment.replace("(reference_select ? match_retiring : match_held) === 1'b1","1'b1")
    bench='''`timescale 1ns/1ps
module tb;
reg [69:0] input_metadata,reference_metadata,retiring_metadata;
reg reference_select;
integer n,b,k,checks=0,seed=32'h45fea174;
function automatic four(input integer n);
case(n%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
'''+fragment+'''
task automatic check;
begin
 #1;
 if(identity_good !== ((input_metadata == (reference_select ? retiring_metadata : reference_metadata)) === 1'b1))
   $fatal(1,"parallel reference differs at %0d",checks);
 checks=checks+1;
end
endtask
initial begin
 // Exhaust all two-bit metadata triples and all four-state selectors.
 for(n=0;n<16384;n=n+1)begin
  input_metadata=0;reference_metadata=0;retiring_metadata=0;
  input_metadata[0]=four(n);input_metadata[1]=four(n/4);
  reference_metadata[0]=four(n/16);reference_metadata[1]=four(n/64);
  retiring_metadata[0]=four(n/256);retiring_metadata[1]=four(n/1024);
  reference_select=four(n/4096);check;
 end
 // Exercise every physical bit, equality and X/Z metadata at each selector.
 for(b=0;b<70;b=b+1)for(k=0;k<4;k=k+1)for(n=0;n<4;n=n+1)begin
  input_metadata=0;reference_metadata=0;retiring_metadata=0;reference_select=four(k);
  retiring_metadata[b]=four(n);check;
  reference_metadata[b]=four(n);check;
  input_metadata[b]=four(n);check;
 end
 for(n=0;n<20000;n=n+1)begin
  input_metadata={$random(seed),$random(seed),$random(seed)};
  reference_metadata={$random(seed),$random(seed),$random(seed)};
  retiring_metadata={$random(seed),$random(seed),$random(seed)};reference_select=four(n);
  if(n%3==0)reference_metadata=input_metadata;
  if(n%3==1)retiring_metadata=input_metadata;
  if(n%7==0)begin reference_metadata=input_metadata;retiring_metadata=input_metadata;end
  if(n%8==0)retiring_metadata[n%70]=1'bx;
  if(n%8==1)reference_metadata[n%70]=1'bz;
  if(n%8==2)input_metadata[n%70]=1'bx;
  check;
 end
 $display("PARALLEL_REFERENCE_ALGEBRA_PASS checks=%0d",checks);$finish;
end
endmodule
'''
    result=compile_run(tmp_path,bench)
    if mutation=='none':assert result.returncode==0 and 'PARALLEL_REFERENCE_ALGEBRA_PASS checks=39744' in result.stdout,result.stdout
    else:assert result.returncode!=0 and 'parallel reference differs' in result.stdout,result.stdout

@pytest.mark.parametrize('mutation',['none','unchecked','no_write_through','lost_abort','drop_final','bypass_certificate'])
def test_real_mailbox_refill_faults_and_recovery(tmp_path,mutation):
    source=(RTL/(STAGE+'.v')).read_text();bank=BANK.read_text()
    bench=(RTL/'tb_product_identity_stage.sv').read_text()
    bench=bench.replace('starlink_pss_product_identity_stage stage(',STAGE+' stage(',1)
    assert STAGE+' stage(' in bench
    old='.reference_metadata(reference_metadata),'
    assert bench.count(old)==1
    bench=bench.replace(old,'.reference_metadata(held_metadata),.retiring_metadata(staged_metadata),.reference_select(metadata_load),',1)
    bench=bench.replace('.output_valid(staged_valid),','.refill_capacity(bank_ready && allow_write),.output_valid(staged_valid),',1)
    if mutation=='unchecked':source=source.replace("(reference_select ? match_retiring : match_held) === 1'b1","1'b1",1)
    elif mutation=='no_write_through':bench=bench.replace('.reference_select(metadata_load)',".reference_select(1'b0)",1)
    elif mutation=='lost_abort':source=source.replace("(abort_epoch !== 1'b0)","1'b0",1)
    elif mutation=='drop_final':bench=bench.replace("((staged_last===1'b0) || bank_commit)","1'b1",1)
    elif mutation=='bypass_certificate':bank=bank.replace("input_metadata_certified === 1'b1","1'b1",1)
    (tmp_path/'stage.v').write_text(source);(tmp_path/'bank.v').write_text(bank)
    result=compile_run(tmp_path,bench,[PARENT,tmp_path/'stage.v',tmp_path/'bank.v'])
    if mutation=='none':
        assert result.returncode==0,result.stdout+result.stderr
        row=re.search(r'PRODUCT_IDENTITY_COMPONENT_PASS good_blocks=(\d+) bad_metadata=420 bad_framing=6 resets=8 reads=(\d+) refills=(\d+) holds=(\d+) oracle=(\d+) updates=(\d+)',result.stdout)
        assert row,result.stdout
        good,reads,refills,holds,oracle,updates=map(int,row.groups())
        assert good==12 and reads==6144 and refills>=510 and holds>=200 and oracle>=1000 and updates>=12
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

GOOD='PARALLEL_PRODUCT_IDENTITY_PASS checks=10000 captures=9216 first_refills=18 four_state_exact=1 same_edge_capture=1\n'
def test_actual_witness():assert experiment.witness(GOOD)['first_refills']==18
@pytest.mark.parametrize('log',['',GOOD+GOOD,GOOD+'FATAL\n',GOOD.replace('checks=10000','checks=9999'),
    GOOD.replace('captures=9216','captures=9215'),GOOD.replace('first_refills=18','first_refills=17'),
    GOOD.replace('four_state_exact=1','four_state_exact=0'),GOOD.replace('same_edge_capture=1','same_edge_capture=0')])
def test_incomplete_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log)
