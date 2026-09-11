"""Integrated READY requires source-matched actual FFT and synthesis evidence."""
import json
from pathlib import Path
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route
ARTIFACTS=Path('/dev/shm/starlink-parallel-ready.uE2Iyp1W')
PIN='5fb473217ce86afe71b36ae7ee879f314d54667c0909bcaa801dcf81364b3590'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_complete_matching_actual_evidence():
    prepared=ARTIFACTS/'prepared-v1';experiment.verify(prepared,PIN)
    experiment.verify_parallel_ready_configuration(prepared)
    main=experiment.audit_parallel_ready(ARTIFACTS/'sim-v1')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v1',PIN,prepared)
    assert main['numerical_rows']==64512
    for result in [main,aux]:
        assert result['parallel_ready']['checks']>=1000
        assert result['forward_capacity_shadow']['runtime_unchanged'] is False

@pytest.mark.parametrize('mutation',['missing','duplicate','checks','ports','current_exact','original_guard_wiring','latency_unchanged'])
def test_incomplete_or_changed_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v1'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_PARALLEL_READY_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    else:
        old=next(x for x in line.split() if x.startswith(mutation+'='))
        text=text.replace(line,line.replace(old,mutation+'=0'),1)
    path=tmp_path/SIM/'simulate.log';path.parent.mkdir(parents=True);path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_parallel_ready(tmp_path,auxiliary=True)

def test_missing_compiled_campaign_blocks_route_before_output(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v1'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text());del outcome['audit']['parallel_ready']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled parallel kernel ready'):
        route.run(main,ARTIFACTS/'synth-v1',tmp_path/'forbidden',ARTIFACTS/'ack-v1')
    assert not (tmp_path/'forbidden').exists()

@pytest.mark.parametrize('mutation',['bench_disabled','synth_disabled'])
def test_compilation_mismatch_rejected(tmp_path,mutation):
    for name in ['tb_fft_staged_output.sv','staged_fft_experiment.tcl']:
        text=(ARTIFACTS/'prepared-v1'/name).read_text()
        if mutation=='bench_disabled':text=text.replace('.PARALLEL_KERNEL_READY(1)','.PARALLEL_KERNEL_READY(0)',1)
        else:text=text.replace(' PARALLEL_KERNEL_READY=1',' PARALLEL_KERNEL_READY=0',1)
        (tmp_path/name).write_text(text)
    with pytest.raises(ValueError,match='matching enabled parallel kernel ready'):experiment.verify_parallel_ready_configuration(tmp_path)
