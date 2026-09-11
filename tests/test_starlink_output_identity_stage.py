from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import output_identity_transform as transform
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

@pytest.mark.parametrize('old,new,changes',[
    ('starlink_pss_fft_buffered_forward_impl.v','starlink_pss_fft_output_identity_impl.v',transform.TOP_CHANGES),
    ('starlink_pss_output_reset_receipt.v','starlink_pss_output_mailbox_staged_identity.v',transform.BANK_CHANGES)])
def test_exact_derived_modules(old,new,changes):
    original=(RTL/old).read_text();candidate=(RTL/new).read_text()
    assert transform.transform(original,changes)==candidate
    assert transform.undo(candidate,changes)==original

@pytest.mark.parametrize('case',range(10))
def test_stage_bank_faults_and_recovery(tmp_path,case):
    bench=RTL/'tb_output_identity_bank.sv'
    command=['iverilog','-g2012','-s','tb','-Ptb.CASE='+str(case),'-o',str(tmp_path/'sim'),str(bench),
             str(RTL/'starlink_pss_product_identity_split_capacity.v'),str(RTL/'starlink_pss_output_mailbox_staged_identity.v')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
    (tmp_path/'bench.sv').write_bytes(bench.read_bytes())
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert f'OUTPUT_IDENTITY_BANK_PASS case={case} fresh_reads=512' in result.stdout
