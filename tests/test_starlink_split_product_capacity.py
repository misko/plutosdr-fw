"""Split physical capacity without changing the legal caller's handshakes."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-final-capacity.vMIiHM/prepared-v1')
OLD='starlink_pss_product_identity_stage.v'
NEW='starlink_pss_product_identity_split_capacity.v'
COMMENT=('  // Physical nonfinal capacity, derived from actual destination ownership.\n'
         '  // Caller contract: for a live nonfinal word it equals output_ready.\n'
         '  // Final publication permission MUST NOT feed this input.\n'
         '  input wire refill_capacity,\n')


def undo_split_top(text):
    old='starlink_pss_product_identity_split_capacity product_identity_stage ('
    new='starlink_pss_product_identity_stage product_identity_stage ('
    assert text.count(old)==1;text=text.replace(old,new,1)
    line="    .refill_capacity((product_bank_ready === 1'b1) && (fast_fault === 1'b0)),\n"
    assert text.count(line)==1
    return text.replace(line,'',1)


def test_exact_runtime_delta_and_physical_separation():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='408204bad0b135494839b37ce242f2cc720e9e918e293aaedcdc0d6a0105a0f6'
    assert (RTL/OLD).read_bytes()==(PARENT/OLD).read_bytes()
    text=(RTL/NEW).read_text()
    assert text.count(COMMENT)==1
    text=text.replace(COMMENT,'',1).replace('module starlink_pss_product_identity_split_capacity (',
                                          'module starlink_pss_product_identity_stage (',1)
    text=text.replace("((output_last === 1'b0) && refill_capacity)","((output_last === 1'b0) && output_ready)",1)
    assert text==(PARENT/OLD).read_text()
    for name in (PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split():
        if (RTL/name).exists():
            text=(RTL/name).read_text()
            if name=='starlink_pss_fft_staged_output_impl.v':text=undo_split_top(text)
            assert text==(PARENT/name).read_text(),name
    # Capacity explicitly follows real bank readiness, not a delayed credit or
    # publication decision. The snapshot inventory replaces, not adds, a stage.
    helper=(ROOT/'tools/staged_fft_experiment.py').read_text()
    assert "'starlink_pss_product_identity_split_capacity.v','starlink_pss_product_mailbox_staged_identity.v'" in helper


def run(tmp_path,mutant=None):
    source=(RTL/NEW).read_text()
    if mutant=='allow_final_refill':source=source.replace("((output_last === 1'b0) && refill_capacity)",'refill_capacity',1)
    elif mutant=='drop_blocked_last':source=source.replace('wire take_output = output_valid && output_ready;',
                                                         'wire take_output = output_valid && refill_capacity;',1)
    elif mutant=='ignore_bank_capacity':source=source.replace("((output_last === 1'b0) && refill_capacity)","(output_last === 1'b0)",1)
    elif mutant=='ignore_abort':source=source.replace("(abort_epoch !== 1'b0)","1'b0",1)
    bench=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,raw_ready=1,fast_fault=0,ram_fault=0,authorized=0;
reg input_valid=0,input_last=0;
reg [35:0] input_data=0;
reg [8:0] input_position=0;
reg [69:0] input_metadata=123,reference_metadata=123;
wire abort_epoch=fast_fault || ram_fault || (raw_ready!==0 && raw_ready!==1);
wire refill_capacity=(raw_ready===1) && (fast_fault===0);
wire old_ready,new_ready,old_valid,new_valid,old_last,new_last,old_identity,new_identity,old_idle,new_idle,old_fault,new_fault;
wire [35:0] old_data,new_data;wire [8:0] old_position,new_position;wire [69:0] old_metadata,new_metadata;
wire old_retire=refill_capacity && ((old_last===0)||(authorized===1));
wire new_retire=refill_capacity && ((new_last===0)||(authorized===1));
starlink_pss_product_identity_stage original(.clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),
 .input_valid(input_valid),.input_ready(old_ready),.input_data(input_data),.input_position(input_position),
 .input_last(input_last),.input_metadata(input_metadata),.reference_metadata(reference_metadata),
 .output_valid(old_valid),.output_ready(old_retire),.output_data(old_data),.output_position(old_position),
 .output_last(old_last),.output_identity_good(old_identity),.output_metadata(old_metadata),.idle(old_idle),.fault(old_fault));
starlink_pss_product_identity_split_capacity candidate(.clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),
 .input_valid(input_valid),.input_ready(new_ready),.input_data(input_data),.input_position(input_position),
 .input_last(input_last),.input_metadata(input_metadata),.reference_metadata(reference_metadata),
 .refill_capacity(refill_capacity),.output_valid(new_valid),.output_ready(new_retire),.output_data(new_data),.output_position(new_position),
 .output_last(new_last),.output_identity_good(new_identity),.output_metadata(new_metadata),.idle(new_idle),.fault(new_fault));
integer checks=0,n,c;
task check;begin
 if({old_ready,old_valid,old_data,old_position,old_last,old_identity,old_metadata,old_idle,old_fault} !==
    {new_ready,new_valid,new_data,new_position,new_last,new_identity,new_metadata,new_idle,new_fault})
   $fatal(1,"split contract differs from original at check %0d",checks);
 checks=checks+1;
end endtask
task tick;begin #1;check;clk=1;#1;check;clk=0;#1;end endtask
task restart;begin resetn=0;tick;resetn=1;raw_ready=1;fast_fault=0;ram_fault=0;authorized=0;input_valid=1;input_last=0;end endtask
initial begin
 // Continuous nonfinal refill, then held final while a future offer is queued.
 restart;
 for(n=0;n<512;n=n+1)begin input_data=n;input_position=n;input_last=(n==511);tick;end
 input_last=0;input_position=0;input_data=999;
 repeat(16)tick;
 authorized=1;tick;tick;input_valid=0;tick;
 // Capacity loss while a nonfinal word is held must stall, not overwrite it.
 restart;tick;raw_ready=0;input_data=1001;repeat(8)tick;raw_ready=1;tick;
 // Every capacity/authorization four-state pair, sampled with held nonfinal
 // and final words. Actual caller converts unknown readiness into quarantine.
 for(c=0;c<32;c=c+1)begin
  restart;input_last=c[4];tick;input_last=0;input_data=c+2000;
  case(c[1:0])0:raw_ready=0;1:raw_ready=1;2:raw_ready=1'bx;3:raw_ready=1'bz;endcase
  case(c[3:2])0:authorized=0;1:authorized=1;2:authorized=1'bx;3:authorized=1'bz;endcase
  tick;tick;
 end
 restart;tick;ram_fault=1;tick;ram_fault=0;tick;
 restart;input_last=1;tick;fast_fault=1;tick;fast_fault=0;tick;
 restart;tick;input_valid=1'bx;tick;input_valid=0;tick;
 restart;input_last=1;tick;resetn=0;tick;resetn=1;input_valid=0;tick;
 if(checks<1200)$fatal(1,"short equivalence campaign");
 $display("SPLIT_CAPACITY_EQUIVALENCE_PASS checks=%0d unknowns=1 stalls=1 held_last=1 resets=1 faults=1",checks);$finish;
end
endmodule
'''
    files=[]
    for name,text in [('old.v',(RTL/OLD).read_text()),('new.v',source),('tb.sv',bench)]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_real_caller_equivalence_with_unknowns_and_recovery(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'SPLIT_CAPACITY_EQUIVALENCE_PASS' in result.stdout,result.stdout+result.stderr


@pytest.mark.parametrize('mutant',['allow_final_refill','drop_blocked_last','ignore_bank_capacity','ignore_abort'])
def test_unsafe_split_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
