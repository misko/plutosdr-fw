"""Bounded independent gates for the opt-in closed-input cutover observation."""
import pytest

from tests.starlink_oracle import retained_closed_input_candidate as c
from tests.starlink_oracle import retained_output_prototype as old


@pytest.mark.parametrize('name',c.PINS)
def test_closed_whole_inverse(name):
    original=c.inverse(name,(c.RTL/name).read_text())
    if name in c.private.PINS:c.private.inverse(name,original)


@pytest.mark.parametrize('name',c.PINS)
@pytest.mark.parametrize('kind',['missing','duplicate','unrelated'])
def test_inverse_mutations(name,kind):
    text=(c.RTL/name).read_text();token=c.PATCHES[name][-1][1]
    if kind=='missing':text=text.replace(token,'')
    elif kind=='duplicate':text=text.replace(token,token*2)
    else:text+='\n'
    with pytest.raises(ValueError,match='inverse'):c.inverse(name,text)


def test_literal_restricted_predicate(tmp_path):
    old.run_sv(tmp_path/'algebra',c.algebra_bench(),[])


def test_real_input_guard_final_edge_and_closed_unknowns(tmp_path):
    old.run_sv(tmp_path/'input', (c.RTL/'tb_input_closed_premise.sv').read_text(),
        [old.BASELINE/'starlink_pss_realtime_input_guard_local_admission.v'])


def test_actual_guard_public_visibility_and_ack_scope(tmp_path):
    old.run_sv(tmp_path/'visibility',c.visibility_bench(),[
        old.BASELINE/'starlink_pss_realtime_result_guard.v',c.RTL/'starlink_pss_result_guard_owner_view.v'])


@pytest.mark.parametrize('offer,closed',[(0,0),(1,0),(0,1),(1,1)])
@pytest.mark.parametrize('stall',[0,1,2])
def test_composition_independent_strobes_and_old_shadows(tmp_path,offer,closed,stall):
    old.run_sv(tmp_path/'composition',c.composition(offer,closed),c.sources(),parameters=[f'-Ptb.STALL={stall}'])
    from tests.starlink_oracle.retained_output_graph import state_inventory
    inventory=state_inventory((tmp_path/'composition/sim.vvp').read_text(),'tb.dut.retained.island')
    assert inventory['declared_bits']==2480
    assert len([r for r in inventory['arrays'] if r['path'].endswith('.payload_memory')])==3


def test_missing_known_one_gate_mutant_rejected(tmp_path):
    text=c.visibility_bench()
    assert text.count('.REQUIRE_KNOWN_COMPLETED_INPUT(1)')==1
    text=text.replace('.REQUIRE_KNOWN_COMPLETED_INPUT(1)','.REQUIRE_KNOWN_COMPLETED_INPUT(0)')
    old.run_sv(tmp_path/'missing-known',text,[old.BASELINE/'starlink_pss_realtime_result_guard.v',
        c.RTL/'starlink_pss_result_guard_owner_view.v'],
        expected_failure='unknown complete certificate gained public visibility')


def test_illegal_ack_complete_gate_mutant_rejected(tmp_path):
    name='starlink_pss_result_guard_owner_view.v'
    text=(c.RTL/name).read_text();token='assign owner_ack_accept = awaiting_ack &&'
    assert text.count(token)==1
    mutant=tmp_path/name
    mutant.write_text(text.replace(token,"assign owner_ack_accept = completed_input_certified === 1'b1 && awaiting_ack &&"))
    old.run_sv(tmp_path/'wrong-ack',c.visibility_bench(),[
        old.BASELINE/'starlink_pss_realtime_result_guard.v',mutant],
        expected_failure='ACK incorrectly tied to shared completed-input certificate')


def test_unclosed_input_slot_mutant_rejected(tmp_path):
    name='starlink_pss_realtime_input_guard_local_admission.v'
    text=(old.BASELINE/name).read_text()
    token='resetn && job_started && !input_complete && !protocol_fault'
    assert text.count(token)==1
    mutant=tmp_path/name
    mutant.write_text(text.replace(token,'resetn && job_started && !protocol_fault'))
    old.run_sv(tmp_path/'open-input',(c.RTL/'tb_input_closed_premise.sv').read_text(),[mutant],
        expected_failure='closed real input guard certified a strobe')


@pytest.mark.parametrize('literal',['-1','2',"32'bx","32'bz"])
def test_unknown_closed_mode_rejected(tmp_path,literal):
    old.run_sv(tmp_path/'bad',c.composition(0,literal),c.sources(),
        expected_failure='closed-input cutover mode must be known zero or one')


def test_no_ack_admission_or_full_diagnostic_substitution():
    top=(c.RTL/'starlink_pss_fft_retained_output_impl.v').read_text()
    restored=c.inverse('starlink_pss_fft_retained_output_impl.v',top)
    for start,end in [('  wire external_fault_now =','  wire forward_handoff_ack'),
                      ('  assign common_current_fault =','  generate for'),
                      ('  assign completion_accept =','  // All detailed')]:
        assert top[top.index(start):top.index(end)]==restored[restored.index(start):restored.index(end)]
    cutover=(c.RTL/'starlink_pss_core_job_cutover.v').read_text()
    original=c.inverse('starlink_pss_core_job_cutover.v',cutover)
    assert cutover[cutover.index('  always @(posedge'):]==original[original.index('  always @(posedge'):]
    guard=(c.RTL/'starlink_pss_result_guard_owner_view.v').read_text()
    assert "(REQUIRE_KNOWN_COMPLETED_INPUT ? completed_input_certified === 1'b1 : completed_input_certified)" in guard
    assert 'return_phase_allowed &&' in guard
