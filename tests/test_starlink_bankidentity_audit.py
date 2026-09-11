"""Reject incomplete actual FFT bank-local checker evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bankidentity_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-bankidentity-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_bankidentity_evidence(recorded):
    root,_=recorded;result=experiment.audit_bankidentity_sim(root)
    assert result['numerical_rows']==64512 and len(result['bankidentity']['boundaries'])==4
    assert result['bankidentity']['checker_exact'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','checks',
                                 'forward','inverse','unchecked','fresh_reads','fresh_release'])
def test_incomplete_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_BANKIDENTITY_CASE_PASS owner=1 selected=1 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_BANKIDENTITY_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change in ('checks','forward','inverse'):
        text=text.replace(terminal,re.sub(change+r'=\d+',change+'=999',terminal))
    elif change=='unchecked':text=text.replace(terminal,terminal.replace('checker_exact=1','checker_exact=0'))
    else:
        before,after={'fresh_reads':('fresh_reads=512','fresh_reads=511'),
                      'fresh_release':('fresh_releases=1','fresh_releases=0')}[change]
        text=text.replace(case,case.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_bankidentity_sim(root)
