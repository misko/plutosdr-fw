"""Bounded source/runner admission; Tcl stubs never execute vendor tools."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tests.starlink_oracle import retained_control_actual as c
from tests.starlink_oracle import retained_control_actual_bundle as b

BASE_PYTHON=Path('/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11')


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    path=tmp_path_factory.mktemp('candidate_bundle')/'bundle'
    result=b.prepare(path)
    return path,result['manifest_sha256']


def test_exact_80_plus_17_source_closure(prepared):
    path,sha=prepared;result=b.verify(path,sha,live=True)
    assert result['sources']==97 and result['files']==100
    manifest=json.loads((path/'manifest.json').read_text())
    assert len(manifest['vectors'])==8 and len(manifest['compiled'])==26
    assert b.QUALIFIED80=='9c7996e6d61a559ddfe99543b80c62063b3a5fed2cd43f7aa7a43b1f664af4f7'
    assert set(b.old.source_names())<set(b.source_names())
    assert sum('retained_output_closed_candidate/' in x for x in manifest['compiled'])==4
    assert not any('scripted' in x for x in manifest['compiled'])
    assert c.inverse_bench((path/'bench.sv').read_text())==c.old.actual_bench()


def test_explicit_one_shot_and_after(prepared,tmp_path):
    path,sha=prepared
    with pytest.raises(ValueError,match='overwrite'):b.prepare(path)
    with pytest.raises(ValueError,match='flag'):b.stage(path,tmp_path/'run',sha)
    b.stage(path,tmp_path/'run',sha,authorize=True)
    with pytest.raises(ValueError,match='overwrite'):b.stage(path,tmp_path/'run',sha,authorize=True)
    assert b.after(path,tmp_path/'run',sha)['copied']['manifest_sha256']==sha
    with pytest.raises(ValueError,match='overwrite'):b.after(path,tmp_path/'run',sha)


@pytest.mark.parametrize('where',['source','bundle','link','parent'])
def test_output_containment_before_creation(prepared,tmp_path,where):
    path,sha=prepared
    if where=='source':bad=c.ROOT/'never-created-candidate-output'
    elif where=='bundle':bad=path/'never-created-output'
    elif where=='link':
        (tmp_path/'alias').symlink_to(tmp_path,target_is_directory=True);bad=tmp_path/'alias/run'
    else:bad=tmp_path/'uncreated/../run'
    with pytest.raises(ValueError):b.stage(path,bad,sha,authorize=True)
    assert not bad.exists()
    if where=='source':
        with pytest.raises(ValueError):b.prepare(bad)


@pytest.mark.parametrize('mutation',['sha','missing','extra','link','source_join','float_length','old_kind','flag','profile','runtime'])
def test_mutated_bundle_never_admitted(prepared,tmp_path,mutation):
    path,sha=prepared;copy=tmp_path/'copy';shutil.copytree(path,copy)
    m=json.loads((copy/'manifest.json').read_text())
    if mutation=='sha':sha='0'*64
    elif mutation=='missing':(copy/'environment.json').unlink()
    elif mutation=='extra':(copy/'extra').write_text('undeclared')
    elif mutation=='link':(copy/'alias').symlink_to(copy/'bench.sv')
    else:
        if mutation=='source_join':
            key=next(iter(m['sources']));m['sources'][key]={'sha256':'0'*64,'bytes':1}
            m['source_signature']=hashlib.sha256(b.encoded(m['sources'])).hexdigest()
        elif mutation=='float_length':
            key=next(iter(m['files']));m['files'][key]['bytes']=float(m['files'][key]['bytes'])
        elif mutation=='old_kind':m['kind']=b.old.KIND
        else:
            name={'flag':'bench.sv','profile':'profile.tcl','runtime':'source_snapshot/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_core_job_cutover.v'}[mutation]
            p=copy/name
            if mutation=='flag':p.write_text(p.read_text().replace('CLOSED_INPUT_CUTOVER=1','CLOSED_INPUT_CUTOVER=0',1))
            else:p.write_bytes(p.read_bytes()+b'\nMUTATED\n')
            m['files'][name]=b.old.receipt(p)
            if mutation=='runtime':
                key=name.removeprefix('source_snapshot/');m['sources'][key]=m['files'][name]
                m['source_signature']=hashlib.sha256(b.encoded(m['sources'])).hexdigest()
        (copy/'manifest.json').write_bytes(b.encoded(m));sha=c.old.sha(copy/'manifest.json')
    with pytest.raises(ValueError):b.verify(copy,sha)


def test_frozen_base_python_cli_from_root(prepared):
    path,sha=prepared;env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'):env.pop(key,None)
    run=subprocess.run([str(BASE_PYTHON),'-B',str(path/'source_snapshot/tools/prepare_starlink_retained_control_actual.py'),
        'verify',str(path),'--expected',sha,'--live'],cwd='/',env=env,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr
    assert json.loads(run.stdout)['manifest_sha256']==sha


def inherited_runner_case(name):
    """Exact old test function body in a separate namespace; no original mutation."""
    source=(c.ROOT/'tests/test_starlink_retained_output_actual_bundle.py').read_text()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    body=ast.get_source_segment(source,node)
    namespace=dict(globals(),a=c.old,b=b)
    exec(compile(body,'<literal old runner test body>','exec'),namespace)
    return namespace[name]


@pytest.mark.parametrize('stage',['create','launch','launch_mutation'])
def test_exact_old_runner_failure_stubs_on_new_bundle(prepared,tmp_path,stage):
    inherited_runner_case('test_runner_stubs_preserve_failure_and_after_integrity')(prepared,tmp_path,stage)


@pytest.mark.parametrize('fault',['wrong_runner','wrong_version','symlink_python','wrong_python'])
def test_exact_old_runner_admission_controls(prepared,tmp_path,fault):
    inherited_runner_case('test_runner_early_admission_rejects')(prepared,tmp_path,fault)


def test_literal_runner_and_cli_inverse():
    b.verify_authority()
    assert 'general.maxThreads 2' in (c.ROOT/b.RUNNER).read_text()
    assert '-u PYTHONOPTIMIZE' in (c.ROOT/b.RUNNER).read_text()
