"""Source-bound additive actual adapter; original full verifier stays authority."""
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import retained_destination_candidate as c

ROOT = Path(__file__).resolve().parents[2]
KIND = 'retained-destination-actual-preparation-v1'
ACQ = 'hdl/library/starlink_pss_acquisition/'
RUNNER = ACQ+'retained_destination_actual/simulate_retained_destination_actual.tcl'
CLI = 'tools/prepare_starlink_retained_destination_actual.py'
EXTRAS = (
    'tests/starlink_oracle/retained_destination_candidate.py',
    'tests/starlink_oracle/retained_destination_inverse.json',
    'tests/starlink_oracle/retained_destination_algebra.py',
    'tests/starlink_oracle/tb_retained_destination_algebra.sv',
    'tests/test_retained_destination_candidate.py',
    'tests/test_retained_destination_algebra.py',
    'tests/starlink_oracle/retained_destination_actual.py',
    'tests/test_retained_destination_actual.py',
    'docs/starlink-retained-destination-actual-recipe-20260911.md',
    ACQ+'retained_destination_candidate/destination_witness.svh',
    ACQ+'retained_destination_candidate/tb_destination_owner.sv',
    *(ACQ+'retained_destination_candidate/'+v[0] for v in c.FILES.values()),
    RUNNER, CLI,
)
READBACK = '''
initial begin
  #0.001;
  if(dut.CONTEXTUAL_DESTINATION_SUMMARY!==1 || dut.retained.island.CONTEXTUAL_DESTINATION_SUMMARY!==1)
    $fatal(1,"destination actual option forwarding");
  $display("DESTINATION_ACTUAL_FLAGS wrapper=1 top=1");
end
'''

def require(ok, message):
    if not ok:
        raise ValueError(message)

def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()

def safe(path):
    require(path.is_absolute() and '..' not in path.parts and
            not any(p.is_symlink() for p in (path,*path.parents)), 'absolute non-symlink path')
    return path

def receipt(path):
    safe(path)
    return {'sha256': c.sha(path), 'bytes': path.stat().st_size}

def sources():
    manifest=c.verify_original_bundle();c.verify_runtime()
    result={n:c.BUNDLE/'source_snapshot'/n for n in manifest['sources']}
    require(not set(result)&set(EXTRAS) and len(EXTRAS)==len(set(EXTRAS)), 'additive overlay collision')
    result.update({n:ROOT/n for n in EXTRAS})
    return result

def verify_runner():
    text=(ROOT/RUNNER).read_text()
    for before,after in (
        ('retained_summary_actual simulate_retained_summary_actual.tcl','retained_destination_actual simulate_retained_destination_actual.tcl'),
        ('prepare_starlink_retained_summary_actual.py','prepare_starlink_retained_destination_actual.py'),
        ('RETAINED_SUMMARY_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM','RETAINED_DESTINATION_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM')):
        require(text.count(after)==1,'literal actual runner boundary')
        text=text.replace(after,before,1)
    require(text==(c.BUNDLE/'source_snapshot'/ACQ/'retained_summary_actual/simulate_retained_summary_actual.tcl').read_text(), 'whole original runner inverse')
    text=(ROOT/CLI).read_text()
    before='from tests.starlink_oracle import retained_summary_actual_bundle as b'
    after='from tests.starlink_oracle import retained_destination_actual as b'
    require(text.count(after)==1 and text.replace(after,before,1)==
            (c.BUNDLE/'source_snapshot/tools/prepare_starlink_retained_summary_actual.py').read_text(),
            'whole original CLI inverse')

def bench():
    text=c.composed_bench(1)
    require(text.count('endmodule')==1, 'actual bench boundary')
    return text.replace('endmodule',READBACK+'\nendmodule',1)

def inverse_bench(text):
    token=READBACK+'\nendmodule'
    require(text.count(token)==1,'actual readback inverse boundary')
    require(text.replace(token,'endmodule',1)==c.composed_bench(1),'whole composed bench inverse')

def profile():
    names=[str(Path(p).relative_to(c.BUNDLE/'source_snapshot')) for p in c.inherited()['sources']]
    for filename,original,_ in c.FILES.values():
        require(names.count(str(original))==1,'actual three-source replacement')
        names[names.index(str(original))]=ACQ+'retained_destination_candidate/'+filename
    names.append(str(c.FILES['owner'][1]))
    require(len(names)==27 and len(set(names))==27,'exact27 source/reference files')
    original=json.loads((c.BUNDLE/'manifest.json').read_text())
    vectors=original['vectors']
    compiled=['source_snapshot/'+n for n in names]
    text='set compiled_names {'+' '.join(compiled)+' bench.sv}\nset vector_names {'+' '.join(vectors)+'}\n'
    return compiled,vectors,text

def new_output(path,*protected):
    safe(path);require(not path.exists(),'no output overwrite')
    require(not any(path.is_relative_to(p) for p in (ROOT,c.BUNDLE,*protected)), 'outside source/input roots')
    return path

def inventory(root):
    result={}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(),'bundle symlink')
        if p.is_file() and p!=root/'manifest.json':result[str(p.relative_to(root))]=receipt(p)
    return result

