from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from private_replay_sequence_experiment_v3 import mirror_ready_stimulus

def stimulus():
    return "release dut.kernel_ready;\nforce dut.kernel_ready=1'b0;\nrelease dut.kernel_ready;\nforce dut.kernel_ready=1'b0;\nrelease dut.kernel_ready;"

def test_only_reference_gets_matching_forced_input():
    old=stimulus();new=mirror_ready_stimulus(old)
    assert new.count("force replay_kernel_reference.input_ready=1'b0;")==2
    assert new.count('release replay_kernel_reference.input_ready;')==3
    assert new.replace("force replay_kernel_reference.input_ready=1'b0;",'').replace('release replay_kernel_reference.input_ready;','')==old

@pytest.mark.parametrize('change',["force dut.kernel_ready=1'b0;",'release dut.kernel_ready;'])
def test_incomplete_force_inventory_rejected(change):
    with pytest.raises(ValueError):mirror_ready_stimulus(stimulus().replace(change,'',1))

def test_smoke_replays_every_inherited_ready_force_branch():
    source=(ROOT/'tools/private_replay_sequence_smoke_v3.py').read_text()
    for call in ['aux_reset_boundary(2,0);','aux_reset_boundary(2,1);','aux_reset_boundary(3,0);','aux_reset_boundary(3,1);','aux_delay(1);','run_private_replay_sequence_boundaries;']:
        assert call in source
