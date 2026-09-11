"""Actual FFT phase evidence must include stalls, unread overlap and recovery."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preflightpublication_audit',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-preflightpublication-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_phase_evidence(recorded):
    root,_=recorded;result=experiment.audit_preflightpublication_sim(root)
    assert result['numerical_rows']==64512 and result['preflightpublication']['phase_exact']
    assert not result['continuous_rx'] and not result['physical_signoff']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','short_pause',
                                 'checks','replay','unread','unchecked','fresh_reads','fresh_release'])
def test_incomplete_phase_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_PREFLIGHT_PUBLICATION_CASE_PASS boundary=2 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_PREFLIGHT_PUBLICATION_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change=='short_pause':text=text.replace(case,re.sub(r'paused=\d+','paused=127',case))
    elif change in ('checks','replay','unread'):
        text=text.replace(terminal,re.sub(change+r'=\d+',change+'=1',terminal))
    elif change=='unchecked':text=text.replace(terminal,terminal.replace('phase_exact=1','phase_exact=0'))
    else:
        before,after={'fresh_reads':('fresh_reads=512','fresh_reads=511'),
                      'fresh_release':('fresh_releases=1','fresh_releases=0')}[change]
        text=text.replace(case,case.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_preflightpublication_sim(root)
