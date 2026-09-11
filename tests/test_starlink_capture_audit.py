"""Reject incomplete or weakened private descriptor capture evidence."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capture_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-capture-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_capture_evidence(recorded):
    root,_=recorded;result=experiment.audit_capture_sim(root)
    assert result['numerical_rows']==64512
    assert result['capture']=={
        'boundaries':[('0','512','1'),('1','512','1'),('2','0','0')],
        'loads':32616,'holds':74846,'accepts':18,
        'private_load_checked':True,'held_until_release':True}
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','missing_cycles','loads','holds','accepts','release','veto','freeze'])
def test_incomplete_capture_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change.startswith('missing_'):
        prefix={'missing_case':'STAGED_CAPTURE_CASE_PASS boundary=1 ',
                'missing_terminal':'STAGED_CAPTURE_PASS ',
                'missing_cycles':'STAGED_CAPTURE_CYCLES_PASS '}[change]
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'loads':('loads=32616','loads=999'),
            'holds':('holds=74846','holds=999'),
            'accepts':('accepts=18','accepts=17'),
            'release':('STAGED_CAPTURE_CASE_PASS boundary=1 reads=512 releases=1','STAGED_CAPTURE_CASE_PASS boundary=1 reads=512 releases=0'),
            'veto':('STAGED_CAPTURE_CASE_PASS boundary=2 reads=0 releases=0','STAGED_CAPTURE_CASE_PASS boundary=2 reads=1 releases=0'),
            'freeze':('held_until_release=1','held_until_release=0'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_capture_sim(root)
