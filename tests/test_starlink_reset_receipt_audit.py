"""Reject incomplete or overclaimed current reset/CDC evidence."""
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import record_reset_receipt_evidence as evidence

ARTIFACTS=Path('/dev/shm/starlink-reset-cdc.nCo3Wwmo')


def test_current_evidence():
    result=evidence.assess(ARTIFACTS)
    assert result==json.loads((ARTIFACTS/'assessment.json').read_text())
    assert result['first_stage_fanout_clean'] and result['purge_source_registered']
    assert not result['deployment_eligible'] and not result['timing']['internal_timing_pass']


@pytest.mark.parametrize('mutation',['extra_fanout','critical_cdc','missing_terminal',
                                    'applied_constraints','false_timing_pass','wrong_slack'])
def test_altered_evidence_rejected(monkeypatch,mutation):
    original=Path.read_text
    def read(path,*args,**kwargs):
        text=original(path,*args,**kwargs)
        if path==ARTIFACTS/'structure-v1/controls.txt' and mutation=='extra_fanout':
            text=text.replace('{output_bank/request_sync_reg[1]/D}',
                              '{output_bank/request_sync_reg[1]/D} {epoch_barrier/slow_purge_count_reg[0]/D}')
        if path==ARTIFACTS/'structure-v1/cdc.rpt' and mutation=='critical_cdc':
            text+='\nCDC-1 Critical 1 unsafe\n'
        if path==ARTIFACTS/'structure-v1.log' and mutation=='missing_terminal':
            text=text.replace('\nRESET_RECEIPT_STRUCTURE_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE\n','\n')
        if path==ARTIFACTS/'structure-v1/receipt.txt' and mutation=='applied_constraints':
            text=text.replace('constraints_changed=false','constraints_changed=true')
        if path==ARTIFACTS/'route-v1/audit.json' and mutation in {'false_timing_pass','wrong_slack'}:
            value=json.loads(text)
            if mutation=='false_timing_pass':value['internal_timing_pass']=True
            else:value['wns_ns']=0.1
            text=json.dumps(value)
        return text
    monkeypatch.setattr(Path,'read_text',read)
    with pytest.raises(ValueError):evidence.assess(ARTIFACTS)
