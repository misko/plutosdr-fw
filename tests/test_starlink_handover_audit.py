"""Audit-negative controls; these do not substitute for actual RTL fault tests."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('handover_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture(params=[(2,6,56,51),(4,7,58,52)],ids=['live-lookup-v2','held-bundle-v4'])
def recorded(tmp_path,request):
    version,fault_cases,admissions,completions=request.param
    actual=ROOT.parent/f'staged-handover-actual-v{version}'
    destination=tmp_path/SIM;destination.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(actual/SIM/name,destination/name)
    return tmp_path,destination,fault_cases,admissions,completions

def test_complete_handover_receipts(recorded):
    output,_,fault_cases,admissions,completions=recorded
    result=experiment.audit_handover_sim(output,fault_cases=fault_cases)
    assert result['numerical_rows']==64512
    assert result['handover']['admissions']==admissions and result['handover']['completions']==completions
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_reset','short_prefix','early_rearm','missing_fault','late_release',
                                  'missing_last_read','missing_timestamp','truncated_timestamp','missing_terminal'])
def test_incomplete_handover_receipts_fail(recorded,change):
    output,sim,fault_cases,_,_=recorded;path=sim/'simulate.log';text=path.read_text()
    if change in {'missing_reset','missing_fault','missing_timestamp','missing_terminal'}:
        prefix={'missing_reset':'STAGED_RESET_PASS side=2 ', 'missing_fault':'STAGED_FAULT_PASS boundary=3 ',
                'missing_timestamp':'STAGED_TIMESTAMP_PASS mode=4 ', 'missing_terminal':'STAGED_HANDOVER_PASS '}[change]
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    else:
        before,after={
            'short_prefix':('aborted_forward_prefix=65','aborted_forward_prefix=63'),
            'early_rearm':('slow_purge_edges=5','slow_purge_edges=0'),
            'late_release':('STAGED_FAULT_PASS boundary=3 no_late_publication=1 releases=0','STAGED_FAULT_PASS boundary=3 no_late_publication=1 releases=1'),
            'missing_last_read':('STAGED_FAULT_PASS boundary=5 no_late_publication=1 releases=0 reads=512','STAGED_FAULT_PASS boundary=5 no_late_publication=1 releases=0 reads=511'),
            'truncated_timestamp':('base=a5a5a5a5a5a5a000','base=00000000a5a5a000'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_handover_sim(output,fault_cases=fault_cases)

def test_campaign_cannot_silently_omit_writer_fault(recorded):
    output,_,fault_cases,_,_=recorded
    with pytest.raises(ValueError):
        experiment.audit_handover_sim(output,fault_cases=7 if fault_cases==6 else 6)
