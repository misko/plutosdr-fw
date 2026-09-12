"""Exact integration/observer mapping and strict actual witness parsing."""
from pathlib import Path
import ast
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import replay_capacity_buffer_experiment as capacity
import replay_capacity_ring_experiment as ring
import replay_capacity_buffer_transform as transform
import replay_capacity_buffer_bench_mapping as mapping
RTL=capacity.RTL

def test_exact_capacity_top_and_original_publication_vetoes():
    old=(RTL/(capacity.base.NEW+'.v')).read_text();new=(RTL/(capacity.NEW+'.v')).read_text()
    assert transform.transform(old,transform.TOP_CHANGES)==new
    assert transform.undo(new,transform.TOP_CHANGES)==old
    for start,end in [('wire product_commit_authorized =',';'),('wire replay_publication_fault =',';')]:
        assert old.split(start,1)[1].split(end,1)[0]==new.split(start,1)[1].split(end,1)[0]

@pytest.mark.parametrize('old,new,changes',[
    ('private_replay_sequence_observer.svh','replay_capacity_kernel_observer.svh',mapping.OBSERVER_CHANGES),
    ('private_replay_sequence_boundaries_v2.svh','replay_capacity_kernel_boundaries.svh',mapping.BOUNDARY_CHANGES)])
def test_explicit_consumer_mapping(old,new,changes):
    assert capacity.mapped((RTL/old).read_text(),changes)==(RTL/new).read_text()

def test_ring_adds_private_write_proof_without_removing_conservation():
    original=(RTL/'replay_capacity_buffer_observer.svh').read_text()
    new=(RTL/'replay_capacity_ring_observer.svh').read_text()
    assert new.startswith(original)
    assert 'private ring write without current cancellation' in new
    assert 'cancelled ring write retained ownership' in new

def test_stall_relocation_changes_only_consumer_delay_payload():
    original=Path('/dev/shm/starlink-private-replay.if3LELsS/aux-prepared-v3/tb_fft_buffered_forward.sv').read_text()
    changed=capacity.relocate_stall(original)
    a=original.index('  task automatic aux_delay(')
    b=original.index('  task automatic run_buffered_auxiliary;',a)
    task=original[a:b];marker='      end else begin\n        while(!dut.forward_buffer_valid'
    c=task.index(marker);tail=task[c:]
    for old,new in [('forward_buffer_valid','replay_valid'),('forward_buffer_data','replay_data'),('forward_buffer_position','replay_position')]:
        tail=tail.replace(old,new)
    assert changed==original[:a]+task[:c]+tail+original[b:]
    assert changed.count("force dut.kernel_ready=1'b0;")==original.count("force dut.kernel_ready=1'b0;")==2
    assert 'for(n=0;n<128;n=n+1)' in changed

GOOD='REPLAY_CAPACITY_PASS checks=10000 inputs=9216 outputs=9216 cancelled=0 full_cycles=0 refills=9198 word_exact=1 current_veto=1\n'
def test_healthy_capacity_witness():assert capacity.witness(GOOD)['outputs']==9216
@pytest.mark.parametrize('old,new',[('checks=10000','checks=9999'),('inputs=9216','inputs=9215'),('outputs=9216','outputs=9215'),
 ('cancelled=0','cancelled=1'),('refills=9198','refills=8999'),('word_exact=1','word_exact=0'),('current_veto=1','current_veto=0')])
def test_incomplete_capacity_rejected(old,new):
    with pytest.raises(ValueError):capacity.witness(GOOD.replace(old,new))
@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD+'FATAL'])
def test_missing_duplicate_or_failed_capacity_rejected(bad):
    with pytest.raises(ValueError):capacity.witness(bad)

RING=GOOD+'REPLAY_RING_PASS checks=10000 private_writes=0 publication_fenced=1\n'
AUX=RING.replace('private_writes=0','private_writes=6')
def test_ring_witness():
    assert ring.witness(RING)['private_writes']==0
    assert ring.witness(AUX,True)['private_writes']==6
@pytest.mark.parametrize('bad,aux',[(RING,True),(AUX,False),(RING.replace('publication_fenced=1','publication_fenced=0'),False),
 (RING+RING.splitlines()[-1]+'\n',False),(GOOD,False)])
def test_incomplete_ring_witness_rejected(bad,aux):
    with pytest.raises(ValueError):ring.witness(bad,aux)

@pytest.mark.parametrize('name',['replay_capacity_buffer_experiment.py','replay_capacity_ring_experiment.py',
 'replay_capacity_buffer_smoke.py','replay_capacity_ring_smoke.py',
 'route_replay_capacity_probe.py','route_replay_ring_probe.py',
 'inspect_replay_capacity_buffer.py','inspect_replay_capacity_buffer_v2.py'])
def test_helpers_parse(name):ast.parse((ROOT/'tools'/name).read_text())

def test_exploratory_routes_do_not_claim_complete_qualification():
    for name in ['route_replay_capacity_probe.py','route_replay_ring_probe.py']:
        text=(ROOT/'tools'/name).read_text()
        assert 'exploratory_only=True' in text and 'complete_fault_campaign_verified=False' in text
        assert 'physical_signoff=False,deployment_eligible=False' in text
