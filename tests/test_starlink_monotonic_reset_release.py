"""Common-epoch reset simplification: exact parent comparison and stopped clocks."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-split-preflight.2BQ3zjL5/prepared-v1')
BARRIER='starlink_pss_reset_receipt_barrier.v'
TOP='starlink_pss_fft_staged_output_impl.v'

def undo_barrier(text):
    start=text.index('module starlink_pss_reset_receipt_barrier #(')
    end=text.index(') (',start)+3
    text=text[:start]+'module starlink_pss_reset_receipt_barrier ('+text[end:]
    text,n=re.subn(r'  // BEGIN MONOTONIC RESET RELEASE\n.*?  // END MONOTONIC RESET RELEASE\n',
        '  assign fast_running = raw_epoch_ok && outer_fast_running && fast_release;\n'
        '  assign slow_running = raw_epoch_ok && outer_slow_running && fast_release_slow[1];\n',text,flags=re.S)
    assert n==1
    return text

def test_exact_barrier_delta():
    assert undo_barrier((RTL/BARRIER).read_text())==(PARENT/BARRIER).read_text()

def undo_top(text):
    for old,new in [
        ('  parameter integer SPLIT_PREFLIGHT_IDENTITY = 0,\n  parameter integer MONOTONIC_OUTER_RESET = 0','  parameter integer SPLIT_PREFLIGHT_IDENTITY = 0'),
        ('starlink_pss_reset_receipt_barrier #(.MONOTONIC_OUTER_RESET(MONOTONIC_OUTER_RESET)) epoch_barrier (','starlink_pss_reset_receipt_barrier epoch_barrier (')]:
        assert text.count(old)==1;text=text.replace(old,new,1)
    return text

def undo_bench(text):
    if '// BEGIN FORWARD CAPACITY SHADOW' in text:
        from tests.test_starlink_forward_capacity_contract import undo_bench as undo_capacity
        text=undo_capacity(text)
    text,n=re.subn(r'  // BEGIN MONOTONIC RESET WITNESS\n.*?  // END MONOTONIC RESET WITNESS\n','',text,flags=re.S)
    assert n==1
    for value in ['      report_monotonic_release; // MONOTONIC RESET REPORT\n',',.MONOTONIC_OUTER_RESET(1)']:
        assert text.count(value)==1;text=text.replace(value,'',1)
    return text

def test_exact_integration_delta():
    assert undo_top((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    name='tb_fft_staged_output.sv';assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()
    assert (ROOT/'tools/staged_fft_experiment.tcl').read_text().replace(' MONOTONIC_OUTER_RESET=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name not in {TOP,BARRIER} and (RTL/name).exists():assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name

def run(tmp_path,fast=2857,slow=5000,phase=0,mode='1',mutation=None,negative=0):
    text=(RTL/BARRIER).read_text()
    changes={
        'skip_fast_purge':('outer_fast_running && fast_purge_count == 2 && slow_purge_fast[1]', 'outer_fast_running && slow_purge_fast[1]'),
        'skip_slow_receipt':('outer_fast_running && fast_purge_count == 2 && slow_purge_fast[1]', 'outer_fast_running && fast_purge_count == 2'),
        'skip_slow_sync':('assign slow_running = raw_epoch_ok && fast_release_slow[1];','assign slow_running = raw_epoch_ok && fast_release;'),
        'ignore_idle':("fast_mailboxes_reset_idle === 1'b1", "1'b1"),
    }
    if mutation:
        old,new=changes[mutation];assert text.count(old)==1;text=text.replace(old,new,1)
    (tmp_path/'candidate.v').write_text(text)
    (tmp_path/'reference.v').write_text((PARENT/BARRIER).read_text().replace('module starlink_pss_reset_receipt_barrier (','module reference_barrier (',1))
    top=(RTL/TOP).read_text()
    reset_logic=top[top.index('  (* ASYNC_REG = "TRUE" *) reg [1:0] slow_reset_fast'):top.index('  wire outer_slow_running')]
    reset_logic+= '  wire outer_slow_running = slow_reset_slow[1] && fast_reset_slow[1];\n'
    bench='''`timescale 1ps/1ps
module tb;
reg clk=0,fft_clk=0,slow_enable=1,fast_enable=1;
reg resetn=0,fft_resetn=0;
reg slow_idle=0,fast_idle=0;
reg violate_slow=0,violate_fast=0;
always #__FAST__ if(fast_enable)fft_clk=~fft_clk;
initial begin #__PHASE__;forever begin #__SLOW__;if(slow_enable)clk=~clk;end end
__RESET_LOGIC__
wire os=outer_slow_running && !violate_slow,of=outer_fast_running && !violate_fast;
wire sr,fr,ref_sr,ref_fr;
starlink_pss_reset_receipt_barrier #(.MONOTONIC_OUTER_RESET(__MODE__)) dut(
 .slow_clk(clk),.fast_clk(fft_clk),.resetn(resetn),.fft_resetn(fft_resetn),
 .outer_slow_running(os),.outer_fast_running(of),
 .slow_mailboxes_reset_idle(slow_idle),.fast_mailboxes_reset_idle(fast_idle),
 .slow_running(sr),.fast_running(fr));
reference_barrier ref_dut(
 .slow_clk(clk),.fast_clk(fft_clk),.resetn(resetn),.fft_resetn(fft_resetn),
 .outer_slow_running(os),.outer_fast_running(of),
 .slow_mailboxes_reset_idle(slow_idle),.fast_mailboxes_reset_idle(fast_idle),
 .slow_running(ref_sr),.fast_running(ref_fr));
integer checks=0,epochs=0,k,j;reg initialized=0,negative_active=0;
task check;begin
 #1;
 if(initialized && !negative_active)begin
  if({sr,fr}!=={ref_sr,ref_fr})$fatal(1,"release equivalence mismatch");
  if((sr===1'b1 && os!==1'b1)||(fr===1'b1 && of!==1'b1))$fatal(1,"outer readiness implication failed");
  if((resetn!==1'b1 || fft_resetn!==1'b1) && {sr,fr}!==2'b00)$fatal(1,"raw reset did not cancel");
  checks=checks+1;
 end
end endtask
always @(posedge clk or negedge clk)check;
always @(posedge fft_clk or negedge fft_clk)check;
always @(resetn or fft_resetn)check;
task wait_release;begin
 wait(sr===1'b1 && fr===1'b1);#3;epochs=epochs+1;
end endtask
function four(input integer i);case(i%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase endfunction
initial begin
 #100003;initialized=1;resetn=1;fft_resetn=1;
 // Slow receipt may arrive first, but fast idle must still be observed twice.
 slow_idle=1;#200003;if(fr || sr)$fatal(1,"fast purge bypassed");
 fast_idle=1;wait_release;
 for(k=0;k<24;k=k+1)begin
  // Exercise each reset independently, including X/Z, while either clock or
  // both clocks are stopped. Raw reset is released before clock restart.
  #11003;fast_enable=(k%3==0);slow_enable=(k%3==1);
  if(k%2==0)resetn=(k%6==0)?1'bx:((k%6==2)?1'bz:1'b0);
  else fft_resetn=(k%6==1)?1'bx:((k%6==3)?1'bz:1'b0);
  #20003;if({sr,fr}!==0)$fatal(1,"stopped raw reset cancellation failed");
  resetn=1;fft_resetn=1;slow_idle=0;fast_idle=0;
  #200003;if({sr,fr}!==0)$fatal(1,"stopped epoch released early");
  fast_enable=1;slow_enable=1;
  // Unknown idle levels must not count as reset receipts.
  for(j=0;j<12;j=j+1)begin
   #17003;slow_idle=(j%2)?1'bx:1'bz;fast_idle=(j%2)?1'bz:1'bx;
  end
  #7;if({sr,fr}!==0)$fatal(1,"unknown idle released epoch");
  if(k%2==0)begin slow_idle=1;#200003;if({sr,fr}!==0)$fatal(1,"fast idle missing");fast_idle=1;end
  else begin fast_idle=1;#200003;if({sr,fr}!==0)$fatal(1,"slow idle missing");slow_idle=1;end
  wait_release;
  // Once running, mailbox occupancy is normal and does not revoke release.
  for(j=0;j<8;j=j+1)begin #27003;slow_idle=four(j);fast_idle=four(j+1);end
 end
 if(__NEGATIVE__)begin
  negative_active=1;
  if(__NEGATIVE__==1)violate_fast=1;else violate_slow=1;
  #3;
  if(__MODE__==1)begin
   if({sr,fr}==={ref_sr,ref_fr})$fatal(1,"nonmonotonic counterexample missing");
  end else if({sr,fr}!=={ref_sr,ref_fr})$fatal(1,"generic mode changed");
  $display("NONMONOTONIC_CONTRACT_COUNTEREXAMPLE side=%0d mode=%0d",__NEGATIVE__,__MODE__);
 end
 if(checks<1000 || epochs!=25)$fatal(1,"short reset campaign");
 $display("MONOTONIC_RESET_COMPONENT_PASS checks=%0d epochs=%0d",checks,epochs);$finish;
end
initial begin #100000000;$fatal(1,"absolute deadline");end
endmodule
'''
    for key,value in {'FAST':fast,'SLOW':slow,'PHASE':phase,'MODE':mode,'RESET_LOGIC':reset_logic,'NEGATIVE':negative}.items():bench=bench.replace('__'+key+'__',str(value))
    (tmp_path/'bench.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'bench.sv'),str(tmp_path/'candidate.v'),str(tmp_path/'reference.v')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('fast,slow',[(2857,5000),(2500,5000),(5000,2857)])
@pytest.mark.parametrize('phase',[0,1,1234,4999])
@pytest.mark.parametrize('mode',[0,1])
def test_common_epoch_equivalence(tmp_path,fast,slow,phase,mode):
    result=run(tmp_path,fast,slow,phase,mode)
    assert result.returncode==0 and 'epochs=25' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode',[0,1])
@pytest.mark.parametrize('negative',[1,2])
def test_nonmonotonic_inputs_require_generic_mode(tmp_path,mode,negative):
    result=run(tmp_path,mode=mode,negative=negative)
    assert result.returncode==0 and 'NONMONOTONIC_CONTRACT_COUNTEREXAMPLE' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['skip_fast_purge','skip_slow_receipt','skip_slow_sync','ignore_idle'])
def test_unsafe_release_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'absolute deadline' not in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode',['2',"32'bx","32'bz"])
def test_invalid_mode_rejected(tmp_path,mode):
    result=run(tmp_path,mode=mode)
    assert result.returncode!=0 and 'known boolean mode' in result.stdout,result.stdout+result.stderr
