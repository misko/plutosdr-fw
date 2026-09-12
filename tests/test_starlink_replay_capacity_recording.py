"""Recorders retain the inherited evidence gates and fail closed on test XML."""
import ast
import pytest
from tests.test_starlink_replay_capacity_integration import ROOT
from record_replay_capacity_evidence import passing_xml

def test_inherited_evidence_body_exact():
    old=(ROOT/'tools/route_private_replay_sequence.py').read_text().split('\ndef run(',1)[0]
    new=(ROOT/'tools/replay_local_fault_evidence.py').read_text().split('\nimport replay_local_fault_experiment_v2',1)[0]
    assert new==old.replace('def evidence(','def inherited_evidence(').replace('len(names)==41','len(names)==47')

@pytest.mark.parametrize('tag',['failure','error','skipped'])
def test_bad_xml_rejected(tmp_path,tag):
    p=tmp_path/'bad.xml';p.write_text('<testsuite><testcase><'+tag+'/></testcase></testsuite>')
    with pytest.raises(ValueError):passing_xml(p,1)

def test_count_exact(tmp_path):
    p=tmp_path/'good.xml';p.write_text('<testsuite><testcase/></testsuite>')
    passing_xml(p,1)
    with pytest.raises(ValueError):passing_xml(p,2)

@pytest.mark.parametrize('name',['record_replay_capacity_evidence.py','replay_local_fault_evidence.py','run_replay_local_regression.py'])
def test_helpers_parse(name):ast.parse((ROOT/'tools'/name).read_text())
