"""Require real pending-receipt ownership/cancellation coverage before routing."""
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
ARTIFACTS=Path('/dev/shm/starlink-completion-stage.rTnPYQ8U')
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_actual_pair_and_runtime_identical_monitor_correction():
    prepared=ARTIFACTS/'prepared-v2'
    main=experiment.audit_completion_slot(ARTIFACTS/'sim-v3')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v2',experiment.sha(prepared/'SHA256SUMS'),prepared)
    assert main['numerical_rows']==64512
    assert aux['completion_slot']['boundaries']==['0','1','2']
    assert experiment.sha(ARTIFACTS/'prepared-v1/SHA256SUMS')=='ae1a66db7b8c98f7832ebdc64b32ee247e9db4ef3faf27ac6577ce6d48a4e4eb'
    assert experiment.sha(prepared/'SHA256SUMS')=='579b4b69fee7eb67a20befbb901d53b0ff033dd7305603e57b532d950d47114c'
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:assert (prepared/name).read_bytes()==(ARTIFACTS/'prepared-v1'/name).read_bytes(),name
    for mode in ['sim','ack']:
        failed=json.loads((ARTIFACTS/(mode+'-v1')/'outcome.json').read_text())
        assert failed['sources_unchanged'] and 'simulator failure' in failed['error']
    assert not (ARTIFACTS/'route-v1').exists()


@pytest.mark.parametrize('mutation',['missing','duplicate','short_accepts','short_consumes','short_holds',
                                    'wrong_ownership','wrong_payload','missing_boundary','short_recovery'])
def test_incomplete_actual_receipt_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v2'/SIM/'simulate.log').read_text()
    line=next(line for line in text.splitlines(True) if line.startswith('STAGED_COMPLETION_SLOT_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation.startswith('short_') and mutation!='short_recovery':
        field=mutation.removeprefix('short_');text=text.replace(line,re.sub(field+r'=\d+',field+'=1',line),1)
    elif mutation in {'wrong_ownership','wrong_payload'}:
        field='immediate_ownership' if mutation=='wrong_ownership' else 'held_payload'
        text=text.replace(line,line.replace(field+'=1',field+'=0'),1)
    else:
        case=next(line for line in text.splitlines(True) if line.startswith('STAGED_COMPLETION_SLOT_CASE_PASS boundary=0 '))
        text=text.replace(case,'' if mutation=='missing_boundary' else case.replace('fresh_reads=512','fresh_reads=511'),1)
    target=tmp_path/SIM/'simulate.log';target.parent.mkdir(parents=True);target.write_text(text)
    with pytest.raises(ValueError):experiment.audit_completion_slot(tmp_path,auxiliary=True)


def test_missing_compiled_main_receipt_blocks_route(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v3'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v3/outcome.json').read_text());del outcome['audit']['completion_slot']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled completion slot'):
        route.run(main,ARTIFACTS/'synth-v2',tmp_path/'forbidden',ARTIFACTS/'ack-v2')
    assert not (tmp_path/'forbidden').exists()
