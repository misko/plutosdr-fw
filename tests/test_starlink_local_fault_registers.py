"""Exercise the exact new RTL register block, separately from public fencing."""
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import local_fault_experiment as experiment

@pytest.mark.parametrize('case',range(38))
def test_each_fact_capture_fallback_and_pending_reset(tmp_path,case):
    text=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    start=text.index('  reg [32:0] local_fault_snapshot;')
    end=text.index('  // END SCALAR FAULT SOURCES',start)
    fragment=text[start:end]
    bench='''`timescale 1ns/1ps
module tb;
parameter integer CASE=0;
localparam INPUT_OFFER_FAULT_SUMMARY=(CASE==33?0:1);
localparam CONTEXTUAL_DESTINATION_SUMMARY=1;
reg fft_clk=0;always #3 fft_clk=!fft_clk;
reg fast_running=0,fast_fault=0,retained_reserved_known=1;
reg [32:0] admission_reject_expanded=0;
wire result_fault=admission_reject_expanded[32];
wire [18:0] sticky_fault_sources={admission_reject_expanded[32:24],
    (|admission_reject_expanded[23:16]),(|admission_reject_expanded[15:8]),admission_reject_expanded[7:0]};
'''+fragment+'''
task automatic edge_check;
begin @(posedge fft_clk);#0.001;end
endtask
initial begin
  edge_check;
  if(fast_fault!==0 || local_fault_snapshot!==0)$fatal(1,"initial reset");
  @(negedge fft_clk);fast_running=1;
  if(CASE==34)retained_reserved_known=0;
  if(CASE<33)admission_reject_expanded=33'b1<<CASE;
  else if(CASE==36)admission_reject_expanded[3]=1'bx;
  else if(CASE==37)admission_reject_expanded[3]=1'bz;
  else admission_reject_expanded[3]=1;
  edge_check;
  if(local_fault_snapshot!==admission_reject_expanded)$fatal(1,"fact capture changed");
  if(fast_fault!==(CASE==32 || CASE==33 || CASE==34))$fatal(1,"wrong first capture edge");
  @(negedge fft_clk);admission_reject_expanded=0;
  if(CASE==35)fast_running=0;
  edge_check;
  if(CASE==35)begin
    if(fast_fault!==0 || local_fault_snapshot!==0)$fatal(1,"pending reset did not purge");
  end else if(CASE<36)begin
    if(fast_fault!==1)$fatal(1,"fault not latched by second edge");
  end else if(fast_fault!==0)$fatal(1,"unknown-only if semantics changed");
  @(negedge fft_clk);fast_running=0;
  edge_check;
  if(fast_fault!==0 || local_fault_snapshot!==0)$fatal(1,"fault reset");
  @(negedge fft_clk);fast_running=1;retained_reserved_known=1;
  repeat(5)begin edge_check;if(fast_fault!==0 || local_fault_snapshot!==0)$fatal(1,"stale fault after reset");end
  $display("LOCAL_REGISTER_PASS case=%0d",CASE);$finish;
end
initial begin #1000;$fatal(1,"deadline");end
endmodule
'''
    (tmp_path/'bench.sv').write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.CASE='+str(case),'-o',str(tmp_path/'sim'),str(tmp_path/'bench.sv')],capture_output=True,text=True,timeout=15)
    (tmp_path/'compile.log').write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=15)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert f'LOCAL_REGISTER_PASS case={case}' in result.stdout
