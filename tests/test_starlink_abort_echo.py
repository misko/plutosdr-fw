"""Local fault views preserve immediate abort and all original mailbox behavior."""
from pathlib import Path
import re
import subprocess
import sys
import pytest
from tests import test_starlink_completion_mailbox_stage as bank
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import abort_echo_transform as transform
import abort_echo_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

@pytest.mark.parametrize('kind',list(transform.NAMES))
def test_exact_additive_delta(kind):
    old,new=transform.NAMES[kind]
    assert transform.transform((RTL/(old+'.v')).read_text(),kind)==(RTL/(new+'.v')).read_text()
    if kind=='TOP':
        text=(RTL/(new+'.v')).read_text()
        assert 'reg output_descriptor_locked;' in text
        assert 'output_descriptor_locked<=1;' in text

def run_sim(tmp_path,source,bench):
    (tmp_path/'dut.sv').write_text(source);(tmp_path/'tb.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
        str(tmp_path/'dut.sv'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

VALUES="""
 function value(input integer n);
   case(n&3) 0:value=0;1:value=1;2:value=1'bx;3:value=1'bz;endcase
 endfunction
"""

@pytest.mark.parametrize('kind',['STAGE','LEDGER'])
@pytest.mark.parametrize('mutation',['none','drop_sticky','drop_local'])
def test_four_state_absorption(tmp_path,kind,mutation):
    source=(RTL/(transform.NAMES[kind][1]+'.v')).read_text()
    marker='  assign local_fault ='
    before,local=source.split(marker)
    if mutation=='drop_sticky':
        assert local.count('resetn && (fault_q ||')==1
        local=local.replace('resetn && (fault_q ||',"resetn && (1'b0 ||",1)
    if mutation=='drop_local':
        term="(local_abort_epoch !== 1'b0)" if kind=='STAGE' else '(pending && !pending_good)'
        assert local.count(term)==1
        local=local.replace(term,"1'b0",1)
    source=before+marker+local
    if kind=='STAGE':
        body="""
 reg resetn=0,g=0,b=0,input_valid=0,output_ready=0,q=0;
 wire fault,local_fault;
 starlink_pss_identity_local_fault dut(
   .clk(1'b0),.resetn(resetn),.abort_epoch(g||b),.local_abort_epoch(b),
   .input_valid(input_valid),.output_ready(output_ready),
   .input_data(36'b0),.input_position(9'b0),.input_last(1'b0),
   .input_metadata(70'b0),.reference_metadata(70'b0),.refill_capacity(1'b0),
   .fault(fault),.local_fault(local_fault));
 wire original_parent=(g!==1'b0)||(fault!==1'b0);
 wire local_parent=(g!==1'b0)||(local_fault!==1'b0);
 integer n;
 initial begin
   force dut.fault_q=q;
   for(n=0;n<4096;n=n+1)begin
     resetn=value(n);g=value(n>>2);b=value(n>>4);
     input_valid=value(n>>6);output_ready=value(n>>8);q=value(n>>10);
     #1;if(original_parent!==local_parent)$fatal(1,"local fault absorption changed");
   end
   $display("ABSORPTION_PASS vectors=4096");$finish;
 end
"""
    else:
        body="""
 reg resetn=0,parent_fault=0,scalar_fault=0,q=0,p=0,good=0,command_valid=0,response_ready=0;
 wire fault,local_fault;
 starlink_pss_descriptor_local_fault dut(
   .clk(1'b0),.resetn(resetn),.abort_epoch(parent_fault||scalar_fault),
   .command_valid(command_valid),.response_ready(response_ready),
   .command_opcode(2'b0),.command_tag(32'b0),.command_descriptor(70'b0),
   .lookup_valid(1'b0),.lookup_tag(32'b0),.fault(fault),.local_fault(local_fault));
 wire original_parent=resetn&&(parent_fault||scalar_fault||fault);
 wire local_parent=resetn&&(parent_fault||scalar_fault||local_fault);
 integer n;
 initial begin
   force dut.fault_q=q;force dut.pending=p;force dut.pending_good=good;
   // Parent fault register is known after coordinated reset; scalar_fault
   // is built entirely from case-inequality checks and is always known.
   for(n=0;n<16384;n=n+1)begin
     parent_fault=n&1;scalar_fault=(n>>1)&1;resetn=value(n>>2);
     q=value(n>>4);p=value(n>>6);good=value(n>>8);
     command_valid=value(n>>10);response_ready=value(n>>12);
     #1;if(original_parent!==local_parent)$fatal(1,"local fault absorption changed");
   end
   $display("ABSORPTION_PASS vectors=16384");$finish;
 end
"""
    result=run_sim(tmp_path,source,'module tb;'+VALUES+body+'endmodule')
    if mutation=='none':
        assert result.returncode==0 and 'ABSORPTION_PASS' in result.stdout,result.stdout
    else:
        assert result.returncode!=0 and 'local fault absorption changed' in result.stdout,result.stdout

@pytest.mark.parametrize('cancel',range(6))
@pytest.mark.parametrize('stall',[1,37])
def test_original_mailbox_full_state_equivalence(tmp_path,monkeypatch,cancel,stall):
    original=Path.read_text
    adapter=original(RTL/'starlink_pss_completion_local_fault.v')
    adapter=adapter.replace('module starlink_pss_completion_local_fault','module starlink_pss_completion_mailbox_stage',1)
    adapter+=original(RTL/'starlink_pss_descriptor_local_fault.v')
    adapter+=original(RTL/'starlink_pss_completion_mailbox_stage.v').replace(
        'module starlink_pss_completion_mailbox_stage','module original_completion_mailbox',1)
    observer=original(RTL/'abort_echo_observer.svh')
    replacements={
        'starlink_pss_completion_mailbox_stage':'original_completion_mailbox',
        'dut.output_control.':'dut.',
        'dut.fast_running':'resetn','dut.fast_fault':'abort_epoch',
        'dut.output_allocate_valid':'allocate_valid','dut.engine_metadata':'allocate_descriptor',
        'dut.output_complete_valid':'complete_valid','dut.inverse_tag':'complete_tag',
        'dut.guard_return_data[1]':'complete_final_data','dut.output_replay_private_ready':'replay_ready',
        'dut.output_request':'bank_request','dut.output_ack_sync':'bank_ack_sync',
        'dut.output_bank_local_fault':'bank_fault','dut.output_bank_fault':'bank_fault',
        'dut.inverse_descriptor_live':'lookup_valid','dut.output_complete_accept':'(complete_valid && complete_ready)',
        'fft_clk':'clk',
        '.allocated_ready(1\'b1)':'.allocated_ready(allocated_ready)',
        '.lookup_tag(complete_tag)':'.lookup_tag(lookup_tag)',
        'echo_checks<10000 || echo_completions<18':'echo_checks<100 || echo_completions<1',
    }
    for before,after in replacements.items():observer=observer.replace(before,after)
    # inverse_tag is used by completion and lookup in the real top. Component
    # lookup follows the independent reader tag, so correct just that port.
    observer=observer.replace('.lookup_tag(complete_tag)','.lookup_tag(lookup_tag)')
    def read(path,*args,**kwargs):
        text=original(path,*args,**kwargs)
        if path==RTL/'starlink_pss_completion_mailbox_stage.v':return adapter
        if path==RTL/'tb_staged_mailbox_control.sv':
            assert text.count('\nendmodule')==text.count('$finish(0);')==1
            text=text.replace('\nendmodule',observer+'\nendmodule',1)
            text=text.replace('$finish(0);','report_abort_echo;$finish(0);',1)
        return text
    monkeypatch.setattr(Path,'read_text',read)
    result=bank.run(tmp_path,cancel,stall,1)
    assert result.returncode==0 and 'ABORT_ECHO_PASS' in result.stdout,result.stdout+result.stderr

GOOD='ABORT_ECHO_PASS checks=177096 completions=18 removed_echoes=0 quarantine_checks=0 original_mailbox_exact=1\n'
def test_complete_witness():
    assert experiment.witness(GOOD)['completions']==18
    aux=GOOD.replace('removed_echoes=0','removed_echoes=1').replace('quarantine_checks=0','quarantine_checks=1')
    assert experiment.witness(aux,True)['removed_echoes']==1

@pytest.mark.parametrize('text',['',GOOD+GOOD,GOOD+'FATAL bad',GOOD.replace('completions=18','completions=0'),
    GOOD.replace('checks=177096','checks=1'),GOOD.replace('original_mailbox_exact=1','original_mailbox_exact=0')])
def test_weak_witness_rejected(text):
    with pytest.raises(ValueError):experiment.witness(text)

def test_auxiliary_must_exercise_echo():
    with pytest.raises(ValueError):experiment.witness(GOOD,True)
