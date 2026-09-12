from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_reporting_delay_does_not_relax_local_quarantine():
    rtl=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
    old=(rtl/'private_replay_sequence_boundaries.svh').read_text()
    new=(rtl/'private_replay_sequence_boundaries_v2.svh').read_text()
    start=new.index('        $display("PRIVATE_REPLAY_PENDING_FAULT')
    end=new.index('        repeat(100)begin',start)
    early=new[start:end]
    assert new[:start]+new[end:]==old
    assert 'repeat(12)begin' in early
    for gate in ['dut.forward_buffer_private_fault!==1','dut.registered_quarantine!==1',
                 'output_valid || aux_reads || aux_releases || dut.job_accept || dut.completion_accept',
                 'dut.product_bank.owner_request!==product_before','dut.output_request!==output_before']:
        assert gate in early
    assert 'if(fault!==1' in new[end:]

def test_actual_synchronizer_is_not_bypassed():
    source=(ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_private_replay_sequence_impl.v').read_text()
    assert 'else fast_fault_slow <= {fast_fault_slow[0], fast_fault};' in source
    assert 'assign fault = source_fault || slow_lookup_fault || fast_fault_slow[1];' in source
