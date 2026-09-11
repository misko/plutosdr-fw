"""Private fact payload may differ only outside original certificate validity."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-completion-stage.rTnPYQ8U/prepared-v2')
NAME='starlink_pss_admission_certificate.v'
TOP='starlink_pss_fft_staged_output_impl.v'
BENCH='tb_fft_staged_output.sv'
PAYLOAD='''  // Invalid evidence is private and has no reset value contract in opt-in mode.
  // Capture on the original acceptance edge, then hold while valid/consumed.
  // Validity and current permit fencing below remain the original authority.
  generate if (PRIVATE_FACT_CAPTURE) begin : private_facts
    always @(posedge clk)
      if (!snapshot_valid && !consumed) snapshot_good<=checks_good;
  end else begin : legacy_facts
    always @(posedge clk)
      if (!resetn || quarantine || !request) snapshot_good<=0;
      else if (!snapshot_valid && !consumed) snapshot_good<=checks_good;
  end endgenerate
'''

def undo_top(text):
    old='#(.CHECKS(36),.PRIVATE_FACT_CAPTURE(1)) admission_gate ('
    assert text.count(old)==1
    return text.replace(old,'#(.CHECKS(36)) admission_gate (',1)

def undo_payload(text):
    assert text.count(PAYLOAD)==1
    return text.replace(PAYLOAD,'',1).replace('CHECKS=24,\n  parameter integer PRIVATE_FACT_CAPTURE=0','CHECKS=24',1).replace(
      'snapshot_valid<=0;consumed<=0;','snapshot_valid<=0;snapshot_good<=0;consumed<=0;',1).replace(
      '        snapshot_valid<=1;','        snapshot_good<=checks_good;snapshot_valid<=1;',1)

def parent_runtime_bytes(path):
    return undo_payload(path.read_text()).encode() if path.name==NAME else path.read_bytes()

def undo_bench(text):
    before='''        if({dut.admission_permit,dut.admission_gate.snapshot_valid,dut.admission_gate.consumed} !==
           {legacy_admission_permit,legacy_admission.snapshot_valid,legacy_admission.consumed} ||
           (dut.admission_gate.snapshot_valid && compressed_admission!==legacy_admission.snapshot_good) ||'''
    after='''        if({dut.admission_permit,dut.admission_gate.snapshot_valid,dut.admission_gate.consumed,compressed_admission} !==
           {legacy_admission_permit,legacy_admission.snapshot_valid,legacy_admission.consumed,legacy_admission.snapshot_good} ||'''
    assert text.count(before)==1;text=text.replace(before,after,1)
    text,count=re.subn(r'  // BEGIN PRIVATE ADMISSION FACTS WITNESS\n.*?  // END PRIVATE ADMISSION FACTS WITNESS\n','',text,flags=re.S)
    assert count==1
    for n,mode in [(6,'AUXILIARY'),(4,'MAIN')]:
        line=' '*n+'report_private_admission_facts; // PRIVATE ADMISSION FACTS '+mode+'\n'
        assert text.count(line)==1;text=text.replace(line,'',1)
    return text

def test_exact_opt_in_delta_and_unchanged_runtime():
    assert undo_top((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    assert undo_payload((RTL/NAME).read_text())==(PARENT/NAME).read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name not in {TOP,NAME} and (RTL/name).exists():
            assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name

def test_exact_bench_delta():
    assert undo_bench((RTL/BENCH).read_text())==(PARENT/BENCH).read_text()

def run(tmp_path,width=36,mode=1,mutation=None):
    source=(RTL/NAME).read_text()
    mutations={
      'follow_owned':('if (!snapshot_valid && !consumed) snapshot_good<=checks_good;',"if (1'b1) snapshot_good<=checks_good;"),
      'skip_capture':('if (!snapshot_valid && !consumed) snapshot_good<=checks_good;',"if (1'b0) snapshot_good<=checks_good;"),
      'omit_valid':('!quarantine && snapshot_valid &&','!quarantine &&'),
      'omit_quarantine':('request && !quarantine &&','request &&')}
    if mutation:
        before,after=mutations[mutation];assert before in source;source=source.replace(before,after,1)
    reference=(PARENT/NAME).read_text().replace('module starlink_pss_admission_certificate','module original_certificate',1)
    bench='''`timescale 1ns/1ps
module tb;
parameter integer WIDTH=36,MODE=1;
reg clk=0;always #5 clk=~clk;
reg resetn=0,request=0,quarantine=0,consume=0;
reg [WIDTH-1:0] checks_good=0;
wire permit,valid,old_permit,old_valid;
wire [WIDTH-1:0] good,old_good;
starlink_pss_admission_certificate #(.CHECKS(WIDTH),.PRIVATE_FACT_CAPTURE(MODE)) dut(
 .clk(clk),.resetn(resetn),.request(request),.quarantine(quarantine),.consume(consume),
 .checks_good(checks_good),.permit(permit),.snapshot_valid(valid),.snapshot_good(good));
original_certificate #(.CHECKS(WIDTH)) ref_dut(
 .clk(clk),.resetn(resetn),.request(request),.quarantine(quarantine),.consume(consume),
 .checks_good(checks_good),.permit(old_permit),.snapshot_valid(old_valid),.snapshot_good(old_good));
integer checks=0,owned=0,differences=0,n,j,k;
function value(input integer n);case(n)0:value=0;1:value=1;2:value=1'bx;3:value=1'bz;endcase endfunction
task verify;begin
 if({permit,valid,dut.consumed}!=={old_permit,old_valid,ref_dut.consumed}) $fatal(1,"control mismatch");
 if((MODE==0 || valid===1'b1) && good!==old_good) $fatal(1,"owned or legacy payload mismatch");
 if(valid===1'b1)owned=owned+1;
 else if(good!==old_good)differences=differences+1;
 checks=checks+1;
end endtask
task step(input reg r,q,c,s,input reg [WIDTH-1:0] facts);begin
 @(negedge clk);resetn=r;request=q;quarantine=c;consume=s;checks_good=facts;#0.01;verify;
 @(posedge clk);#0.01;verify;
end endtask
initial begin
 repeat(2)@(posedge clk);#0.1;
 // Fresh capture, hold changing facts, consume exactly once, cancel and retry.
 step(1,0,0,0,{WIDTH{1'b1}});step(1,1,0,0,{WIDTH{1'b1}});
 repeat(4)step(1,1,0,0,0);
 step(1,1,1,1,0);step(1,1,0,0,{WIDTH{1'b1}});
 step(1,1,0,1,0);repeat(3)step(1,1,0,1,{WIDTH{1'b1}});
 step(1,0,0,0,0);step(1,1,0,0,0);step(0,1,0,1,{WIDTH{1'b1}});
 // All four-state controls and data, each preceded by a fresh known reset.
 for(n=0;n<256;n=n+1)for(j=0;j<4;j=j+1)begin
  step(0,0,0,0,0);step(1,0,0,0,{WIDTH{1'b1}});
  step(1,1,0,0,{WIDTH{1'b1}});
  step(value(n%4),value((n/4)%4),value((n/16)%4),value((n/64)%4),{WIDTH{value(j)}});
 end
 step(0,0,0,0,0);
 for(k=0;k<2000;k=k+1)step((k%47)!=0,(k%11)!=0,(k%53)==0,(k%5)==0,k);
 if(checks<10000 || owned<100 || (MODE==1 && differences<100))$fatal(1,"coverage short");
 $display("PRIVATE_FACT_COMPONENT_PASS checks=%0d owned=%0d invalid_differences=%0d",checks,owned,differences);$finish;
end
initial begin #200000;$fatal(1,"watchdog");end
endmodule
'''
    files=[]
    for name,text in [('candidate.v',source),('reference.v',reference),('tb.sv',bench)]:
        p=tmp_path/name;p.write_text(text);files.append(str(p))
    compiled=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.WIDTH={width}',f'-Ptb.MODE={mode}','-o',str(tmp_path/'sim'),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('width',[1,24,36,42])
@pytest.mark.parametrize('mode',[0,1])
def test_private_and_exact_legacy(tmp_path,width,mode):
    result=run(tmp_path,width,mode)
    assert result.returncode==0 and 'PRIVATE_FACT_COMPONENT_PASS' in result.stdout,result.stdout

@pytest.mark.parametrize('mutation',['follow_owned','skip_capture','omit_valid','omit_quarantine'])
def test_unsafe_mutations_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation)
    assert result.returncode!=0 and 'mismatch' in result.stdout and 'watchdog' not in result.stdout,result.stdout
