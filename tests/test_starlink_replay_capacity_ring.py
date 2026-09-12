"""Alternate-slot storage must preserve two-slot public/private-valid behavior."""
from pathlib import Path
import subprocess
import pytest
from tests.test_starlink_replay_capacity_buffer import BENCH,ROOT,RTL
import sys
sys.path.insert(0,str(ROOT/'tools'))
import replay_capacity_ring_transform as transform

RING=RTL/'starlink_pss_replay_capacity_ring.v'
def test_exact_top_delta():
    a=(RTL/'starlink_pss_fft_replay_capacity_buffer_impl.v').read_text()
    b=(RTL/'starlink_pss_fft_replay_capacity_ring_impl.v').read_text()
    assert transform.transform(a,transform.TOP_CHANGES)==b
    assert transform.undo(b,transform.TOP_CHANGES)==a

@pytest.mark.parametrize('mutation',['none','ready_bypass','ignore_cancel','write_wrong_slot','reset_valid'])
def test_ring_public_equivalence_and_mutations(tmp_path,mutation):
    source=RING.read_text()
    if mutation=='ready_bypass':source=source.replace('!fault_q && count!=2','!fault_q && (count!=2 || output_ready)',1)
    elif mutation=='ignore_cancel':source=source.replace("(cancel_now !== 1'b0)","1'b0",1)
    elif mutation=='write_wrong_slot':source=source.replace('if(push && write_slot)slot1<=input_data;','if(push && write_slot)slot0<=input_data;',1)
    elif mutation=='reset_valid':source=source.replace('count<=0;read_slot<=0;write_slot<=0;fault_q<=0;','count<=1;read_slot<=0;write_slot<=0;fault_q<=0;',1)
    bench=BENCH.replace('__TIMESCALE__',chr(96)+'timescale 1ns/1ps').replace('starlink_pss_replay_capacity_buffer dut(.*);','starlink_pss_replay_capacity_ring dut(.*);')
    insert=r'''
wire reference_ready,reference_valid,reference_private,reference_empty,reference_fault;
wire [120:0] reference_data;wire [1:0] reference_count;
starlink_pss_replay_capacity_buffer reference(
 .clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),.cancel_now(cancel_now),
 .input_valid(input_valid),.input_ready(reference_ready),.input_data(input_data),
 .output_valid(reference_valid),.output_private_valid(reference_private),
 .output_ready(output_ready),.output_data(reference_data),.occupancy(reference_count),
 .empty(reference_empty),.fault(reference_fault));
task compare_original;
begin
 if({input_ready,output_valid,output_private_valid,occupancy,empty,fault} !==
    {reference_ready,reference_valid,reference_private,reference_count,reference_empty,reference_fault})
   $fatal(1,"ring changed original controls");
 if(output_private_valid===1 && output_data!==reference_data)$fatal(1,"ring changed owned payload");
end
endtask
'''
    bench=bench.replace('task compare;\nbegin','task compare;\nbegin\n compare_original;',1).replace('\nendmodule','\n'+insert+'\nendmodule',1)
    (tmp_path/'ring.v').write_text(source);(tmp_path/'tb.sv').write_text(bench)
    built=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'ring.v'),str(RTL/'starlink_pss_replay_capacity_buffer.v'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(built.stdout+built.stderr);assert built.returncode==0,built.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutation=='none':assert result.returncode==0 and 'REPLAY_CAPACITY_COMPONENT_PASS' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

def test_payload_write_enables_do_not_use_current_downstream_capacity():
    text=RING.read_text()
    block=text.split('  always @(posedge clk)begin',1)[1]
    assert block.count('if(push &&')==2 and 'pop' not in block and 'output_ready' not in block
    assert 'wire push=input_valid && input_ready;' in text
    assert 'assign input_ready=resetn && !fault_q && count!=2;' in text
