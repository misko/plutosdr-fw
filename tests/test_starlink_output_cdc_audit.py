"""Incomplete CDC evidence must not be mistaken for a qualified crossing."""
import json
from pathlib import Path
import re
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_output_metadata_cdc as audit

ARTIFACTS=Path('/dev/shm/starlink-output-cdc.JIdEms')


def fixture(tmp_path):
    for relative in ['inspection-v1/outcome.json','fanout-v1/receipt.txt','fanout-v1/control_fanout.txt','contract-v1.xml']:
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ARTIFACTS/relative,target)
    shutil.copytree(ARTIFACTS/'inspection-v1/inspection',tmp_path/'inspection-v1/inspection')
    for log in (ARTIFACTS/'contract-v1').glob('test_actual_bundle*/simulate.log'):
        if log.parent.is_symlink():continue
        target=tmp_path/log.relative_to(ARTIFACTS);target.parent.mkdir(parents=True)
        shutil.copyfile(log,target)


def test_current_assessment_keeps_structural_gate_closed():
    result=audit.assess(ARTIFACTS)
    assert result==json.loads((ARTIFACTS/'cdc_assessment.json').read_text())
    assert result['digital_contract_pass'] and result['metadata_bits']==37
    assert result['max_data_delay_ns']==1.158
    assert len(result['first_stage_extra_endpoints'])==4
    assert result['cdc1_critical_count']==4 and result['cdc10_critical_count']==1
    assert not result['control_structure_qualified']
    assert not result['constraint_change_authorized'] and not result['deployment_eligible']


@pytest.mark.parametrize('mutation',['missing_bit','duplicate_bit','wrong_clock','wrong_endpoint','wrong_delay',
                                   'missing_stage','missing_case','short_capture','short_rewrite','skipped_test','failed_inspection'])
def test_incomplete_proofs_rejected(tmp_path,mutation):
    fixture(tmp_path)
    if mutation in {'missing_bit','duplicate_bit','wrong_clock','wrong_endpoint','wrong_delay'}:
        path=tmp_path/'inspection-v1/inspection/paths.tsv';rows=path.read_text().splitlines(True)
        if mutation=='missing_bit':rows.pop()
        elif mutation=='duplicate_bit':rows[-1]=rows[1]
        elif mutation=='wrong_clock':rows[1]=rows[1].replace('island_175','source_100')
        elif mutation=='wrong_endpoint':rows[1]=rows[1].replace('metadata_out_hold_reg[0]','metadata_out_hold_reg[1]')
        else:
            fields=rows[1].rstrip().split('\t');fields[5]='0.001';rows[1]='\t'.join(fields)+'\n'
        path.write_text(''.join(rows))
    elif mutation=='missing_stage':
        path=tmp_path/'fanout-v1/control_fanout.txt'
        path.write_text(path.read_text().replace('{output_bank/request_sync_reg[1]/D}',''))
    elif mutation in {'missing_case','short_capture','short_rewrite'}:
        path=next((tmp_path/'contract-v1').glob('test_actual_bundle*/simulate.log'))
        if mutation=='missing_case':path.unlink()
        else:
            field='min_publish_capture_ps' if mutation=='short_capture' else 'min_ack_rewrite_ps'
            path.write_text(re.sub(field+r'=\d+',field+'=1',path.read_text()))
    elif mutation=='skipped_test':
        path=tmp_path/'contract-v1.xml';path.write_text(path.read_text().replace('skipped="0"','skipped="1"',1))
    else:
        path=tmp_path/'inspection-v1/outcome.json';result=json.loads(path.read_text());result['returncode']=1
        path.write_text(json.dumps(result))
    with pytest.raises(ValueError):audit.assess(tmp_path)
