"""Four-state fault alias proof using pinned real checker/cutover sources."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent/'staged-capture-prepared-v1'
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
PINS={
    'starlink_pss_fft_staged_output_impl.v':'e6fd9bd1a57c4c9b9c9a187d44033174682fd380a1d1c8a7faf2ff479c254666',
    'starlink_pss_realtime_input_guard_local_admission.v':'55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233',
    'starlink_pss_core_job_cutover.v':'eb4316e12bac49c37bd9a2dbf272b32c2b689529187f8e95b8fc34952ddad9aa',
}

def statement(text,name):
    matches=re.findall(r'\b(?:wire|assign)\s+'+name+r'\s*=\s*.*?;',text,re.S)
    assert len(matches)==1,name
    return matches[0]

def reference_sources():
    result={}
    for name,digest in PINS.items():
        data=(BASE/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        result[name]=data.decode()
    return result

def inverse(source,original):
    start='  // Exact guard-facing alias,';end='  wire forward_handoff_ack'
    assert source.count(start)==1 and source.count(end)==1
    restored=source[:source.index(start)]+source[source.index(end):]
    binding='.external_fault_now(guard_external_fault_now)'
    assert restored.count(binding)==1
    restored=restored.replace(binding,'.external_fault_now(external_fault_now)',1)
    assert restored==original,'unrelated top change or wrong guard binding'

def test_complete_top_inverse_and_cutover_parallel_formulas():
    refs=reference_sources();inverse(TOP.read_text(),refs['starlink_pss_fft_staged_output_impl.v'])
    cutover=refs['starlink_pss_core_job_cutover.v']
    names=['known','any_raw','configured_owner','orphan','premature_reset','early_result','fault_now']
    for name in names:
        left=statement(cutover,name);right=statement(cutover,'summary_'+name)
        for n in sorted(names,key=len,reverse=True):right=right.replace('summary_'+n,n)
        right=right.replace('offered_input_beat','input_beat').replace('offered_input_complete','input_complete')
        assert re.sub(r'\s+','',left)==re.sub(r'\s+','',right),name

def aggregate(source):
    declarations='\n'.join(statement(source,n) for n in ['external_fault_now','offered_external_fault_now','guard_external_fault_now'])
    return '''`timescale 1ns/1ps
module aggregate #(parameter INPUT_OFFER_FAULT_SUMMARY=1)(
 input wire input_fault_now,cutover_fault_now,cutover_offered_fault_now,other,
 output wire original,candidate);
 wire input_guard_fault=0,slow_faults_fast=other,vendor_fault_now=0,fast_fault=0,kernel_fault=0;
 wire product_overflow=0,product_bank_fault=0,product_bank_framing_fault_now=0,handoff_fault_now=0,retained_fault_now=0;
 wire [7:0] cutover_reasons=0,retained_reasons=0;
'''+declarations+'''
 assign original=external_fault_now;assign candidate=guard_external_fault_now;
endmodule
'''

BENCH=r'''
`timescale 1ns/1ps
module tb;
function automatic four(input integer x);
begin case(x%4) 0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase end
endfunction
reg resetn=0,enable=0,iv=0,ready=0,job_start=0;
reg sjob=0,sstarted=0,scomplete=0,sfault=0;
reg [8:0] expected=0,position=0;reg last=0;reg [69:0] metadata=70'h1234;
wire transport,beat,complete,input_fault;
wire offer=iv && transport,offer_complete=offer && last;
reg frame=0,raw_output=0,status=0;
wire old_cut,new_cut,original,candidate;
starlink_pss_realtime_input_guard_local_admission #(.CHECK_INPUT_BLOCK_IDENTITY(1),.BALANCED_IDENTITY_EQ(1),.LOCAL_FIRST_ADMISSION(1)) checker_dut(
 .clk(1'b0),.resetn(resetn),.job_start(job_start),.job_descriptor(70'h1234),.input_enable(enable),
 .input_valid(iv),.input_transport_ready(transport),.input_data(36'b0),.input_position(position),
 .input_last(last),.input_metadata(metadata),.core_input_tready(ready),
 .certified_input_beat(beat),.certified_input_complete(complete),.fault_now(input_fault));
starlink_pss_core_job_cutover #(.ENABLE_OFFERED_FAULT_SUMMARY(1)) cutover_dut(
 .clk(1'b0),.resetn(1'b1),.core_resetn(resetn),.job_accept(1'b0),.job_inverse(1'b0),
 .producer_closed(1'b0),.config_accept(1'b0),.input_beat(beat),.input_complete(complete),
 .offered_input_beat(offer),.offered_input_complete(offer_complete),.raw_frame(frame),
 .raw_output(raw_output),.raw_status(status),.raw_vendor_faults(3'b0),.fault_now(old_cut),.offered_fault_now(new_cut));
aggregate a(.input_fault_now(input_fault),.cutover_fault_now(old_cut),.cutover_offered_fault_now(new_cut),.other(1'b0),.*);
reg bf=0,bc=0,bo=0,bother=0;wire b_original,b_candidate,d_original,d_candidate;
aggregate b(.input_fault_now(bf),.cutover_fault_now(bc),.cutover_offered_fault_now(bo),.other(bother),.original(b_original),.candidate(b_candidate));
aggregate #(.INPUT_OFFER_FAULT_SUMMARY(0)) d(.input_fault_now(bf),.cutover_fault_now(bc),.cutover_offered_fault_now(bo),.other(bother),.original(d_original),.candidate(d_candidate));
integer v,s,n,checks=0,zero_cases=0,one_cases=0,unknown_cases=0,masked_differences=0,unknown_fallbacks=0;
initial begin
 for(v=0;v<256;v=v+1) begin
   bf=four(v);bc=four(v/4);bo=four(v/16);bother=four(v/64);#0.001;
   if(d_original!==d_candidate) $fatal(1,"disabled alias changed fault");
   if((bf!==1'b0 || bc===bo) && b_original!==b_candidate) $fatal(1,"scalar four-state absorption/fallback");
 end
 if(`SMALL_ONLY) begin $display("GUARD_FAULT_SCALAR_PASS cases=256");$finish;end
 for(s=0;s<8;s=s+1) begin
   for(v=0;v<65536;v=v+1) begin
     resetn=four(v);enable=four(v/4);iv=four(v/16);ready=four(v/64);
     sjob=four(v/256);sstarted=four(v/1024);scomplete=four(v/4096);sfault=four(v/16384);
     job_start=s==7 ? resetn : 1'b0;
     expected=0;position=0;last=0;metadata=70'h1234;frame=0;raw_output=0;status=0;
     case(s)
       1:begin expected=511;position=511;last=1;status=1;end
       2:begin expected=9;position=8;raw_output=1;end
       3:begin last=1;status=1;end
       4:begin expected=511;position=511;last=1'bx;end
       5:metadata[69]=1'bx;
       6:begin expected=9'bx;frame=1'bx;end
       7:metadata[0]=~metadata[0];
     endcase
     force checker_dut.job_started=sjob;force checker_dut.input_started=sstarted;
     force checker_dut.input_complete=scomplete;force checker_dut.fault_reasons={3{sfault}};
     force checker_dut.expected_position=expected;force checker_dut.descriptor=70'h1234;
     force cutover_dut.owner_open=1'b1;force cutover_dut.configured=1'b1;
     force cutover_dut.reset_flushed=1'b1;force cutover_dut.fresh_frame=1'b1;force cutover_dut.fresh_full=1'b0;
     #0.001;
     if(input_fault===1'b0) begin
       zero_cases=zero_cases+1;
       if({offer,offer_complete}!=={beat,complete} || old_cut!==new_cut)
         $fatal(1,"real checker offer/certificate premise failed s=%0d v=%0d",s,v);
     end else if(input_fault===1'b1) begin
       one_cases=one_cases+1;if(old_cut!==new_cut) masked_differences=masked_differences+1;
     end else begin
       unknown_cases=unknown_cases+1;if(original===1'bx) unknown_fallbacks=unknown_fallbacks+1;
     end
     if(original!==candidate) $fatal(1,"real checker/cutover external fault differed");
     checks=checks+1;
   end
 end
 if(checks!=524288 || zero_cases==0 || one_cases==0 || unknown_cases==0 || masked_differences==0 || unknown_fallbacks==0)
   $fatal(1,"missing fault equivalence coverage");
 $display("GUARD_FAULT_REAL_PASS cases=%0d zero=%0d one=%0d unknown=%0d masked=%0d fallback=%0d",checks,zero_cases,one_cases,unknown_cases,masked_differences,unknown_fallbacks);
 $finish;
end
endmodule
'''

def execute(tmp_path,source,small=False):
    refs=reference_sources();inverse(source,refs['starlink_pss_fft_staged_output_impl.v'])
    for name in ['starlink_pss_realtime_input_guard_local_admission.v','starlink_pss_core_job_cutover.v']:
        (tmp_path/name).write_text(refs[name])
    (tmp_path/'aggregate.v').write_text(aggregate(source))
    (tmp_path/'tb.sv').write_text('`define SMALL_ONLY '+str(int(small))+'\n'+BENCH)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','aggregate.v',
        'starlink_pss_realtime_input_guard_local_admission.v','starlink_pss_core_job_cutover.v','tb.sv'],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp','sim'],cwd=tmp_path,capture_output=True,text=True,timeout=120)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_real_checker_cutover_four_state_equivalence(tmp_path):
    result=execute(tmp_path,TOP.read_text())
    assert result.returncode==0 and 'GUARD_FAULT_REAL_PASS cases=524288 ' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('change',['no_fallback','ignore_disable','drop_fault'])
def test_guard_alias_mutants_rejected(tmp_path,change):
    source=TOP.read_text();before=statement(source,'guard_external_fault_now')
    after={
        'no_fallback':'wire guard_external_fault_now = INPUT_OFFER_FAULT_SUMMARY ? offered_external_fault_now : external_fault_now;',
        'ignore_disable':before.replace('INPUT_OFFER_FAULT_SUMMARY &&',"1'b1 &&"),
        'drop_fault':'wire guard_external_fault_now = 1\'b0;',
    }[change]
    result=execute(tmp_path,source.replace(before,after,1),small=True)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout
