"""Fault partition is additive: every old FIFO signal stays cycle-exact."""
import subprocess
import pytest
from tests.test_starlink_replay_capacity_buffer import BENCH, ROOT, RTL
import sys
sys.path.insert(0,str(ROOT/'tools'))
import replay_local_fault_transform as transform

def test_exact_additive_changes():
    for old,new,changes in [
        ('starlink_pss_fft_replay_capacity_ring_impl','starlink_pss_fft_replay_local_fault_impl',transform.TOP_CHANGES),
        ('starlink_pss_replay_capacity_ring','starlink_pss_replay_local_fault_ring',transform.BANK_CHANGES)]:
        a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
        assert transform.transform(a,changes)==b
        assert transform.undo(b,changes)==a

@pytest.mark.parametrize('mutation',['none','cancel_echo','ignore_unknown','ignore_sticky','suppress_all_on_cancel','ignore_cancel'])
def test_fault_partition_and_original_behavior(tmp_path,mutation):
    source=(RTL/'starlink_pss_replay_local_fault_ring.v').read_text()
    if mutation=='cancel_echo':source=source.replace('fault_q || local_control_bad','fault_q || control_bad',1)
    elif mutation=='ignore_unknown':source=source.replace("(cancel_now !== 1'b0 && cancel_now !== 1'b1)","1'b0",1)
    elif mutation=='ignore_sticky':source=source.replace('fault_q || local_control_bad','local_control_bad',1)
    elif mutation=='suppress_all_on_cancel':source=source.replace('fault_q || local_control_bad',"(fault_q || local_control_bad) && !cancel_now",1)
    elif mutation=='ignore_cancel':source=source.replace("(cancel_now !== 1'b0)","1'b0",1)
    bench=BENCH.replace('__TIMESCALE__',chr(96)+'timescale 1ns/1ps')
    bench=bench.replace('starlink_pss_replay_capacity_buffer dut(.*);','wire local_fault;\nstarlink_pss_replay_local_fault_ring dut(.*);')
    extra=r'''
wire reference_ready,reference_valid,reference_private,reference_empty,reference_fault;
wire [120:0] reference_data;wire [1:0] reference_count;
integer partition_checks=0,external_only=0,malformed_cancel=0,sticky_checks=0;
starlink_pss_replay_capacity_ring reference(
 .clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),.cancel_now(cancel_now),
 .input_valid(input_valid),.input_ready(reference_ready),.input_data(input_data),
 .output_valid(reference_valid),.output_private_valid(reference_private),
 .output_ready(output_ready),.output_data(reference_data),.occupancy(reference_count),
 .empty(reference_empty),.fault(reference_fault));
task compare_partition;
reg expected_local;
begin
 if({input_ready,output_valid,output_private_valid,occupancy,empty,fault} !==
    {reference_ready,reference_valid,reference_private,reference_count,reference_empty,reference_fault})
   $fatal(1,"fault partition changed original controls");
 if(output_private_valid===1 && output_data!==reference_data)$fatal(1,"changed owned payload");
 expected_local=resetn && (reference.fault_q || abort_epoch!==0 ||
   (cancel_now!==0 && cancel_now!==1) || (input_valid!==0 && input_valid!==1) ||
   (output_ready!==0 && output_ready!==1) || reference_count>2);
 if(local_fault!==expected_local)$fatal(1,"local fault partition mismatch");
 if(resetn && cancel_now===1 && !expected_local)begin
   external_only=external_only+1;
   if(fault!==1 || output_valid!==0)$fatal(1,"external cancellation lost immediate veto");
 end
 if(resetn && cancel_now!==0 && cancel_now!==1)malformed_cancel=malformed_cancel+1;
 if(resetn && reference.fault_q)sticky_checks=sticky_checks+1;
 partition_checks=partition_checks+1;
end
endtask
'''
    bench=bench.replace('task compare;\nbegin','task compare;\nbegin\n compare_partition;',1)
    bench=bench.replace(' $finish;', ''' if(partition_checks<10000 || external_only<3 || malformed_cancel<3 || sticky_checks<3)
   $fatal(1,"vacuous fault partition test");
 $display("LOCAL_FAULT_COMPONENT_PASS checks=%0d external_only=%0d malformed=%0d sticky=%0d",partition_checks,external_only,malformed_cancel,sticky_checks);
 $finish;''',1).replace('\nendmodule','\n'+extra+'\nendmodule',1)
    (tmp_path/'local.v').write_text(source);(tmp_path/'tb.sv').write_text(bench)
    built=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'local.v'),str(RTL/'starlink_pss_replay_capacity_ring.v'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(built.stdout+built.stderr);assert built.returncode==0,built.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutation=='none':assert result.returncode==0 and 'LOCAL_FAULT_COMPONENT_PASS' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
