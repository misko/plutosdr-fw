"""Complete original campaign and one-shot source admission; no vendor call."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from tests.starlink_oracle import retained_destination_actual as b
c=b.c
BASE_PYTHON=Path('/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11')

@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    out=tmp_path_factory.mktemp('prepared')/'bundle'
    receipt=b.prepare(out)
    return out,receipt['manifest_sha256']

def test_complete_source_profile_inverse(prepared):
    out,sha=prepared;m=json.loads((out/'manifest.json').read_text())
    assert b.verify(out,sha,live=True)['sources']==132
    assert len(m['files'])==134 and len(m['compiled'])==27 and len(m['vectors'])==8
    b.inverse_bench((out/'bench.sv').read_text());b.verify_runner()
    assert sum('retained_destination_candidate/' in p for p in m['compiled'])==3
    assert all('bank_identity' not in p for p in m['compiled'])

@pytest.fixture(scope='module')
def scripted(tmp_path_factory,prepared):
    bundle,_=prepared
    directory=tmp_path_factory.mktemp('script')/'run'
    sources=[bundle/n for n in json.loads((bundle/'manifest.json').read_text())['compiled']]
    script=directory.parent/'OFFLINE_NOT_FFT.sv';script.write_text(c.inherited()['script'])
    result=c.run_sv(directory,b.bench(),sources+[script],vectors=True)
    assert result.returncode==0,result.stdout+result.stderr
    return directory

def test_complete_original_script_and_parser(scripted):
    result=b.verify_result(scripted/'simulation.log',scripted/'actual_words.csv','OFFLINE_SCRIPT_NOT_FFT')
    assert result.pop('destination')['mode']==1
    reference=c.BUNDLE.parent/'retained-summary-script-parent.jVE5ixKt/summary-result.json'
    assert result==json.loads(reference.read_text())
    assert c.sha(scripted/'actual_words.csv')=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'

@pytest.mark.parametrize('kind',['missing_flags','duplicate_flags','wrong_flags','missing_proof','duplicate_proof',
    'wrong_mode','wrong_releases','short_pre','short_post','unknown_marker','late_error','missing_old_frame','numerical'])
def test_results_reject_incomplete_or_wrong_evidence(tmp_path,scripted,kind):
    text=(scripted/'simulation.log').read_text();csv=(scripted/'actual_words.csv').read_text()
    flag='DESTINATION_ACTUAL_FLAGS wrapper=1 top=1'
    proof=next(x for x in text.splitlines() if x.startswith('DESTINATION_COMPOSED_PASS '))
    if kind=='missing_flags':text=text.replace(flag,'')
    elif kind=='duplicate_flags':text+='\n'+flag+'\n'
    elif kind=='wrong_flags':text=text.replace(flag,flag.replace('top=1','top=0'))
    elif kind=='missing_proof':text=text.replace(proof,'')
    elif kind=='duplicate_proof':text+='\n'+proof+'\n'
    elif kind=='wrong_mode':text=text.replace(proof,proof.replace('mode=1','mode=0'))
    elif kind=='wrong_releases':text=text.replace(proof,proof.replace('releases=17','releases=18'))
    elif kind in ('short_pre','short_post'):
        field=kind.removeprefix('short_')
        text=text.replace(proof,re.sub(r'\b'+field+r'=\d+',field+'=2000',proof))
    elif kind=='unknown_marker':text+='\nDESTINATION_UNKNOWN value=0\n'
    elif kind=='late_error':text+='\nFATAL_ERROR: injected\n'
    elif kind=='missing_old_frame':text='\n'.join(x for x in text.splitlines() if not x.startswith('RACT_FRAME '))+'\n'
    else:csv=csv.splitlines()[0]+'\n'
    log=tmp_path/'parser-only.log';log.write_text(text)
    numerical=tmp_path/'parser-only.csv';numerical.write_text(csv)
    with pytest.raises(ValueError):b.verify_result(log,numerical,'OFFLINE_SCRIPT_NOT_FFT')

@pytest.mark.parametrize('token',['CONTEXTUAL_DESTINATION_SUMMARY=1','destination composed exact common',
    'destination composed full17 owner state','destination actual option forwarding','actual causal frame'])
def test_full_bench_changes_rejected(token):
    text=b.bench();assert token in text
    with pytest.raises(ValueError):b.inverse_bench(text.replace(token,token+'_changed',1))

@pytest.mark.parametrize('kind',['digest','missing','extra','symlink','source_join','flag','profile','runtime','old_kind','bool_alias'])
def test_bundle_changes_rejected(tmp_path,prepared,kind):
    source,expected=prepared;out=tmp_path/'copy';shutil.copytree(source,out)
    m=json.loads((out/'manifest.json').read_text())
    if kind=='digest':expected='0'*64
    elif kind=='missing':(out/'profile.tcl').unlink()
    elif kind=='extra':(out/'unlisted').write_text('unexpected')
    elif kind=='symlink':(out/'alias').symlink_to(out/'bench.sv')
    else:
        if kind=='source_join':
            name=next(iter(m['sources']));m['sources'][name]['sha256']='0'*64
        elif kind=='old_kind':m['kind']='retained-summary-actual-preparation-v1'
        elif kind=='bool_alias':m['actual_execution']=0
        else:
            name={'flag':'bench.sv','profile':'profile.tcl',
                  'runtime':'source_snapshot/'+b.ACQ+'retained_destination_candidate/'+c.FILES['owner'][0]}[kind]
            p=out/name;text=p.read_text()
            p.write_text(text.replace('CONTEXTUAL_DESTINATION_SUMMARY=1','CONTEXTUAL_DESTINATION_SUMMARY=0',1) if kind=='flag' else text+'\nMUTATED\n')
            m['files'][name]=b.receipt(p)
            if kind=='runtime':m['sources'][name.removeprefix('source_snapshot/')]=m['files'][name]
        (out/'manifest.json').write_bytes(b.encoded(m));expected=c.sha(out/'manifest.json')
    with pytest.raises(ValueError):b.verify(out,expected)

def test_explicit_stage_and_no_overwrite(tmp_path,prepared):
    bundle,expected=prepared
    with pytest.raises(ValueError):b.prepare(bundle)
    with pytest.raises(ValueError):b.stage(bundle,tmp_path/'run',expected)
    b.stage(bundle,tmp_path/'run',expected,authorize=True)
    b.after(bundle,tmp_path/'run',expected)
    with pytest.raises(ValueError):b.after(bundle,tmp_path/'run',expected)
    with pytest.raises(ValueError):b.stage(bundle,tmp_path/'run',expected,authorize=True)

@pytest.mark.parametrize('where',['root','bundle','relative','parent','symlink'])
def test_output_paths_rejected(tmp_path,prepared,where):
    bundle,expected=prepared
    out={'root':b.ROOT/'never-created','bundle':bundle/'never-created','relative':Path('relative'),'parent':tmp_path/'../never-created'}.get(where)
    if where=='symlink':
        alias=tmp_path/'alias';alias.symlink_to(tmp_path,target_is_directory=True);out=alias/'never-created'
    with pytest.raises(ValueError):b.stage(bundle,out,expected,authorize=True)

def test_exact_frozen_cli_from_root(prepared):
    bundle,expected=prepared
    result=subprocess.run([str(BASE_PYTHON),'-B',str(bundle/'source_snapshot'/b.CLI),
        'verify',str(bundle),'--expected',expected,'--live'],cwd='/',env=c.clean_env(),capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['sources']==132

@pytest.mark.parametrize('kind',['cli','runner'])
def test_exact_transport_source_mutations_rejected(tmp_path,monkeypatch,kind):
    for name in (b.CLI,b.RUNNER):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((b.ROOT/name).read_bytes()+(b'\n' if name==(b.CLI if kind=='cli' else b.RUNNER) else b''))
    monkeypatch.setattr(b,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='inverse'):b.verify_runner()

def inherited_case(name):
    source=(c.BUNDLE/'source_snapshot/tests/test_starlink_retained_output_actual_bundle.py').read_text()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    body=ast.get_source_segment(source,node)
    if name=='test_runner_stubs_preserve_failure_and_after_integrity':
        # One additional unchanged old-owner observer module:27+bench, not26+bench.
        token='len(expected_sv) == len(set(expected_sv)) == 27'
        assert body.count(token)==1;body=body.replace(token,token[:-2]+'28')
    namespace=dict(globals(),a=SimpleNamespace(REF=c.BUNDLE/'source_snapshot'/b.ACQ/'retained_output_actual/reference'))
    exec(compile(body,'<pinned old runner test>','exec'),namespace)
    return namespace[name]

@pytest.mark.parametrize('stage',['create','launch','launch_mutation'])
def test_literal_runner_failures(prepared,tmp_path,stage):
    inherited_case('test_runner_stubs_preserve_failure_and_after_integrity')(prepared,tmp_path,stage)

@pytest.mark.parametrize('fault',['wrong_runner','wrong_version','symlink_python','wrong_python'])
def test_literal_runner_admission(prepared,tmp_path,fault):
    inherited_case('test_runner_early_admission_rejects')(prepared,tmp_path,fault)
