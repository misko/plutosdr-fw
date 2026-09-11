"""Reject incomplete descriptor-snapshot cancellation evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('certification_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    sim=tmp_path/SIM;sim.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-certification-actual-v1'/SIM/name,sim/name)
    return tmp_path,sim

def test_complete_certification_evidence(recorded):
    root,_=recorded;result=experiment.audit_certification_sim(root)
    assert result['numerical_rows']==64512
    assert result['certification']['snapshot_cancelled'] and result['certification']['consume_cancelled']
    assert result['certification']['fresh_recovery']
    assert not result['physical_signoff'] and not result['continuous_rx']

@pytest.mark.parametrize('change',['missing_case','missing_terminal','duplicate_cycles','checks','differences','stale_read','fresh_read','fresh_release','unchecked'])
def test_weakened_certification_evidence_rejected(recorded,change):
    root,sim=recorded;path=sim/'simulate.log';text=path.read_text()
    if change.startswith('missing_'):
        prefix='STAGED_CERTIFICATION_CASE_PASS boundary=5 ' if change=='missing_case' else 'STAGED_CERTIFICATION_PASS '
        assert any(line.startswith(prefix) for line in text.splitlines())
        text='\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    elif change=='duplicate_cycles':
        text+='\n'+next(line for line in text.splitlines() if line.startswith('STAGED_CERTIFICATION_CYCLES_PASS '))+'\n'
    elif change in ('checks','differences'):
        line=next(line for line in text.splitlines() if line.startswith('STAGED_CERTIFICATION_CYCLES_PASS '))
        field='checks' if change=='checks' else 'private_differences'
        changed,count=re.subn(r'\b'+field+r'=\d+',field+'='+str(999 if change=='checks' else 1),line)
        assert count==1;text=text.replace(line,changed)
    else:
        before,after={
            'stale_read':('boundary=0 stale_starts=0 stale_reads=0','boundary=0 stale_starts=0 stale_reads=1'),
            'fresh_read':('fresh_reads=512 fresh_releases=1','fresh_reads=511 fresh_releases=1'),
            'fresh_release':('fresh_reads=512 fresh_releases=1','fresh_reads=512 fresh_releases=0'),
            'unchecked':('snapshot_cancelled=1 consume_cancelled=1','snapshot_cancelled=1 consume_cancelled=0'),
        }[change]
        assert before in text;text=text.replace(before,after,1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_certification_sim(root)
