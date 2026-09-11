"""Exact source inverse and four-state authorization under the phase contract."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
BASE=ROOT.parent/'staged-preflightpublication-prepared-v1'/TOP.name

def block():
    text=TOP.read_text();start=text.index('  // BEGIN PUBLICATION FAULT SCOPE\n')
    end=text.index('  // END PUBLICATION FAULT SCOPE\n')+len('  // END PUBLICATION FAULT SCOPE\n')
    return text,start,end

def test_only_publication_authorization_changes():
    old=BASE.read_bytes()
    assert hashlib.sha256(old).hexdigest()=='b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143'
    text,start,end=block()
    original='  wire output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready && !common_current_fault;\n'
    assert text[:start]+original+text[end:]==old.decode()

def test_v2_changes_only_contradictory_test_injections():
    first=ROOT.parent/'staged-publicationscope-prepared-v1'
    second=ROOT.parent/'staged-publicationscope-prepared-v2'
    names=(second/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==17
    for name in names:assert (first/name).read_bytes()==(second/name).read_bytes(),name
    old=(first/'tb_fft_staged_output.sv').read_text()
    new=(second/'tb_fft_staged_output.sv').read_text()
    new=new.replace('        // Drive sources shared by scalar and expanded validation views.\n        // Forcing only a reduced aggregate would violate their contract.\n','',1)
    new=new.replace("        0: force dut.event_last_missing=1'b1;", "        0: force dut.offered_external_fault_now=1'b1;",1)
    new=new.replace("        1: force dut.owners[0].result_guard.summary_faults_now=8'h01;", "        1: force dut.guard_offered_local_fault[0]=1'b1;",1)
    new=new.replace("        2: force dut.owners[1].result_guard.summary_faults_now=8'h01;", "        2: force dut.guard_offered_local_fault[1]=1'b1;",1)
    new=new.replace('      release dut.event_last_missing;\n      release dut.owners[0].result_guard.summary_faults_now;release dut.owners[1].result_guard.summary_faults_now;',
                    '      release dut.offered_external_fault_now;\n      release dut.guard_offered_local_fault[0];release dut.guard_offered_local_fault[1];',1)
    assert new==old,'all consistency assertions and other cases remain literal'

def run(tmp_path,mutant=None):
    text,start,end=block();declarations=text[start:end]
    if mutant=='drop_external':declarations=declarations.replace('= offered_external_fault_now ||',"= 1'b0 ||",1)
    elif mutant=='drop_sticky':declarations=declarations.replace('|| result_fault;',"|| 1'b0;",1)
    elif mutant=='drop_unknown':declarations=declarations.replace('&& publication_replay_known ?',"&& 1'b1 ?",1)
    elif mutant=='drop_default':declarations=declarations.replace('CERTIFIED_ADMISSION && publication_replay_known ?',"1'b1 && publication_replay_known ?",1)
    bench=r'''
`timescale 1ns/1ps
module tb;
 reg CERTIFIED_ADMISSION,output_replay_valid,output_descriptor_valid,output_bank_ready;
 reg [5:0] remaining;
 reg preflight_fault;
 wire offered_external_fault_now=remaining[0];
 wire [1:0] guard_offered_local_fault=remaining[2:1];
 wire output_bank_fault=remaining[3],output_bank_framing_fault_now=remaining[4],result_fault=remaining[5];
 wire common_current_fault=(|remaining) || preflight_fault;
'''+declarations+r'''
 wire original=output_replay_valid && output_descriptor_valid && output_bank_ready && !common_current_fault;
 function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
 function [5:0] quad(input integer n);integer b;begin for(b=0;b<6;b=b+1)quad[b]=val((n>>(2*b))&3);end endfunction
 integer mode,n,p,r,d,b,cases=0;
 initial begin
 for(mode=0;mode<2;mode=mode+1)for(n=0;n<4096;n=n+1)
  for(p=0;p<4;p=p+1)for(r=0;r<4;r=r+1)for(d=0;d<4;d=d+1)for(b=0;b<4;b=b+1)
   // Certified live replay requires preflight known zero. Idle and unknown
   // replay and default mode remain exhaustively compared without that premise.
   if(!(mode==1 && r==1 && p!=0))begin
    CERTIFIED_ADMISSION=mode;remaining=quad(n);preflight_fault=val(p);
    output_replay_valid=val(r);output_descriptor_valid=val(d);output_bank_ready=val(b);#1;
    if(output_replay_accept!==original)$fatal(1,"publication authorization mismatch");
    cases=cases+1;
   end
 $display("PUBLICATION_SCOPE_PASS cases=%0d current_veto_exact=1 unknown_default_exact=1",cases);$finish;
 end
endmodule
'''
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_four_state_publication_and_fallbacks(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'PUBLICATION_SCOPE_PASS cases=1900544 ' in result.stdout,result.stdout

@pytest.mark.parametrize('mutant',['drop_external','drop_sticky','drop_unknown','drop_default'])
def test_unsafe_publication_mutants_fail(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout
