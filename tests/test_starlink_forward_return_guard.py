"""New ownership/readiness contract before modifying receiver wiring."""
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def run(tmp_path,case,mutation=None,mode=0):
    bench=(RTL/'tb_forward_return_guard.sv').read_text()
    if mutation=='raw_capacity':
        bench=bench.replace('(bank_busy && !bank_fault)','bank_capture_ready',1)
    if mutation=='early_ack':
        bench=bench.replace('wait_product ? product_owned :','wait_product ? 1\'b1 :',1)
    (tmp_path/'tb.sv').write_text(bench)
    command=['iverilog','-g2012','-s','tb','-P',f'tb.GUARD_MODE={mode}','-o',str(tmp_path/'sim'),
        str(RTL/'starlink_pss_result_guard_owner_view.v'),str(RTL/'starlink_pss_forward_return_bank.v'),str(tmp_path/'tb.sv')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim'),f'+CASE={case}'],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('case',range(6))
@pytest.mark.parametrize('mode',[0,1])
def test_local_ownership_final_qualification_and_real_guard_ack(tmp_path,case,mode):
    result=run(tmp_path,case,mode=mode)
    assert result.returncode==0,result.stdout+result.stderr
    assert f'FORWARD_RETURN_GUARD_PASS case={case} reads=512 commits=1 acks=1 late_final_ready=1 product_ack_required=1 mode={mode}' in result.stdout

@pytest.mark.parametrize('mutation',['raw_capacity','early_ack'])
@pytest.mark.parametrize('mode',[0,1])
def test_unsafe_ready_wiring_rejected(tmp_path,mutation,mode):
    result=run(tmp_path,1,mutation,mode)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
