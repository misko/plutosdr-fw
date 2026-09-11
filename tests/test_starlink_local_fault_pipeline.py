from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import local_fault_transform as transform
import local_fault_experiment as experiment
import audit_local_fault as audit

def test_exact_pipeline_delta_preserves_every_other_expression():
    original=(experiment.RTL/(experiment.base.NEW+'.v')).read_text()
    candidate=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    assert len(transform.CHANGES)==2
    assert transform.transform(original)==candidate
    assert transform.undo(candidate)==original
    assert 'reg [32:0] local_fault_snapshot;' in candidate
    assert 'else local_fault_snapshot <= admission_reject_expanded;' in candidate
    assert "else if (local_fault_profile ? (result_fault || (|local_fault_snapshot)) :" in candidate

@pytest.mark.parametrize('index',range(2))
def test_missing_transform_site_rejected(index):
    original=(experiment.RTL/(experiment.base.NEW+'.v')).read_text()
    with pytest.raises(AssertionError):transform.transform(original.replace(transform.CHANGES[index][0],'MISSING',1))

MAIN='LOCAL_FAULT_PASS checks=10000 delayed_edges=0 pending_checks=0 exact_sources=1 bounded_abort=1 publication_fenced=1\n'
HEAD=MAIN.replace('delayed_edges=0','delayed_edges=6').replace('pending_checks=0','pending_checks=6')
CASES=''.join(f'LOCAL_FAULT_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6))
TERMINAL='LOCAL_FAULT_BOUNDARIES_PASS cases=6 delayed_fault_exercised=1 fresh_recovery=1\n'
AUX=HEAD+CASES+TERMINAL

def test_healthy_evidence():assert audit.witness(MAIN)['pending_checks']==0
def test_auxiliary_evidence():assert audit.witness(AUX,True)['delayed_edges']==6

@pytest.mark.parametrize('log',['',MAIN+MAIN,MAIN+'FATAL\n',MAIN.replace('checks=10000','checks=9999'),
    MAIN.replace('delayed_edges=0','delayed_edges=1'),MAIN.replace('pending_checks=0','pending_checks=1')])
def test_incomplete_main_rejected(log):
    with pytest.raises(ValueError):audit.witness(log)

@pytest.mark.parametrize('log',[AUX+AUX,AUX+'FATAL\n',AUX.replace('delayed_edges=6','delayed_edges=5'),
    AUX.replace('pending_checks=6','pending_checks=5'),AUX.replace('exact_sources=1','exact_sources=0'),
    AUX.replace('bounded_abort=1','bounded_abort=0'),AUX.replace('publication_fenced=1','publication_fenced=0'),
    AUX.replace('new_publications=0','new_publications=1',1),AUX.replace('fresh_reads=512','fresh_reads=511',1)])
def test_incomplete_auxiliary_rejected(log):
    with pytest.raises(ValueError):audit.witness(log,True)

@pytest.mark.parametrize('line',range(7))
def test_every_boundary_required(line):
    lines=(CASES+TERMINAL).splitlines(True);del lines[line]
    with pytest.raises(ValueError):audit.witness(HEAD+''.join(lines),True)
