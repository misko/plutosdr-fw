"""Actual handoff equality coverage must survive re-audit before routing."""
import json
from pathlib import Path
import re
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route

ARTIFACTS=Path('/dev/shm/starlink-balanced-handoff.5K7fHIYq')
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_both_current_actual_campaigns():
    prepared=ARTIFACTS/'prepared-v2'
    main=experiment.audit_balancedhandoff(ARTIFACTS/'sim-v2')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v2',experiment.sha(prepared/'SHA256SUMS'),prepared)
    assert main['numerical_rows']==64512
    assert main['balancedhandoff']['exact_current'] and aux['balancedhandoff']['exact_current']


def test_monitor_correction_changes_no_runtime_and_preserves_failed_evidence():
    old=ARTIFACTS/'prepared-v1';new=ARTIFACTS/'prepared-v2'
    assert experiment.sha(old/'SHA256SUMS')=='ccd6dc48b97cc486332d74ff785554c6bacbb7b34c84af584ca4c561c3b4add1'
    assert experiment.sha(new/'SHA256SUMS')=='c6b632215fbd08fa2c06150652f39a3967163566eeaac8c01138c7475c1c429e'
    names=(new/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:assert (old/name).read_bytes()==(new/name).read_bytes(),name
    failed=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text())
    assert failed['sources_unchanged'] and 'simulator failure' in failed['error']
    log=(ARTIFACTS/'sim-v2'/SIM/'simulate.log').read_text()
    assert 'STAGED_COMPLETION_CASE_PASS boundary=6' in log
    assert re.search(r'^STAGED_HANDOFF_SETTLED_DELTA .*before=1 reference=0 settled=0$',log,re.M)
    assert not (ARTIFACTS/'route-v1').exists()


@pytest.mark.parametrize('mutation',['missing','duplicate','short_checks','short_owned','wrong_identity'])
def test_incomplete_auxiliary_handoff_witness_rejected(tmp_path,mutation):
    source=ARTIFACTS/'ack-v2'/SIM/'simulate.log'
    text=source.read_text()
    line=next(line for line in text.splitlines(True) if line.startswith('STAGED_BALANCED_HANDOFF_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation=='wrong_identity':text=text.replace(line,line.replace('exact_current=1','exact_current=0'),1)
    else:
        field=mutation.removeprefix('short_');text=text.replace(line,re.sub(field+r'=\d+',field+'=1',line),1)
    target=tmp_path/SIM/'simulate.log';target.parent.mkdir(parents=True);target.write_text(text)
    with pytest.raises(ValueError,match='complete actual balanced handoff'):
        experiment.audit_balancedhandoff(tmp_path,auxiliary=True)


def test_route_rejects_missing_main_compiled_proof(tmp_path):
    source=ARTIFACTS/'sim-v2'
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(source/SIM/name,main/SIM/name)
    outcome=json.loads((source/'outcome.json').read_text());del outcome['audit']['balancedhandoff']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled balanced handoff'):
        route.run(main,ARTIFACTS/'synth-v2',tmp_path/'forbidden',ARTIFACTS/'ack-v2')
    assert not (tmp_path/'forbidden').exists()
