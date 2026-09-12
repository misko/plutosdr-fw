"""Mirrored fault injections must remain single statements inside if/else."""
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import guard_pulse_experiment as rejected
import guard_pulse_experiment_v2 as rejected_scoped
import guard_pulse_experiment_v3 as fixed

BODY="""if(choose==0)force dut.owners[0].result_guard.fault_reasons=8'h04;
else force dut.owners[1].result_guard.fault_reasons=8'h04;
if(choose==0)release dut.owners[0].result_guard.fault_reasons;
else release dut.owners[1].result_guard.fault_reasons;"""

def test_only_scoping_delta_and_original_targets():
    text=fixed.mirror_guard_faults(BODY)
    assert text.count('begin ')==text.count(' end')==4
    assert ''.join(text.replace('begin ','').replace(' end','').split())==''.join(rejected.mirror_guard_faults(BODY).split())
    assert text.count('force dut.')==text.count('release dut.')==2

@pytest.mark.parametrize('good',[False,True])
@pytest.mark.parametrize('adjacent',[False,True])
def test_conditional_injection_compiles(tmp_path,good,adjacent):
    body=BODY
    if adjacent:
        body=BODY.split('if(choose==0)release')[0]+"release dut.owners[0].result_guard.fault_reasons;release dut.owners[1].result_guard.fault_reasons;"
    helper=fixed if good else (rejected_scoped if adjacent else rejected)
    code=helper.mirror_guard_faults(body)
    source="""module guard;reg[7:0]fault_reasons=0;endmodule
module fixture_design;
for(genvar n=0;n<2;n=n+1)begin:owners guard result_guard();end
endmodule
module tb;fixture_design dut();reg choose=0;
for(genvar n=0;n<2;n=n+1)begin:pulse_guard_reference guard original();end
initial begin """+code+" $finish;end endmodule"
    path=tmp_path/'tb.sv';path.write_text(source)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert (result.returncode==0)==good,result.stdout+result.stderr
    if not good:assert 'syntax error' in result.stderr

@pytest.mark.parametrize('text',['',BODY+BODY])
def test_missing_or_duplicate_injections_rejected(text):
    with pytest.raises(ValueError):fixed.mirror_guard_faults(text)
