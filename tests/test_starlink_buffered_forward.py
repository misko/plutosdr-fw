"""Exact experimental source boundary; numerical authority is actual simulation."""
from pathlib import Path
import re
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import buffered_forward_transform as transform
import buffered_forward_experiment as experiment

def test_exact_derivation_and_inverse():
    old=(experiment.RTL/(experiment.OLD+'.v')).read_text()
    new=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    assert transform.transform(old)==new
    assert transform.undo(new)==old
    assert len(transform.CHANGES)==12

@pytest.mark.parametrize('index',range(12))
def test_transform_rejects_missing_required_site(index):
    old=(experiment.RTL/(experiment.OLD+'.v')).read_text()
    before=transform.CHANGES[index][0]
    with pytest.raises(AssertionError):transform.transform(old.replace(before,'REMOVED_SITE',1))

def test_reference_runtime_and_bank_unchanged():
    parent=experiment.PARENT
    assert experiment.base.sha(parent/'SHA256SUMS')==experiment.PARENT_PIN
    names=re.search(r'set runtime_names \{([^}]+)\}',(parent/'profile.tcl').read_text())[1].split()
    assert len(names)==23
    checked=0
    for name in names:
        local=experiment.RTL/name
        if local.exists():
            assert local.read_bytes()==(parent/name).read_bytes(),name
            checked+=1
    assert checked>=18

def test_bank_capture_and_elastic_replay_boundaries():
    top=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    assert '.capture_valid(core_output_valid && !routed_inverse)' in top
    assert '.seal_valid(guard_commit[0] && !next_inverse)' in top
    assert '.input_valid(forward_buffer_valid && !fast_fault && product_bank_ready)' in top
    assert 'forward_receipt_wait ? product_bank_valid : (forward_buffer_owned && !forward_buffer_fault)' in top
    assert '.abort_epoch(fast_fault || result_fault)' in top
    assert 'wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault;' in top
