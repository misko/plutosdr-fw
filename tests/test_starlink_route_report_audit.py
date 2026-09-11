"""Report-auditor controls using copies, not new FPGA implementation runs."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('route_report_audit',ROOT/'tools/audit_staged_fft_route.py')
auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)
sys.path.pop(0)

@pytest.fixture(params=[2,4],ids=['live-lookup-v2','held-bundle-v4'])
def reports(tmp_path,request):
    original=ROOT.parent/f'staged-handover-route-v{request.param}'
    shutil.copytree(original/'route',tmp_path/'route')
    shutil.copyfile(original/'route.tcl',tmp_path/'route.tcl')
    receipt=json.loads((original/'outcome.json').read_text())
    # The originals retain their complete execution provenance. This temporary
    # parser fixture binds only its copied recipe, so later development of the
    # live runner does not turn a historical report control into a source claim.
    receipt['before']={str(tmp_path/'route.tcl'):auditor.sha(tmp_path/'route.tcl')}
    (tmp_path/'outcome.json').write_text(json.dumps(receipt))
    return tmp_path,request.param

def test_global_worst_clock_pair(reports):
    root,version=reports
    result=auditor.audit(root)
    assert result['source_and_checkpoint_verified']
    assert not result['deployment_eligible']
    if version==2:
        assert result['wns_ns']==-5.429
        assert result['worst_clock_pair']==['island_175','source_100']
        assert result['same_domain_175_setup_ns']==-4.026

@pytest.mark.parametrize('change',['checkpoint','clock_pair','route_errors','recipe','execution'])
def test_corrupt_evidence_rejected(reports,change):
    root,_=reports
    if change=='checkpoint':
        (root/'route/retained_output_routed.dcp').write_bytes(b'bad checkpoint')
    elif change=='recipe':
        with (root/'route.tcl').open('a') as stream:stream.write('\n# changed\n')
    elif change=='execution':
        path=root/'outcome.json';receipt=json.loads(path.read_text())
        receipt['error']='failed execution';path.write_text(json.dumps(receipt))
    else:
        name='paths.txt' if change=='clock_pair' else 'route_status.rpt'
        path=root/'route'/name;text=path.read_text()
        if change=='clock_pair':
            lines=text.splitlines()
            key='island_175.island_175.max.slack='
            assert sum(line.startswith(key) for line in lines)==1
            text='\n'.join(key+'999.000' if line.startswith(key) else line for line in lines)+'\n'
        else:
            import re
            text,count=re.subn(r'(# of nets with routing errors\.*\s*:\s*)0',r'\g<1>1',text)
            assert count==1
        path.write_text(text)
    with pytest.raises(ValueError):auditor.audit(root)
