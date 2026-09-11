"""Source-bound actual FFT evidence is mandatory, including private differences."""
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
ARTIFACTS=Path('/dev/shm/starlink-private-admission.jU5bmytc')
PIN='e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_actual_pair_and_frozen_source_boundaries():
    prepared=ARTIFACTS/'prepared-v1'
    experiment.verify(prepared,PIN)
    main=experiment.audit_private_facts(ARTIFACTS/'sim-v1')
    aux=route.verify_ack_auxiliary(ARTIFACTS/'ack-v1',PIN,prepared)
    assert main['numerical_rows']==64512 and aux['private_facts']['owned']>=10
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text())
    assert outcome['returncode']==0 and outcome['sources_unchanged'] and outcome['prepared_sha']==PIN
    assert json.dumps(main,sort_keys=True)==json.dumps(outcome['audit'],sort_keys=True)

@pytest.mark.parametrize('mutation',['missing','duplicate','short_checks','short_owned','short_differences','bad_permit','bad_owned'])
def test_incomplete_actual_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v1'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_PRIVATE_FACTS_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation.startswith('short_'):
        field={'short_checks':'checks','short_owned':'owned','short_differences':'invalid_differences'}[mutation]
        text=text.replace(line,re.sub(field+r'=\d+',field+'=1',line),1)
    else:
        field='permit_exact' if mutation=='bad_permit' else 'owned_exact'
        text=text.replace(line,line.replace(field+'=1',field+'=0'),1)
    log=tmp_path/SIM/'simulate.log';log.parent.mkdir(parents=True);log.write_text(text)
    with pytest.raises(ValueError,match='private admission facts'):
        experiment.audit_private_facts(tmp_path,auxiliary=True)

def test_missing_compiled_witness_blocks_route_before_output(tmp_path):
    main=tmp_path/'main';(main/SIM).mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(ARTIFACTS/'sim-v1'/SIM/name,main/SIM/name)
    outcome=json.loads((ARTIFACTS/'sim-v1/outcome.json').read_text());del outcome['audit']['private_facts']
    (main/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='compiled private facts'):
        route.run(main,ARTIFACTS/'synth-v1',tmp_path/'forbidden',ARTIFACTS/'ack-v1')
    assert not (tmp_path/'forbidden').exists()
