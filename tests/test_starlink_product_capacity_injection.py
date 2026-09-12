"""Drive the same corruption on a real acceptance edge, not a refill bubble."""
import re
import pytest
from tests.test_starlink_product_registered_capacity_qualification import fixture
import product_registered_capacity_experiment_v2 as experiment

MARKER='PRODUCT_CAPACITY_CORRUPTION_OFFER accepted_edge=1 original_position=100 corrupted_position=0\n'

def test_only_fault_three_trigger_and_offer_witness_change():
    source=(experiment.RTL/'buffered_forward_fault_campaign.svh').read_text()
    changed=experiment.qualify_corruption_edge(source)
    a=source.index('  task automatic aux_fault(');b=source.index('  task automatic aux_reset_boundary',a)
    assert changed[:a]==source[:a]
    assert changed[changed.index('  task automatic aux_reset_boundary'):]==source[b:]
    assert changed.count('force dut.forward_buffer_position=9\'d0;')==1
    assert changed.count('release dut.forward_buffer_position;')==source.count('release dut.forward_buffer_position;')==2
    assert 'repeat(100)begin' in changed
    assert 'fault not quarantined case=%0d' in changed
    assert 'dut.joiner.kernel_rom.input_accept!==1' in changed
    assert 'dut.joiner.input_valid!==1 || dut.kernel_ready!==1 || dut.joiner.input_bin_index!==0' in changed
    assert 'else if(which==3)while(!(dut.joiner.input_valid && dut.kernel_ready && dut.forward_buffer_position==100))' in changed

@pytest.mark.parametrize('auxiliary',[False,True])
def test_qualification_retains_prior_proofs(auxiliary):
    result=experiment.qualification(fixture(auxiliary)+(MARKER if auxiliary else ''),auxiliary)
    assert result['product_capacity']['first_refills']==0

@pytest.mark.parametrize('marker',['',MARKER+MARKER,MARKER.replace('accepted_edge=1','accepted_edge=0')])
def test_missing_or_invalid_injection_proof_rejected(marker):
    with pytest.raises(ValueError):experiment.qualification(fixture(True)+marker,True)

def test_main_aux_runtime_identical():
    from pathlib import Path
    root=Path('/dev/shm/starlink-product-capacity.9xKDnOQI')
    main=root/'prepared-v1';aux=root/'aux-prepared-v2'
    assert (main/'profile.tcl').read_bytes()==(aux/'profile.tcl').read_bytes()
    names=re.search(r'set runtime_names \{([^}]+)\}',(main/'profile.tcl').read_text())[1].split()
    assert len(names)==43
    assert all((main/n).read_bytes()==(aux/n).read_bytes() for n in names)
