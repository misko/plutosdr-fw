"""Qualified forward receipt, ACK interlock and complete source-delta tests."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest
from tests.test_starlink_product_stage_integration import undo_product_stage

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / 'hdl/library/starlink_pss_acquisition/staged_control'
TOP = RTL / 'starlink_pss_fft_staged_output_impl.v'
BASE = ROOT.parent / 'staged-ackcombined-prepared-v1'


def undo_forward_receipt(text):
    text=undo_product_stage(text)
    start = text.index('  // BEGIN FORWARD COMPLETION RECEIPT\n')
    end = text.index('  // END FORWARD COMPLETION RECEIPT\n', start) + len('  // END FORWARD COMPLETION RECEIPT\n')
    text = text[:start] + text[end:]
    assert text.count('(forward_receipt_wait ? product_bank_valid') == 2
    text = text.replace('(forward_receipt_wait ? product_bank_valid', '(forward_committed ? product_bank_valid')
    old = '        if (return_commit_valid && result_destination_ready && !next_inverse)\n'
    new = ('        if (CERTIFIED_ADMISSION ? (guard_commit[0] && !next_inverse) :\n'
           '            (return_commit_valid && result_destination_ready && !next_inverse))\n')
    assert text.count(new) == 1
    return text.replace(new, old, 1)


def test_entire_runtime_delta_is_receipt_and_ack_interlock():
    assert hashlib.sha256((BASE/'SHA256SUMS').read_bytes()).hexdigest() == 'ecb302eab62a44de27a6b27d4d0414effe487e270498d2adb1ec83f79d01a38a'
    assert undo_forward_receipt(TOP.read_text()) == (BASE/TOP.name).read_text()
    names = (BASE/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    for name in names:
        if name != TOP.name and (RTL/name).exists():
            assert (RTL/name).read_bytes() == (BASE/name).read_bytes(), name
    guard = (RTL/'starlink_pss_result_guard_owner_view.v').read_text()
    assert 'commit_pulse <= final_commit;' in guard
    assert 'wire final_commit = mailbox_commit_valid && mailbox_input_ready;' in guard


def run(tmp_path, mutant=None):
    top = TOP.read_text()
    wait = re.search(r'  wire forward_receipt_wait = .*?;', top).group()
    start = top.index('        if (CERTIFIED_ADMISSION ? (guard_commit[0]')
    stop = top.index('          forward_committed <= 1;', start) + len('          forward_committed <= 1;')
    update = top[start:stop]
    if mutant == 'early_ack': wait = wait.replace(' || (CERTIFIED_ADMISSION && guard_commit[0])', '')
    elif mutant == 'raw_last': update = update.replace('guard_commit[0]', 'raw_last')
    elif mutant == 'lost_receipt': update = update.replace('guard_commit[0]', "1'b0")
    elif mutant == 'lost_fallback': update = update.replace('CERTIFIED_ADMISSION ?', "1'b1 ?")
    source = r'''`timescale 1ns/1ps
module tb;
reg clk=0,fast_running=0,CERTIFIED_ADMISSION=1,next_inverse=0;
reg return_commit_valid=0,result_destination_ready=0,admit=0;
reg product_bank_valid=0,kernel_ready=1,product_bank_ready=1;
reg raw_last=0,current_fault=0,sticky_fault=0;
reg [1:0] guard_commit=0;
reg forward_committed=0,original=0;
integer mode,n,checks=0,pending=0;
''' + wait + r'''
wire actual_ready=forward_receipt_wait ? product_bank_valid : kernel_ready && product_bank_ready;
wire old_ready=original ? product_bank_valid : kernel_ready && product_bank_ready;
wire publish=forward_committed && !current_fault && !sticky_fault;
always @(posedge clk) begin
  if(!fast_running) begin forward_committed<=0; original<=0;guard_commit<=0;end
  else begin
    guard_commit[0]<=return_commit_valid && result_destination_ready && !next_inverse;
    if(return_commit_valid && result_destination_ready && !next_inverse)original<=1;
''' + update + r'''
    if(admit)begin original<=0;forward_committed<=0;end
  end
end
task tick;begin #1;clk=1;#1;clk=0;#1;
 if(fast_running)begin
   checks=checks+1;
   if(forward_receipt_wait!==original || actual_ready!==old_ready)$fatal(1,"ACK wait changed");
   if(publish && (!original || current_fault || sticky_fault))$fatal(1,"unauthorized publication");
   if(forward_committed!==original)begin
     if(!CERTIFIED_ADMISSION || forward_committed!==0 || original!==1 || guard_commit[0]!==1)
       $fatal(1,"unqualified completion difference");
     pending=pending+1;
   end
 end
end endtask
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
initial begin
 for(mode=0;mode<2;mode=mode+1)for(n=0;n<32;n=n+1)begin
   CERTIFIED_ADMISSION=mode;fast_running=0;admit=0;tick;fast_running=1;
   // Malformed/unqualified LAST must never be receipt authority.
   return_commit_valid=0;result_destination_ready=1;raw_last=1;
   product_bank_valid=0;current_fault=0;sticky_fault=0;tick;
   raw_last=0;
   // Known qualified completion, followed by known/X/Z downstream readiness.
   return_commit_valid=n&1;result_destination_ready=1;
   tick;return_commit_valid=0;
   current_fault=(n>>1)&1;sticky_fault=current_fault;tick;
   product_bank_valid=val((n>>2)&3);tick;
   current_fault=0;tick;product_bank_valid=1;tick;
   admit=1;tick;admit=0;tick;
   fast_running=0;tick;
 end
 if(pending!=16)$fatal(1,"pending coverage count %0d",pending);
 $display("FORWARD_RECEIPT_TRANSITIONS_PASS checks=%0d pending=%0d ack_exact=1 publication_subset=1",checks,pending);$finish;
end
endmodule
'''
    path=tmp_path/'tb.sv';path.write_text(source)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_receipt_transition_and_actual_ack_wait(tmp_path):
    result=run(tmp_path)
    assert result.returncode == 0 and 'FORWARD_RECEIPT_TRANSITIONS_PASS' in result.stdout,result.stdout+result.stderr


@pytest.mark.parametrize('mutant',['early_ack','raw_last','lost_receipt','lost_fallback'])
def test_unsafe_receipt_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode != 0 and 'FATAL' in result.stdout,result.stdout+result.stderr
