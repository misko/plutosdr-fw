"""Shadow-only replay ownership contract; no change to publication authority."""
import hashlib
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-private-admission.jU5bmytc/prepared-v1')

def undo_bench(text):
    if '// BEGIN INTEGRATED REPLAY FENCE WITNESS' in text:
        from tests.test_starlink_replay_quiet_fence import undo_bench as undo_fence
        text=undo_fence(text)
    for label in ['WITNESS','BOUNDARIES','AUXILIARY']:
        text,count=re.subn(r' *// BEGIN REPLAY QUIET '+label+r'\n.*? *// END REPLAY QUIET '+label+r'\n','',text,flags=re.S)
        assert count==1
    for spaces,mode in [(6,'AUXILIARY'),(4,'MAIN')]:
        line=' '*spaces+'report_replay_quiet; // REPLAY QUIET '+mode+'\n'
        assert text.count(line)==1;text=text.replace(line,'',1)
    return text

def test_runtime_byte_identical_and_exact_additive_bench():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203'
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if (RTL/name).exists():
            text=(RTL/name).read_text()
            if name=='starlink_pss_fft_staged_output_impl.v' and '// BEGIN REPLAY QUIET PUBLICATION FENCE' in text:
                from tests.test_starlink_replay_quiet_fence import undo_top
                text=undo_top(text)
            assert text==(PARENT/name).read_text(),name
    name='tb_fft_staged_output.sv'
    assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()
    top=(RTL/'starlink_pss_fft_staged_output_impl.v').read_text()
    if '// BEGIN REPLAY QUIET PUBLICATION FENCE' in top:
        from tests.test_starlink_replay_quiet_fence import undo_top
        top=undo_top(top)
    original=re.search(r'wire output_replay_accept = ([^;]+);',top)[1]
    shadow=re.search(r'wire replay_original_predicate = ([^;]+);',(RTL/name).read_text())[1]
    assert re.sub(r'\s+','',shadow.replace('dut.',''))==re.sub(r'\s+','',original)

def run(tmp_path,seed=1,mutation=None):
    guard=(RTL/'starlink_pss_result_guard_owner_view.v').read_text()
    begin=guard.index('  wire summary_effective_input_full =')
    end=guard.index('  assign offered_local_fault_now',begin)
    expression='mailbox_input_fault || offered_input_beat || offered_input_complete || core_event_frame_started || core_status_tvalid || core_output_tvalid'
    if mutation in ['drop_status','drop_output','drop_mailbox']:
        field={'drop_status':'core_status_tvalid','drop_output':'core_output_tvalid','drop_mailbox':'mailbox_input_fault'}[mutation]
        expression=expression.replace(field,"1'b0",1)
    active=1 if mutation=='assume_active_safe' else 0
    bench='''`timescale 1ns/1ps
module tb;
parameter integer SEED=1;
localparam integer WATCHDOG_CYCLES=256;
reg active=__ACTIVE__;
reg output_bank_reserved,input_complete_seen,input_bank_reserved;
reg [9:0] input_count,output_count;
reg offered_input_beat,offered_input_complete,frame_seen,core_event_frame_started;
reg core_status_tvalid,status_seen,exponent_seen;
reg [7:0] core_status_tdata,age;
reg [4:0] output_exponent,status_exponent;
reg core_output_tvalid,core_output_tlast,return_valid,return_last,mailbox_input_ready,mailbox_input_fault;
reg [23:0] core_output_tuser;
__GUARD__
wire reduced_fault=__EXPRESSION__;
integer n,j,rng,checks=0;
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
task vary_payload;begin
 input_count=$random(rng);output_count=$random(rng);core_status_tdata=$random(rng);
 core_output_tuser=$random(rng);output_exponent=$random(rng);status_exponent=$random(rng);
 output_bank_reserved=$random(rng);input_bank_reserved=$random(rng);input_complete_seen=$random(rng);
 frame_seen=$random(rng);status_seen=$random(rng);exponent_seen=$random(rng);
 core_output_tlast=$random(rng);return_valid=$random(rng);return_last=$random(rng);
 mailbox_input_ready=$random(rng);age=$random(rng);
end endtask
task check;begin #0.001;
 if(summary_fault_now!==reduced_fault)$fatal(1,"quiet guard algebra mismatch");checks=checks+1;
end endtask
initial begin
 rng=SEED;
 // All four-state offered/event/mailbox tuples, with varied stale payload.
 for(n=0;n<4096;n=n+1)begin
  vary_payload;
  offered_input_beat=val(n%4);offered_input_complete=val((n/4)%4);
  core_event_frame_started=val((n/16)%4);core_status_tvalid=val((n/64)%4);
  core_output_tvalid=val((n/256)%4);mailbox_input_fault=val((n/1024)%4);check;
 end
 // Unknown payload cannot resurrect inactive status/output validation.
 core_status_tdata=8'hxx;core_output_tuser=24'hzzzzzz;input_count=10'bx;
 output_count=10'bx;output_exponent=5'bx;status_exponent=5'bz;
 for(j=0;j<16;j=j+1)begin
  offered_input_beat=0;offered_input_complete=0;core_event_frame_started=0;mailbox_input_fault=0;
  core_status_tvalid=val(j%4);core_output_tvalid=val(j/4);check;
 end
 $display("REPLAY_QUIET_ALGEBRA_PASS checks=%0d inactive_only=1 four_state_exact=1",checks);$finish;
end
endmodule
'''.replace('__GUARD__',guard[begin:end]).replace('__EXPRESSION__',expression).replace('__ACTIVE__',str(active))
    path=tmp_path/'tb.sv';path.write_text(bench)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.SEED={seed}','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('seed',[1,2,3,7,17,31,127,4095])
def test_inactive_guard_exact_four_state_summary(tmp_path,seed):
    result=run(tmp_path,seed)
    assert result.returncode==0 and 'checks=4112 inactive_only=1 four_state_exact=1' in result.stdout,result.stdout

@pytest.mark.parametrize('mutation',['drop_status','drop_output','drop_mailbox','assume_active_safe'])
def test_unsafe_reductions_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation)
    assert result.returncode!=0 and 'algebra mismatch' in result.stdout,result.stdout
