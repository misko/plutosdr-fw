"""Combined route needs complete main AND same-source auxiliary FFT proof."""
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route
BASE=ROOT.parent/'staged-ackcombined-prepared-v1'
MAIN=ROOT.parent/'staged-ackcombined-actual-v1'
AUX=ROOT.parent/'staged-ackcombined-aux-v1'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_original_campaign_and_deadline_preserved():
    parent=ROOT.parent/'staged-enginecapture-prepared-v1'
    assert hashlib.sha256((parent/'SHA256SUMS').read_bytes()).hexdigest()=='f6e1d4b8dd2df5c927fdcf0859ca6a17fee6c53c675a0b7c01668a9d413b08f7'
    old=(parent/'tb_fft_staged_output.sv').read_text()
    text=(BASE/'tb_fft_staged_output.sv').read_text()
    assert text.count('initial begin #3000000;')==1
    text=text.replace('module tb #(parameter integer ACK_ONLY=0);','module tb;',1)
    start=text.index('  // Original ACK-state update')
    end=text.index('  reg [35:0] forwards',start)
    text=text[:start]+text[end:]
    start=text.index('  task automatic private_ack_boundary(')
    end=text.index('  endtask\n',start)+len('  endtask\n')
    text=text[:start]+text[end:]
    start=text.index('    if(ACK_ONLY) begin\n')
    end=text.index('    for(mode=0;mode<6;mode=mode+1) begin\n',start)
    text=text[:start]+text[end:]
    text=text.replace('    if(private_ack_checks<1000)$fatal(1,"combined ACK main witness coverage missing");\n    $display("STAGED_ACKCOMBINED_MAIN_PASS checks=%0d public_exact=1",private_ack_checks);\n','',1)
    text=text.replace('\nmodule tb_ack_only;\n  tb #(.ACK_ONLY(1)) isolated();\nendmodule\n','',1)
    assert text==old,'original main checks must all remain unchanged'


def aux_fixture(tmp_path):
    target=tmp_path/SIM;target.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(AUX/SIM/name,target/name)
    shutil.copyfile(AUX/'outcome.json',tmp_path/'outcome.json')
    return target/'simulate.log'


def test_both_actual_campaigns_pass():
    main=experiment.audit_ackcombined_sim(MAIN)
    aux=route.verify_ack_auxiliary(AUX,experiment.sha(BASE/'SHA256SUMS'),BASE)
    assert main['numerical_rows']==64512 and main['ackcombined']['auxiliary_required']
    assert aux['boundaries']==[str(n) for n in range(6)] and aux['public_exact']


@pytest.mark.parametrize('mutation',['missing_case','duplicate_case','short_reads','short_release',
                                    'short_checks','short_quarantine','lost_public_equality'])
def test_auxiliary_evidence_mutants(tmp_path,mutation):
    log=aux_fixture(tmp_path);text=log.read_text()
    case=next(s for s in text.splitlines(True) if s.startswith('STAGED_PRIVATEACK_CASE_PASS boundary=0 '))
    receipt=next(s for s in text.splitlines(True) if s.startswith('STAGED_ACKCOMBINED_AUX_PASS '))
    if mutation=='missing_case':text=text.replace(case,'',1)
    elif mutation=='duplicate_case':text+=case
    elif mutation=='short_reads':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    elif mutation=='short_release':text=text.replace(case,case.replace('fresh_releases=1','fresh_releases=0'),1)
    elif mutation=='short_checks':text=text.replace(receipt,re.sub(r'checks=\d+','checks=1',receipt),1)
    elif mutation=='short_quarantine':text=text.replace(receipt,re.sub(r'quarantined=\d+','quarantined=299',receipt),1)
    else:text=text.replace(receipt,receipt.replace('public_exact=1','public_exact=0'),1)
    log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_ackcombined_aux(tmp_path)


def test_auxiliary_is_not_optional():
    with pytest.raises(ValueError,match='requires its auxiliary'):
        route.verify_ack_auxiliary(None,'unused',BASE)


def test_main_audit_cannot_hide_the_compiled_auxiliary_requirement():
    assert route.ack_auxiliary_required(BASE,{'ackcombined':{}})
    with pytest.raises(ValueError,match='compiled combined campaign'):
        route.ack_auxiliary_required(BASE,{'enginecapture':{}})


@pytest.mark.parametrize('mutation',['failed','wrong_mode','wrong_sha','wrong_root','changed_source','has_error','altered_audit'])
def test_route_rejects_mismatched_or_failed_auxiliary(tmp_path,mutation):
    aux_fixture(tmp_path);path=tmp_path/'outcome.json';data=json.loads(path.read_text())
    if mutation=='failed':data['returncode']=1
    elif mutation=='wrong_mode':data['mode']='sim'
    elif mutation=='wrong_sha':data['prepared_sha']='0'*64
    elif mutation=='wrong_root':data['command'][-3]='/different/prepared/root'
    elif mutation=='changed_source':data['sources_unchanged']=False
    elif mutation=='has_error':data['error']='injected failure'
    else:data['audit']['checks']=0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):route.verify_ack_auxiliary(tmp_path,experiment.sha(BASE/'SHA256SUMS'),BASE)
