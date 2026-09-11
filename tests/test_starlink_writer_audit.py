"""Audit controls for the captured writer-descriptor validation stage."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('writer_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-replay-actual-v2'/SIM/name,sim/name)
    return tmp_path,sim

def test_writer_pending_fence_evidence(recorded):
    root,_=recorded;result=experiment.audit_writer_sim(root)
    assert result['numerical_rows']==64512
    assert result['writer']=={'boundaries':list(map(str,range(4))),'pending_fenced':True}
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','pending_fence','publication','release'])
def test_invalid_writer_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in {'missing_case','missing_terminal'}:
        prefix='STAGED_WRITER_CASE_PASS boundary=3 ' if change=='missing_case' else 'STAGED_WRITER_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'pending_fence':('pending_fenced=1','pending_fenced=0'),
            'publication':('STAGED_WRITER_CASE_PASS boundary=0 publications=0','STAGED_WRITER_CASE_PASS boundary=0 publications=1'),
            'release':('STAGED_WRITER_CASE_PASS boundary=0 publications=0 releases=0','STAGED_WRITER_CASE_PASS boundary=0 publications=0 releases=1'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_writer_sim(root)
