"""Compare complete original/shared guard outputs and private state."""
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
import shared_preflight_history_transform as transform

def test_exact_source_delta():
    for old,new,changes in [
        ('starlink_pss_fft_private_replay_sequence_impl','starlink_pss_fft_shared_preflight_history_impl',transform.TOP_CHANGES),
        ('starlink_pss_result_guard_owner_view','starlink_pss_result_guard_shared_preflight',transform.GUARD_CHANGES)]:
        a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
        assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

@pytest.mark.parametrize('mode,mutation',[(0,'none'),(1,'none'),(1,'drop_history'),(1,'omit_cause'),(1,'no_async_reset'),(1,'extra_cycle')])
def test_full_guard_comparison(tmp_path,mode,mutation):
    source=(RTL/'starlink_pss_result_guard_shared_preflight.v').read_text()
    bench=(RTL/'tb_shared_preflight_guard.sv').read_text().replace('__MODE__',str(mode))
    if mutation=='drop_history':source=source.replace('(|shared_preflight_history)',"1'b0",1)
    elif mutation=='omit_cause':source=source.replace('(|shared_preflight_history)','(|shared_preflight_history[4:0])',1)
    elif mutation=='no_async_reset':bench=bench.replace('always @(posedge clk or negedge resetn)','always @(posedge clk)',1)
    elif mutation=='extra_cycle':
        bench=bench.replace('reg [5:0] shared_preflight_history;','reg [5:0] shared_preflight_history;\nreg [5:0] delayed;\nalways @(posedge clk or negedge resetn)if(!resetn)delayed<=0;else delayed<=preflight_events_now;',1)
        bench=bench.replace('shared_preflight_history|preflight_events_now','shared_preflight_history|delayed',1)
    (tmp_path/'guard.v').write_text(source);(tmp_path/'tb.sv').write_text(bench)
    built=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(RTL/'starlink_pss_result_guard_owner_view.v'),str(tmp_path/'guard.v'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(built.stdout+built.stderr);assert built.returncode==0,built.stdout+built.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutation=='none':assert result.returncode==0 and 'SHARED_PREFLIGHT_COMPONENT_PASS' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

def test_history_and_current_vetoes():
    top=(RTL/'starlink_pss_fft_shared_preflight_history_impl.v').read_text()
    old=(RTL/'starlink_pss_fft_private_replay_sequence_impl.v').read_text()
    for prefix in ['wire preparation_fault_now =','wire product_commit_authorized =','wire replay_publication_fault =']:
        assert top.split(prefix,1)[1].split(';',1)[0]==old.split(prefix,1)[1].split(';',1)[0]
    assert 'always @(posedge fft_clk or negedge fast_running)' in top
    assert 'else shared_preflight_history <= shared_preflight_history | preflight_events_now;' in top
    assert '.preflight_fault_evidence_now(preparation_fault_now)' in top
