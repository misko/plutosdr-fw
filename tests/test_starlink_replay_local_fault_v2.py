"""Distinct terminal marker must coexist with inherited strict audit labels."""
import pytest
from tests.test_starlink_replay_local_fault_integration import GOOD,FAULT,ROOT
import replay_local_fault_experiment_v2 as experiment
import audit_local_fault_v3 as inherited

def renamed(text):return text.replace('REPLAY_LOCAL_FAULT_PASS','REPLAY_CANCELLATION_PARTITION_PASS')

def test_distinct_terminal_marker():
    log=renamed(GOOD)+'LOCAL_FAULT_PASS checks=10000 delayed_edges=0 pending_checks=0 exact_sources=1 bounded_abort=1 publication_fenced=1\n'
    assert experiment.witness(log)['external_only']==0
    assert inherited.witness(log)['checks']==10000

@pytest.mark.parametrize('text,aux,passes',[(GOOD,False,True),(FAULT,True,True),(GOOD,True,False),(FAULT,False,False),
    (GOOD.replace('registered_cause=1','registered_cause=0'),False,False),
    (GOOD+GOOD.splitlines()[-1]+'\n',False,False)])
def test_v2_witness(text,aux,passes):
    if passes:assert experiment.witness(renamed(text),aux)['partition_checks']==10000
    else:
        with pytest.raises(ValueError):experiment.witness(renamed(text),aux)

def test_only_observer_label_changed():
    rtl=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
    assert (rtl/'replay_local_fault_observer_v2.svh').read_text()==renamed((rtl/'replay_local_fault_observer.svh').read_text())
    a=(ROOT/'tools/replay_local_fault_experiment.py').read_text()
    b=(ROOT/'tools/replay_local_fault_experiment_v2.py').read_text()
    assert b==renamed(a).replace('replay_local_fault_observer.svh','replay_local_fault_observer_v2.svh')
