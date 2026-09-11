"""Reject missing or weakened whole-handoff evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('heldhandoff_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-heldhandoff-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_heldhandoff_evidence(recorded):
    root,_=recorded;result=experiment.audit_heldhandoff_sim(root)
    assert result['numerical_rows']==64512 and result['heldhandoff']['exact_offers']
    assert result['heldhandoff']['immediate_veto'] and len(result['heldhandoff']['boundaries'])==6
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','checks','replays','unchecked','veto','fresh_reads','fresh_release'])
def test_weakened_heldhandoff_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_HELDHANDOFF_CASE_PASS boundary=5 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_HELDHANDOFF_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change in ('checks','replays'):
        text=text.replace(terminal,re.sub(r'\b'+change+r'=\d+',f'{change}='+('999' if change=='checks' else '17'),terminal))
    else:
        before,after={'unchecked':('exact_offers=1','exact_offers=0'),'veto':('immediate_veto=1','immediate_veto=0'),
            'fresh_reads':('fresh_reads=512','fresh_reads=511'),'fresh_release':('fresh_releases=1','fresh_releases=0')}[change]
        target=case if change.startswith('fresh_') else terminal
        text=text.replace(target,target.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_heldhandoff_sim(root)
