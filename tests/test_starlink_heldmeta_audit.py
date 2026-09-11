"""Reject incomplete live original-bank comparison evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('heldmeta_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-heldmeta-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_heldmeta_evidence(recorded):
    root,_=recorded;result=experiment.audit_heldmeta_sim(root)
    assert result['numerical_rows']==64512 and result['heldmeta']['exact_bank']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing','duplicate','checks','firsts','finals','replays','reads','stalls','unchecked'])
def test_weakened_heldmeta_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_HELDMETA_PASS '))
    if change=='missing':text=text.replace(terminal,'')
    elif change=='duplicate':text+='\n'+terminal+'\n'
    elif change=='unchecked':text=text.replace(terminal,terminal.replace('exact_bank=1','exact_bank=0'))
    else:
        limit={'checks':999,'firsts':17,'finals':35,'replays':17,'reads':9215,'stalls':999}[change]
        text=text.replace(terminal,re.sub(r'\b'+change+r'=\d+',f'{change}={limit}',terminal))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_heldmeta_sim(root)
