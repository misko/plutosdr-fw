"""Exact opt-in RTL delta, fail-closed profiles and publication truth table."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-replay-quiet.C5YGuYRF/prepared-v2')
TOP='starlink_pss_fft_staged_output_impl.v'

def undo_top(text):
    for label in ['REPLAY FENCE CONFIGURATION','REPLAY QUIET PUBLICATION FENCE']:
        replacement='' if label=='REPLAY FENCE CONFIGURATION' else '  wire output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready && !common_current_fault;\n'
        text,count=re.subn(r' *// BEGIN '+label+r'\n.*? *// END '+label+r'\n',lambda _:replacement,text,flags=re.S)
        assert count==1
    for before,after in [
      ('  parameter integer CONTEXTUAL_DESTINATION_SUMMARY = 0,\n  parameter integer REPLAY_QUIET_PUBLICATION = 0','  parameter integer CONTEXTUAL_DESTINATION_SUMMARY = 0'),
      ('  wire [1:0] guard_active;\n',''),('.owner_active(guard_active[OWNER])','.owner_active()')]:
        assert text.count(before)==1;text=text.replace(before,after,1)
    return text

def undo_bench(text):
    text,count=re.subn(r' *// BEGIN INTEGRATED REPLAY FENCE WITNESS\n.*? *// END INTEGRATED REPLAY FENCE WITNESS\n','',text,flags=re.S)
    assert count==1
    line='      $display("STAGED_REPLAY_FENCE_PASS enabled=1 profile=1 independent_shadow=1 current_publication_exact=1"); // INTEGRATED REPLAY FENCE REPORT\n'
    assert text.count(line)==1;text=text.replace(line,'',1)
    before='.CONTEXTUAL_DESTINATION_SUMMARY(1),.REPLAY_QUIET_PUBLICATION(1)) dut(.*);'
    assert text.count(before)==1;text=text.replace(before,'.CONTEXTUAL_DESTINATION_SUMMARY(1)) dut(.*);',1)
    assert text.count('current_exact=1 runtime_unchanged=0')==1
    return text.replace('current_exact=1 runtime_unchanged=0','current_exact=1 runtime_unchanged=1',1)

def test_exact_runtime_bench_and_synthesis_profile_delta():
    assert undo_top((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    name='tb_fft_staged_output.sv';assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name!=TOP and (RTL/name).exists():assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name
    tcl=(ROOT/'tools/staged_fft_experiment.tcl').read_text()
    assert tcl.count(' REPLAY_QUIET_PUBLICATION=1')==1
    assert tcl.replace(' REPLAY_QUIET_PUBLICATION=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()

def run(tmp_path,mode='1',profile=31,mutation=None):
    text=(RTL/TOP).read_text()
    block=re.search(r'  // BEGIN REPLAY QUIET PUBLICATION FENCE\n.*?  // END REPLAY QUIET PUBLICATION FENCE\n',text,re.S)[0]
    mutations={
      'drop_status':('core_status_valid || core_output_valid',"1'b0 || core_output_valid"),
      'ignore_owner':('!guard_active[0] && !guard_active[1]',"1'b1"),
      'omit_external':('offered_external_fault_now || result_fault',"1'b0 || result_fault"),
      'wrong_profile':('REPLAY_QUIET_PUBLICATION === 1 && REPLAY_FENCE_PROFILE','REPLAY_QUIET_PUBLICATION === 1')}
    if mutation:
        before,after=mutations[mutation];assert block.count(before)==1;block=block.replace(before,after,1)
    bench='''`timescale 1ns/1ps
module tb;
parameter integer MODE=1,PROFILE=31;
localparam integer REPLAY_QUIET_PUBLICATION=MODE;
localparam integer REGISTERED_SCHEDULING=(PROFILE>>0)&1,INPUT_OFFER_FAULT_SUMMARY=(PROFILE>>1)&1;
localparam integer CONTEXTUAL_DESTINATION_SUMMARY=(PROFILE>>2)&1,PRIVATE_DESCRIPTOR_OFFER=(PROFILE>>3)&1,CLOSED_INPUT_CUTOVER=(PROFILE>>4)&1;
localparam [3:0] ACK_DRAIN=7;
reg [3:0] state;reg next_inverse,routed_inverse,preparing;
reg [1:0] guard_active;
reg offered_external_fault_now,result_fault,output_bank_fault,output_bank_framing_fault_now,preparation_fault_now;
reg core_status_valid,core_output_valid,event_frame,summary_offer_beat,summary_offer_complete;
reg output_replay_valid,output_descriptor_valid,output_bank_ready,common_current_fault;
__BLOCK__
wire base=output_replay_valid && output_descriptor_valid && output_bank_ready;
wire expected=(MODE===0) ? base && !common_current_fault :
 ((MODE===1 && PROFILE==31) ? base && state==7 && next_inverse && routed_inverse &&
  !preparing && guard_active==0 && !offered_external_fault_now && !result_fault &&
  !output_bank_fault && !output_bank_framing_fault_now && !preparation_fault_now &&
  !core_status_valid && !core_output_valid && !event_frame && !summary_offer_beat && !summary_offer_complete : 1'b0);
integer n,k,checks=0;reg [31:0] rng=32'had024783;
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
task seed;begin
 state=7;next_inverse=1;routed_inverse=1;preparing=0;guard_active=0;
 offered_external_fault_now=0;result_fault=0;output_bank_fault=0;output_bank_framing_fault_now=0;preparation_fault_now=0;
 core_status_valid=0;core_output_valid=0;event_frame=0;summary_offer_beat=0;summary_offer_complete=0;
 output_replay_valid=1;output_descriptor_valid=1;output_bank_ready=1;common_current_fault=0;
end endtask
task check;begin #0.001;if(output_replay_accept!==expected)$fatal(1,"publication fence mismatch");checks=checks+1;end endtask
initial begin
 seed;check;
 // Each context, capacity and current-fault input independently vetoes.
 for(n=0;n<16;n=n+1)for(k=0;k<4;k=k+1)begin
  seed;
  case(n)
   0:guard_active[0]=val(k);1:guard_active[1]=val(k);
   2:core_status_valid=val(k);3:core_output_valid=val(k);4:event_frame=val(k);
   5:summary_offer_beat=val(k);6:summary_offer_complete=val(k);7:offered_external_fault_now=val(k);
   8:result_fault=val(k);9:output_bank_fault=val(k);10:output_bank_framing_fault_now=val(k);
   11:preparation_fault_now=val(k);12:output_replay_valid=val(k);13:output_descriptor_valid=val(k);
   14:output_bank_ready=val(k);15:common_current_fault=val(k);
  endcase
  check;
 end
 for(n=0;n<16;n=n+1)begin seed;state=n;check;end
 for(n=0;n<4096;n=n+1)begin
  seed;rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  {state,next_inverse,routed_inverse,preparing,guard_active,offered_external_fault_now,result_fault,
   output_bank_fault,output_bank_framing_fault_now,preparation_fault_now,core_status_valid,core_output_valid,
   event_frame,summary_offer_beat,summary_offer_complete,output_replay_valid,output_descriptor_valid,
   output_bank_ready,common_current_fault}=rng;
  check;
 end
 $display("REPLAY_FENCE_COMPONENT_PASS checks=%0d mode=%0d profile=%0d",checks,MODE,PROFILE);$finish;
end
endmodule
'''.replace('__BLOCK__',block)
    path=tmp_path/'tb.sv';path.write_text(bench)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.MODE={mode}',f'-Ptb.PROFILE={profile}','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr);assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('mode,profile',[('0',0),('0',31)]+[('1',n) for n in range(32)]+[('2',31),("32'bx",31),("32'bz",31)])
def test_default_opt_in_and_invalid_profiles(tmp_path,mode,profile):
    result=run(tmp_path,mode,profile)
    assert result.returncode==0 and 'REPLAY_FENCE_COMPONENT_PASS checks=4177' in result.stdout,result.stdout

@pytest.mark.parametrize('mutation',['drop_status','ignore_owner','omit_external','wrong_profile'])
def test_unsafe_fences_rejected(tmp_path,mutation):
    result=run(tmp_path,profile=0 if mutation=='wrong_profile' else 31,mutation=mutation)
    assert result.returncode!=0 and 'publication fence mismatch' in result.stdout,result.stdout
