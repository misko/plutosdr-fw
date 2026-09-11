"""The split interface must prove exact actual-FFT acceptance before routing."""
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

ARTIFACTS=Path(os.environ.get('STARLINK_SPLIT_CAPACITY_EVIDENCE','/dev/shm/starlink-split-capacity.URCQhd'))
MAIN=ARTIFACTS/'sim-v1';AUX=ARTIFACTS/'ack-v1';PREPARED=ARTIFACTS/'prepared-v1'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_complete_actual_pair():
    main=experiment.audit_splitcapacity(MAIN)
    aux=route.verify_ack_auxiliary(AUX,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)
    assert main['numerical_rows']==64512
    for result in [main,aux]:
        assert result['splitcapacity']['input_ready_exact']
        assert result['splitcapacity']['current_retirement_exact']
    assert aux['productstage']['boundaries']==[str(n) for n in range(12)]


def fixture(tmp_path,source=AUX):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    shutil.copyfile(source/SIM/'simulate.log',folder/'simulate.log')
    shutil.copyfile(source/'outcome.json',tmp_path/'outcome.json')
    return folder/'simulate.log'


@pytest.mark.parametrize('mutation',['missing','duplicate','short_checks','short_nonfinal',
                                   'input_ready_exact','current_retirement_exact'])
def test_incomplete_split_evidence_rejected(tmp_path,mutation):
    path=fixture(tmp_path);text=path.read_text()
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_SPLIT_CAPACITY_PASS '))
    if mutation=='missing':text=text.replace(receipt,'',1)
    elif mutation=='duplicate':text+=receipt
    elif mutation.startswith('short_'):
        field=mutation.removeprefix('short_');text=text.replace(receipt,re.sub(field+r'=\d+',field+'=1',receipt),1)
    else:text=text.replace(receipt,receipt.replace(mutation+'=1',mutation+'=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError,match='split capacity exact acceptance'):
        experiment.audit_splitcapacity(tmp_path,auxiliary=True)


def test_auxiliary_cannot_omit_split_audit(tmp_path):
    fixture(tmp_path);path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['splitcapacity'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='re-audit mismatch'):
        route.verify_ack_auxiliary(tmp_path,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)


def test_main_cannot_omit_compiled_split_requirement(tmp_path):
    fixture(tmp_path,MAIN)
    shutil.copyfile(MAIN/SIM/'staged_words.csv',tmp_path/SIM/'staged_words.csv')
    path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['splitcapacity'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled split capacity campaign differ'):
        route.run(tmp_path,ARTIFACTS/'synth-v1',tmp_path/'must-not-route',AUX)
    assert not (tmp_path/'must-not-route').exists()
