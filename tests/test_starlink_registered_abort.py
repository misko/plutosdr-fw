from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import registered_abort_transform as transform
import registered_abort_experiment as experiment

def test_exact_private_abort_delta_and_public_vetoes():
    original=(experiment.RTL/(experiment.base.NEW+'.v')).read_text()
    candidate=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    assert transform.transform(original)==candidate
    assert transform.undo(candidate)==original
    assert len(transform.CHANGES)==3
    for line in ['wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault;',
                 'wire replay_publication_fault = offered_external_fault_now || result_fault ||',
                 'assign registered_quarantine = fast_fault || result_fault || (|epoch_input_reasons) ||',
                 'assign admission_reject[18] = result_fault;']:
        assert line in candidate

@pytest.mark.parametrize('index',range(3))
def test_missing_required_delta_rejected(index):
    original=(experiment.RTL/(experiment.base.NEW+'.v')).read_text()
    with pytest.raises(AssertionError):transform.transform(original.replace(transform.CHANGES[index][0],'MISSING',1))

MAIN='REGISTERED_ABORT_PASS checks=10000 fault_edges=0 private_captures=0 private_writes=0 current_publication_fenced=1 next_edge_global_abort=1\n'
AUX=MAIN.replace('fault_edges=0','fault_edges=6').replace('private_captures=0','private_captures=1').replace('private_writes=0','private_writes=1')
CASES=''.join(f'REGISTERED_ABORT_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6))
TERMINAL='REGISTERED_ABORT_BOUNDARIES_PASS cases=6 private_delta_exercised=1 fresh_recovery=1\n'
AUX+=CASES+TERMINAL

def test_healthy_witness():
    assert experiment.witness(MAIN)['fault_edges']==0

def test_auxiliary_witness():
    assert experiment.witness(AUX,True)['private_captures']==1

@pytest.mark.parametrize('log',['',MAIN+MAIN,MAIN+'FATAL\n',MAIN.replace('checks=10000','checks=9999'),MAIN.replace('fault_edges=0','fault_edges=1')])
def test_incomplete_healthy_evidence_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log)

@pytest.mark.parametrize('log',[AUX+AUX,AUX+'FATAL\n',AUX.replace('fault_edges=6','fault_edges=5'),
    AUX.replace('private_captures=1','private_captures=0'),AUX.replace('private_writes=1','private_writes=0'),
    AUX.replace('current_publication_fenced=1','current_publication_fenced=0'),
    AUX.replace('new_publications=0','new_publications=1',1),AUX.replace('fresh_reads=512','fresh_reads=511',1)])
def test_incomplete_auxiliary_evidence_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log,True)

@pytest.mark.parametrize('line',range(7))
def test_each_missing_fault_boundary_rejected(line):
    lines=(CASES+TERMINAL).splitlines(True);del lines[line]
    head=AUX.splitlines(True)[0]
    with pytest.raises(ValueError):experiment.witness(head+''.join(lines),True)
