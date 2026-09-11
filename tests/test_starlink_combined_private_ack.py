"""Exact runtime inverse and four-state private ACK transition contract."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest
from tests.test_starlink_forward_receipt import undo_forward_receipt

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BASE=ROOT.parent/'staged-enginecapture-prepared-v1'
GUARD='starlink_pss_result_guard_owner_view.v'
TOP='starlink_pss_fft_staged_output_impl.v'

def test_complete_guard_and_top_inverse():
    for name,pin in [(TOP,'ff67df5cd0bf0fe45ab926e4c234ccbb7005cf82d7bec6c011652af4141b03ec'),
                     (GUARD,'ba0b9e308e2747e43edeec6c9b4bb486b2c1fc12d7d850d2bbf6a6ff02cc4431')]:
        old=(BASE/name).read_bytes();assert hashlib.sha256(old).hexdigest()==pin
        text=(RTL/name).read_text()
        if name==TOP:
            text=undo_forward_receipt(text)
            text=text.replace('    .PRIVATE_ACK_RETIREMENT(CERTIFIED_ADMISSION && OWNER==1),\n','',1)
        else:
            text=text.replace('  parameter integer PRIVATE_ACK_RETIREMENT = 0,\n','',1)
            start=text.index('  // BEGIN PRIVATE ACK RETIREMENT\n')
            end=text.index('  // END PRIVATE ACK RETIREMENT\n',start)+len('  // END PRIVATE ACK RETIREMENT\n')
            text=text[:start]+text[end:]
            text=text.replace('!protocol_fault && private_ack_clear_allowed)','!protocol_fault && !idle_fault_now)',1)
            text=text.replace('      // Legacy retains a faulted ACK wait; opt-in private retirement may clear\n'
                '      // on a known fault. The public ACK below still rejects that same edge.\n',
                '      // Retain a faulted ACK wait and never clear it on a coincident orphan.\n',1)
        assert text==old.decode(),'unrelated runtime change: '+name

def run(tmp_path,mutant=None):
    source=(RTL/GUARD).read_text()
    found=re.findall(r'  wire private_ack_clear_allowed = .*?;',source,re.S);assert len(found)==1
    decl=found[0]
    if mutant=='unknown_clear':decl=decl.replace("(idle_fault_now === 1'b0 || idle_fault_now === 1'b1)","1'b1")
    if mutant=='drop_fallback':decl=decl.replace('PRIVATE_ACK_RETIREMENT ?',"1'b1 ?")
    if mutant=='no_private_clear':decl=decl.replace('PRIVATE_ACK_RETIREMENT ?',"1'b0 ?")
    bench=r'''`timescale 1ns/1ps
module tb;
reg PRIVATE_ACK_RETIREMENT,awaiting_ack,mailbox_input_ready,protocol_fault,idle_fault_now,final_commit;
'''+decl+r'''
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer m,a,r,p,f,c,cases=0,differences=0;
reg candidate,original;
initial begin
 for(m=0;m<2;m=m+1)for(a=0;a<2;a=a+1)for(r=0;r<2;r=r+1)
 for(p=0;p<2;p=p+1)for(f=0;f<4;f=f+1)for(c=0;c<2;c=c+1)begin
   PRIVATE_ACK_RETIREMENT=m;awaiting_ack=a;mailbox_input_ready=r;
   protocol_fault=p;idle_fault_now=val(f);final_commit=c;#1;
   candidate=awaiting_ack;original=awaiting_ack;
   if(awaiting_ack && mailbox_input_ready && !protocol_fault && private_ack_clear_allowed)candidate=0;
   if(awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now)original=0;
   if(final_commit)begin candidate=1;original=1;end
   if(m && a && r && !p && f==1 && !c)begin
     if(candidate!==0 || original!==1)$fatal(1,"missing intentional known-fault private retirement");
     differences=differences+1;
   end else if(candidate!==original)$fatal(1,"unpermitted private ACK transition difference");
   cases=cases+1;
 end
 $display("PRIVATE_ACK_TRANSITION_PASS cases=%0d differences=%0d unknown_exact=1 fallback_exact=1",cases,differences);$finish;
end
endmodule
'''
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_four_state_private_ack_transition(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'PRIVATE_ACK_TRANSITION_PASS cases=128 differences=1 unknown_exact=1 fallback_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['unknown_clear','drop_fallback','no_private_clear'])
def test_incorrect_private_ack_transition_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

def accounting(tmp_path,variant='normal'):
    source=(RTL/GUARD).read_text()
    if variant=='missing_external':
        source=source.replace('reservation_error, external_fault_now || mailbox_input_fault}',
                              'reservation_error, mailbox_input_fault}',1)
    ports=source.split(') (',1)[1].split(');',1)[0]
    declarations=[];connections=[]
    for width,names in re.findall(r'input wire\s*(\[[^\]]+\])?\s*([^\n]+)',ports):
        for name in names.split(','):
            name=name.strip()
            if not name:continue
            assert re.fullmatch(r'\w+',name),name
            declarations.append(f"reg {width or ''} {name}='0;")
            connections.append(f'.{name}({name})')
    params='.PRIVATE_ACK_RETIREMENT(1),.USE_PHASE_INPUT_FAULT(1)' if variant=='bad_mode' else '.PRIVATE_ACK_RETIREMENT(1)'
    bench='`timescale 1ns/1ps\nmodule tb;\n'+'\n'.join(declarations)+'\n'
    bench+='starlink_pss_result_guard_owner_view #('+params+') dut('+','.join(connections)+');\n'
    facts=['external_fault_now','mailbox_input_fault','certified_input_beat','certified_input_complete',
           'core_event_frame_started','core_status_tvalid','core_output_tvalid']
    bench+=r'''
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer n;
initial begin
 resetn=1;#1;resetn=0;#1;resetn=1;
 input_bank_reserved=1;output_bank_reserved=1;mailbox_input_ready=1;
 for(n=0;n<16384;n=n+1)begin
'''+ '\n'.join(f'{name}=val((n>>{2*i})&3);' for i,name in enumerate(facts))+r'''
   #1;
   if(dut.active!==0 || dut.protocol_fault!==0 || dut.idle_fault_now!==dut.fault_now)
     $fatal(1,"inactive idle fault omitted from sticky accounting");
 end
 $display("PRIVATE_ACK_ACCOUNTING_PASS cases=16384 four_state_exact=1");$finish;
end
endmodule
'''
    rtl=tmp_path/'guard.v';rtl.write_text(source)
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(rtl),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_real_guard_inactive_fault_accounting(tmp_path):
    result=accounting(tmp_path)
    assert result.returncode==0 and 'PRIVATE_ACK_ACCOUNTING_PASS cases=16384 four_state_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('variant',['missing_external','bad_mode'])
def test_incomplete_accounting_or_contract_rejected(tmp_path,variant):
    result=accounting(tmp_path,variant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
