"""Reject incomplete shadow contract evidence; no physical/release assertion."""
import json
from pathlib import Path
import re
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import staged_fft_experiment as experiment
ARTIFACTS=Path('/dev/shm/starlink-replay-quiet.C5YGuYRF')
PIN='4608ae9ac75663c6e5eee752ee2489d7ef79c38701172d0572218413860ec850'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_successful_frozen_actual_pair():
    experiment.verify(ARTIFACTS/'prepared-v2',PIN)
    for mode in ['sim','ack']:
        root=ARTIFACTS/(mode+'-v2');result=json.loads((root/'outcome.json').read_text())
        assert result['returncode']==0 and result['sources_unchanged'] and 'error' not in result
        assert result['prepared_sha']==PIN and result['command'][-3]==str(ARTIFACTS/'prepared-v2')
        audited=experiment.audit_replay_quiet(root,auxiliary=mode=='ack')
        assert json.dumps(audited,sort_keys=True)==json.dumps(result['audit'],sort_keys=True)

@pytest.mark.parametrize('mutation',['missing','duplicate','short_checks','short_offers','short_accepts','short_sweep','wrong_exact','bad_paused','missing_case','short_recovery'])
def test_incomplete_contract_evidence_rejected(tmp_path,mutation):
    text=(ARTIFACTS/'ack-v2'/SIM/'simulate.log').read_text()
    line=next(x for x in text.splitlines(True) if x.startswith('STAGED_REPLAY_QUIET_PASS '))
    if mutation=='missing':text=text.replace(line,'',1)
    elif mutation=='duplicate':text+=line
    elif mutation.startswith('short_') and mutation!='short_recovery':
        field=mutation.removeprefix('short_');text=text.replace(line,re.sub(field+r'=\d+',field+'=1',line),1)
    elif mutation=='wrong_exact':text=text.replace(line,line.replace('current_exact=1','current_exact=0'),1)
    elif mutation=='bad_paused':text=text.replace(line,line.replace('paused=0','paused=1'),1)
    else:
        case=next(x for x in text.splitlines(True) if x.startswith('STAGED_REPLAY_QUIET_CASE_PASS boundary=0 '))
        text=text.replace(case,'' if mutation=='missing_case' else case.replace('fresh_reads=512','fresh_reads=511'),1)
    log=tmp_path/SIM/'simulate.log';log.parent.mkdir(parents=True);log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_replay_quiet(tmp_path,auxiliary=True)
