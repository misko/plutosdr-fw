"""Actual-bank four-state equivalence and strict source delta."""
from pathlib import Path
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import product_local_framing_transform as transform
import product_local_framing_experiment as experiment
RTL=experiment.RTL
OLD='starlink_pss_product_mailbox_staged_identity'
BANK=experiment.BANK

@pytest.mark.parametrize('old,new,changes',[
    (OLD,BANK,transform.BANK_CHANGES),
    (experiment.base.NEW,experiment.NEW,transform.TOP_CHANGES)])
def test_exact_source_delta(old,new,changes):
    a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

def bench(width):
    template=r'''__TIMESCALE__
module tb;
localparam W=WIDTH,DEPTH=1<<W;
reg clk=0,resetn=0,valid=0,last=0,certificate=1,other=1,read_ready=0;
reg [W-1:0] position=0;
reg [35:0] data=0;
wire ready,fault,current_fault,request,output_valid;
wire ref_ready,ref_fault,ref_current_fault,ref_request,ref_output_valid;
wire permission=other && !ref_current_fault;
BANK #(.ADDRESS_WIDTH(W),.RESET_RELEASE_EXTERNAL(1),.EXPLICIT_COMMIT(1)) dut(
 .input_clk(clk),.input_resetn(resetn),.input_valid(valid),.input_ready(ready),
 .input_commit_authorized(permission),.input_other_commit_authorized(other),
 .input_data(data),.input_position(position),.input_last(last),
 .input_metadata(70'h12345),.input_metadata_certified(certificate),
 .input_fault(fault),.input_framing_fault_now(current_fault),
 .output_clk(clk),.output_resetn(resetn),.output_valid(output_valid),
 .output_ready(read_ready),.owner_request(request));
OLD #(.ADDRESS_WIDTH(W),.RESET_RELEASE_EXTERNAL(1),.EXPLICIT_COMMIT(1)) original(
 .input_clk(clk),.input_resetn(resetn),.input_valid(valid),.input_ready(ref_ready),
 .input_commit_authorized(permission),
 .input_data(data),.input_position(position),.input_last(last),
 .input_metadata(70'h12345),.input_metadata_certified(certificate),
 .input_fault(ref_fault),.input_framing_fault_now(ref_current_fault),
 .output_clk(clk),.output_resetn(resetn),.output_valid(ref_output_valid),
 .output_ready(read_ready),.owner_request(ref_request));
integer n,j,b,checks=0,reads=0,unknown_frames=0,rejected=0;
function automatic four(input integer d);
case(d%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
task compare;
begin
 if({ready,fault,current_fault,request,output_valid,dut.write_position,dut.acknowledge_sync,dut.request_sync,
     dut.metadata_in_hold,dut.metadata_out_hold,dut.reading,dut.read_all_loaded,dut.read_address,
     dut.read_output_position,dut.read_payload,dut.read_valid,dut.acknowledge_toggle} !==
    {ref_ready,ref_fault,ref_current_fault,ref_request,ref_output_valid,original.write_position,original.acknowledge_sync,original.request_sync,
     original.metadata_in_hold,original.metadata_out_hold,original.reading,original.read_all_loaded,original.read_address,
     original.read_output_position,original.read_payload,original.read_valid,original.acknowledge_toggle})
   $fatal(1,"bank public/private state mismatch n=%0d position=%b last=%b cert=%b other=%b",n,position,last,certificate,other);
 checks=checks+1;
end endtask
task tick;begin #1;compare;clk=1;#1;compare;clk=0;#1;end endtask
task reset_bank;begin
 resetn=0;valid=0;other=1;last=0;certificate=1;read_ready=0;position=0;tick;
 resetn=1;tick;
end endtask
task prime_final;begin
 reset_bank;
 for(j=0;j<DEPTH-1;j=j+1)begin valid=1;position=j;last=0;data=j;tick;end
 if(dut.write_position!==W'(DEPTH-1))$fatal(1,"final cursor not primed");
end endtask
task fresh;
begin
 reset_bank;
 for(j=0;j<DEPTH;j=j+1)begin
   valid=1;position=j;last=j==DEPTH-1;data=j;tick;
 end
 valid=0;read_ready=1;j=0;
 repeat(DEPTH+8)begin
   if(output_valid)begin
     if(dut.output_data!==36'(j) || dut.output_position!==W'(j))$fatal(1,"fresh data mismatch");
     j=j+1;reads=reads+1;
   end
   tick;
 end
 if(j!=DEPTH || fault || dut.request_toggle!==dut.acknowledge_sync[1])$fatal(1,"fresh block/ACK missing");
end endtask
initial begin
 if(W==2)begin
   for(n=0;n<4096;n=n+1)begin
     prime_final;
     position={four(n/4),four(n)};last=four(n/16);certificate=four(n/64);
     other=four(n/256);valid=four(n/1024);#1;
     if(dut.input_framing_valid===1'bx)unknown_frames=unknown_frames+1;
     if(dut.input_framing_valid!==1 && valid===1 && other===1)rejected=rejected+1;
     tick;
     valid=0;repeat(4)tick;
     fresh;
   end
 end else begin
   for(n=0;n<2304;n=n+1)begin
     prime_final;position=DEPTH-1;b=n/64;
     if(b%4!=0)position[b/4]=b%4==1?1'b0:b%4==2?1'bx:1'bz;
     last=four(n);certificate=four(n/4);other=four(n/16);valid=1;
     #1;if(dut.input_framing_valid===1'bx)unknown_frames=unknown_frames+1;
     if(dut.input_framing_valid!==1 && other===1)rejected=rejected+1;
     tick;valid=0;repeat(4)tick;
   end
   fresh;
 end
 if(unknown_frames<1 || rejected<1)$fatal(1,"no unknown/malformed coverage");
 $display("LOCAL_FRAMING_BANK_PASS width=%0d cases=%0d checks=%0d reads=%0d unknown=%0d rejected=%0d",W,n,checks,reads,unknown_frames,rejected);
 $finish;
end
endmodule
'''
    return template.replace('__TIMESCALE__',chr(96)+'timescale 1ns/1ps').replace('W=WIDTH,','W='+str(width)+',').replace('BANK #(',BANK+' #(').replace('OLD #(',OLD+' #(')

