"""Exact source partition and same-edge sticky semantics, including X/Z."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-forward-final.VUVSznt1/prepared-v1')
TOP='starlink_pss_fft_staged_output_impl.v'
OLD="""  always @(posedge fft_clk)
    if (!fast_running) fast_fault <= 0;
    else if (any_fast_fault) fast_fault <= 1;
"""

def undo_top(text):
    from tests.test_starlink_scalar_fault_sources import undo_top as undo_scalar
    text=undo_scalar(text)
    if '// BEGIN DISTRIBUTED STICKY FAULT' not in text:return text
    text,n=re.subn(r'  // BEGIN DISTRIBUTED STICKY FAULT\n.*?  // END DISTRIBUTED STICKY FAULT\n',
        lambda _:OLD,text,flags=re.S)
    assert n==1
    line='  wire fast_fault; // DISTRIBUTED STICKY FAULT OUTPUT\n'
    assert text.count(line)==1
    return text.replace(line,'  reg fast_fault;\n',1)

def undo_bench(text):
    if '// BEGIN DISTRIBUTED STICKY FAULT WITNESS' not in text:return text
    text,n=re.subn(r'  // BEGIN DISTRIBUTED STICKY FAULT WITNESS\n.*?  // END DISTRIBUTED STICKY FAULT WITNESS\n','',text,flags=re.S)
    assert n==1
    line='      report_sticky_fault; // DISTRIBUTED STICKY FAULT REPORT\n'
    assert text.count(line)==1
    return text.replace(line,'',1)

def test_one_runtime_module_and_additive_bench():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    changed=[]
    for name in names:
        if not (RTL/name).exists():continue
        text=(RTL/name).read_text()
        if text!=(PARENT/name).read_text():changed.append(name)
        assert (undo_top(text) if name==TOP else text)==(PARENT/name).read_text(),name
    assert changed==[TOP]
    assert undo_bench((RTL/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text()
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl']:
        assert (ROOT/'tools'/name).read_bytes()==(PARENT/name).read_bytes()

def declaration(source,name):
    rows=re.findall(r'  wire '+name+r' =.*?;',source,re.S)
    assert len(rows)==1,name
    return rows[0]

def run(tmp_path,mutation=None,scalar=False):
    source=(RTL/TOP).read_text()
    if not scalar:
        from tests.test_starlink_scalar_fault_sources import undo_top as undo_scalar
        source=undo_scalar(source)
    label='SCALAR FAULT SOURCES' if scalar else 'DISTRIBUTED STICKY FAULT'
    block=re.search(r'  // BEGIN '+label+r'\n.*?  // END '+label+r'\n',source,re.S)[0]
    if mutation:
        before=block
        if mutation=='reset':block=block.replace('if (!fast_running)',"if (1'b0)",1)
        elif mutation=='not_sticky' and scalar:block=block.replace('else if (|sticky_fault_sources) fast_fault <= 1;','else fast_fault <= |sticky_fault_sources;',1)
        elif mutation=='skip_first' and scalar:block=block.replace('(|sticky_fault_sources)','(|sticky_fault_sources[18:1])',1)
        elif mutation=='skip_last' and scalar:block=block.replace('(|sticky_fault_sources)','(|sticky_fault_sources[17:0])',1)
        elif mutation=='not_sticky':block=block.replace("else if (sticky_fault_sources[cause_index]) sticky_fault_latched[cause_index] <= 1'b1;",
            "else sticky_fault_latched[cause_index] <= sticky_fault_sources[cause_index];",1)
        elif mutation=='skip_first':block=block.replace('else if (sticky_fault_sources[cause_index])','else if (cause_index!=0 && sticky_fault_sources[cause_index])',1)
        elif mutation=='skip_last':block=block.replace('else if (sticky_fault_sources[cause_index])','else if (cause_index!=18 && sticky_fault_sources[cause_index])',1)
        elif mutation=='context':block=block.replace("((fast_running === 1'b1) ?","(fast_running ?",1)
        elif mutation=='fallback':block=block.replace("(retained_reserved_known === 1'b1)","1'b1",1)
        else:raise AssertionError(mutation)
        assert block!=before
    # Extract the existing scalar reference declarations; only their leaf
    # inputs are abstracted. The exact top inverse separately fixes the mapping
    # from these leaf bits to the existing runtime admission_reject assignments.
    reference='\n'.join(declaration(source,name) for name in [
        'original_common_current_fault','offered_common_current_fault',
        'destination_original_common','destination_offered_common','contextual_destination_common'])
    bench=r"""`timescale 1ns/1ps
module tb;
reg fft_clk=0,fast_running=0,retained_reserved_known=1,preparation_fault_now=0;
reg [31:0] INPUT_OFFER_FAULT_SUMMARY=1,CONTEXTUAL_DESTINATION_SUMMARY=1;
reg [18:0] admission_reject=0;
reg external_fault_now=0,forward_fault_now=0,inverse_fault_now=0;
wire offered_external_fault_now=|admission_reject[7:0];
wire [1:0] guard_offered_local_fault=admission_reject[9:8];
wire output_bank_fault=admission_reject[10];
wire output_bank_framing_fault_now=admission_reject[11];
wire [5:0] summary_preflight_events=admission_reject[17:12];
wire result_fault=admission_reject[18];
__REFERENCE__
wire any_fast_fault=(CONTEXTUAL_DESTINATION_SUMMARY === 0) ?
 (INPUT_OFFER_FAULT_SUMMARY ? offered_common_current_fault : original_common_current_fault) :
 contextual_destination_common;
wire fast_fault;
reg original_fault;
__BLOCK__
always @(posedge fft_clk)
 if(!fast_running)original_fault<=0;
 else if(any_fast_fault)original_fault<=1;
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
function [31:0] mode(input integer n);case(n)0:mode=0;1:mode=1;2:mode=32'bx;3:mode=32'bz;endcase endfunction
integer a,b,k,r,p,c,v,n,checks=0,resets=0,sets=0;
task tick;begin
 #1;
 if((|sticky_fault_sources)!==any_fast_fault)$fatal(1,"source partition mismatch checks=%0d",checks);
 fft_clk=1;#1;
 if(fast_fault!==original_fault)$fatal(1,"sticky edge/persistence mismatch checks=%0d",checks);
 if(fast_running===0)resets=resets+1;
 else if(any_fast_fault===1)sets=sets+1;
 checks=checks+1;fft_clk=0;
end endtask
initial begin
 tick;
 for(a=0;a<4;a=a+1)for(b=0;b<4;b=b+1)for(k=0;k<4;k=k+1)
 for(r=0;r<4;r=r+1)for(p=0;p<4;p=p+1)for(c=0;c<19;c=c+1)for(v=0;v<4;v=v+1)begin
   INPUT_OFFER_FAULT_SUMMARY=mode(a);CONTEXTUAL_DESTINATION_SUMMARY=mode(b);
   retained_reserved_known=val(k);preparation_fault_now=val(p);
   external_fault_now=0;forward_fault_now=0;inverse_fault_now=0;
   admission_reject=0;fast_running=0;tick;
   admission_reject[c]=val(v);fast_running=val(r);tick;
   // A known fault must dominate unrelated unknown causes.
   admission_reject[(c+1)%19]=1'b1;admission_reject[(c+2)%19]=1'bx;tick;
   // Fault disappearance may not clear sticky capture.
   admission_reject=0;preparation_fault_now=0;tick;
 end
 for(n=0;n<2000;n=n+1)begin
   INPUT_OFFER_FAULT_SUMMARY=mode($random&3);CONTEXTUAL_DESTINATION_SUMMARY=mode($random&3);
   retained_reserved_known=val($random&3);preparation_fault_now=val($random&3);
   external_fault_now=val($random&3);forward_fault_now=val($random&3);inverse_fault_now=val($random&3);
   fast_running=val($random&3);
   for(c=0;c<19;c=c+1)admission_reject[c]=val($random&3);
   tick;
 end
 $display("DISTRIBUTED_STICKY_CONTRACT_PASS checks=%0d resets=%0d sets=%0d same_edge=1 four_state=1",checks,resets,sets);$finish;
end
endmodule
""".replace('__REFERENCE__',reference).replace('__BLOCK__',block)
    if scalar:bench=bench.replace('wire fast_fault;','reg fast_fault;',1)
    tb=tmp_path/'tb.sv';tb.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tb)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_scalar_partition_and_clocked_fourstate_capture(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'DISTRIBUTED_STICKY_CONTRACT_PASS checks=313297' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['reset','not_sticky','skip_first','skip_last','context','fallback'])
def test_invalid_capture_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation)
    assert result.returncode!=0 and 'mismatch' in result.stdout,result.stdout+result.stderr
