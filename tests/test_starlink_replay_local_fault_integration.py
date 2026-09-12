"""Strict witness parsing and unchanged publication/fault-campaign requirements."""
import ast
import pytest
from tests.test_starlink_replay_capacity_integration import ROOT, RTL, RING, AUX
import replay_local_fault_experiment as experiment

GOOD=RING+'REPLAY_LOCAL_FAULT_PASS checks=10000 external_only=0 current_veto=1 registered_cause=1\n'
FAULT=AUX+'REPLAY_LOCAL_FAULT_PASS checks=10000 external_only=7 current_veto=1 registered_cause=1\n'

def test_partition_witness():
    assert experiment.witness(GOOD)['external_only']==0
    assert experiment.witness(FAULT,True)['external_only']==7

@pytest.mark.parametrize('bad,aux',[(GOOD,True),(FAULT,False),(RING,False),
    (GOOD.replace('checks=10000 external_only','checks=9999 external_only'),False),
    (GOOD.replace('current_veto=1 registered_cause','current_veto=0 registered_cause'),False),
    (GOOD.replace('registered_cause=1','registered_cause=0'),False),
    (GOOD+GOOD.splitlines()[-1]+'\n',False),(GOOD+'FATAL',False)])
def test_incomplete_witness_rejected(bad,aux):
    with pytest.raises(ValueError):experiment.witness(bad,aux)

def test_actual_publication_checks_unchanged():
    old=(RTL/'starlink_pss_fft_replay_capacity_ring_impl.v').read_text()
    new=(RTL/'starlink_pss_fft_replay_local_fault_impl.v').read_text()
    for prefix in ['wire product_commit_authorized =','wire replay_publication_fault =']:
        assert old.split(prefix,1)[1].split(';',1)[0]==new.split(prefix,1)[1].split(';',1)[0]
    assert new.count(' || replay_fifo_local_fault;')==1
    assert '.cancel_now(forward_buffer_fault)' in new
    assert '.fault(replay_fifo_fault),.local_fault(replay_fifo_local_fault)' in new

def test_prepare_only_adds_observer_and_selects_new_top():
    source=(ROOT/'tools/replay_local_fault_experiment.py').read_text()
    assert 'base.prepare(path,auxiliary)' in source
    assert 'base.run(mode,prepared,pin,output)' in source
    assert '45 parent runtime modules unchanged' in source
    # No inherited observer/task substitution or coverage-threshold relaxation.
    assert 'guard_delays' not in source and 'relocate_stall' not in source

@pytest.mark.parametrize('name',['replay_local_fault_experiment.py','route_replay_local_fault_probe.py','replay_local_fault_transform.py'])
def test_helpers_parse(name):ast.parse((ROOT/'tools'/name).read_text())

def test_route_scope_remains_exploratory():
    source=(ROOT/'tools/route_replay_local_fault_probe.py').read_text()
    assert 'exploratory_only=True' in source
    assert 'complete_fault_campaign_verified=False' in source
    assert 'physical_signoff=False,deployment_eligible=False' in source