def prepare(output):
    verify_runner();paths=sources();before={n:receipt(p) for n,p in paths.items()}
    new_output(output);output.mkdir(parents=True)
    for n,p in paths.items():
        target=output/'source_snapshot'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    (output/'bench.sv').write_text(bench())
    compiled,vectors,text=profile();(output/'profile.tcl').write_text(text)
    require(before=={n:receipt(p) for n,p in sources().items()},'source changed during prepare')
    m={'kind':KIND,'source_root':str(ROOT),'sources':before,'original_manifest':c.MANIFEST_SHA,
       'compiled':compiled,'vectors':vectors,'files':inventory(output),'actual_execution':False,
       'source_before_after_equal':True}
    (output/'manifest.json').write_bytes(encoded(m))
    return verify(output,c.sha(output/'manifest.json'),live=True)

def verify(bundle,expected,*,live=False):
    safe(bundle);verify_runner()
    raw=(bundle/'manifest.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected,'external manifest digest')
    m=json.loads(raw)
    require(set(m)=={'kind','source_root','sources','original_manifest','compiled','vectors','files','actual_execution','source_before_after_equal'},'manifest fields')
    require(encoded(m)==raw and m['kind']==KIND and m['original_manifest']==c.MANIFEST_SHA and
            m['actual_execution'] is False and m['source_before_after_equal'] is True,'manifest identity/types')
    paths=sources();expected_sources={n:receipt(p) for n,p in paths.items()}
    require(encoded(m['sources'])==encoded(expected_sources),'complete source authority')
    expected_files={'source_snapshot/'+n for n in paths}|{'bench.sv','profile.tcl'}
    require(set(m['files'])==expected_files and encoded(inventory(bundle))==encoded(m['files']),'complete file inventory')
    for n,value in expected_sources.items():
        require(encoded(m['files']['source_snapshot/'+n])==encoded(value),'source snapshot join')
    compiled,vectors,text=profile()
    require(m['compiled']==compiled and m['vectors']==vectors and (bundle/'profile.tcl').read_text()==text,'exact compiled profile')
    inverse_bench((bundle/'bench.sv').read_text())
    if live:
        source_root=safe(Path(m['source_root']))
        require(all(receipt(source_root/n)==expected_sources[n] for n in EXTRAS),'live additive source changed')
    return {'manifest_sha256':expected,'sources':len(paths),'files':len(expected_files),
            'live_checked':live,'actual_execution':False}

def stage(bundle,output,expected,*,authorize=False):
    require(authorize,'explicit actual staging flag')
    before=verify(bundle,expected,live=True);new_output(output,bundle)
    output.mkdir(parents=True);shutil.copytree(bundle,output/'inputs')
    copied=verify(output/'inputs',expected,live=True)
    (output/'before.json').write_bytes(encoded({'original':before,'copied':copied}))
    return before

def after(bundle,output,expected):
    result={'original':verify(bundle,expected,live=True),'copied':verify(output/'inputs',expected,live=True)}
    path=safe(output)/'after.json';require(not path.exists(),'no after overwrite')
    path.write_bytes(encoded(result));return result

def verify_result(log,numerical,kind):
    require(kind in ('OFFLINE_SCRIPT_NOT_FFT','ACTUAL_VENDOR_FFT'),'explicit execution kind')
    result=c.frozen_child('print(json.dumps(c.verify_result(Path('+repr(str(log))+'),Path('+repr(str(numerical))+'),kind='+repr(kind)+'),sort_keys=True))')
    text=log.read_text()
    require(not re.search(r'FATAL|ERROR|FAIL',text),'destination failure marker')
    require(re.findall(r'^DESTINATION_ACTUAL_FLAGS.*$',text,re.M)==['DESTINATION_ACTUAL_FLAGS wrapper=1 top=1'],'destination actual flags')
    rows=re.findall(r'^DESTINATION_COMPOSED_PASS mode=(\d+) pre=(\d+) post=(\d+) releases=(\d+) admits=(\d+) publications=(\d+)$',text,re.M)
    require(len(rows)==1,'unique destination proof')
    mode,pre,post,releases,admits,pubs=map(int,rows[0])
    require(mode==1 and pre>1000 and post>1000 and (releases,admits,pubs)==(17,19,19),'complete destination proof counts')
    require(pre==post==result['contexts'][-1]['cycle'], 'destination every-edge final-cycle join')
    markers=re.findall(r'^DESTINATION_\S+',text,re.M)
    require(sorted(markers)==['DESTINATION_ACTUAL_FLAGS','DESTINATION_COMPOSED_PASS'],'destination marker inventory')
    return dict(result,destination={'mode':mode,'pre':pre,'post':post,'releases':releases,'admits':admits,'publications':pubs})

def results(output,expected):
    verify(output/'inputs',expected,live=True)
    sim=output/'project/retained_output_actual.sim/sim_1/behav/xsim'
    return verify_result(sim/'simulate.log',sim/'actual_words.csv','ACTUAL_VENDOR_FFT')
