"""Require actual private-step/public-veto evidence, not just numerical PASS."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('replay_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-replay-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_replay_authorization_evidence(recorded):
    root,_=recorded;result=experiment.audit_replay_sim(root)
    assert result['numerical_rows']==64512
    assert result['handover']['admissions']==84 and result['handover']['completions']==64
    assert result['replay']['boundaries']==[(str(n),str(int(n<3))) for n in range(5)]
    assert result['replay']['actual_authorization_checked']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','authorization','no_private_step','publication','release'])
def test_invalid_replay_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in {'missing_case','missing_terminal'}:
        prefix='STAGED_REPLAY_CASE_PASS boundary=2 ' if change=='missing_case' else 'STAGED_REPLAY_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'authorization':('actual_authorization_checked=1','actual_authorization_checked=0'),
            'no_private_step':('STAGED_REPLAY_CASE_PASS boundary=0 private_step=1','STAGED_REPLAY_CASE_PASS boundary=0 private_step=0'),
            'publication':('private_step=1 publications=0','private_step=1 publications=1'),
            'release':('private_step=1 publications=0 releases=0','private_step=1 publications=0 releases=1'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_replay_sim(root)
