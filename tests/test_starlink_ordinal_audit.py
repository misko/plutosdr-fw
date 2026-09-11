"""Reject incomplete actual-FFT private ordinal evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ordinal_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-ordinal-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_ordinal_evidence(recorded):
    root,_=recorded;result=experiment.audit_ordinal_sim(root)
    assert result['numerical_rows']==64512
    ordinal=result['ordinal']
    assert ordinal['boundaries']==[(str(n),str(512 if n>=3 else 0),str(int(n>=3))) for n in range(5)]
    assert ordinal['advances']==9216 and ordinal['holds']>=1000
    assert ordinal['public_acceptance_preserved'] and ordinal['quarantine_checked']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','missing_cycles','advances','holds','public_acceptance','private_advance','reads','release'])
def test_incomplete_ordinal_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change.startswith('missing_'):
        prefix={'missing_case':'STAGED_ORDINAL_CASE_PASS boundary=2 ',
                'missing_terminal':'STAGED_ORDINAL_PASS ',
                'missing_cycles':'STAGED_ORDINAL_CYCLES_PASS '}[change]
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    elif change=='holds':
        text,n=re.subn(r'(STAGED_ORDINAL_CYCLES_PASS advances=9216 holds=)\d+',r'\g<1>999',text)
        assert n==1
    else:
        before,after={
            'advances':('STAGED_ORDINAL_CYCLES_PASS advances=9216','STAGED_ORDINAL_CYCLES_PASS advances=9215'),
            'public_acceptance':('public_acceptance_preserved=1','public_acceptance_preserved=0'),
            'private_advance':('STAGED_ORDINAL_CASE_PASS boundary=0 private_advance=1','STAGED_ORDINAL_CASE_PASS boundary=0 private_advance=0'),
            'reads':('STAGED_ORDINAL_CASE_PASS boundary=1 private_advance=1 reads=0','STAGED_ORDINAL_CASE_PASS boundary=1 private_advance=1 reads=1'),
            'release':('STAGED_ORDINAL_CASE_PASS boundary=4 private_advance=1 reads=512 releases=1','STAGED_ORDINAL_CASE_PASS boundary=4 private_advance=1 reads=512 releases=0'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_ordinal_sim(root)
