"""Bounded source/real-module/behavioral tests, never vendor timing evidence."""
import pytest

from tests.starlink_oracle import retained_offer_summary_candidate as c
from tests.starlink_oracle import retained_output_prototype as old


@pytest.mark.parametrize('name', c.PINS)
def test_whole_source_inverse(name):
    restored = c.inverse(name, (c.RTL / name).read_text())
    assert restored == (c.closed.RTL / name).read_text()
    c.closed.inverse(name, restored)


@pytest.mark.parametrize('name', c.PINS)
@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'unrelated'])
def test_inverse_mutations(name, kind):
    text = (c.RTL / name).read_text()
    token = c.PATCHES[name][-1][1]
    if kind == 'missing':
        text = text.replace(token, '')
    elif kind == 'duplicate':
        text = text.replace(token, token * 2)
    else:
        text += '\n'
    with pytest.raises(ValueError, match='inverse'):
        c.inverse(name, text)


def test_literal_dependent_summary_partition():
    assert len(c.assert_literal_summary_partition()) == 12


def test_real_input_guard_512_and_four_state_premise(tmp_path):
    old.run_sv(tmp_path / 'input', (c.RTL / 'tb_offer_input_premise.sv').read_text(),
               [old.BASELINE / 'starlink_pss_realtime_input_guard_local_admission.v'])


@pytest.mark.parametrize('kind', ['ready', 'last', 'owner'])
def test_real_premise_mutations(tmp_path, kind):
    text = (c.RTL / 'tb_offer_input_premise.sv').read_text()
    token, replacement = {
        'ready': ('input_valid&&input_transport_ready', 'input_valid&&dut.eligible'),
        'last': ('offered_beat&&input_last', 'offered_beat&&!input_last'),
        'owner': ('offered_beat&&route,offered_end&&route', 'offered_beat&&!route,offered_end&&route'),
    }[kind]
    assert text.count(token) == 1
    old.run_sv(tmp_path / kind, text.replace(token, replacement),
               [old.BASELINE / 'starlink_pss_realtime_input_guard_local_admission.v'],
               expected_failure='per-owner summary route mismatch' if kind == 'owner' else 'real input offered premise mismatch')


def test_cutover_real_module_algebra(tmp_path):
    old.run_sv(tmp_path / 'cutover', c.cutover_algebra(), [c.RTL / 'starlink_pss_core_job_cutover.v'])


@pytest.mark.parametrize('mode', [0, 1])
def test_original_guard_all_state_output_and_summary(tmp_path, mode):
    old.run_sv(tmp_path / 'guard', c.guard_equivalence(mode), [
        old.BASELINE / 'starlink_pss_realtime_result_guard.v',
        old.BASELINE / 'starlink_pss_block_mailbox.v',
        old.RTL / 'baseline_tests/tb_starlink_pss_realtime_result_guard.sv',
        c.RTL / 'starlink_pss_result_guard_owner_view.v'])


@pytest.mark.parametrize('mode', [0, 1])
@pytest.mark.parametrize('stall', [0, 2, 5])
def test_composition_exact_original_shadows(tmp_path, mode, stall):
    old.run_sv(tmp_path / 'composition', c.composition(mode), c.sources(), parameters=[f'-Ptb.STALL={stall}'])
    from tests.starlink_oracle.retained_output_graph import state_inventory
    inventory = state_inventory((tmp_path / 'composition/sim.vvp').read_text(), 'tb.dut.retained.island')
    assert inventory['declared_bits'] == 2480
    assert len([r for r in inventory['arrays'] if r['path'].endswith('.payload_memory')]) == 3


@pytest.mark.parametrize('literal', ['-1', '2', "32'bx", "32'bz"])
def test_unknown_mode_rejected(tmp_path, literal):
    old.run_sv(tmp_path / 'bad-mode', c.composition(literal), c.sources(),
               expected_failure='offered fault summary mode must be known zero or one')


def test_common_literal_roots_and_four_state_partition(tmp_path):
    old.run_sv(tmp_path / 'common', c.common_algebra_bench(), [])


@pytest.mark.parametrize('kind', ['input', 'vendor', 'output', 'unknown'])
def test_common_dropped_root_mutations(tmp_path, kind):
    top = (c.RTL / 'starlink_pss_fft_retained_output_impl.v').read_text()
    begin = top.index('  wire offered_external_fault_now =')
    end = top.index('  assign common_current_fault =')
    section = top[begin:end]
    token, replacement = {
        'input': ("(input_fault_now !== 1'b0)", "1'b0"),
        'unknown': ("(input_fault_now !== 1'b0)", "(input_fault_now != 1'b0)"),
        'vendor': ('vendor_fault_now || fast_fault', "1'b0 || fast_fault"),
        'output': ('guard_offered_local_fault[1] ||\n    output_bank_fault ||', 'guard_offered_local_fault[1] ||\n    1\'b0 ||'),
    }[kind]
    # The selected external/current region also contains unrelated full fences;
    # replace only its first offered external root, or unique offered common tail.
    assert token in section
    mutated = top[:begin] + section.replace(token, replacement, 1) + top[end:]
    marker = 'unknown direct input fault not known-one' if kind == 'unknown' else 'common independent root/decomposition mismatch'
    old.run_sv(tmp_path / kind, c.common_algebra_bench(mutated), [], expected_failure=marker)


@pytest.mark.parametrize('kind', range(8))
def test_current_input_fault_real_old_ack_and_publication(tmp_path, kind):
    old.run_sv(tmp_path / 'ack', (c.RTL / 'tb_offer_fault_ack.sv').read_text(), [
        old.BASELINE / 'starlink_pss_realtime_input_guard_local_admission.v',
        c.RTL / 'starlink_pss_result_guard_owner_view.v',
        old.RTL / 'starlink_pss_retained_output_owner.v'], parameters=[f'-Ptb.KIND={kind}'])


@pytest.mark.parametrize('kind', ['missing', 'offer-mask', 'owner-mask', 'unknown'])
def test_direct_global_fault_fence_mutations(tmp_path, kind):
    text = (c.RTL / 'tb_offer_fault_ack.sv').read_text()
    before = "wire offered_common=(input_fault_now!==1'b0);"
    replacement = {
        'missing': "wire offered_common=1'b0;",
        'offer-mask': "wire offered_common=(input_fault_now!==1'b0)&&summary_offer_beat;",
        'owner-mask': "wire offered_common=(input_fault_now!==1'b0)&&1'b0;",
        'unknown': "wire offered_common=(input_fault_now!=1'b0);",
    }[kind]
    assert text.count(before) == 1
    case = 4 if kind == 'offer-mask' else 6 if kind == 'unknown' else 1
    old.run_sv(tmp_path / kind, text.replace(before, replacement), [
        old.BASELINE / 'starlink_pss_realtime_input_guard_local_admission.v',
        c.RTL / 'starlink_pss_result_guard_owner_view.v',
        old.RTL / 'starlink_pss_retained_output_owner.v'], parameters=[f'-Ptb.KIND={case}'],
        expected_failure='current malformed input permitted old real ACK/release')
