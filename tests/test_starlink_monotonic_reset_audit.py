"""Matching reset-release profile and complete real-FFT witness are mandatory."""
import json
from pathlib import Path
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route
ARTIFACTS=Path('/dev/shm/starlink-monotonic-reset.pL4aOpKf')
PIN='adb2543750adea239f66f5b187057aef1ecdbd112cbcf5faef2161f7f6ddb3f3'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_complete_matching_actual_evidence():
    prepared=ARTIFACTS/'prepared-v1';experiment.verify(prepared,PIN)
    experiment.verify_monotonic_reset_configuration(prepared)
    main=experiment.audit_monotonic_reset(ARTIFACTS/'sim-v1')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v1',PIN,prepared)
    assert main['numerical_rows']==64512
    for result in [main,aux]:
        assert min(result['monotonic_reset'][k] for k in ['fast','slow'])>=1000
        assert result['monotonic_reset']['resets']>=4

@pytest.mark.parametrize('mutation',['missing','duplicate','empty_fast','empty_slow','empty_resets','current_exact','latency_unchanged'])
def test_incomplete_or_changed_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v1'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_MONOTONIC_RESET_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation.startswith('empty_'):
        field=mutation.split('_')[1];old=next(x for x in line.split() if x.startswith(field+'='))
        text=text.replace(line,line.replace(old,field+'=0'),1)
    else:text=text.replace(line,line.replace(mutation+'=1',mutation+'=0'),1)
    path=tmp_path/SIM/'simulate.log';path.parent.mkdir(parents=True);path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_monotonic_reset(tmp_path,auxiliary=True)

def test_missing_compiled_campaign_blocks_route_before_output(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v1'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text());del outcome['audit']['monotonic_reset']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled monotonic reset'):
        route.run(main,ARTIFACTS/'synth-v1',tmp_path/'forbidden',ARTIFACTS/'ack-v1')
    assert not (tmp_path/'forbidden').exists()

@pytest.mark.parametrize('mutation',['bench_disabled','synth_disabled'])
def test_compilation_mismatch_rejected(tmp_path,mutation):
    for name in ['tb_fft_staged_output.sv','staged_fft_experiment.tcl']:
        text=(ARTIFACTS/'prepared-v1'/name).read_text()
        if mutation=='bench_disabled':text=text.replace('.MONOTONIC_OUTER_RESET(1)','.MONOTONIC_OUTER_RESET(0)',1)
        else:text=text.replace(' MONOTONIC_OUTER_RESET=1',' MONOTONIC_OUTER_RESET=0',1)
        (tmp_path/name).write_text(text)
    with pytest.raises(ValueError,match='matching enabled monotonic reset'):experiment.verify_monotonic_reset_configuration(tmp_path)
