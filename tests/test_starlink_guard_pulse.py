"""Completion-pulse retiming: visible guard/diagnostic behavior stays exact."""
from pathlib import Path
import re
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import guard_pulse_transform as transform
import guard_pulse_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

@pytest.mark.parametrize('kind',list(transform.NAMES))
def test_exact_runtime_delta(kind):
    old,new=transform.NAMES[kind]
    a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,kind)==b
    if kind=='GUARD':
        for marker in ['wire final_commit =','assign mailbox_commit_valid =','wire [7:0] faults_now =',
                       'assign owner_ack_accept =','wire private_ack_clear_allowed =']:
            assert a.split(marker)[1].split(';')[0]==b.split(marker)[1].split(';')[0]
        assert 'commit_pulse <= final_commit;' in b
    else:
        assert 'reg output_descriptor_locked;' in b
        assert 'starlink_pss_completion_mailbox_stage #(' in b

@pytest.mark.parametrize('private_ack',[0,1])
@pytest.mark.parametrize('mutation',['none','no_active_view','no_ack_view','logical_receipt','no_active_clear','wrong_ack_priority'])
def test_full_guard_frames_four_state_and_immediate_ack(tmp_path,private_ack,mutation):
    source=(RTL/'starlink_pss_result_guard_commit_pulse.v').read_text()
    changes={
        'no_active_view':('active_storage && !completion_receipt','active_storage'),
        'no_ack_view':('ack_storage || completion_receipt','ack_storage'),
        'logical_receipt':("commit_pulse === 1'b1","commit_pulse == 1'b1"),
        'no_active_clear':('else if (completion_receipt) active_storage <= 0;','else if (1\'b0) active_storage <= 0;'),
        'wrong_ack_priority':('      if (completion_receipt) ack_storage <= 1;\n      if (awaiting_ack && mailbox_input_ready && !protocol_fault && private_ack_clear_allowed)\n        ack_storage <= 0;',
                              '      if (awaiting_ack && mailbox_input_ready && !protocol_fault && private_ack_clear_allowed)\n        ack_storage <= 0;\n      if (completion_receipt) ack_storage <= 1;'),
    }
    if mutation!='none':
        a,b=changes[mutation];assert source.count(a)==1;source=source.replace(a,b,1)
    bench=(RTL/'tb_guard_commit_pulse.sv').read_text().replace('__PRIVATE_ACK__',str(private_ack))
    (tmp_path/'guard.v').write_text(source);(tmp_path/'tb.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),
        str(RTL/'starlink_pss_result_guard_owner_view.v'),str(tmp_path/'guard.v'),str(tmp_path/'tb.sv')],
        capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutation=='none':
        assert result.returncode==0,result.stdout+result.stderr
        row=re.search(r'GUARD_PULSE_COMPONENT_PASS checks=(\d+) pulses=(\d+) storage_edges=(\d+) immediate_acks=(\d+) unknown_pulses=(\d+) four_state_causes=4096 random_cycles=20000',result.stdout)
        assert row and all(int(x)>0 for x in row.groups()),result.stdout
    else:
        assert result.returncode!=0 and 'guard mismatch' in result.stdout,result.stdout

GOOD=''.join(f'GUARD_PULSE_PASS owner={o} checks=177096 pulses=18 storage_edges=18 immediate_acks=0 outputs_exact=1 effective_state_exact=1\n' for o in range(2))
def test_both_complete_witnesses():
    assert len(experiment.witness(GOOD)['owners'])==2

@pytest.mark.parametrize('text',['',GOOD+GOOD,GOOD+'FATAL bad',GOOD.splitlines()[0],
    GOOD.replace('storage_edges=18','storage_edges=0'),GOOD.replace('checks=177096','checks=1'),
    GOOD.replace('effective_state_exact=1','effective_state_exact=0')])
def test_missing_weak_or_duplicate_witness_rejected(text):
    with pytest.raises(ValueError):experiment.witness(text)

def test_storage_injection_mirrors_only_original_oracle():
    bench='\n'.join(f"{verb} dut.owners[{o}].result_guard.fault_reasons"+("=8'h04;" if verb=='force' else ';') for o in range(2) for verb in ['force','release'])
    result=experiment.mirror_guard_faults(bench)
    assert result.count('force dut.')==result.count('release dut.')==2
    assert result.count('force pulse_guard_reference')==result.count('release pulse_guard_reference')==2
    for owner in range(2):
        for verb in ['force','release']:
            extra=f"{verb} pulse_guard_reference[{owner}].original.fault_reasons"+("=8'h04;" if verb=='force' else ';')
            result=result.replace(extra,'')
    assert result==bench
    with pytest.raises(ValueError):experiment.mirror_guard_faults('')
