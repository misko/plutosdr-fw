"""Actual kernel expression preserves generic and unknown-reset semantics."""
from pathlib import Path
import re
import subprocess
import pytest

RTL=Path(__file__).resolve().parents[1]/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_kernel_rom.v'

def run(tmp_path,mode=1,mutation=None):
    source=RTL.read_text()
    expr=re.search(r'  // BEGIN PARALLEL KERNEL READY\n.*?  // END PARALLEL KERNEL READY\n',source,re.S)[0]
    changes={
      'reset_fallback':("resetn === 1'b1 ? parallel_input_room : output_stage_ready",'parallel_input_room'),
      'ignore_fault':('assign input_ready = resetn && !flush && !protocol_fault &&\n      (resetn', 'assign input_ready = resetn && !flush &&\n      (resetn'),
      'ignore_flush':('assign input_ready = resetn && !flush && !protocol_fault &&\n      (resetn', 'assign input_ready = resetn && !protocol_fault &&\n      (resetn'),
      'ignore_capacity':('!output_valid || downstream_capacity',"1'b1"),
    }
    if mutation:
        old,new=changes[mutation];assert expr.count(old)==1;expr=expr.replace(old,new,1)
    bench='''`timescale 1ns/1ps
module tb;
localparam PARALLEL_INPUT_CAPACITY=__MODE__;
reg resetn,flush,protocol_fault,output_valid,output_ready,downstream_capacity;
wire input_ready;
wire output_stage_ready=!output_valid||output_ready;
__EXPR__
integer n,checks=0;
function val(input integer i);case(i%4)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
initial begin
 for(n=0;n<4096;n=n+1)begin
  resetn=val(n);flush=val(n>>2);protocol_fault=val(n>>4);output_valid=val(n>>6);
  output_ready=val(n>>8);downstream_capacity=val(n>>10);
  // The caller obligation applies only in a known active epoch. All values
  // of an otherwise irrelevant capacity input are retained outside it.
  if(resetn===1'b1)downstream_capacity=output_ready;
  #0.001;
  if(input_ready!==(resetn&&!flush&&!protocol_fault&&output_stage_ready))$fatal(1,"four-state ready mismatch");
  checks=checks+1;
 end
 $display("PARALLEL_READY_FOURSTATE_PASS checks=%0d",checks);$finish;
end
endmodule
'''.replace('__MODE__',str(mode)).replace('__EXPR__',expr)
    (tmp_path/'tb.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr);return result

@pytest.mark.parametrize('mode',[0,1])
def test_fourstate_current_ready(tmp_path,mode):
    result=run(tmp_path,mode);assert result.returncode==0 and 'checks=4096' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['reset_fallback','ignore_fault','ignore_flush','ignore_capacity'])
def test_unsafe_ready_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation);assert result.returncode!=0 and 'four-state ready mismatch' in result.stdout,result.stdout+result.stderr
