"""Read-only binding checks. Never calls prepare, stage, or any vendor tool."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'tools/retained_summary_synthesis'
spec=importlib.util.spec_from_file_location('bound_summary_synthesis',ROOT/'tools/prepare_starlink_retained_summary_synthesis.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
g=p.gate
BINDING=g.ACCEPTED_ACTUAL
QUALIFIED=Path(BINDING['qualified'])
OWNER=Path(BINDING['owner'])
ACTUAL=Path(BINDING['actual'])
RECOVERY=OWNER.parent
CLI=QUALIFIED/'source_snapshot/tools/prepare_starlink_retained_summary_actual.py'
CSV=ACTUAL/'project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv'
OLD_RESULT=RECOVERY/'retained-control-actual-parent.HbyLZ8I2/run/results.json'


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def inverse(name,text):
    record=json.loads((ASSETS/'binding_inverse.json').read_text())['cases'][name]
    reference=ROOT/record['reference']
    if digest(reference)!=record['reference_sha256']:
        raise ValueError('unbound reference hash')
    for before,after in reversed(record['edits']):
        if text.count(after)!=1:
            raise ValueError('binding inverse literal count')
        text=text.replace(after,before,1)
    if text!=reference.read_text():
        raise ValueError('whole unbound inverse')
    return text


@pytest.mark.parametrize('name', ['admission.py','derive.py','synthesize_retained_summary.tcl',
                                'test_starlink_retained_summary_synthesis.py'])
def test_exact_unbound_inverse(name):
    record=json.loads((ASSETS/'binding_inverse.json').read_text())['cases'][name]
    assert inverse(name,(ROOT/record['target']).read_text())==(ROOT/record['reference']).read_text()


@pytest.mark.parametrize('name', ['admission.py','derive.py','synthesize_retained_summary.tcl'])
@pytest.mark.parametrize('change', ['binding','extra_body'])
def test_unreviewed_binding_or_body_rejected(name,change):
    text=(ASSETS/name).read_text()
    text=text.replace(p.EXPECTED,'0'*64) if change=='binding' else text+'\n# UNREVIEWED_BODY\n'
    with pytest.raises(ValueError):inverse(name,text)


@pytest.fixture(scope='module')
def original_integrity(tmp_path_factory):
    output=tmp_path_factory.mktemp('READ_ONLY_ORIGINAL_INTEGRITY')
    manifest=json.loads((QUALIFIED/'manifest.json').read_text())
    paths={QUALIFIED/'manifest.json',ACTUAL/'inputs/manifest.json',ACTUAL/'results.json',CSV,OLD_RESULT}
    paths.update(OWNER/name for name in BINDING['owner_files'])
    paths.update(QUALIFIED/name for name in manifest['files'])
    paths.update(ACTUAL/'inputs'/name for name in manifest['files'])
    live=Path(manifest['source_root'])
    paths.update(live/name for name in manifest['sources'])
    paths.add(ACTUAL/'project/retained_output_actual.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd')
    before={str(path):digest(path) for path in sorted(paths)}
    (output/'before.json').write_text(json.dumps(before,indent=2,sort_keys=True))
    yield output
    after={str(path):digest(path) for path in sorted(paths)}
    (output/'after.json').write_text(json.dumps(after,indent=2,sort_keys=True))
    assert before==after


def test_real_original_admission_read_only(original_integrity):
    before={n:digest(OWNER/n) for n in BINDING['owner_files']}
    assert g.admit(QUALIFIED,ACTUAL,p.EXPECTED)=={
        'manifest_sha256':p.EXPECTED,'actual':str(ACTUAL),'runtime_files':16,
        'vendor_invoked':False,'actual_success_reused_not_rewritten':True}
    assert before=={n:digest(OWNER/n) for n in BINDING['owner_files']}
    g.check_result(ACTUAL,(ACTUAL/'results.json').read_text())


@pytest.mark.parametrize('action,target',[('verify','qualified'),('verify','copied'),('results','actual')])
def test_real_frozen_cli_read_only(original_integrity,tmp_path,action,target):
    path={'qualified':QUALIFIED,'copied':ACTUAL/'inputs','actual':ACTUAL}[target]
    command=[p.PYTHON,'-B',str(CLI),action,str(path),'--expected',p.EXPECTED]
    if action=='verify':command.append('--live')
    # Explicit four-variable sanitation; the original vendor environment is not changed.
    import os
    env={k:v for k,v in os.environ.items() if k not in
         {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}
    run=subprocess.run(command,cwd='/',env=env,capture_output=True,text=True,timeout=90)
    (tmp_path/'read-only-cli.json').write_text(json.dumps({'command':command,'exit':run.returncode,
        'stdout':run.stdout,'stderr':run.stderr,'mode':'READ_ONLY_NO_PREPARE_STAGE_OR_VENDOR'},indent=2))
    assert run.returncode==0 and not run.stderr
    result=json.loads(run.stdout)
    if action=='verify':
        assert result['manifest_sha256']==p.EXPECTED and result['sources']==116 and result['files']==119
        assert result['live_checked'] is True and result['actual_execution'] is False
    else:
        assert result==json.loads((ACTUAL/'results.json').read_text())
        g.check_result(ACTUAL,run.stdout)
        assert result['kind']=='ACTUAL_VENDOR_FFT' and result['numerical_words']==77953
        assert result['parser_only_not_execution_proof'] is True


def test_entire_original_result_and_rows_preserved(original_integrity):
    result=json.loads((ACTUAL/'results.json').read_text())
    original=json.loads(OLD_RESULT.read_text())
    assert set(result)==set(original)|{'offer_summary'}
    assert {k:v for k,v in result.items() if k!='offer_summary'}==original
    assert result['offer_summary']['RSUMMARY_FLAGS']==[
        dict(wrapper=1,top=1,cutover=1,owner0=1,owner1=1)]
    with CSV.open() as handle:
        assert next(handle).strip()=='context,stream,job,position,data,start,exponent,fast,slow,time_fs'
        assert sum(1 for _ in handle)==77953


def test_old_actual_cannot_replace_bound_original(original_integrity):
    with pytest.raises(ValueError,match='path binding'):
        g.admit(QUALIFIED,OLD_RESULT.parent,p.EXPECTED)


def test_real_admission_cannot_take_arbitrary_manifest(original_integrity):
    with pytest.raises(ValueError,match='manifest binding'):
        g.admit(QUALIFIED,ACTUAL,'0'*64)
