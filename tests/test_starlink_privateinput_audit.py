"""Reject missing or weakened private input accounting evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('privateinput_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-privateinput-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_privateinput_evidence(recorded):
    root,_=recorded;result=experiment.audit_privateinput_sim(root)
    assert result['numerical_rows']==64512 and result['privateinput']['public_exact']
    assert result['privateinput']['unknown_exact'] and len(result['privateinput']['boundaries'])==5
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','duplicate_case','missing_terminal','checks','quarantined','unchecked','unknown','fresh_reads','fresh_release'])
def test_weakened_privateinput_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    case=next(line for line in text.splitlines() if line.startswith('STAGED_PRIVATEINPUT_CASE_PASS boundary=4 '))
    terminal=next(line for line in text.splitlines() if line.startswith('STAGED_PRIVATEINPUT_PASS '))
    if change=='missing_case':text=text.replace(case,'')
    elif change=='duplicate_case':text+='\n'+case+'\n'
    elif change=='missing_terminal':text=text.replace(terminal,'')
    elif change in ('checks','quarantined'):
        text=text.replace(terminal,re.sub(r'\b'+change+r'=\d+',f'{change}='+('999' if change=='checks' else '399'),terminal))
    else:
        before,after={'unchecked':('public_exact=1','public_exact=0'),'unknown':('unknown_exact=1','unknown_exact=0'),
            'fresh_reads':('fresh_reads=512','fresh_reads=511'),'fresh_release':('fresh_releases=1','fresh_releases=0')}[change]
        target=case if change.startswith('fresh_') else terminal
        text=text.replace(target,target.replace(before,after))
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_privateinput_sim(root)
