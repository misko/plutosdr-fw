"""Complete product-stage top inverse and preservation of component sources."""
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-forward-receipt.7z0zKX/prepared-v1')


def undo_product_stage(text):
    for label in ['WIRES','STAGE']:
        text,count=re.subn(r'  // BEGIN PRODUCT IDENTITY '+label+r'\n.*?  // END PRODUCT IDENTITY '+label+r'\n','',text,flags=re.S)
        assert count==1
    pairs=[
      ('.output_valid(product_valid), .output_ready(product_stage_ready && !fast_fault)',
       '.output_valid(product_valid), .output_ready(product_bank_ready && !fast_fault)'),
      ('starlink_pss_product_mailbox_staged_identity #(.RESET_RELEASE_EXTERNAL(1), .EXPLICIT_COMMIT(1)) product_bank',
       'starlink_pss_mailbox_owner_view #(.RESET_RELEASE_EXTERNAL(1), .EXPLICIT_COMMIT(1)) product_bank'),
      ('.input_valid(staged_product_valid && !fast_fault), .input_ready(product_bank_ready)',
       '.input_valid(product_valid && !fast_fault), .input_ready(product_bank_ready)'),
      ('.input_data(staged_product_data), .input_position(staged_product_position), .input_last(staged_product_last)',
       '.input_data({product_q, product_i}), .input_position(product_position), .input_last(product_last)'),
      ('    .input_metadata(staged_product_metadata), .input_metadata_certified(staged_product_identity_good),\n'
       '    .writer_identity_metadata(product_writer_metadata), .writer_identity_load(product_writer_metadata_load),\n',
       "    .input_metadata({1'b1, product_start, product_exponent}),\n"),
      ('.input_fault(product_ram_fault), .input_framing_fault_now(product_bank_framing_fault_now)',
       '.input_fault(product_bank_fault), .input_framing_fault_now(product_bank_framing_fault_now)'),
    ]
    for before,after in pairs:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text


def test_complete_top_delta_and_other_runtime_preserved():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b'
    name='starlink_pss_fft_staged_output_impl.v'
    assert undo_product_stage((RTL/name).read_text())==(PARENT/name).read_text()
    for name in (PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split():
        if name!='starlink_pss_fft_staged_output_impl.v' and (RTL/name).exists():
            assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name


def test_stage_quarantine_feeds_all_existing_product_fault_summaries():
    top=(RTL/'starlink_pss_fft_staged_output_impl.v').read_text()
    assert 'assign product_bank_fault = product_ram_fault || product_stage_fault;' in top
    assert '.abort_epoch(fast_fault || product_ram_fault ||' in top
    assert '.reference_metadata(product_writer_metadata_load ? staged_product_metadata : product_writer_metadata)' in top
    assert '(staged_product_last === 1\'b0) || (product_commit_authorized === 1\'b1)' in top


def undo_product_stage_bench(text):
    text,count=re.subn(r'  // BEGIN FINAL CAPACITY WITNESS\n.*?  // END FINAL CAPACITY WITNESS\n','',text,flags=re.S)
    assert count==1
    text=text.replace('      report_final_capacity; // FINAL CAPACITY AUXILIARY\n','',1)
    text=text.replace('    report_final_capacity; // FINAL CAPACITY MAIN\n','',1)
    for label in ['WITNESS','BOUNDARIES','AUXILIARY']:
        text,count=re.subn(r' *// BEGIN ACTUAL PRODUCT STAGE '+label+r'\n.*? *// END ACTUAL PRODUCT STAGE '+label+r'\n','',text,flags=re.S)
        assert count==1
    text=text.replace('    report_product_stage; // ACTUAL PRODUCT STAGE MAIN\n','',1)
    text=text.replace('if(dut.product_valid && dut.product_stage_ready)',
                      'if(dut.product_valid && dut.product_bank_ready)',1)
    text=text.replace('if(dut.forward_retirement_valid && dut.product_bank_ready && dut.kernel_ready)',
                      'if(dut.forward_retirement_valid && dut.product_bank_ready)',1)
    return text


def test_complete_bench_inverse_preserves_original_cases_and_deadlines():
    name='tb_fft_staged_output.sv'
    assert undo_product_stage_bench((RTL/name).read_text())==(PARENT/name).read_text()
