"""Require both phases and each actual completion-cancellation boundary."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('completion_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture(params=[1,2],ids=['completion-v1','private-rom-v2'])
def recorded(tmp_path,request):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/f'staged-completion-actual-v{request.param}'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_producer_evidence(recorded):
    root,_=recorded;result=experiment.audit_completion_sim(root)
    assert result['numerical_rows']==64512
    assert result['completion']['boundaries']==[(str(n),str(n//3 if n<6 else int(n>=8))) for n in range(10)]
    assert result['completion']['partition_checked']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','partition','phase','reuse','publication','release'])
def test_invalid_completion_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in {'missing_case','missing_terminal'}:
        prefix='STAGED_COMPLETION_CASE_PASS boundary=3 ' if change=='missing_case' else 'STAGED_COMPLETION_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'partition':('STAGED_COMPLETION_PASS cases=10 partition_checked=1','STAGED_COMPLETION_PASS cases=10 partition_checked=0'),
            'phase':('STAGED_COMPLETION_CASE_PASS boundary=3 phase=1','STAGED_COMPLETION_CASE_PASS boundary=3 phase=0'),
            'reuse':('reuse_after_cancel=0','reuse_after_cancel=1'),
            'publication':('reuse_after_cancel=0 publications=0','reuse_after_cancel=0 publications=1'),
            'release':('reuse_after_cancel=0 publications=0 releases=0','reuse_after_cancel=0 publications=0 releases=1'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_completion_sim(root)
