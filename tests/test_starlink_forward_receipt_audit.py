"""Actual forward receipt evidence must include transition checks and recovery."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

import pytest
from tests.test_starlink_product_stage_integration import undo_product_stage_bench

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route

ARTIFACTS=Path(os.environ.get('STARLINK_RECEIPT_EVIDENCE','/dev/shm/starlink-forward-receipt.7z0zKX'))
MAIN=ARTIFACTS/'sim-v1'
AUX=ARTIFACTS/'ack-v1'
PREPARED=ARTIFACTS/'prepared-v1'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_existing_bench_and_deadlines_exact_after_inverse():
    parent=ROOT.parent/'staged-ackcombined-prepared-v1'
    assert experiment.sha(parent/'SHA256SUMS')=='ecb302eab62a44de27a6b27d4d0414effe487e270498d2adb1ec83f79d01a38a'
    text=(ROOT/'hdl/library/starlink_pss_acquisition/staged_control/tb_fft_staged_output.sv').read_text()
    text=undo_product_stage_bench(text)
    for label in ['WITNESS','BOUNDARIES','AUXILIARY']:
        text,count=re.subn(r' *// BEGIN FORWARD RECEIPT '+label+r'\n.*? *// END FORWARD RECEIPT '+label+r'\n','',text,flags=re.S)
        assert count==1
    text=text.replace('    report_forward_receipt; // FORWARD RECEIPT MAIN\n','',1)
    assert text==(parent/'tb_fft_staged_output.sv').read_text()


def test_actual_main_and_auxiliary_are_source_matched():
    main=experiment.audit_forwardreceipt(MAIN)
    auxiliary=route.verify_ack_auxiliary(AUX,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)
    assert main['numerical_rows']==64512
    assert main['forwardreceipt']['ack_exact'] and main['forwardreceipt']['auxiliary_required']
    assert auxiliary['forwardreceipt']['boundaries']==[str(n) for n in range(12)]
    assert auxiliary['forwardreceipt']['publication_subset']


def aux_fixture(tmp_path):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    shutil.copyfile(AUX/SIM/'simulate.log',folder/'simulate.log')
    shutil.copyfile(AUX/'outcome.json',tmp_path/'outcome.json')
    return folder/'simulate.log'


@pytest.mark.parametrize('mutation',['missing_case','duplicate_case','short_reads','short_release',
                                    'missing_receipt','duplicate_receipt','short_checks','short_pending',
                                    'lost_ack_equality','lost_publication_subset'])
def test_incomplete_auxiliary_rejected(tmp_path,mutation):
    path=aux_fixture(tmp_path);text=path.read_text()
    case=next(line for line in text.splitlines(True) if line.startswith('STAGED_FORWARD_RECEIPT_CASE_PASS boundary=0 '))
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_FORWARD_RECEIPT_PASS '))
    if mutation=='missing_case':text=text.replace(case,'',1)
    elif mutation=='duplicate_case':text+=case
    elif mutation=='short_reads':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    elif mutation=='short_release':text=text.replace(case,case.replace('fresh_releases=1','fresh_releases=0'),1)
    elif mutation=='missing_receipt':text=text.replace(receipt,'',1)
    elif mutation=='duplicate_receipt':text+=receipt
    elif mutation=='short_checks':text=text.replace(receipt,re.sub(r'checks=\d+','checks=1',receipt),1)
    elif mutation=='short_pending':text=text.replace(receipt,re.sub(r'pending=\d+','pending=9',receipt),1)
    elif mutation=='lost_ack_equality':text=text.replace(receipt,receipt.replace('ack_exact=1','ack_exact=0'),1)
    else:text=text.replace(receipt,receipt.replace('publication_subset=1','publication_subset=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_forwardreceipt(tmp_path,auxiliary=True)


def test_auxiliary_cannot_drop_new_audit_fields(tmp_path):
    aux_fixture(tmp_path);path=tmp_path/'outcome.json';data=json.loads(path.read_text())
    del data['audit']['forwardreceipt'];path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='re-audit mismatch'):
        route.verify_ack_auxiliary(tmp_path,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)


def test_main_cannot_hide_compiled_receipt_requirement(tmp_path):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(MAIN/SIM/name,folder/name)
    data=json.loads((MAIN/'outcome.json').read_text());del data['audit']['forwardreceipt']
    (tmp_path/'outcome.json').write_text(json.dumps(data))
    with pytest.raises(ValueError,match='compiled forward receipt campaign differ'):
        route.run(tmp_path,ARTIFACTS/'synth-v1',tmp_path/'must-not-route',AUX)
    assert not (tmp_path/'must-not-route').exists()
