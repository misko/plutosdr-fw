"""Actual private engine capture audit rejects incomplete or contradictory proof."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('enginecapture_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
ACTUAL=ROOT.parent/'staged-enginecapture-actual-v1'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def fixture(tmp_path):
    target=tmp_path/SIM;target.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ACTUAL/SIM/name,target/name)
    return target/'simulate.log'


def test_actual_engine_capture_proof(tmp_path):
    fixture(tmp_path);result=experiment.audit_enginecapture_sim(tmp_path)
    assert result['enginecapture']['boundaries']==[str(n) for n in range(6)]
    assert result['numerical_rows']==64512
    assert not result['physical_signoff'] and not result['continuous_rx']


@pytest.mark.parametrize('mutant',['missing_case','duplicate_case','short_recovery','missing_release',
                                  'stale_reads','short_checks','no_private_difference','lost_owned_proof'])
def test_engine_capture_evidence_mutants(tmp_path,mutant):
    log=fixture(tmp_path);text=log.read_text()
    case=next(s for s in text.splitlines(True) if s.startswith('STAGED_ENGINE_CAPTURE_CASE_PASS boundary=0 '))
    receipt=next(s for s in text.splitlines(True) if s.startswith('STAGED_ENGINE_CAPTURE_PASS '))
    if mutant=='missing_case':text=text.replace(case,'',1)
    elif mutant=='duplicate_case':text+=case
    elif mutant=='short_recovery':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    elif mutant=='missing_release':text=text.replace(case,case.replace('fresh_releases=1','fresh_releases=0'),1)
    elif mutant=='stale_reads':text=text.replace(case,case.replace('stale_reads=0','stale_reads=1'),1)
    elif mutant=='short_checks':text=text.replace(receipt,re.sub(r'checks=\d+','checks=1',receipt),1)
    elif mutant=='no_private_difference':text=text.replace(receipt,re.sub(r'private_differences=\d+','private_differences=0',receipt),1)
    else:text=text.replace(receipt,receipt.replace('owned_exact=1','owned_exact=0'),1)
    log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_enginecapture_sim(tmp_path)
