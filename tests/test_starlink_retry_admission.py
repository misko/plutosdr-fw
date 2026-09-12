"""Held request retries and one-shot consumption; not a receiver timing claim."""
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import retry_admission_transform as transform
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def test_exact_top_delta_and_current_fences():
    a=(RTL/'starlink_pss_fft_private_replay_sequence_impl.v').read_text()
    b=(RTL/'starlink_pss_fft_retry_admission_impl.v').read_text()
    assert transform.transform(a,transform.TOP_CHANGES)==b
    assert transform.undo(b,transform.TOP_CHANGES)==a
    for declaration in ['assign job_ready =','wire product_commit_authorized =',
                        'wire replay_publication_fault =','assign registered_quarantine =']:
        assert a.split(declaration)[1].split(';')[0]==b.split(declaration)[1].split(';')[0]
    assert 'wire admission_request = CERTIFIED_ADMISSION && job_valid;' in b

@pytest.mark.parametrize('mutation',['none','no_retry','repeat_consume','no_request','no_quarantine','unknown_good'])
def test_held_request_retry_and_controls(tmp_path,mutation):
    source=(RTL/'starlink_pss_admission_retry_certificate.v').read_text()
    changes={
      'no_retry':('(!snapshot_valid || !sampled_good)','(!snapshot_valid)'),
      'repeat_consume':('consumed <= 1;', 'consumed <= 0;'),
      'no_request':('resetn && request &&','resetn &&'),
      'no_quarantine':('request && !quarantine &&','request &&'),
      'unknown_good':("((&snapshot_good) === 1'b1)","(snapshot_good !== 6'b0)"),
    }
    if mutation!='none':
        old,new=changes[mutation];assert source.count(old)==1;source=source.replace(old,new,1)
    (tmp_path/'dut.v').write_text(source)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
                          str(tmp_path/'dut.v'),str(RTL/'tb_retry_admission_certificate.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stdout+build.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutation=='none':
        assert result.returncode==0 and 'RETRY_ADMISSION_COMPONENT_PASS vectors=4096 accepted_once=4096 control_boundaries=4' in result.stdout,result.stdout
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout
