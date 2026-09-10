"""Source-specific extension of qualified97; original authority stays frozen."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

from . import retained_output_actual_bundle as old
from . import retained_control_actual_bundle as qualified
from . import retained_summary_actual as c

QUALIFIED97='b52ba499ffbec7b4596afaba5b180d8145381ea56a4af60ab4cce30c79631908'
KIND='retained-summary-actual-preparation-v1'
EXTRAS=(
 'tests/starlink_oracle/retained_offer_summary_candidate.py',
 'tests/starlink_oracle/retained_offer_summary_inverse.json',
 'tests/test_starlink_retained_offer_summary.py',
 'docs/starlink-retained-offer-summary-recipe-20260910.md',
 'hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/tb_offer_input_premise.sv',
 'hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/tb_offer_fault_ack.sv',
 'tests/starlink_oracle/retained_summary_actual.py',
 'tests/starlink_oracle/retained_summary_actual_recipe.json',
 'tests/starlink_oracle/retained_summary_actual_bundle.py',
 'tests/test_starlink_retained_summary_actual.py',
 'tests/test_starlink_retained_summary_actual_bundle.py',
 'tools/prepare_starlink_retained_summary_actual.py',
 'docs/starlink-retained-summary-actual-recipe-20260910.md',
 'hdl/library/starlink_pss_acquisition/retained_summary_actual/witness.svh',
 'hdl/library/starlink_pss_acquisition/retained_summary_actual/simulate_retained_summary_actual.tcl',
)
RUNNER=EXTRAS[-1]
encoded=old.encoded


def source_names():
    names=tuple(sorted((*qualified.source_names(),*EXTRAS,
        *(str((c.candidate.RTL/n).relative_to(c.ROOT)) for n in c.PINS))))
    if len(names)!=len(set(names)):raise ValueError('candidate source-list duplicate')
    return names


def sources(root):
    return {n:old.receipt(old.safe(root/n)) for n in source_names()}


def verify_authority():
    qualified.verify_authority()
    c.verify_sources()
    if hashlib.sha256(encoded(qualified.sources(c.ROOT))).hexdigest()!=QUALIFIED97:
        raise ValueError('original qualified97 source changed')
    runner=(c.ROOT/RUNNER).read_text()
    for before,after in [
      ('retained_control_actual simulate_retained_control_actual.tcl','retained_summary_actual simulate_retained_summary_actual.tcl'),
      ('prepare_starlink_retained_control_actual.py','prepare_starlink_retained_summary_actual.py'),
      ('RETAINED_CONTROL_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM','RETAINED_SUMMARY_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM')]:
        if runner.count(after)!=1:raise ValueError('candidate runner inverse boundary')
        runner=runner.replace(after,before,1)
    if runner!=(c.ROOT/qualified.RUNNER).read_text():raise ValueError('candidate runner whole-source inverse')
    cli=(c.ROOT/'tools/prepare_starlink_retained_summary_actual.py').read_text()
    before='from tests.starlink_oracle import retained_control_actual_bundle as b'
    after='from tests.starlink_oracle import retained_summary_actual_bundle as b'
    if cli.count(after)!=1 or cli.replace(after,before,1)!=(c.ROOT/'tools/prepare_starlink_retained_control_actual.py').read_text():
        raise ValueError('candidate CLI whole-source inverse')


def profile():
    compiled=['source_snapshot/'+p.relative_to(c.ROOT).as_posix() for p in c.compiled_sources()]
    vectors=['source_snapshot/'+p.relative_to(c.ROOT).as_posix() for p in sorted(c.old.original.BASELINE.glob('*.mem'))]
    text='set compiled_names {'+' '.join(compiled)+' bench.sv}\nset vector_names {'+' '.join(vectors)+'}\n'
    return compiled,vectors,text


def new_output(path,*forbidden):
    path=old.safe(path)
    if path.exists():raise ValueError('refusing output overwrite/restart')
    for root in (c.ROOT,*forbidden):
        if path==root or root in path.parents:raise ValueError('output within immutable source/input')
    return path


def prepare(output):
    verify_authority();output=new_output(output);before=sources(c.ROOT)
    output.mkdir(parents=True)
    for name in before:
        p=output/'source_snapshot'/name;p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(c.ROOT/name,p)
    (output/'bench.sv').write_text(c.bench())
    compiled,vectors,text=profile();(output/'profile.tcl').write_text(text)
    (output/'environment.json').write_bytes(encoded({'python_version':sys.version,'python_executable':sys.executable,
        'qualification':'preparation only; no vendor invocation'}))
    if sources(c.ROOT)!=before:raise ValueError('source changed during preparation')
    m={'kind':KIND,'source_root':str(c.ROOT),'sources':before,'source_signature':hashlib.sha256(encoded(before)).hexdigest(),
       'qualified97_signature':QUALIFIED97,'files':old._files(output),'compiled':compiled,'vectors':vectors,
       'source_before_after_equal':True,'actual_execution':False}
    (output/'manifest.json').write_bytes(encoded(m))
    return verify(output,c.old.sha(output/'manifest.json'),live=True)


def verify(bundle,expected,*,live=False):
    verify_authority();bundle=old.safe(bundle);p=bundle/'manifest.json'
    if c.old.sha(p)!=expected:raise ValueError('external manifest digest')
    raw=p.read_bytes();m=json.loads(raw)
    fields={'kind','source_root','sources','source_signature','qualified97_signature','files','compiled','vectors','source_before_after_equal','actual_execution'}
    if set(m)!=fields or encoded(m)!=raw or m['kind']!=KIND or m['actual_execution'] is not False or m['source_before_after_equal'] is not True or m['qualified97_signature']!=QUALIFIED97:
        raise ValueError('candidate manifest fields/types/kind')
    expected_files={'source_snapshot/'+n for n in source_names()}|{'bench.sv','profile.tcl','environment.json'}
    if set(m['files'])!=expected_files or encoded(old._files(bundle))!=encoded(m['files']):raise ValueError('complete bundle inventory')
    if sorted(m['sources'])!=list(source_names()) or hashlib.sha256(encoded(m['sources'])).hexdigest()!=m['source_signature']:
        raise ValueError('candidate source signature')
    for name,value in m['sources'].items():
        if encoded(value)!=encoded(m['files']['source_snapshot/'+name]):raise ValueError('source signature not joined to snapshot')
    if encoded(sources(c.ROOT))!=encoded(m['sources']):raise ValueError('executing frozen source mismatch')
    compiled,vectors,text=profile()
    if m['compiled']!=compiled or m['vectors']!=vectors or (bundle/'profile.tcl').read_text()!=text:
        raise ValueError('exact candidate source profile')
    c.inverse_bench((bundle/'bench.sv').read_text())
    if live and encoded(sources(old.safe(Path(m['source_root']))))!=encoded(m['sources']):raise ValueError('live source changed')
    return {'manifest_sha256':expected,'source_signature':m['source_signature'],'sources':len(m['sources']),
        'files':len(m['files']),'live_checked':live,'actual_execution':False}


def stage(bundle,output,expected,*,authorize=False):
    if not authorize:raise ValueError('explicit one-shot actual staging flag required')
    before=verify(bundle,expected,live=True);output=new_output(output,bundle)
    output.mkdir(parents=True);shutil.copytree(bundle,output/'inputs')
    copied=verify(output/'inputs',expected,live=True)
    (output/'before.json').write_bytes(encoded({'original':before,'copied':copied}));return before


def after(bundle,output,expected):
    result={'original':verify(bundle,expected,live=True),'copied':verify(output/'inputs',expected,live=True)}
    path=old.safe(output)/'after.json'
    if path.exists():raise ValueError('refusing after-receipt overwrite')
    path.write_bytes(encoded(result));return result


def results(output,expected):
    verify(output/'inputs',expected,live=True)
    simulation=output/'project/retained_output_actual.sim/sim_1/behav/xsim'
    return c.verify_result(simulation/'simulate.log',simulation/'actual_words.csv',kind='ACTUAL_VENDOR_FFT')
