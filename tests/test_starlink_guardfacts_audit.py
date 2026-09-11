"""Reject incomplete exact guard-fact certificate evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guardfacts_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-guardfacts-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_guardfacts_evidence(recorded):
    root,_=recorded;result=experiment.audit_guardfacts_sim(root)
    assert result['numerical_rows']==64512
    assert len(result['guardfacts']['boundaries'])==32
    assert result['guardfacts']['exact_certificates'] and result['guardfacts']['fresh_recovery']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','cycles','starts','reads','unchecked','fresh_reads','fresh_release'])
def test_weakened_guardfacts_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_GUARDFACTS_CASE_PASS gate=1 owner=1 fact=7 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_GUARDFACTS_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change=='cycles':text=text.replace(terminal,re.sub(r'cycles=\d+','cycles=999',terminal))
    elif change in ('starts','reads'):
        text=text.replace(case,case.replace(change+'=0',change+'=1'))
    else:
        before,after={
            'unchecked':('exact_certificates=1','exact_certificates=0'),
            'fresh_reads':('fresh_reads=512','fresh_reads=511'),
            'fresh_release':('fresh_releases=1','fresh_releases=0'),
        }[change]
        assert before in terminal;text=text.replace(terminal,terminal.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_guardfacts_sim(root)