@pytest.mark.parametrize('width',[2,9])
@pytest.mark.parametrize('mutation',['none','unknown_bypass','other_bypass'])
def test_actual_bank_four_state_and_recovery(tmp_path,width,mutation):
    source=(RTL/(BANK+'.v')).read_text()
    if mutation=='unknown_bypass':source=source.replace("(input_framing_valid === 1'b1)","1'b1",1)
    if mutation=='other_bypass':source=source.replace('!EXPLICIT_COMMIT || input_other_commit_authorized',"1'b1",1)
    changed=tmp_path/'bank.v';changed.write_text(source)
    result=compile_run(tmp_path,bench(width),[changed,RTL/(OLD+'.v')])
    if mutation=='none':
        assert result.returncode==0 and 'LOCAL_FRAMING_BANK_PASS' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'bank public/private state mismatch' in result.stdout,result.stdout+result.stderr

def test_only_self_fault_removed_from_product_permission():
    source=(RTL/(experiment.NEW+'.v')).read_text()
    def expr(name):return source.split('wire '+name+' = ',1)[1].split(';',1)[0]
    assert expr('product_nonlocal_fault_now').split()==expr('external_fault_now').replace('product_bank_framing_fault_now || ','',1).split()
    assert expr('product_other_commit_authorized')==expr('product_commit_authorized').replace('!external_fault_now','!product_nonlocal_fault_now')
    assert '.input_commit_authorized(product_commit_authorized)' in source
    assert '.input_other_commit_authorized(product_other_commit_authorized)' in source

GOOD='PRODUCT_LOCAL_FRAMING_PASS checks=10000 publications=18 local_rejections=0 actual_request_exact=1\n'
def test_witness():assert experiment.witness(GOOD)['publications']==18
@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD+'FATAL',GOOD.replace('10000','9999'),GOOD.replace('publications=18','publications=19'),GOOD.replace('local_rejections=0','local_rejections=1')])
def test_bad_witness(bad):
    with pytest.raises(ValueError):experiment.witness(bad)
