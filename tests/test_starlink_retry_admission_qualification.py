"""Require real held-request coverage and the unchanged original grant oracle."""
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import retry_admission_experiment_v2 as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def auxiliary_log():
    lines=[f'RETRY_ADMISSION_BOUNDARY_PASS case={i} inverse={i//2 if i<4 else (i%2 if i<8 else 0)} fresh_reads=512 fresh_releases=1' for i in range(10)]
    lines += ['RETRY_ADMISSION_BOUNDARIES_PASS cases=10 capacity_stalls=4 one_sided_resets=4 timeout=1 descriptor_fault=1',
              'RETRY_ADMISSION_PASS checks=10000 grants=36 rejected_snapshots=100 capacity_waits=50 original_accept_exact=1 held_identity=1 once_per_request=1']
    return '\n'.join(lines)+'\n'

def test_complete_auxiliary_witness():
    assert experiment.witness(auxiliary_log(),True)['capacity_waits']==50

@pytest.mark.parametrize('missing',range(12))
def test_each_required_witness(missing):
    rows=auxiliary_log().splitlines();del rows[missing]
    with pytest.raises(ValueError):experiment.witness('\n'.join(rows),True)

@pytest.mark.parametrize('old,new',[
    ('checks=10000','checks=9999'),('grants=36','grants=35'),
    ('rejected_snapshots=100','rejected_snapshots=99'),('capacity_waits=50','capacity_waits=49'),
    ('original_accept_exact=1','original_accept_exact=0'),('fresh_reads=512','fresh_reads=511'),
    ('once_per_request=1','once_per_request=0')])
def test_weak_witness_rejected(old,new):
    with pytest.raises(ValueError):experiment.witness(auxiliary_log().replace(old,new,1),True)

def test_duplicate_boundary_rejected():
    log=auxiliary_log()
    with pytest.raises(ValueError):experiment.witness(log+log.splitlines()[0]+'\n',True)

def test_observer_preserves_current_capacity_reference_and_held_identity():
    observer=(RTL/'retry_admission_observer.svh').read_text()
    assert 'dut.job_accept!==old_job_accept' in observer
    for field in ['dut.guard_capacity[dut.next_inverse]','dut.cutover_admission_capacity',
                  'dut.inverse_descriptor_live','dut.engine_metadata,dut.held_phase,dut.held_lease',
                  'retry_request_grants!=1','dut.preparation_fault_now!==1','dut.registered_quarantine!==1']:
        assert field in observer
    assert observer.count('check_retry_admission;')==3

def test_direct_boundaries_require_bounded_retry_cancel_expiry_and_recovery():
    source=(RTL/'retry_admission_boundaries.svh').read_text()
    for check in ['dut.job_accept!==0','dut.config_valid!==0','dut.engine_input_enable!==0',
                  'dut.admission_gate.sampled_good!==0','n<6','n<100',
                  'if(which<6)resetn=0;else fft_resetn=0;',
                  'retry_bad_descriptor=dut.engine_metadata ^ 70\'h1000;','aux_recover;']:
        assert check in source

def test_backpressure_changes_only_injection_targets_not_deadlines_or_checks():
    old=(RTL/'retry_admission_boundaries_v3.svh').read_text()
    new=(RTL/'retry_admission_boundaries_v4.svh').read_text()
    expected=old.replace("          else force dut.guard_capacity=2'b00;",
        "          else if(wanted_inverse==0)force dut.result_destination_ready=1'b0;\n          else force dut.inverse_guard_ready=1'b0;",1)
    expected=expected.replace('release dut.guard_capacity;',
        'release dut.result_destination_ready;release dut.inverse_guard_ready;')
    assert new==expected
    assert 'force dut.guard_capacity' not in new
    assert 'n<6' in new and 'n<100' in new

def test_targeted_tests_select_auxiliary_checkers_before_first_send():
    helper=(ROOT/'tools/retry_admission_experiment_v6.py').read_text()
    assert helper.index('auxiliary_active=1;') < helper.index('run_retry_admission_boundaries;')
    assert "fragment=RTL/'retry_admission_boundaries_v4.svh'" in helper

def test_final_stall_targets_actual_guard_inputs_and_preserves_all_checks():
    before=(RTL/'retry_admission_boundaries_v4.svh').read_text()
    after=(RTL/'retry_admission_boundaries_v5.svh').read_text()
    assert after==before.replace('dut.result_destination_ready','dut.owners[0].result_guard.mailbox_input_ready').replace('dut.inverse_guard_ready','dut.owners[1].result_guard.mailbox_input_ready')
    for owner in range(2):
        assert f"force dut.owners[{owner}].result_guard.mailbox_input_ready=1'b0;" in after
        assert f'release dut.owners[{owner}].result_guard.mailbox_input_ready;' in after
    helper=(ROOT/'tools/retry_admission_experiment_v7.py').read_text()
    assert "fragment=RTL/'retry_admission_boundaries_v5.svh'" in helper
    assert helper.index('auxiliary_active=1;') < helper.index('run_retry_admission_boundaries;')
