from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_private_forward_capture import REFERENCE_INSTANCE
from tests.test_starlink_balanced_forward_identity import compile_run
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import forward_private_status_experiment as experiment
import forward_private_status_transform as transform
RTL=experiment.RTL

def test_exact_private_status_top_delta():
    old=(RTL/(experiment.base.NEW+'.v')).read_text();new=(RTL/(experiment.NEW+'.v')).read_text()
    assert transform.top(old)==new and transform.undo_top(new)==old
    assert "(forward_buffer_fault === 1'b0)" in new
    assert 'offered_external_fault_now || forward_buffer_fault || result_fault ||' in new
    assert 'registered_quarantine = fast_fault || forward_buffer_private_fault || result_fault ||' in new

def test_bank_adds_only_existing_sticky_status():
    old=(RTL/(experiment.base.BANK+'.v')).read_text();new=(RTL/(experiment.BANK+'.v')).read_text()
    assert transform.transform(old,transform.BANK_CHANGES)==new
    assert 'assign private_fault = fault_q;' in new

@pytest.mark.parametrize('case',range(21))
def test_bank_current_behavior_and_private_status(tmp_path,case):
    reference=(RTL/(experiment.base.BANK+'.v')).read_text().replace('module '+experiment.base.BANK+' #(','module bank_reference #(',1)
    (tmp_path/'reference.v').write_text(reference)
    observer=REFERENCE_INSTANCE.replace('      equivalence_checks=equivalence_checks+1;',
        '      if(dut.private_fault!==dut.fault_q)$fatal(1,"private status not existing register");\n      equivalence_checks=equivalence_checks+1;')
    observer=observer.replace('        private_differences=private_differences+1;',
        '        $fatal(1,"private status changed bank progress");')
    bench=(RTL/'tb_forward_return_bank.sv').read_text().replace('starlink_pss_forward_return_bank dut(',experiment.BANK+' dut(',1)
    assert experiment.BANK+' dut(' in bench
    bench=bench.replace('module tb;', 'module tb;\n  wire private_fault;', 1)
    bench=bench.replace('\nendmodule','\n'+observer+'\nendmodule',1)
    result=compile_run(tmp_path,bench,[RTL/(experiment.BANK+'.v'),tmp_path/'reference.v'],case)
    assert result.returncode==0,result.stdout+result.stderr
    row=re.search(r'PRIVATE_FORWARD_CAPTURE_EQ checks=(\d+) private_differences=0 current_exact=1 valid_payload_exact=1',result.stdout)
    assert row and int(row[1])>2000,result.stdout

MAIN='FORWARD_PRIVATE_STATUS_PASS checks=10000 new_fault_edges=0 private_completions=0 guard_delays=0 current_publication_fenced=1 registered_reuse_fenced=1 bounded_global_fault=1\n'
HEAD=MAIN.replace('new_fault_edges=0','new_fault_edges=11').replace('private_completions=0','private_completions=2').replace('guard_delays=0','guard_delays=1')
LINES=[f'FORWARD_PRIVATE_STATUS_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(11)]
LINES+=['FORWARD_PRIVATE_STATUS_BOUNDARIES_PASS cases=11 private_delta_exercised=1 fresh_recovery=1\n']
AUX=HEAD+''.join(LINES)
def test_main_witness():assert experiment.witness(MAIN)['new_fault_edges']==0
def test_auxiliary_witness():assert experiment.witness(AUX,True)['private_completions']==2

@pytest.mark.parametrize('line',range(12))
def test_each_boundary_required(line):
    lines=LINES.copy();del lines[line]
    with pytest.raises(ValueError):experiment.witness(HEAD+''.join(lines),True)

@pytest.mark.parametrize('log',[AUX+AUX,AUX+'FATAL\n',AUX.replace('new_fault_edges=11','new_fault_edges=10'),
    AUX.replace('private_completions=2','private_completions=1'),AUX.replace('guard_delays=1','guard_delays=0'),
    AUX.replace('bounded_global_fault=1','bounded_global_fault=0'),AUX.replace('current_publication_fenced=1','current_publication_fenced=0'),
    AUX.replace('new_publications=0','new_publications=1',1),AUX.replace('fresh_reads=512','fresh_reads=511',1)])
def test_incomplete_auxiliary_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log,True)
