"""New candidate witnesses; frozen old arithmetic/parser remains authoritative."""
import hashlib

import pytest

from tests.starlink_oracle import retained_control_actual as c


@pytest.fixture(scope='module')
def scripted(tmp_path_factory):
    p=tmp_path_factory.mktemp('candidate_script')/'run'
    status=c.offline(p)
    assert status=={'compile':0,'script_exit':0,'kind':'OFFLINE_SCRIPT_NOT_FFT','service_executed':False}
    return p


def test_full_original_bench_profile_inverse():
    c.verify_sources()
    assert c.inverse_bench(c.bench())==c.old.actual_bench()
    original=c.old.compiled_sources();actual=c.compiled_sources()
    assert len(original)==len(actual)==26
    assert sum(a!=b for a,b in zip(original,actual,strict=True))==4
    for a,b in zip(original,actual,strict=True):
        assert a==b or (a.name==b.name and b.parent==c.candidate.RTL)
    text=c.bench()
    assert text.count('.completed_input_fault_now(candidate_original_completed_input_fault)')==3
    assert text.index('wire candidate_original_completed_input_fault;')<text.index('assign candidate_original_completed_input_fault')
    assert 'unconditional owner0 mailbox_input_metadata' in text
    assert 'unconditional owner1 descriptor' in text


def test_scripted_full_shadow_and_44_receipts(scripted):
    result=c.verify_result(scripted/'simulation.log',scripted/'actual_words.csv',kind='OFFLINE_SCRIPT_NOT_FFT')
    assert result['numerical_words']==77953
    assert result['parser_only_not_execution_proof'] is True
    assert sum(map(len,result['candidate'].values()))==44


def test_complete_script_csv_equals_unchanged_v5(scripted,tmp_path):
    baseline=tmp_path/'unchanged_v5'
    assert c.old.offline(baseline,execute=True)['script_exit']==0
    assert (baseline/'actual_words.csv').read_bytes()==(scripted/'actual_words.csv').read_bytes()
    assert hashlib.sha256((baseline/'actual_words.csv').read_bytes()).digest()==hashlib.sha256((scripted/'actual_words.csv').read_bytes()).digest()


@pytest.mark.parametrize('token',[
    'PRIVATE_DESCRIPTOR_OFFER=1','CLOSED_INPUT_CUTOVER=1',
    'candidate_original_completed_input_fault','candidate binding 1','candidate binding 2','candidate binding 3',
    'candidate sampled inverse descriptor','candidate active/parked/real-ACK descriptor changed',
    'candidate closed input strobe premise','candidate final input prematurely',
    'actual48 input','actual causal frame','unconditional owner0 descriptor',
])
def test_complete_inverse_rejects_any_checker_delta(token):
    text=c.bench();assert token in text
    with pytest.raises(ValueError,match='inverse'):
        c.inverse_bench(text.replace(token,token+'_mutant',1))


@pytest.mark.parametrize('prefix',['RCAND_FLAGS','RCAND_JOB','RCAND_OWNER','RCAND_PROOF','RACT_FRAME'])
@pytest.mark.parametrize('change',['missing','duplicate'])
def test_marker_missing_duplicate(scripted,tmp_path,prefix,change):
    lines=(scripted/'simulation.log').read_text().splitlines()
    i=next(i for i,x in enumerate(lines) if x.startswith(prefix+' '))
    if change=='missing':lines.pop(i)
    else:lines.insert(i,lines[i])
    log=tmp_path/'parser_only.log';log.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):c.verify_result(log,scripted/'actual_words.csv',kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('prefix,field',[
    ('RCAND_FLAGS',x) for x in ('private_offer','closed_input','wrapper_private','wrapper_closed')
]+[('RCAND_JOB',x) for x in ('context','job','inverse','start','cycle','offered','sampled')]
 +[('RCAND_OWNER',x) for x in ('owner','accepted','real_ack','held')]
 +[('RCAND_PROOF',x) for x in ('jobs','final_inputs','closed_pre','closed_post','public_pre')])
def test_new_receipt_payload_mutants(scripted,tmp_path,prefix,field):
    lines=(scripted/'simulation.log').read_text().splitlines()
    i=next(i for i,x in enumerate(lines) if x.startswith(prefix+' '))
    tokens=lines[i].split();j=next(j for j,t in enumerate(tokens) if t.startswith(field+'='))
    tokens[j]=field+'=-1';lines[i]=' '.join(tokens)
    log=tmp_path/'parser_only.log';log.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):c.verify_result(log,scripted/'actual_words.csv',kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('failure',['FATAL_ERROR: injected','eRrOr: injected'])
def test_complete_receipts_never_mask_failure(scripted,tmp_path,failure):
    log=tmp_path/'parser_only.log';log.write_text((scripted/'simulation.log').read_text()+failure+'\n')
    with pytest.raises(ValueError,match='fatal/error'):
        c.verify_result(log,scripted/'actual_words.csv',kind='OFFLINE_SCRIPT_NOT_FFT')
