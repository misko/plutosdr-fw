"""Only registered-scheduler private payload capture changes, not authority."""
import hashlib
from pathlib import Path
import subprocess

import pytest
from tests.test_starlink_forward_receipt import undo_forward_receipt

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
TOP=RTL/'starlink_pss_fft_staged_output_impl.v'
BASE=ROOT.parent/'staged-inputidentity-prepared-v2'


def capture_block():
    text=TOP.read_text();start=text.index('    // BEGIN PRIVATE ENGINE DESCRIPTOR\n')
    end=text.index('    // END PRIVATE ENGINE DESCRIPTOR\n')+len('    // END PRIVATE ENGINE DESCRIPTOR\n')
    return text,start,end


def test_complete_engine_capture_inverse():
    old=(BASE/TOP.name).read_text()
    assert hashlib.sha256(old.encode()).hexdigest()=='2711556e640f6fd64995a755af9ba328529b38c498afe87b26ef842c84b35002'
    text,start,end=capture_block();text=text[:start]+text[end:]
    text=undo_forward_receipt(text)
    # New ACK delta has a separate complete top/guard inverse.
    text=text.replace('    .PRIVATE_ACK_RETIREMENT(CERTIFIED_ADMISSION && OWNER==1),\n','',1)
    start=text.index('  end else begin : registered_scheduling\n')
    legacy=text[:start];registered=text[start:]
    registered=registered.replace('        engine_input_reserved <= 0; engine_output_reserved <= 0;',
        '        engine_metadata <= 0; engine_input_reserved <= 0; engine_output_reserved <= 0;',1)
    registered=registered.replace('          WAIT_BANK: if (selected_valid && destination_reserved) begin\n',
        '          WAIT_BANK: if (selected_valid && destination_reserved) begin\n            engine_metadata <= selected_metadata;\n',1)
    assert legacy+registered==old
    for name in (BASE/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split():
        if name not in {TOP.name,'starlink_pss_result_guard_owner_view.v'} and (RTL/name).exists():
            from tests.test_starlink_private_admission_facts import parent_runtime_bytes
            assert parent_runtime_bytes(RTL/name)==(BASE/name).read_bytes(),name


def run(tmp_path,mutant=None):
    text,start,end=capture_block();block=text[start:end]
    variants={
        'capture_active':('state == WAIT_BANK',"1'b1"),
        'miss_transition':('state == WAIT_BANK','state == 4\'d9'),
        'lost_reset':('engine_metadata <= 0;',"engine_metadata <= 70'b1;"),
        'corrupt_capture':('engine_metadata <= selected_metadata;','engine_metadata <= ~selected_metadata;'),
    }
    if mutant:
        before,after=variants[mutant];assert block.count(before)==1
        block=block.replace(before,after,1)
    bench=r'''
`timescale 1ns/1ps
module tb;
 reg fft_clk=0,fast_running=0,registered_quarantine=0,selected_valid=0,destination_reserved=0;
 reg [3:0] state=0;
 localparam WAIT_BANK=4'd2;
 reg [69:0] selected_metadata=0,engine_metadata,original;
 integer f,s,q,v,d,m,checks=0,private_differences=0;
 reg old_accept;
'''+block+r'''
 always @(posedge fft_clk)begin
   if(!fast_running)original<=0;
   else if(registered_quarantine)begin end
   else case(state)WAIT_BANK:if(selected_valid && destination_reserved)original<=selected_metadata;endcase
 end
 function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
 task edge_tick;begin #1;fft_clk=1;#1;fft_clk=0;#1;end endtask
 initial begin
 for(f=0;f<4;f=f+1)for(s=0;s<4;s=s+1)for(q=0;q<4;q=q+1)
 for(v=0;v<4;v=v+1)for(d=0;d<4;d=d+1)for(m=0;m<4;m=m+1)begin
   fast_running=0;edge_tick;
   if(engine_metadata!==70'b0)$fatal(1,"reset lost");
   fast_running=val(f);registered_quarantine=val(q);selected_valid=val(v);destination_reserved=val(d);
   case(s)0:state=WAIT_BANK;1:state=4'd6;2:state=4'bxxxx;3:state=4'bzzzz;endcase
   case(m)0:selected_metadata=70'h123456;1:selected_metadata=70'h3abcde;
     2:selected_metadata=70'bx;3:selected_metadata=70'bz;endcase
   // Literal original if/case semantics, including X controls (not !q && ...).
   old_accept=0;
   if(!fast_running)begin end else if(registered_quarantine)begin end
   else case(state)WAIT_BANK:if(selected_valid && destination_reserved)old_accept=1;endcase
   edge_tick;checks=checks+1;
   if(old_accept && engine_metadata!==original)$fatal(1,"owned descriptor mismatch");
   if(s!=0 && engine_metadata!==original)$fatal(1,"capture outside private wait");
   if(engine_metadata!==original)private_differences=private_differences+1;
   if(old_accept)begin
     // Once accepted, private data must freeze through active processing.
     fast_running=1;state=4'd6;selected_metadata=~selected_metadata;edge_tick;
     if(engine_metadata!==original)$fatal(1,"owned payload changed");
   end
 end
 if(private_differences==0)$fatal(1,"private-only captures unexercised");
 $display("ENGINE_CAPTURE_PASS checks=%0d private_differences=%0d transfer_exact=1 freeze=1",checks,private_differences);
 $finish;
 end
endmodule
'''
    source=tmp_path/'tb.sv';source.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(source)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_four_state_capture_freeze_and_transfer(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'ENGINE_CAPTURE_PASS checks=4096 ' in result.stdout,result.stdout


@pytest.mark.parametrize('mutant',['capture_active','miss_transition','lost_reset','corrupt_capture'])
def test_unsafe_capture_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout
