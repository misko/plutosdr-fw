"""Evidence controls for inverse final-validation staging, not new RF tests."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('final_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-final-actual-v3'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_final_validation_evidence(recorded):
    root,_=recorded;result=experiment.audit_final_sim(root)
    assert result['numerical_rows']==64512
    assert result['final']=={
        'boundaries':[(str(n),str(int(n==1 or n>=4)),str(512 if n>=6 else 0),str(int(n>=6))) for n in range(8)],
        'partition_checked':True,'fault_consume_checked':True,'held_final_rewrites':18}
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','missing_rewrites','rewrite_count','partition','fault_consume','late_reads','stalled_release','veto'])
def test_incomplete_final_validation_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change.startswith('missing_'):
        prefix={'missing_case':'STAGED_FINAL_CASE_PASS boundary=5 ',
                'missing_terminal':'STAGED_FINAL_PASS ',
                'missing_rewrites':'STAGED_FINAL_REWRITES_PASS '}[change]
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'rewrite_count':('STAGED_FINAL_REWRITES_PASS words=18','STAGED_FINAL_REWRITES_PASS words=19'),
            'partition':('STAGED_FINAL_PASS cases=8 partition_checked=1','STAGED_FINAL_PASS cases=8 partition_checked=0'),
            'fault_consume':('STAGED_FINAL_CASE_PASS boundary=1 private_consume=1','STAGED_FINAL_CASE_PASS boundary=1 private_consume=0'),
            'late_reads':('STAGED_FINAL_CASE_PASS boundary=6 private_consume=1 reads=512','STAGED_FINAL_CASE_PASS boundary=6 private_consume=1 reads=511'),
            'stalled_release':('STAGED_FINAL_CASE_PASS boundary=7 private_consume=1 reads=512 releases=1','STAGED_FINAL_CASE_PASS boundary=7 private_consume=1 reads=512 releases=0'),
            'veto':('STAGED_FINAL_CASE_PASS boundary=4 private_consume=1 reads=0','STAGED_FINAL_CASE_PASS boundary=4 private_consume=1 reads=1'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_final_sim(root)
