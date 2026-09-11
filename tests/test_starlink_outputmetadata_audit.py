"""Actual live/replay identity coverage is mandatory before output-bank routing."""
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

ARTIFACTS=Path(os.environ.get('STARLINK_OUTPUT_METADATA_EVIDENCE','/dev/shm/starlink-output-metadata.MB5fY8'))
MAIN=ARTIFACTS/'sim-v3';AUX=ARTIFACTS/'ack-v3';PREPARED=ARTIFACTS/'prepared-v3'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_diagnostic_corrections_preserve_all_runtime_sources():
    pins={1:'a9656c0346a5c3125fbe230b2ef3875e4feba94333721b7b912f06b1ed014b65',
          2:'70140af367445b965a596ea53562145eb957fbd6410ce6de654c6a943c8039fa',
          3:'dc97c80ce1999e9a18053524c3dcd325d029705560c2425aef2e0fe05f20d1b7'}
    names=(PREPARED/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for version,pin in pins.items():
        folder=ARTIFACTS/f'prepared-v{version}'
        assert experiment.sha(folder/'SHA256SUMS')==pin
        inventory=dict((name,digest) for digest,name in (line.split() for line in (folder/'SHA256SUMS').read_text().splitlines()))
        for name in names:
            assert experiment.sha(folder/name)==inventory[name]
            assert (folder/name).read_bytes()==(PREPARED/name).read_bytes(),(version,name)


def test_complete_actual_pair():
    main=experiment.audit_outputmetadata(MAIN)
    aux=route.verify_ack_auxiliary(AUX,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)
    assert main['numerical_rows']==64512
    for result in [main,aux]:
        assert result['outputmetadata']['current_exact']
        assert result['outputmetadata']['unchanged_publication']
    assert aux['outputmetadata']['boundaries']==[str(n) for n in range(6)]


def fixture(tmp_path,source=AUX):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    shutil.copyfile(source/SIM/'simulate.log',folder/'simulate.log')
    shutil.copyfile(source/'outcome.json',tmp_path/'outcome.json')
    return folder/'simulate.log'


@pytest.mark.parametrize('mutation',['missing','duplicate','short_checks','short_live','short_replay',
                                   'current_exact','unchanged_publication'])
def test_incomplete_branch_evidence_rejected(tmp_path,mutation):
    path=fixture(tmp_path);text=path.read_text()
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_OUTPUT_METADATA_PASS '))
    if mutation=='missing':text=text.replace(receipt,'',1)
    elif mutation=='duplicate':text+=receipt
    elif mutation.startswith('short_'):
        field=mutation.removeprefix('short_');text=text.replace(receipt,re.sub(field+r'=\d+',field+'=1',receipt),1)
    else:text=text.replace(receipt,receipt.replace(mutation+'=1',mutation+'=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError,match='output metadata actual branch comparison'):
        experiment.audit_outputmetadata(tmp_path,auxiliary=True)


@pytest.mark.parametrize('mutation',['missing','duplicate','short_reads','short_release'])
def test_incomplete_actual_corruption_recovery_rejected(tmp_path,mutation):
    path=fixture(tmp_path);text=path.read_text()
    case=next(line for line in text.splitlines(True) if line.startswith('STAGED_OUTPUT_METADATA_CASE_PASS boundary=0 '))
    if mutation=='missing':text=text.replace(case,'',1)
    elif mutation=='duplicate':text+=case
    elif mutation=='short_reads':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    else:text=text.replace(case,case.replace('fresh_releases=1','fresh_releases=0'),1)
    path.write_text(text)
    with pytest.raises(ValueError,match='output metadata actual boundary inventory'):
        experiment.audit_outputmetadata(tmp_path,auxiliary=True)


def test_auxiliary_cannot_omit_output_audit(tmp_path):
    fixture(tmp_path);path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['outputmetadata'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='re-audit mismatch'):
        route.verify_ack_auxiliary(tmp_path,experiment.sha(PREPARED/'SHA256SUMS'),PREPARED)


def test_main_cannot_omit_compiled_output_requirement(tmp_path):
    fixture(tmp_path,MAIN)
    shutil.copyfile(MAIN/SIM/'staged_words.csv',tmp_path/SIM/'staged_words.csv')
    path=tmp_path/'outcome.json';outcome=json.loads(path.read_text())
    del outcome['audit']['outputmetadata'];path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled output metadata campaign differ'):
        route.run(tmp_path,ARTIFACTS/'synth-v3',tmp_path/'must-not-route',AUX)
    assert not (tmp_path/'must-not-route').exists()
