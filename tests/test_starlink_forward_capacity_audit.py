"""Require complete source-bound shadow evidence, not a production claim."""
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
ARTIFACTS=Path('/dev/shm/starlink-forward-capacity.tHq0mgHO')
PIN='a00d28c144210551b42a63b64f204f9ad0707b4553345abbaa1d193f4323a08e'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_source_bound_actual_pair():
    experiment.verify(ARTIFACTS/'prepared-v2',PIN)
    for mode in ['sim','ack']:
        root=ARTIFACTS/(mode+'-v2');result=json.loads((root/'outcome.json').read_text())
        assert result['returncode']==0 and result['sources_unchanged'] and 'error' not in result
        assert result['prepared_sha']==PIN and result['command'][-3]==str(ARTIFACTS/'prepared-v2')
        audited=experiment.audit_forward_capacity(root,auxiliary=mode=='ack')
        assert json.dumps(audited,sort_keys=True)==json.dumps(result['audit'],sort_keys=True)
        assert audited['forward_capacity_shadow']['runtime_unchanged']
        assert not audited['forward_capacity_shadow']['production_interface_proven']

@pytest.mark.parametrize('mutation',['missing','duplicate','checks','healthy','faults','unexplained','runtime_unchanged'])
def test_incomplete_or_changed_contract_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v2'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_FORWARD_CAPACITY_SHADOW_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    else:
        old=next(x for x in line.split() if x.startswith(mutation+'='))
        text=text.replace(line,line.replace(old,mutation+('=1' if mutation=='unexplained' else '=0')),1)
    log=tmp_path/SIM/'simulate.log';log.parent.mkdir(parents=True);log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_forward_capacity(tmp_path,auxiliary=True)
