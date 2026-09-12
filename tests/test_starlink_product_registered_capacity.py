"""Actual mailbox, ordered words, deliberately zero simultaneous refills."""
import re
import pytest
from tests.test_starlink_parallel_product_identity import RTL,PARENT,BANK,compile_run
import product_registered_capacity_transform as transform
import product_registered_capacity_experiment as experiment

def test_exact_declared_delta():
    for old,new,changes in [
        ('starlink_pss_fft_private_replay_sequence_impl.v',experiment.NEW+'.v',transform.TOP_CHANGES),
        ('starlink_pss_product_identity_parallel_reference.v',experiment.BANK+'.v',transform.BANK_CHANGES),
        ('parallel_product_identity_observer.svh','product_registered_capacity_observer.svh',transform.OBSERVER_CHANGES)]:
        a=(RTL/old).read_text();b=(RTL/new).read_text()
        assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

@pytest.mark.parametrize('mutation',['none','restore_refill','unchecked','lost_abort','drop_final','bypass_certificate'])
def test_real_mailbox_slow_refill_faults_recovery(tmp_path,mutation):
    source=(RTL/(experiment.BANK+'.v')).read_text();bank=BANK.read_text()
    bench=(RTL/'tb_product_identity_stage.sv').read_text()
    bench=bench.replace('starlink_pss_product_identity_stage stage(',experiment.BANK+' stage(',1)
    bench=bench.replace('.reference_metadata(reference_metadata),','.reference_metadata(held_metadata),.retiring_metadata(staged_metadata),.reference_select(metadata_load),',1)
    bench=bench.replace('.output_valid(staged_valid),','.refill_capacity(bank_ready && allow_write),.output_valid(staged_valid),',1)
    assert bench.count('if(!input_ready)$fatal(1,"first-word reference update inserted a refill pause");')==1
    bench=bench.replace('if(!input_ready)$fatal(1,"first-word reference update inserted a refill pause");','if(input_ready!==0)$fatal(1,"first-word retirement must not refill occupied slot");',1)
    assert bench.count('refills<511')==1
    bench=bench.replace('refills<511','refills!=0',1)
    if mutation=='restore_refill':source=source.replace('live && !full','live && (!full || refill_capacity)',1)
    elif mutation=='unchecked':source=source.replace("(reference_select ? match_retiring : match_held) === 1'b1","1'b1",1)
    elif mutation=='lost_abort':source=source.replace("(abort_epoch !== 1'b0)","1'b0",1)
    elif mutation=='drop_final':bench=bench.replace("((staged_last===1'b0) || bank_commit)","1'b1",1)
    elif mutation=='bypass_certificate':bank=bank.replace("input_metadata_certified === 1'b1","1'b1",1)
    (tmp_path/'stage.v').write_text(source);(tmp_path/'bank.v').write_text(bank)
    result=compile_run(tmp_path,bench,[PARENT,tmp_path/'stage.v',tmp_path/'bank.v'])
    if mutation=='none':
        assert result.returncode==0,result.stdout+result.stderr
        row=re.search(r'PRODUCT_IDENTITY_COMPONENT_PASS good_blocks=(\d+) bad_metadata=420 bad_framing=6 resets=8 reads=(\d+) refills=(\d+) holds=(\d+) oracle=(\d+) updates=(\d+)',result.stdout)
        assert row,result.stdout
        good,reads,refills,holds,oracle,updates=map(int,row.groups())
        assert good==12 and reads==6144 and refills==0 and holds>=200 and oracle>=1000 and updates>=12
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

GOOD='REGISTERED_PRODUCT_CAPACITY_PASS checks=10000 captures=9216 first_refills=0 first_retire=18 first_capture=18 four_state_exact=1 same_edge_capture=1\n'
def test_witness():assert experiment.witness(GOOD)['first_refills']==0
@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD+'FATAL',GOOD.replace('first_refills=0','first_refills=1'),
    GOOD.replace('first_retire=18','first_retire=17'),GOOD.replace('first_capture=18','first_capture=17'),
    GOOD.replace('four_state_exact=1','four_state_exact=0')])
def test_incomplete_witness_rejected(bad):
    with pytest.raises(ValueError):experiment.witness(bad)
