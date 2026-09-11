"""Fail closed on incomplete private sequence actual-FFT evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sequence_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-sequence-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_sequence_evidence(recorded):
    root,_=recorded;result=experiment.audit_sequence_sim(root)
    assert result['numerical_rows']==64512
    assert result['sequence']['next_block_checked'] and result['sequence']['quarantine_checked']
    assert result['sequence']['advances']==9216 and result['sequence']['finals']==18
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','duplicate_terminal','missing_cycles','advances','holds','finals','wrong_final','leak','unchecked'])
def test_weakened_sequence_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in ('missing_case','missing_cycles'):
        prefix='STAGED_SEQUENCE_CASE_PASS boundary=5 ' if change=='missing_case' else 'STAGED_SEQUENCE_CYCLES_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    elif change=='duplicate_terminal':
        text+='\n'+next(line for line in text.splitlines() if line.startswith('STAGED_SEQUENCE_PASS '))+'\n'
    elif change in ('advances','holds','finals'):
        line=next(line for line in text.splitlines() if line.startswith('STAGED_SEQUENCE_CYCLES_PASS '))
        modified,count=re.subn(r'\b'+change+r'=\d+',change+'='+str({'advances':9215,'holds':999,'finals':17}[change]),line)
        assert count==1;text=text.replace(line,modified)
    else:
        before,after={
            'wrong_final':('boundary=5 private_advance=1 final=1','boundary=5 private_advance=1 final=0'),
            'leak':('boundary=5 private_advance=1 final=1 reads=0 releases=0','boundary=5 private_advance=1 final=1 reads=1 releases=0'),
            'unchecked':('next_block_checked=1 quarantine_checked=1','next_block_checked=0 quarantine_checked=1'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_sequence_sim(root)
