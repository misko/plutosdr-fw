"""Non-vacuous observer coverage and same-location inherited fault injection."""
import re
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import shared_preflight_history_experiment_v2 as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def log(auxiliary):
    rows=[]
    if auxiliary:
        rows += [f'SHARED_PREFLIGHT_BOUNDARY_PASS case={i} cause={i if i<6 else 3} raw_reset={int(i>=8)} fresh_reads=512 fresh_releases=1' for i in range(10)]
        rows += ['SHARED_PREFLIGHT_BOUNDARIES_PASS cases=10 causes=6 metadata_unknown=2 raw_resets=2 original_guards_exact=1']
    rows += [f'SHARED_PREFLIGHT_GUARD_PASS owner={o} checks=10000 preflight_edges={6 if auxiliary else 0} outputs_exact=1 private_state_exact=1' for o in range(2)]
    return '\n'.join(rows)+'\n'

@pytest.mark.parametrize('auxiliary',[False,True])
def test_complete_witness(auxiliary):
    assert experiment.witness(log(auxiliary),auxiliary)['auxiliary']==auxiliary

@pytest.mark.parametrize('index',range(13))
def test_each_required_auxiliary_witness(index):
    rows=log(True).splitlines()
    del rows[index]
    with pytest.raises(ValueError):experiment.witness('\n'.join(rows),True)

@pytest.mark.parametrize('old,new',[
    ('checks=10000','checks=9999'),
    ('preflight_edges=6','preflight_edges=0'),
    ('outputs_exact=1','outputs_exact=0'),
    ('private_state_exact=1','private_state_exact=0'),
    ('fresh_reads=512','fresh_reads=511'),
    ('raw_reset=1','raw_reset=0'),
    ('metadata_unknown=2','metadata_unknown=0'),
])
def test_weakened_witness_rejected(old,new):
    with pytest.raises(ValueError):experiment.witness(log(True).replace(old,new,1),True)

def test_duplicate_owner_and_boundary_rejected():
    for row in [log(True).splitlines()[0],log(True).splitlines()[-1]]:
        with pytest.raises(ValueError):experiment.witness(log(True)+row+'\n',True)

def injection_source():
    return '\n'.join(f"force dut.owners[{o}].result_guard.fault_reasons=8'h04;\nrelease dut.owners[{o}].result_guard.fault_reasons;" for o in range(2))

def test_force_maps_storage_and_reference_without_disabling_observer():
    new=experiment.mirror_guard_storage_faults(injection_source())
    for owner in range(2):
        assert f"force dut.owners[{owner}].result_guard.private_fault_reasons=8'h04;" in new
        assert f"force shared_guard_reference[{owner}].original.fault_reasons=8'h04;" in new
        assert f'release dut.owners[{owner}].result_guard.private_fault_reasons;' in new
        assert f'release shared_guard_reference[{owner}].original.fault_reasons;' in new
    assert new.count('dut.shared_preflight_history!==0')==2

@pytest.mark.parametrize('mutation',['missing','duplicate'])
def test_ambiguous_force_mapping_rejected(mutation):
    source=injection_source()
    source=source.replace('force dut.owners[0]','force dut.owners[9]',1) if mutation=='missing' else source+'\n'+source
    with pytest.raises(ValueError):experiment.mirror_guard_storage_faults(source)

def test_every_guard_interface_port_is_bound_or_compared():
    original=(RTL/'starlink_pss_result_guard_owner_view.v').read_text().split(');',1)[0]
    observer=(RTL/'shared_preflight_guard_observer.svh').read_text()
    ports=re.findall(r'\b(input|output)\s+(?:wire|reg)\s+(?:\[[^\]]+\]\s+)?(\w+)',original)
    assert len(ports)>40
    for direction,name in ports:
        if direction=='input':
            assert f'.{name}(dut.owners[owner].result_guard.{name})' in observer
        else:
            assert f'.{name}()' in observer
            assert f'dut.owners[owner].result_guard.{name} !== original.{name}' in observer
    assert 'always @(posedge fft_clk)begin\n    compare_guard;' in observer
    assert '#0.001;compare_guard;' in observer

def test_direct_cause_campaign_retains_quarantine_and_recovery():
    fragment=(RTL/'shared_preflight_history_boundaries.svh').read_text()
    for cause in ['preflight_valid','preflight_position','preflight_lease','engine_metadata','product_bank_ready','preparation_age']:
        assert f'force dut.{cause}=' in fragment
        assert f'release dut.{cause};' in fragment
    for check in ['dut.shared_preflight_history!==expected_history','dut.job_accept!==0','dut.completion_accept!==0',
                  'dut.product_owner_request!==product_before','dut.output_request!==output_before',
                  'if(which==8)resetn=0;else fft_resetn=0;','aux_recover;']:
        assert check in fragment

def test_sticky_fault_observer_matches_procedural_four_state_updates(tmp_path):
    import subprocess
    source=(ROOT/'tools/shared_preflight_history_experiment_v3.py').read_text()
    assert "local_expected_fault=dut.fast_fault;" in source
    assert "if(dut.result_fault || (|dut.local_fault_snapshot))local_expected_fault=1;" in source
    bench="""`timescale 1ns/1ps
module tb;
reg clk=0,q,a,b,expected,old_oracle;
integer i,j,k,mismatches=0;
always @(posedge clk)if(a||b)q<=1;
function automatic four(input integer n);
case(n)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
initial begin
for(i=0;i<4;i=i+1)for(j=0;j<4;j=j+1)for(k=0;k<4;k=k+1)begin
q=four(i);a=four(j);b=four(k);
expected=q;if(a||b)expected=1;
old_oracle=q||a||b;
#1;clk=1;#1;
if(q!==expected)$fatal(1,"procedural reference mismatch");
if(q!==old_oracle)mismatches=mismatches+1;
clk=0;#1;
end
if(mismatches==0)$fatal(1,"old oracle weakness not exercised");
$display("PROCEDURAL_STICKY_PASS cases=64");$finish;
end
endmodule
"""
    (tmp_path/'tb.sv').write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'tb.sv')],capture_output=True,text=True)
    assert build.returncode==0,build.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0 and 'PROCEDURAL_STICKY_PASS cases=64' in result.stdout
