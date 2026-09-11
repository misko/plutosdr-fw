"""Whole forward-return bank before changing the actual receiver controller."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
SOURCE=RTL/'starlink_pss_forward_return_bank.v'

def run(tmp_path,case=0,mutation=None):
    source=SOURCE.read_text()
    changes={
        'seal_bypass':('if (capture_final) state<=WAIT_SEAL;','if (capture_final) state<=REPLAY;'),
        'ready_coupling':('state==CAPTURE && write_count<DEPTH;','state==CAPTURE && write_count<DEPTH && output_ready;'),
        'ordinal':("((capture_position == write_count[ADDRESS_WIDTH-1:0]) !== 1'b1)","1'b0"),
        'metadata':("((capture_descriptor == descriptor) !== 1'b1)","1'b0"),
        'exponent':("(write_count!=0 && ((capture_exponent == exponent) !== 1'b1))","1'b0"),
        'late_abort':('assign fault = resetn && (fault_q || fault_now);','assign fault = resetn && fault_q;'),
        'ram_reset_leak':('state<=IDLE;fault_q<=0;replay_valid<=0;','state<=REPLAY;fault_q<=0;replay_valid<=1;'),
        'read_when_stalled':("(!replay_valid || output_ready===1'b1)","1'b1"),
        'extra_read':('read_count<DEPTH;','read_count<=DEPTH;'),
    }
    if mutation:
        before,after=changes[mutation]
        assert source.count(before)==1
        source=source.replace(before,after,1)
    path=tmp_path/'bank.v';path.write_text(source)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
        str(path),str(RTL/'tb_forward_return_bank.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim'),f'+CASE={case}'],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_full_blocks_stalls_seal_reset_and_throughput(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0,result.stdout+result.stderr
    row=re.search(r'FORWARD_RETURN_BANK_PASS blocks=12 reads=6144 stalls=(\d+) cycles=(\d+) capture_decoupled=1 seal_required=1 reset_cases=3',result.stdout)
    assert row and int(row[1])>100 and int(row[2])>12000,result.stdout

@pytest.mark.parametrize('case',range(1,21))
def test_malformed_or_aborted_block_is_fenced_and_recovers(tmp_path,case):
    result=run(tmp_path,case)
    assert result.returncode==0,result.stdout+result.stderr
    assert f'FORWARD_RETURN_FAULT_PASS case={case} fresh_reads=512 immediate_fence=1 sticky=1' in result.stdout

@pytest.mark.parametrize('mutation,case',[
    ('seal_bypass',0),('ready_coupling',0),('ordinal',3),('metadata',4),
    ('exponent',5),('late_abort',11),('ram_reset_leak',0),('read_when_stalled',0),('extra_read',0)])
def test_unsafe_mutations_rejected(tmp_path,mutation,case):
    result=run(tmp_path,case,mutation)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

def test_existing_actual_runtime_is_unchanged():
    parent=Path('/dev/shm/starlink-scalar-fault.xuB1HWdl/prepared-v1')
    names=(parent/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if (RTL/name).exists():assert (RTL/name).read_bytes()==(parent/name).read_bytes(),name
    assert (RTL/'tb_fft_staged_output.sv').read_bytes()==(parent/'tb_fft_staged_output.sv').read_bytes()
