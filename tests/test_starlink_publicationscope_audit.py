"""Require retained fault vetoes, original authorization equality and recovery."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publicationscope_audit',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-publicationscope-actual-v2'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_publication_scope_evidence(recorded):
    root,_=recorded;result=experiment.audit_publicationscope_sim(root)
    assert result['numerical_rows']==64512 and result['publicationscope']['authorization_exact']
    assert not result['continuous_rx'] and not result['physical_signoff']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','checks',
                                 'live','unchecked','publication','fresh_reads','fresh_release'])
def test_incomplete_publication_scope_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_PUBLICATION_SCOPE_CASE_PASS boundary=5 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_PUBLICATION_SCOPE_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change in ('checks','live'):
        text=text.replace(terminal,re.sub(change+r'=\d+',change+'=1',terminal))
    elif change=='unchecked':text=text.replace(terminal,terminal.replace('authorization_exact=1','authorization_exact=0'))
    else:
        before,after={'publication':('publications=0','publications=1'),
                      'fresh_reads':('fresh_reads=512','fresh_reads=511'),
                      'fresh_release':('fresh_releases=1','fresh_releases=0')}[change]
        text=text.replace(case,case.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_publicationscope_sim(root)
