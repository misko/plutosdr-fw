"""Cycle-wise comparison with original ROM; invalid payload is intentionally private."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent/'staged-completion-prepared-v1'
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_kernel_rom.v'

def bench():
    declarations=[];instances=[]
    for n in range(3):
        declarations.append(f'wire ready{n},valid{n},last{n};wire [17:0] ki{n},kq{n};wire [8:0] bin{n};wire [4:0] exp{n};wire [63:0] start{n};wire [5:0] flags{n};')
        module='golden_kernel' if n==0 else 'starlink_pss_kernel_rom'
        parameter='' if n==0 else f',.PRIVATE_PAYLOAD_BUBBLES({n-1})'
        instances.append(f'''{module} #(.ROM_FILE("kernel.mem"),.DATA_WIDTH(18),.BALANCED_BLOCK_IDENTITY_EQ(1){parameter}) d{n}(
          .clk(clk),.resetn(resetn),.flush(flush),.input_valid(iv),.input_ready(ready{n}),
          .input_bin_index(ib),.input_block_exponent(ie),.input_last(il),.input_block_start_index(istart),
          .output_valid(valid{n}),.output_ready(oready),.output_kernel_i(ki{n}),.output_kernel_q(kq{n}),
          .output_bin_index(bin{n}),.output_block_exponent(exp{n}),.output_last(last{n}),.output_block_start_index(start{n}),
          .accepted_pulse(flags{n}[0]),.emitted_pulse(flags{n}[1]),.input_block_complete_pulse(flags{n}[2]),
          .sequence_error_pulse(flags{n}[3]),.metadata_error_pulse(flags{n}[4]),.protocol_fault(flags{n}[5]));''')
    return '''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,flush=0,iv=0,il=0,oready=0,hold_reader=0;
reg [8:0] ib=0;reg [4:0] ie=0;reg [63:0] istart=0;
integer cycles=0,reads=0,blockno,pos,kind,checks=0;
always #5 clk=~clk;
always @(negedge clk) begin cycles=cycles+1;oready=!hold_reader && cycles%11<8;end
'''+'\n'.join(declarations+instances)+'''
always @(posedge clk) begin
  if(valid0 && oready) reads=reads+1;
  #0.01;
  if({ready0,valid0,flags0}!=={ready1,valid1,flags1} || {ready0,valid0,flags0}!=={ready2,valid2,flags2})
    $fatal(1,"public control differs cycle=%0d",cycles);
  if(valid0 && ({ki0,kq0,bin0,exp0,last0,start0}!=={ki1,kq1,bin1,exp1,last1,start1} ||
                {ki0,kq0,bin0,exp0,last0,start0}!=={ki2,kq2,bin2,exp2,last2,start2}))
    $fatal(1,"valid/stalled payload differs cycle=%0d",cycles);
  checks=checks+1;
end
task tick;begin @(posedge clk);#0.1;@(negedge clk);#0.1;end endtask
task clear_epoch;begin iv=0;resetn=0;hold_reader=0;repeat(3)tick;resetn=1;tick;end endtask
task send(input integer b,input integer p);
begin
  iv=1;ib=p;ie=7+b;il=p==511;istart=64'ha5a5a5a500000000+b*447;
  @(posedge clk);while(!ready0) @(posedge clk);#0.1;@(negedge clk);#0.1;iv=0;
end endtask
initial begin
clear_epoch;
for(blockno=0;blockno<8;blockno=blockno+1) begin
  for(pos=0;pos<512;pos=pos+1) begin
    if(pos%7==0) begin iv=0;ib=509;ie=31;istart=64'hffffffffffffffff;il=1;tick;end
    send(blockno,pos);
  end
end
while(valid0)tick;
if(reads!=4096) $fatal(1,"healthy inventory missing");
for(kind=0;kind<4;kind=kind+1) begin
  clear_epoch;if(kind>=2)send(0,0);
  iv=1;ib=kind==0 ? 2 : kind>=2 ? 1 : 0;il=kind==1;ie=kind==2 ? 9 : 7;
  istart=kind==3 ? 64'h123 : 64'ha5a5a5a500000000;
  @(posedge clk);while(!ready0)@(posedge clk);#0.1;@(negedge clk);#0.1;iv=0;
  repeat(3)tick;if(!flags0[5]) $fatal(1,"malformed beat not quarantined");
end
clear_epoch;hold_reader=1;send(0,0);iv=0;ib=17;istart=42;repeat(7)tick;
flush=1;tick;flush=0;hold_reader=0;tick;
if(valid0 || flags0[5]) $fatal(1,"flush failed");
send(0,0);while(valid0)tick;
$display("PRIVATE_KERNEL_PASS healthy=4096 malformed=4 flush=1 checks=%0d",checks);$finish;
end
initial begin #300000;$fatal(1,"watchdog");end
endmodule
'''

def execute(tmp_path,source,bench_text=None):
    assert hashlib.sha256((BASE/'starlink_pss_kernel_rom.v').read_bytes()).hexdigest()=='0b4ee87d93d61c6fa12ee9992aa517a3a8be568835075531d9af4453f4ec80e5'
    assert hashlib.sha256((BASE/'upper_edge_pss_kernel_q17.mem').read_bytes()).hexdigest()=='694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a'
    original=(BASE/'starlink_pss_kernel_rom.v').read_text()
    (tmp_path/'golden.v').write_text(original.replace('module starlink_pss_kernel_rom #(','module golden_kernel #(',1))
    (tmp_path/'candidate.v').write_text(source)
    (tmp_path/'kernel.mem').write_bytes((BASE/'upper_edge_pss_kernel_q17.mem').read_bytes())
    (tmp_path/'tb.sv').write_text(bench() if bench_text is None else bench_text)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','golden.v','candidate.v','tb.sv'],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp','sim'],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr)
    return result

def test_private_rom_matches_original_public_contract(tmp_path):
    before=hashlib.sha256(RTL.read_bytes()).hexdigest()
    result=execute(tmp_path,RTL.read_text())
    assert hashlib.sha256(RTL.read_bytes()).hexdigest()==before
    assert result.returncode==0 and 'PRIVATE_KERNEL_PASS healthy=4096 malformed=4 flush=1' in result.stdout,result.stdout

@pytest.mark.parametrize('change',['stall','publish','skip_check'])
def test_unsafe_private_rom_mutants_rejected(tmp_path,change):
    before,after={
      'stall':('if (PRIVATE_PAYLOAD_BUBBLES && input_ready)','if (PRIVATE_PAYLOAD_BUBBLES)'),
      'publish':('if (output_stage_ready)\n        output_valid <= 1\'b0;',"if (output_stage_ready)\n        output_valid <= PRIVATE_PAYLOAD_BUBBLES;"),
      'skip_check':('if (protocol_error_now) begin','if (protocol_error_now && !PRIVATE_PAYLOAD_BUBBLES) begin'),
    }[change]
    source=RTL.read_text();assert source.count(before)==1
    result=execute(tmp_path,source.replace(before,after,1))
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout
