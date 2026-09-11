"""Real actual binding is read-only; negatives modify copied policy only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result
b=module('bank_binding',ROOT/'tools/bind_starlink_retained_bank_identity_synthesis.py')

@pytest.fixture(scope='module')
def bound(tmp_path_factory):
    out=tmp_path_factory.mktemp('bound')/'source'
    b.export(out)
    return out

def test_exact_two_changes_and_actual_readonly(bound):
    pins=b.source_pins()
    for n,h in pins.items():
        if n in b.EDITS:
            assert b.restored(n,(bound/n).read_text())==(ROOT/n).read_text()
        else:assert b.sha(bound/n)==h
    g=module('real_bank_gate',bound/b.PREFIX/'admission.py')
    before={n:b.sha(b.OWNER/n) for n in b.BINDING['owner_files']}
    assert g.admit(Path(b.BINDING['qualified']),Path(b.BINDING['actual']),b.MANIFEST)['runtime_files']==16
    g.check_result(Path(b.BINDING['actual']),(b.OWNER/'run/results.json').read_text())
    assert before=={n:b.sha(b.OWNER/n) for n in before}

@pytest.mark.parametrize('kind',['old_manifest','old_run','owner_hash','result_hash','cli_hash','missing_owner'])
def test_wrong_actual_binding_rejected(bound,monkeypatch,kind):
    g=module('bad_bank_gate',bound/b.PREFIX/'admission.py')
    binding=copy.deepcopy(g.ACCEPTED_ACTUAL)
    if kind=='old_manifest':binding['manifest_sha256']='b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
    elif kind=='old_run':binding['actual']=str(b.RECOVERY/'retained-summary-actual-parent.XYAbt6Np/run')
    elif kind=='owner_hash':binding['owner_files']['owner.py']='0'*64
    elif kind=='missing_owner':binding['owner_files'].pop('owner.py')
    else:binding['results_sha256' if kind=='result_hash' else 'cli_sha256']='0'*64
    monkeypatch.setattr(g,'ACCEPTED_ACTUAL',binding)
    with pytest.raises(ValueError):g.admit(Path(b.BINDING['qualified']),Path(b.BINDING['actual']),b.MANIFEST)

@pytest.mark.parametrize('name',b.EDITS)
@pytest.mark.parametrize('kind',['missing','duplicate','unrelated'])
def test_bound_inverse_mutants(bound,name,kind):
    text=(bound/name).read_text();token=b.EDITS[name][1]
    changed=text+'\n' if kind=='unrelated' else text.replace(token,'' if kind=='missing' else token*2)
    with pytest.raises(ValueError,match='inverse'):b.restored(name,changed)

@pytest.mark.parametrize('kind',['overwrite','relative','source','qualified','owner','symlink'])
def test_export_scope_rejected(bound,tmp_path,kind):
    path={'overwrite':bound,'relative':Path('relative'),'source':ROOT/'never-bound',
          'qualified':Path(b.BINDING['qualified'])/'never-bound','owner':b.OWNER/'never-bound'}.get(kind)
    if kind=='symlink':
        path=tmp_path/'alias';path.symlink_to(tmp_path,target_is_directory=True);path=path/'never-bound'
    with pytest.raises(ValueError):b.export(path)
