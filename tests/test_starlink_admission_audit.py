"""Require the actual certificate-cancellation evidence, not just FFT numerics."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('admission_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture(params=[2,3],ids=['clocked-facts-v2','held-lookup-v3'])
def recorded(tmp_path,request):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/f'staged-admission-actual-v{request.param}'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_admission_evidence(recorded):
    root,_=recorded;result=experiment.audit_admission_sim(root)
    assert result['numerical_rows']==64512
    assert result['handover']['admissions']==59 and result['handover']['completions']==52
    assert result['admission']=={'boundaries':list(map(str,range(6))),'partition_checked':True}
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','partition','start','publication','release'])
def test_invalid_admission_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in {'missing_case','missing_terminal'}:
        prefix='STAGED_ADMISSION_CASE_PASS boundary=3 ' if change=='missing_case' else 'STAGED_ADMISSION_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={'partition':('partition_checked=1','partition_checked=0'),
                      'start':('starts_after_cancel=0','starts_after_cancel=1'),
                      'publication':('starts_after_cancel=0 publications=0','starts_after_cancel=0 publications=1'),
                      'release':('starts_after_cancel=0 publications=0 releases=0','starts_after_cancel=0 publications=0 releases=1')}[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_admission_sim(root)
