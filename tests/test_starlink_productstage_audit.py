"""Source-matched real FFT proof is required for the integrated product stage."""
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

ARTIFACTS=Path(os.environ.get('STARLINK_PRODUCT_STAGE_EVIDENCE','/dev/shm/starlink-product-integrated.1FSkuP'))
MAIN=ARTIFACTS/'sim-v2';AUX=ARTIFACTS/'ack-v2';PREPARED=ARTIFACTS/'prepared-v2'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_complete_actual_main_auxiliary_pair():
    main=experiment.audit_productstage(MAIN)
    aux=route.verify_ack_auxiliary(AUX,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)
    assert main['numerical_rows']==64512 and main['productstage']['private_conservation']
    assert aux['productstage']['boundaries']==[str(n) for n in range(12)]


def fixture(tmp_path):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    shutil.copyfile(AUX/SIM/'simulate.log',folder/'simulate.log')
    shutil.copyfile(AUX/'outcome.json',tmp_path/'outcome.json')
    return folder/'simulate.log'


@pytest.mark.parametrize('mutation',['missing_case','duplicate_case','short_read','short_release',
                                    'missing_receipt','duplicate_receipt','short_pushes','short_pops',
                                    'short_checks','short_updates','short_holds','lost_identity','lost_conservation'])
def test_incomplete_product_stage_auxiliary_rejected(tmp_path,mutation):
    path=fixture(tmp_path);text=path.read_text()
    case=next(line for line in text.splitlines(True) if line.startswith('STAGED_PRODUCT_STAGE_CASE_PASS boundary=0 '))
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_PRODUCT_STAGE_PASS '))
    if mutation=='missing_case':text=text.replace(case,'',1)
    elif mutation=='duplicate_case':text+=case
    elif mutation=='short_read':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    elif mutation=='short_release':text=text.replace(case,case.replace('fresh_releases=1','fresh_releases=0'),1)
    elif mutation=='missing_receipt':text=text.replace(receipt,'',1)
    elif mutation=='duplicate_receipt':text+=receipt
    elif mutation.startswith('short_'):
        field=mutation.removeprefix('short_');text=text.replace(receipt,re.sub(field+r'=\d+',field+'=1',receipt),1)
    elif mutation=='lost_identity':text=text.replace(receipt,receipt.replace('original_identity=1','original_identity=0'),1)
    else:text=text.replace(receipt,receipt.replace('private_conservation=1','private_conservation=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_productstage(tmp_path,auxiliary=True)


def test_auxiliary_cannot_drop_required_product_audit(tmp_path):
    fixture(tmp_path);path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['productstage'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='re-audit mismatch'):
        route.verify_ack_auxiliary(tmp_path,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)


def test_main_cannot_hide_compiled_product_requirement(tmp_path):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(MAIN/SIM/name,folder/name)
    outcome=json.loads((MAIN/'outcome.json').read_text());del outcome['audit']['productstage']
    (tmp_path/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled product stage campaign differ'):
        route.run(tmp_path,ARTIFACTS/'synth-v2',tmp_path/'must-not-route',AUX)
    assert not (tmp_path/'must-not-route').exists()
