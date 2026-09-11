"""Integrated fence needs matching sim/synth enablement and actual proof."""
import json
from pathlib import Path
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
import route_starlink_staged_fft as route
ARTIFACTS=Path('/dev/shm/starlink-replay-fence.I2dOca4T')
PIN='74a8ab46a668e51ee3d9b7e3f8a8f4e7a83180b7c9c3168b3ea4b71ab60800a9'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_matching_actual_pair_and_configuration():
    prepared=ARTIFACTS/'prepared-v1';experiment.verify(prepared,PIN)
    experiment.verify_replay_fence_configuration(prepared)
    main=experiment.audit_replay_fence(ARTIFACTS/'sim-v1')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v1',PIN,prepared)
    assert main['numerical_rows']==64512 and main['replay_quiet']['runtime_unchanged'] is False
    assert main['replay_fence']==aux['replay_fence']

@pytest.mark.parametrize('mutation',['missing','duplicate','enabled','profile','independent_shadow','current_publication_exact','wrong_classification'])
def test_bad_integrated_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v1'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_REPLAY_FENCE_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation=='wrong_classification':text=text.replace('current_exact=1 runtime_unchanged=0','current_exact=1 runtime_unchanged=1',1)
    else:text=text.replace(line,line.replace(mutation+'=1',mutation+'=0'),1)
    log=tmp_path/SIM/'simulate.log';log.parent.mkdir(parents=True);log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_replay_fence(tmp_path,auxiliary=True)

def test_missing_compiled_main_fence_blocks_route(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v1'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text());del outcome['audit']['replay_fence']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled replay fence'):
        route.run(main,ARTIFACTS/'synth-v1',tmp_path/'forbidden',ARTIFACTS/'ack-v1')
    assert not (tmp_path/'forbidden').exists()

@pytest.mark.parametrize('mutation',['bench_disabled','synth_disabled','witness_missing'])
def test_mismatched_compilation_profiles_rejected(tmp_path,mutation):
    for name in ['tb_fft_staged_output.sv','staged_fft_experiment.tcl']:
        text=(ARTIFACTS/'prepared-v1'/name).read_text()
        if mutation=='bench_disabled':text=text.replace('.REPLAY_QUIET_PUBLICATION(1)','.REPLAY_QUIET_PUBLICATION(0)',1)
        elif mutation=='synth_disabled':text=text.replace(' REPLAY_QUIET_PUBLICATION=1',' REPLAY_QUIET_PUBLICATION=0',1)
        else:text=text.replace('// BEGIN INTEGRATED REPLAY FENCE WITNESS','// missing witness',1)
        (tmp_path/name).write_text(text)
    with pytest.raises(ValueError,match='matching enabled'):
        experiment.verify_replay_fence_configuration(tmp_path)
