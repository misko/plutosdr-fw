"""Limited source inverse and four-state private observation selection."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BASE=ROOT.parent/'staged-privateack-prepared-v1'
GUARD='starlink_pss_result_guard_owner_view.v';TOP='starlink_pss_fft_staged_output_impl.v'

def test_complete_input_observation_inverse():
    for name,pin in [(TOP,'0b9c0df873e15c0d85af87cd71a51f28d1740649c41d91c0c135bf53b55ef0e4'),
                     (GUARD,'f61335a983f7757ea15a97619eb33fb972945da09e72cadc45ba31c3f1838b0f')]:
        old=(BASE/name).read_bytes();assert hashlib.sha256(old).hexdigest()==pin
        text=(RTL/name).read_text()
        if name==TOP:
            text=text.replace('    .PRIVATE_INPUT_OBSERVATIONS(CERTIFIED_ADMISSION && OWNER==1),\n','',1)
            text=text.replace('    .private_input_fault_now(input_fault_now),\n','',1)
            text=text.replace('  // Offered events never drive delivery. An opted-in inverse guard may observe\n'
                              '  // them privately; current input faults quarantine any uncertified difference.\n',
                              '  // Offered events are summary-only. They NEVER drive delivery or counters.\n',1)
        else:
            text=text.replace('  parameter integer PRIVATE_INPUT_OBSERVATIONS = 0,\n','',1)
            text=text.replace('  input wire private_input_fault_now,\n','',1)
            start=text.index('  // BEGIN PRIVATE INPUT OBSERVATIONS\n')
            end=text.index('  // END PRIVATE INPUT OBSERVATIONS\n',start)+len('  // END PRIVATE INPUT OBSERVATIONS\n')
            text=text[:start]+text[end:]
            text=text.replace('if (observed_input_beat) input_count','if (certified_input_beat) input_count',1)
            text=text.replace('if (observed_input_complete) input_complete_seen','if (certified_input_complete) input_complete_seen',1)
        assert text==old.decode(),'unrelated runtime change: '+name

def simulate(tmp_path,bench,sources=()):
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),*map(str,sources),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def selection(tmp_path,mutant=None):
    source=(RTL/GUARD).read_text();decl=[]
    for name in ['private_input_known','observed_input_beat','observed_input_complete']:
        found=re.findall(r'  wire '+name+r' = .*?;',source,re.S);assert len(found)==1;decl.append(found[0])
    text='\n'.join(decl)
    mutations={
        'unknown_offer':('PRIVATE_INPUT_OBSERVATIONS && private_input_known','PRIVATE_INPUT_OBSERVATIONS'),
        'drop_fallback':('PRIVATE_INPUT_OBSERVATIONS && private_input_known','private_input_known'),
        'certified_only':('PRIVATE_INPUT_OBSERVATIONS && private_input_known',"1'b0"),
        'wrong_complete':('offered_input_complete : certified_input_complete','offered_input_beat : certified_input_complete'),
    }
    if mutant:
        before,after=mutations[mutant];assert before in text;text=text.replace(before,after)
    bench=r'''`timescale 1ns/1ps
module tb;
reg PRIVATE_INPUT_OBSERVATIONS,private_input_fault_now;
reg offered_input_beat,offered_input_complete,certified_input_beat,certified_input_complete;
'''+text+r'''
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer m,f,b,c,d,e,cases=0;reg [1:0] wanted;
initial begin
 for(m=0;m<2;m=m+1)for(f=0;f<4;f=f+1)for(b=0;b<4;b=b+1)for(c=0;c<4;c=c+1)
 for(d=0;d<4;d=d+1)for(e=0;e<4;e=e+1)begin
   PRIVATE_INPUT_OBSERVATIONS=m;private_input_fault_now=val(f);
   offered_input_beat=val(b);offered_input_complete=val(c);certified_input_beat=val(d);certified_input_complete=val(e);#1;
   wanted=(m && f<2) ? {offered_input_beat,offered_input_complete} : {certified_input_beat,certified_input_complete};
   if({observed_input_beat,observed_input_complete}!==wanted)$fatal(1,"private input selection/fallback");
   cases=cases+1;
 end
 $display("PRIVATE_INPUT_SELECTION_PASS cases=%0d unknown_exact=1 fallback_exact=1",cases);$finish;
end
endmodule
'''
    return simulate(tmp_path,bench)

def test_four_state_private_input_selection(tmp_path):
    result=selection(tmp_path)
    assert result.returncode==0 and 'PRIVATE_INPUT_SELECTION_PASS cases=2048 unknown_exact=1 fallback_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['unknown_offer','drop_fallback','certified_only','wrong_complete'])
def test_wrong_private_input_selection_rejected(tmp_path,mutant):
    result=selection(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

def checker_premise(tmp_path,mutant=None):
    path=BASE/'starlink_pss_realtime_input_guard_local_admission.v'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233'
    beat='input_valid && input_transport_ready' if mutant!='ignore_eligibility' else 'input_valid && core_input_tready'
    complete='offer && input_last' if mutant!='wrong_completion' else 'offer && !input_last'
    bench=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,job_start=0,input_enable=0,input_valid=0,input_last=0,core_input_tready=0;
reg [69:0] job_descriptor=70'h123456789abcdef,input_metadata=0;
reg [35:0] input_data=0;reg [8:0] input_position=0;
wire input_transport_ready,certified_input_beat,certified_input_complete,fault_now;
starlink_pss_realtime_input_guard_local_admission #(.CHECK_INPUT_BLOCK_IDENTITY(1),
 .BALANCED_IDENTITY_EQ(1),.LOCAL_FIRST_ADMISSION(1)) dut (
 .clk(clk),.resetn(resetn),.job_start(job_start),.job_descriptor(job_descriptor),
 .input_enable(input_enable),.input_valid(input_valid),.input_ready(),.input_transport_ready(input_transport_ready),
 .input_data(input_data),.input_position(input_position),.input_last(input_last),.input_metadata(input_metadata),
 .core_input_tdata(),.core_input_tvalid(),.core_input_tready(core_input_tready),.core_input_tlast(),
 .certified_input_beat(certified_input_beat),.certified_input_complete(certified_input_complete),
 .input_complete(),.fault_now(fault_now),.duplicate_start_fault_now(),.fault_events_now(),.protocol_fault(),.fault_reasons());
wire offer='''+beat+';\nwire complete='+complete+r''';
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer mode,p,n,cases=0,qualified=0;reg [8:0] position;
initial begin
 #1;resetn=1;
 for(mode=0;mode<4;mode=mode+1)for(p=0;p<3;p=p+1)for(n=0;n<16384;n=n+1)begin
   position=p==0 ? 0 : p==1 ? 32 : 511;
   dut.job_started=(mode!=0);dut.input_started=(mode==2);dut.input_complete=(mode==3);
   dut.fault_reasons=0;dut.descriptor=job_descriptor;dut.expected_position=position;
   input_valid=val(n&3);input_enable=val((n>>2)&3);core_input_tready=val((n>>4)&3);
   input_last=val((n>>6)&3);job_start=val((n>>12)&3);
   case((n>>8)&3)0:input_metadata=job_descriptor;1:input_metadata=job_descriptor^70'd1;
      2:input_metadata={70{1'bx}};3:input_metadata={70{1'bz}};endcase
   case((n>>10)&3)0:input_position=position;1:input_position=position^9'd1;
      2:input_position={9{1'bx}};3:input_position={9{1'bz}};endcase
   #1;
   if(fault_now===1'b0)begin
     if({offer,complete}!=={certified_input_beat,certified_input_complete})
       $fatal(1,"known-good checker offer differs from certificate");
     qualified=qualified+1;
   end
   cases=cases+1;
 end
 if(qualified<1000)$fatal(1,"checker premise coverage missing");
 $display("PRIVATE_INPUT_CHECKER_PASS cases=%0d known_good=%0d four_state_exact=1",cases,qualified);$finish;
end
endmodule
'''
    return simulate(tmp_path,bench,[path])

def test_real_checker_offer_premise(tmp_path):
    result=checker_premise(tmp_path)
    assert result.returncode==0 and 'PRIVATE_INPUT_CHECKER_PASS cases=196608 ' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['ignore_eligibility','wrong_completion'])
def test_wrong_checker_offer_rejected(tmp_path,mutant):
    result=checker_premise(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
