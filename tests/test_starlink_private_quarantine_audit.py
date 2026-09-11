"""Actual evidence must cover the opt-in private-offer behavior before routing."""
import json
from pathlib import Path
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route
ARTIFACTS=Path('/dev/shm/starlink-private-quarantine.tu8FkVR0')
PIN='2f518556a5e04dc9e161aff35d3c079914a1ecb9d6d7ffb1c6d8064b5337fb25'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_complete_matching_actual_evidence():
    prepared=ARTIFACTS/'prepared-v1';experiment.verify(prepared,PIN)
    experiment.verify_private_quarantine_configuration(prepared)
    main=experiment.audit_private_quarantine(ARTIFACTS/'sim-v1')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v1',PIN,prepared)
    assert main['numerical_rows']==64512
    assert main['private_quarantine']['differences']>0 and aux['private_quarantine']['differences']>0

@pytest.mark.parametrize('mutation',['missing','duplicate','empty_coverage','no_differences','public_fenced','healthy_exact'])
def test_incomplete_or_unsafe_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v1'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_PRIVATE_QUARANTINE_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation in ['empty_coverage','no_differences']:
        field='checks' if mutation=='empty_coverage' else 'differences'
        old=next(x for x in line.split() if x.startswith(field+'='))
        text=text.replace(line,line.replace(old,field+'=0'),1)
    else:text=text.replace(line,line.replace(mutation+'=1',mutation+'=0'),1)
    path=tmp_path/SIM/'simulate.log';path.parent.mkdir(parents=True);path.write_text(text)
    with pytest.raises(ValueError):experiment.audit_private_quarantine(tmp_path,auxiliary=True)

def test_missing_compiled_campaign_blocks_route_before_output(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v1'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text());del outcome['audit']['private_quarantine']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled private quarantine'):
        route.run(main,ARTIFACTS/'synth-v1',tmp_path/'forbidden',ARTIFACTS/'ack-v1')
    assert not (tmp_path/'forbidden').exists()

@pytest.mark.parametrize('mutation',['bench_disabled','synth_disabled'])
def test_compilation_mismatch_rejected(tmp_path,mutation):
    for name in ['tb_fft_staged_output.sv','staged_fft_experiment.tcl']:
        text=(ARTIFACTS/'prepared-v1'/name).read_text()
        if mutation=='bench_disabled':text=text.replace('.PRIVATE_QUARANTINE_OFFER(1)) dut','.PRIVATE_QUARANTINE_OFFER(0)) dut',1)
        else:text=text.replace(' PRIVATE_QUARANTINE_OFFER=1',' PRIVATE_QUARANTINE_OFFER=0',1)
        (tmp_path/name).write_text(text)
    with pytest.raises(ValueError,match='matching enabled private quarantine'):experiment.verify_private_quarantine_configuration(tmp_path)
