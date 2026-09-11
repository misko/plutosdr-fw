from pathlib import Path
import re
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import local_completion_transform as transform
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def test_exact_private_delta():
    old=(RTL/'starlink_pss_fft_buffered_forward_impl.v').read_text()
    new=(RTL/'starlink_pss_fft_completion_local_impl.v').read_text()
    assert transform.transform(old)==new
    assert transform.undo(new)==old
    assert len(transform.CHANGES)==3

def simulate(tmp_path,mutation=None):
    bench=(RTL/'tb_local_completion_facts.sv').read_text()
    changes={
        'omit_real_fault':('compressed={checks[41:32],checks[25:0]}','compressed={checks[41:32],checks[25:1],1\'b1}'),
        'omit_quarantine':('.request(request),.quarantine(quarantine),.consume(consume),\n    .checks_good(compressed)', '.request(request),.quarantine(1\'b0),.consume(consume),\n    .checks_good(compressed)'),
        'omit_request':('.request(request),.quarantine(quarantine),.consume(consume),\n    .checks_good(compressed)', '.request(1\'b1),.quarantine(quarantine),.consume(consume),\n    .checks_good(compressed)'),
        'wrong_expansion':("expanded={new_good[35:26],6'b111111,new_good[25:0]}","expanded={new_good[35:26],6'b111110,new_good[25:0]}"),
    }
    if mutation:
        before,after=changes[mutation];assert bench.count(before)==1;bench=bench.replace(before,after)
    source=tmp_path/'bench.sv';source.write_text(bench)
    binary=tmp_path/'sim'
    command=['iverilog','-g2012','-s','tb','-o',str(binary),str(source),str(RTL/'starlink_pss_admission_certificate.v')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0
    result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_cycle_exact_private_certificate(tmp_path):
    result=simulate(tmp_path);assert result.returncode==0,result.stdout+result.stderr
    match=re.search(r'LOCAL_COMPLETION_UNIT_PASS checks=(\d+) owned=(\d+) permits=(\d+) private_differences=(\d+)',result.stdout)
    assert match and int(match[1])>=70000 and int(match[2])>=100 and int(match[3])>=10 and int(match[4])>=100

@pytest.mark.parametrize('mutation',['omit_real_fault','omit_quarantine','omit_request','wrong_expansion'])
def test_mutants_rejected(tmp_path,mutation):
    result=simulate(tmp_path,mutation)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout
