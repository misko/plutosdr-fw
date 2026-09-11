"""Require source-matched actual FFT evidence for final-slot capacity isolation."""
import json
import os
from pathlib import Path
import re
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route

ARTIFACTS=Path(os.environ.get('STARLINK_FINAL_CAPACITY_EVIDENCE','/dev/shm/starlink-final-capacity.vMIiHM'))
MAIN=ARTIFACTS/'sim-v1';AUX=ARTIFACTS/'ack-v1';PREPARED=ARTIFACTS/'prepared-v1'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_complete_actual_pair():
    main=experiment.audit_finalcapacity(MAIN)
    aux=route.verify_ack_auxiliary(AUX,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)
    assert main['numerical_rows']==64512
    for result in [main,aux]:
        assert result['finalcapacity']['no_refill']
        assert result['finalcapacity']['producer_quiet']
        assert result['finalcapacity']['actual_bank_return']
    assert aux['productstage']['boundaries']==[str(n) for n in range(12)]


def fixture(tmp_path,source=AUX):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    shutil.copyfile(source/SIM/'simulate.log',folder/'simulate.log')
    shutil.copyfile(source/'outcome.json',tmp_path/'outcome.json')
    return folder/'simulate.log'


@pytest.mark.parametrize('mutation',['missing','duplicate','short_finals','short_starts',
                                   'no_refill','producer_quiet','actual_bank_return'])
def test_incomplete_capacity_evidence_rejected(tmp_path,mutation):
    path=fixture(tmp_path);text=path.read_text()
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_FINAL_CAPACITY_PASS '))
    if mutation=='missing':text=text.replace(receipt,'',1)
    elif mutation=='duplicate':text+=receipt
    elif mutation.startswith('short_'):
        field=mutation.removeprefix('short_');text=text.replace(receipt,re.sub(field+r'=\d+',field+'=11',receipt),1)
    else:text=text.replace(receipt,receipt.replace(mutation+'=1',mutation+'=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError,match='actual final capacity'):
        experiment.audit_finalcapacity(tmp_path,auxiliary=True)


def test_auxiliary_cannot_omit_capacity_audit(tmp_path):
    fixture(tmp_path);path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['finalcapacity'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='re-audit mismatch'):
        route.verify_ack_auxiliary(tmp_path,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)


def test_main_cannot_omit_compiled_capacity_requirement(tmp_path):
    fixture(tmp_path,MAIN)
    shutil.copyfile(MAIN/SIM/'staged_words.csv',tmp_path/SIM/'staged_words.csv')
    path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['finalcapacity'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled final capacity campaign differ'):
        route.run(tmp_path,ARTIFACTS/'synth-v1',tmp_path/'must-not-route',AUX)
    assert not (tmp_path/'must-not-route').exists()
