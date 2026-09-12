"""Parser mutation checks: changed refill coverage cannot skip other gates."""
from pathlib import Path
import re
import pytest
from tests.test_starlink_product_registered_capacity import experiment,RTL,GOOD

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=Path('/dev/shm/starlink-replay-capacity.MDfTXxjB')

def fixture(auxiliary):
    # Existing measured log is only a parser fixture, not evidence of this RTL.
    folder='local-aux-v2' if auxiliary else 'local-sim-v2'
    log=(REFERENCE/folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    return re.sub(r'^PARALLEL_PRODUCT_IDENTITY_PASS[^\n]*\n',lambda _:GOOD,log,flags=re.M)

@pytest.mark.parametrize('auxiliary',[False,True])
def test_all_functional_gates_required(auxiliary):
    result=experiment.qualification(fixture(auxiliary),auxiliary)
    assert len(result)==(13 if auxiliary else 11)
    assert result['product_capacity']['first_refills']==0

@pytest.mark.parametrize('marker',[
    'REGISTERED_PRODUCT_CAPACITY_PASS','OUTPUT_IDENTITY_PASS','BALANCED_FORWARD_IDENTITY_PASS',
    'REGISTERED_ABORT_PASS','LOCAL_FAULT_PASS','FORWARD_PRIVATE_STATUS_PASS',
    'PRODUCT_RETIREMENT_RECEIPT_PASS','PRIVATE_FORWARD_DESCRIPTOR_PASS',
    'OUTPUT_RETIREMENT_RECEIPT_PASS','PRIVATE_REPLAY_SEQUENCE_PASS',
    'BUFFERED_AUX_PASS','OUTPUT_IDENTITY_BOUNDARIES_PASS',
    'PRIVATE_REPLAY_SEQUENCE_BOUNDARIES_PASS','PRODUCT_CURRENT_FENCE_BOUNDARIES_PASS'])
def test_missing_inherited_gate_rejected(marker):
    log=fixture(True)
    assert re.search(r'^'+marker+r'\b',log,re.M)
    broken=re.sub(r'^'+marker+r'[^\n]*\n','',log,flags=re.M)
    with pytest.raises(ValueError):experiment.qualification(broken,True)

def test_lean_runtime_publication_predicates_and_deadline_unchanged():
    old=(RTL/'starlink_pss_fft_private_replay_sequence_impl.v').read_text()
    new=(RTL/(experiment.NEW+'.v')).read_text()
    for prefix in ['wire product_commit_authorized =','wire replay_publication_fault =','wire product_retire_ready =']:
        assert new.split(prefix,1)[1].split(';',1)[0]==old.split(prefix,1)[1].split(';',1)[0]
    assert 'replay_fifo' not in new
    capacity=new.split('wire forward_parallel_capacity =',1)[1].split(';',1)[0]
    assert 'product_bank_ready' not in capacity and 'product_identity_idle' in capacity
    assert 'actual.run(' in (ROOT/'tools/product_registered_capacity_experiment.py').read_text()
    assert '0<int(r[1])<=5215' in (ROOT/'tools/buffered_forward_experiment.py').read_text()

def test_early_route_not_deployment():
    text=(ROOT/'tools/route_product_registered_capacity_probe.py').read_text()
    assert 'exploratory_only=True' in text and 'complete_fault_campaign_verified=False' in text
    assert 'physical_signoff=False,deployment_eligible=False' in text
