"""Reject incomplete private-final capture evidence from actual FFT runs."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('finalcapture_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-finalcapture-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_finalcapture_evidence(recorded):
    root,_=recorded;result=experiment.audit_finalcapture_sim(root)
    assert result['numerical_rows']==64512
    assert result['finalcapture']['original_payload_checked']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing','duplicate','loads','holds','accepts','fault_loads','unchecked','missing_parent','late_error'])
def test_weakened_finalcapture_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    line=next(row for row in text.splitlines() if row.startswith('STAGED_FINALCAPTURE_PASS '))
    if change=='missing':text=text.replace(line,'')
    elif change=='duplicate':text+='\n'+line+'\n'
    elif change=='late_error':text+='\nFATAL: after success\n'
    elif change=='unchecked':text=text.replace('original_payload_checked=1','original_payload_checked=0')
    elif change=='missing_parent':text=text.replace('STAGED_CAPTURE_PASS cases=3 private_load_checked=1 held_until_release=1','')
    else:
        limit={'loads':999,'holds':999,'accepts':17,'fault_loads':99}[change]
        altered,count=re.subn(r'\b'+change+r'=\d+',change+'='+str(limit),line)
        assert count==1;text=text.replace(line,altered)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_finalcapture_sim(root)
