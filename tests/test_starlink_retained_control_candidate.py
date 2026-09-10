"""Offline default-off private descriptor candidate; no actual FFT or timing claim."""
import hashlib

import pytest

from tests.starlink_oracle import retained_control_candidate as c
from tests.starlink_oracle import retained_output_prototype as old


@pytest.mark.parametrize('name', c.PINS)
def test_exact_inverse(name):
    assert hashlib.sha256(c.inverse(name, (c.CANDIDATE/name).read_text()).encode()).hexdigest() == c.PINS[name]


@pytest.mark.parametrize('name', c.PINS)
@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'unrelated'])
def test_inverse_mutants(name, kind):
    text = (c.CANDIDATE/name).read_text()
    after = c.PATCHES[name][-1][1]
    if kind == 'missing': text = text.replace(after, '')
    elif kind == 'duplicate': text = text.replace(after, after*2)
    else: text += '\n'
    with pytest.raises(ValueError, match='inverse'): c.inverse(name, text)


@pytest.mark.parametrize('mode', [0, 1])
def test_full_original_guard_matrix_and_independent_private_state(tmp_path, mode):
    old.run_sv(tmp_path/'guard', c.guard_boundary_bench(mode), [
        old.BASELINE/'starlink_pss_realtime_result_guard.v', old.BASELINE/'starlink_pss_block_mailbox.v',
        c.CANDIDATE/'starlink_pss_result_guard_owner_view.v',
        old.RTL/'baseline_tests/tb_starlink_pss_realtime_result_guard.sv'])


def test_missing_offer_kills_independent_caller_witness(tmp_path):
    old.run_sv(tmp_path/'missing', c.guard_boundary_bench(1, True), [
        old.BASELINE/'starlink_pss_realtime_result_guard.v', old.BASELINE/'starlink_pss_block_mailbox.v',
        c.CANDIDATE/'starlink_pss_result_guard_owner_view.v',
        old.RTL/'baseline_tests/tb_starlink_pss_realtime_result_guard.sv'],
        expected_failure='accepted job missing private offer')


@pytest.mark.parametrize('literal', ["1'bx", "1'bz"])
def test_unknown_unaccepted_offer_cannot_change_owned_state(tmp_path, literal):
    text=c.guard_boundary_bench(1).replace("wire private_offer = 1'b1;",
        f"wire private_offer = stimulus.dut.job_valid ? 1'b1 : {literal};")
    old.run_sv(tmp_path/'unknown-unaccepted', text, [
        old.BASELINE/'starlink_pss_realtime_result_guard.v', old.BASELINE/'starlink_pss_block_mailbox.v',
        c.CANDIDATE/'starlink_pss_result_guard_owner_view.v',
        old.RTL/'baseline_tests/tb_starlink_pss_realtime_result_guard.sv'])


@pytest.mark.parametrize('literal', ["1'bx", "1'bz"])
def test_unknown_accepted_offer_violates_caller_contract(tmp_path, literal):
    text=c.guard_boundary_bench(1).replace("wire private_offer = 1'b1;", f"wire private_offer = {literal};")
    old.run_sv(tmp_path/'unknown-accepted', text, [
        old.BASELINE/'starlink_pss_realtime_result_guard.v', old.BASELINE/'starlink_pss_block_mailbox.v',
        c.CANDIDATE/'starlink_pss_result_guard_owner_view.v',
        old.RTL/'baseline_tests/tb_starlink_pss_realtime_result_guard.sv'],
        expected_failure='accepted job missing private offer')


def test_wrong_sampled_descriptor_rejected_by_independent_model(tmp_path):
    text=c.guard_boundary_bench(1)
    token='.job_descriptor(stimulus.dut.job_descriptor)'
    assert text.count(token)==1
    text=text.replace(token, ".job_descriptor(stimulus.dut.job_descriptor ^ 70'b1)")
    old.run_sv(tmp_path/'wrong-descriptor', text, [
        old.BASELINE/'starlink_pss_realtime_result_guard.v', old.BASELINE/'starlink_pss_block_mailbox.v',
        c.CANDIDATE/'starlink_pss_result_guard_owner_view.v',
        old.RTL/'baseline_tests/tb_starlink_pss_realtime_result_guard.sv'],
        expected_failure='independent private descriptor model')


def test_wrong_phase_offer_rejected_at_real_top_admission(tmp_path):
    paths=c.sources()
    name='starlink_pss_fft_retained_output_impl.v'
    text=(c.CANDIDATE/name).read_text()
    token='.private_descriptor_offer(job_valid && next_inverse == OWNER)'
    assert text.count(token)==1
    mutant=tmp_path/name
    mutant.write_text(text.replace(token, '.private_descriptor_offer(job_valid && next_inverse != OWNER)'))
    old.run_sv(tmp_path/'wrong-phase', c.composition(1),
        [mutant if p.name==name else p for p in paths],
        expected_failure='accepted job missing private offer')


@pytest.mark.parametrize('mode', [0, 1])
@pytest.mark.parametrize('stall', [0, 1, 2])
def test_complete_composition_original_shadows(tmp_path, mode, stall):
    old.run_sv(tmp_path/'composition', c.composition(mode), c.sources(), parameters=[f'-Ptb.STALL={stall}'])


@pytest.mark.parametrize('literal', ["-1", "2", "32'bx", "32'bz"])
def test_literal_unknown_mode_rejected(tmp_path, literal):
    old.run_sv(tmp_path/'bad-mode', c.composition(literal), c.sources(),
               expected_failure='private descriptor mode must be known zero or one')


def test_private_offer_has_no_ready_fallback_and_admission_unchanged():
    top=(c.CANDIDATE/'starlink_pss_fft_retained_output_impl.v').read_text()
    assert '.private_descriptor_offer(job_valid && next_inverse == OWNER),' in top
    assert '.job_valid(job_valid && job_ready && next_inverse == OWNER),' in top
    guard=(c.CANDIDATE/'starlink_pss_result_guard_owner_view.v').read_text()
    assert '(USE_PRIVATE_DESCRIPTOR_OFFER ? private_descriptor_offer : job_valid)' in guard
    assert 'wire job_accept = job_valid && job_ready;' in guard
    assert 'if (!active && !awaiting_ack && !protocol_fault &&\n          (USE_PRIVATE' in guard
