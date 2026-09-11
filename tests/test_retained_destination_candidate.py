"""Additive candidate with complete unchanged inherited scripted campaign."""
import json
from pathlib import Path
import re

import pytest

from tests.starlink_oracle import retained_destination_candidate as c
from tests.starlink_oracle import retained_destination_algebra as algebra


@pytest.mark.parametrize('name', c.FILES)
def test_whole_original_source_inverse(name):
    filename=c.FILES[name][0]
    assert c.inverse(name,(c.RTL/filename).read_text())==c.original(name)


@pytest.mark.parametrize('name', c.FILES)
@pytest.mark.parametrize('kind', ['missing','duplicate','unrelated'])
def test_whole_inverse_rejects_any_changed_source(name,kind):
    text=(c.RTL/c.FILES[name][0]).read_text()
    token=c.PATCHES[name][-1][1]
    if kind=='missing':text=text.replace(token,'',1)
    elif kind=='duplicate':text=text.replace(token,token*2,1)
    else:text+='\n'
    with pytest.raises(ValueError,match='inverse'):c.inverse(name,text)


def test_owner_all_four_state_controls_and_clocked_outputs(tmp_path):
    result=c.run_sv(tmp_path/'owner',(c.RTL/'tb_destination_owner.sv').read_text(),[
        c.BUNDLE/'source_snapshot'/c.FILES['owner'][1],c.RTL/c.FILES['owner'][0]])
    assert result.returncode==0,result.stdout+result.stderr
    assert not re.search(r'FATAL|ERROR|FAIL',result.stdout+result.stderr)
    rows=re.findall(r'^DESTINATION_OWNER_PASS cases=(\d+) checks=(\d+) releases=(\d+) unknowns=(\d+)$',result.stdout,re.M)
    assert len(rows)==1
    cases,checks,releases,unknowns=map(int,rows[0])
    assert cases==262144 and checks>1000000 and releases>0 and unknowns==2


def test_actual_owner_port_and_top_expression_four_state(tmp_path):
    result=c.run_sv(tmp_path/'actual-port-algebra',c.runtime_algebra(),[c.RTL/c.FILES['owner'][0]])
    assert result.returncode==0,result.stdout+result.stderr
    algebra.verify_receipt(result.stdout+result.stderr)


@pytest.mark.parametrize('kind',['current','reason','knownness','fallback'])
def test_executed_runtime_root_and_fallback_mutants(tmp_path,kind):
    top=(c.RTL/c.FILES['top'][0]).read_text()
    if kind in ('current','reason'):
        before=algebra.statement(top,'offered_external_fault_now')
        token='retained_fault_now' if kind=='current' else '(|retained_reasons)'
        assert before.count(token)==1
        after=before.replace(token,"1'b0")
    else:
        before=algebra.statement(top,'contextual_destination_common')
        after=(before.replace(' && retained_reserved_known','') if kind=='knownness' else
               before.replace('(INPUT_OFFER_FAULT_SUMMARY ? offered_common_current_fault : original_common_current_fault)',"1'b0"))
    assert before!=after and top.count(before)==1
    changed=top.replace(before,after,1)
    mutant=tmp_path/'mutated-top.v';mutant.write_text(changed)
    with pytest.raises(ValueError,match='inverse'):c.inverse('top',changed)
    result=c.run_sv(tmp_path/'runtime-mutant',c.runtime_algebra(changed),[c.RTL/c.FILES['owner'][0]])
    assert result.returncode!=0
    assert 'DESTINATION_CONTEXTUAL_EQUIVALENCE_FAILED' in result.stdout
    assert 'DESTINATION_ALGEBRA_PASS' not in result.stdout


@pytest.mark.parametrize('mode',[0,1])
def test_complete_seven_context_script_and_all_original_result_gates(tmp_path,mode):
    c.verify_runtime()
    directory=tmp_path/'composition'
    result=c.composed(directory,mode)
    assert result.returncode==0,result.stdout+result.stderr
    assert not re.search(r'FATAL|ERROR|FAIL',result.stdout+result.stderr)
    parsed=c.verify_composed_result(directory)
    assert parsed['numerical_words']==77953 and parsed['parser_only_not_execution_proof'] is True
    assert c.sha(directory/'actual_words.csv')=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'
    reference=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-script-parent.jVE5ixKt/summary-result.json')
    assert parsed==json.loads(reference.read_text())
    rows=re.findall(r'^DESTINATION_COMPOSED_PASS mode=(\d+) pre=(\d+) post=(\d+) releases=(\d+) admits=(\d+) publications=(\d+)$',result.stdout,re.M)
    assert len(rows)==1
    option,pre,post,releases,admits,pubs=map(int,rows[0])
    assert option==mode and pre>1000 and post>1000 and (releases,admits,pubs)==(17,19,19)


@pytest.mark.parametrize('literal',['-1','2',"32'bx","32'bz"])
def test_invalid_option_never_runs_full_campaign(tmp_path,literal):
    result=c.composed(tmp_path/'invalid',literal)
    assert result.returncode!=0
    assert 'contextual destination summary mode must be known zero or one' in result.stdout
    assert 'DESTINATION_COMPOSED_PASS' not in result.stdout
