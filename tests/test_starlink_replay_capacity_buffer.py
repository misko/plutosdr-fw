"""Two-slot replay capacity, conservation, cancellation and reset tests."""
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BANK=RTL/'starlink_pss_replay_capacity_buffer.v'

BENCH=r'''__TIMESCALE__
module tb;
reg clk=0,reset_a=0,reset_b=0,abort_epoch=0,cancel_now=0,input_valid=0,output_ready=0;
wire resetn=reset_a&&reset_b;
reg [120:0] input_data=0;
wire input_ready,output_valid,output_private_valid,empty,fault;
wire [120:0] output_data;
wire [1:0] occupancy;
starlink_pss_replay_capacity_buffer dut(.*);
reg [120:0] first,second;
integer count=0,pushed=0,popped=0,dropped=0,checks=0,simultaneous=0,full_stalls=0;
integer n,k,level,seed=32'h163ebaf1;
reg sampled_push,sampled_pop,sampled_fault,sampled_reset;
reg [120:0] sampled_data;
function automatic four(input integer x);
case(x%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
task compare;
begin
 if(resetn)begin
   if(occupancy!==2'(count) || empty!==(count==0))$fatal(1,"occupancy mismatch");
   if(output_valid && (count==0 || output_data!==first))$fatal(1,"accepted-word order mismatch");
   if(fault && output_valid!==0)$fatal(1,"current fault exposed public word");
 end else if(input_ready!==0 || output_valid!==0 || output_private_valid!==0)$fatal(1,"reset exposed data");
 checks=checks+1;
end endtask
task tick;
begin
 #1;compare;
 sampled_reset=!resetn;sampled_fault=fault===1;
 sampled_push=input_valid===1 && input_ready===1;
 sampled_pop=output_valid===1 && output_ready===1;
 sampled_data=input_data;
 if(sampled_reset || sampled_fault)begin
   dropped=dropped+count+(sampled_push?1:0);count=0;
 end else begin
   if(sampled_pop)begin first=second;count=count-1;popped=popped+1;end
   if(sampled_push)begin
     if(count==0)first=sampled_data;else if(count==1)second=sampled_data;
     else $fatal(1,"accepted without storage");
     count=count+1;pushed=pushed+1;
   end
   if(sampled_push&&sampled_pop)simultaneous=simultaneous+1;
 end
 clk=1;#1;compare;clk=0;#1;
end endtask
task clean;
begin
 reset_a=0;reset_b=0;input_valid=0;output_ready=0;abort_epoch=0;cancel_now=0;tick;
 reset_a=1;reset_b=1;tick;
 if(fault || occupancy || !input_ready)$fatal(1,"reset did not recover");
end endtask
task fill(input integer words);
begin
 clean;
 for(k=0;k<words;k=k+1)begin input_valid=1;input_data=121'(k+100);tick;end
 input_valid=0;
end endtask
task drain;
begin
 input_valid=0;output_ready=1;tick;tick;tick;
 if(count!=0 || !empty || fault)$fatal(1,"drain failed");
end endtask
initial begin
 clean;
 // Continuous traffic must sustain one word/clock after the first stored word.
 for(n=0;n<4096;n=n+1)begin
   input_valid=1;output_ready=1;input_data={57'h123456789abcdef,64'(n)};tick;
   if(!input_ready || !output_valid || count!=1)$fatal(1,"continuous throughput bubble");
 end
 if(pushed!=4096 || popped!=4095 || simultaneous!=4095)$fatal(1,"one-per-clock not established");
 drain;
 for(n=0;n<20000;n=n+1)begin
   input_valid=($random(seed)&3)!=0;
   output_ready=($random(seed)&7)>2;
   input_data={$random(seed),$random(seed),$random(seed),$random(seed)};
   if(n%19==0)input_data[70]=1'bx;
   if(count==2)begin
     #1;if(input_ready!==0)$fatal(1,"capacity depends on downstream ready");
     full_stalls=full_stalls+1;
   end
   tick;
 end
 drain;
 if(full_stalls<100)$fatal(1,"no full-bank stalls");
 // Local input capacity is independent of all four-state downstream controls.
 for(level=0;level<3;level=level+1)
   for(n=0;n<256;n=n+1)begin
     fill(level);
     input_valid=four(n);output_ready=four(n/4);
     cancel_now=four(n/16);abort_epoch=four(n/64);#1;
     if(input_ready!==(level<2))$fatal(1,"capacity depends on current control");
     if((cancel_now!==0 || abort_epoch!==0 ||
         (input_valid!==0&&input_valid!==1) || (output_ready!==0&&output_ready!==1)) && fault!==1)
       $fatal(1,"unknown/cancel control was not rejected");
     tick;
     if(fault)begin
       if(output_valid!==0 || output_private_valid!==0 || !empty)$fatal(1,"fault did not purge");
       input_valid=1;output_ready=1;cancel_now=0;abort_epoch=0;tick;
       if(!fault || input_ready || output_valid)$fatal(1,"fault recovered without reset");
     end
     fill(2);drain;
   end
 // Either common raw reset source must purge both slots; stale data is unreachable.
 for(level=0;level<3;level=level+1)
   for(n=0;n<2;n=n+1)begin
     fill(level);
     if(n==0)reset_a=0;else reset_b=0;
     tick;
     if(occupancy!==0)$fatal(1,"one-sided reset retained words");
     fill(2);drain;
   end
 $display("REPLAY_CAPACITY_COMPONENT_PASS checks=%0d continuous=4096 four_state=768 raw_resets=6 simultaneous=%0d full_stalls=%0d",checks,simultaneous,full_stalls);
 $finish;
end
endmodule
'''
def run(tmp_path,mutation):
    source=BANK.read_text()
    if mutation=='ready_bypass':source=source.replace('!fault_q && !tail_valid','!fault_q && (!tail_valid || output_ready)',1)
    elif mutation=='ignore_cancel':source=source.replace("(cancel_now !== 1'b0)","1'b0",1)
    elif mutation=='drop_tail':source=source.replace('if(pop && tail_valid)head_data<=tail_data;','if(pop && tail_valid)head_data<=0;',1)
    elif mutation=='reset_valid':source=source.replace('head_valid<=0;tail_valid<=0;fault_q<=0;','head_valid<=1;tail_valid<=0;fault_q<=0;',1)
    (tmp_path/'bank.v').write_text(source)
    (tmp_path/'tb.sv').write_text(BENCH.replace('__TIMESCALE__',chr(96)+'timescale 1ns/1ps'))
    built=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'bank.v'),str(tmp_path/'tb.sv')],text=True,capture_output=True,timeout=30)
    (tmp_path/'compile.log').write_text(built.stdout+built.stderr)
    assert built.returncode==0,built.stdout+built.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],text=True,capture_output=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result
@pytest.mark.parametrize('mutation',['none','ready_bypass','ignore_cancel','drop_tail','reset_valid'])
def test_capacity_conservation_and_mutations(tmp_path,mutation):
    result=run(tmp_path,mutation)
    if mutation=='none':assert result.returncode==0 and 'REPLAY_CAPACITY_COMPONENT_PASS' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
def test_input_capacity_has_no_current_downstream_dependency():
    source=BANK.read_text()
    assert source.split('assign input_ready=',1)[1].split(';',1)[0]=='resetn && !fault_q && !tail_valid'
