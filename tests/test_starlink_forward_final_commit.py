"""Same-edge forward completion under the existing retirement contract."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-ready-absorption.QxP2Z5AO/prepared-v1')
GUARD='starlink_pss_result_guard_owner_view.v'

def undo_guard(text):
    if '// BEGIN FORWARD FINAL COMMIT' not in text:return text
    text,n=re.subn(r'  // BEGIN FORWARD FINAL COMMIT\n.*?  // END FORWARD FINAL COMMIT\n',
        lambda _: '  wire final_commit = mailbox_commit_valid && mailbox_input_ready;\n',text,flags=re.S)
    assert n==1
    return text

def undo_bench(text):
    from tests.test_starlink_distributed_sticky_fault import undo_bench as undo_sticky
    text=undo_sticky(text)
    if '// BEGIN FORWARD FINAL COMMIT WITNESS' not in text:return text
    text,n=re.subn(r'  // BEGIN FORWARD FINAL COMMIT WITNESS\n.*?  // END FORWARD FINAL COMMIT WITNESS\n','',text,flags=re.S)
    assert n==1
    line='      report_forward_final; // FORWARD FINAL REPORT\n'
    assert text.count(line)==1
    return text.replace(line,'',1)

def test_exact_one_guard_delta():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    changed=[]
    for name in names:
        if not (RTL/name).exists():continue
        text=(RTL/name).read_text()
        if name=='starlink_pss_fft_staged_output_impl.v':
            from tests.test_starlink_distributed_sticky_fault import undo_top
            text=undo_top(text)
        if text!=(PARENT/name).read_text():changed.append(name)
        assert (undo_guard(text) if name==GUARD else text)==(PARENT/name).read_text(),name
    assert changed==[GUARD]
    assert undo_bench((RTL/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text()
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl']:
        assert (ROOT/'tools'/name).read_bytes()==(PARENT/name).read_bytes()

def run(tmp_path,mode=1,completed=1,mutation=None):
    source=(RTL/GUARD).read_text()
    if mutation in {'fault','qualified','reset','fallback'}:
        block=re.search(r'  // BEGIN FORWARD FINAL COMMIT\n.*?  // END FORWARD FINAL COMMIT\n',source,re.S)[0]
        changed=block
        if mutation=='fault':changed=block.replace('!forward_final_fault && ','',1)
        if mutation=='qualified':changed=block.replace('final_qualified && ','',1)
        if mutation=='reset':changed=block.replace('(resetn && active','(active',1)
        if mutation=='fallback':changed=block.replace("USE_FORWARD_RETIREMENT && inverse_phase === 1'b0","USE_FORWARD_RETIREMENT",1)
        assert changed!=block
        source=source.replace(block,changed,1)
    ports=source.split(') (',1)[1].split(');',1)[0]
    decl=[];connections=[]
    for width,names in re.findall(r'input wire\s*(\[[^\]]+\])?\s*([^\n]+)',ports):
        for name in names.split(','):
            name=name.strip()
            if name:
                assert re.fullmatch(r'\w+',name)
                decl.append(f"reg {width or ''} {name}='0;");connections.append(f'.{name}({name})')
    bench='`timescale 1ns/1ps\nmodule tb;\n'+'\n'.join(decl)+'\n'
    bench+=f'starlink_pss_result_guard_owner_view #(.USE_FORWARD_RETIREMENT({mode}),.USE_COMPLETED_INPUT_FAULT({completed})) dut('+','.join(connections)+');\n'
    bench+=r'''
reg final_bit=0, qualified=0, framing=0;
integer n,checks=0;
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
initial begin
 force dut.active_private=1'b1;
 force dut.return_occupied=1'b1;
 force dut.fault_reasons=8'b0;
 force dut.age=0;
 force dut.return_last=final_bit;
 force dut.final_qualified=qualified;
 output_bank_reserved=1;completed_input_certified=1;
 for(n=0;n<65536;n=n+1)begin
   resetn=val(n&3);final_bit=val((n>>2)&3);
   mailbox_input_ready=val((n>>4)&3);
   external_fault_now=val((n>>6)&3);completed_input_fault_now=external_fault_now;
   forward_mailbox_fault=val((n>>8)&3);inverse_phase=val((n>>10)&3);
   framing=val((n>>12)&3);qualified=val((n>>14)&3);
   mailbox_input_fault=forward_mailbox_fault ||
     (__BROKEN__ ? framing : (inverse_phase === 1'b0 ? 1'b0 : framing));
   #1;
   if(dut.final_commit !== (dut.mailbox_commit_valid && mailbox_input_ready))
     $fatal(1,"final commit mismatch case=%0d candidate=%b reference=%b",n,dut.final_commit,dut.mailbox_commit_valid && mailbox_input_ready);
   checks=checks+1;
 end
 $display("FORWARD_FINAL_CONTRACT_PASS checks=%0d four_state=1",checks);$finish;
end
endmodule
'''.replace('__BROKEN__','1' if mutation=='broken_contract' else '0')
    rtl=tmp_path/'guard.v';rtl.write_text(source)
    tb=tmp_path/'tb.sv';tb.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(rtl),str(tb)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('mode,completed',[(0,0),(0,1),(1,0),(1,1)])
def test_real_guard_fourstate_handshake(tmp_path,mode,completed):
    result=run(tmp_path,mode,completed)
    assert result.returncode==0 and 'FORWARD_FINAL_CONTRACT_PASS checks=65536' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['fault','qualified','reset','fallback','broken_contract'])
def test_missing_veto_or_invalid_caller_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation)
    assert result.returncode!=0 and 'final commit mismatch' in result.stdout,result.stdout+result.stderr
