"""Exact source-specific destination candidate; Icarus only, no vendor entry."""
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / 'hdl/library/starlink_pss_acquisition/retained_destination_candidate'
BUNDLE = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-prelaunch-v1')
MANIFEST_SHA = 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
SOURCE_SIGNATURE = 'cf37ea269f9c220a3cfeea1761757657bccc5faff62aade4dec1d87a7d0694fb'
PATCH_FILE = Path(__file__).with_name('retained_destination_inverse.json')
PATCHES = json.loads(PATCH_FILE.read_text())
ACQ = Path('hdl/library/starlink_pss_acquisition')
FILES = {
    'owner': ('starlink_pss_retained_destination_owner.v',
              ACQ/'retained_output/starlink_pss_retained_output_owner.v',
              'b6280f6a894ec120f0e57415d5cc6da7b9e193a65f42b1d7f9789cbdbaa5d648'),
    'top': ('starlink_pss_fft_retained_destination_impl.v',
            ACQ/'retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v',
            '3b98a25b8c5d50a18da1692511ae1647c2969fadf5c55d679278b2d5a7bbf0ff'),
    'wrapper': ('starlink_pss_fft_bank_owned_retained_destination_probe.v',
                ACQ/'retained_output_summary_candidate/starlink_pss_fft_bank_owned_retained_output_probe.v',
                '7367d534792385eab3b4264f2e36849b18222e6fe848ef7dbc0887394de8bf94'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_env():
    return {k:v for k,v in os.environ.items() if k not in
            ('PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH')}


def verify_original_bundle():
    if sha(BUNDLE/'manifest.json') != MANIFEST_SHA:
        raise ValueError('destination inherited manifest')
    manifest=json.loads((BUNDLE/'manifest.json').read_text())
    if len(manifest['sources']) != 116 or manifest['source_signature'] != SOURCE_SIGNATURE:
        raise ValueError('destination inherited116')
    if len(manifest['files']) != 119:
        raise ValueError('destination inherited file set')
    for relative,expected in manifest['files'].items():
        path=BUNDLE/relative
        if path.is_symlink() or not path.resolve().is_relative_to(BUNDLE) or \
                path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
            raise ValueError('destination inherited file: '+relative)
    return manifest


def original(name):
    path=BUNDLE/'source_snapshot'/FILES[name][1]
    if sha(path) != FILES[name][2]: raise ValueError('destination baseline pin')
    return path.read_text()


def inverse(name,text):
    for before,after in reversed(PATCHES[name]):
        if text.count(after) != 1: raise ValueError('destination inverse boundary')
        text=text.replace(after,before,1)
    if text != original(name): raise ValueError('destination whole-source inverse')
    return text


def verify_runtime():
    for name,(filename,_,_) in FILES.items(): inverse(name,(RTL/filename).read_text())
    top=(RTL/FILES['top'][0]).read_text()
    if 'retained_owner.' in top: raise ValueError('hierarchical runtime knownness')
    return {filename:sha(RTL/filename) for filename,_,_ in FILES.values()}


def frozen_child(body):
    verify_original_bundle()
    # Same fixed namespace isolation as the reviewed original standalone CLI.
    code='''import json,sys,types
from pathlib import Path
root=Path.cwd()
for name,path in (("tests",root/"tests"),("tests.starlink_oracle",root/"tests/starlink_oracle")):
 package=types.ModuleType(name);package.__path__=[str(path)];package.__package__=name;sys.modules[name]=package
from tests.starlink_oracle import retained_summary_actual as c
c.verify_sources()
'''+body
    result=subprocess.run([sys.executable,'-B','-c',code],cwd=BUNDLE/'source_snapshot',env=clean_env(),
                          text=True,capture_output=True,timeout=30)
    if result.returncode: raise ValueError('destination frozen helper: '+result.stderr)
    return json.loads(result.stdout)


@functools.lru_cache(maxsize=1)
def inherited():
    result=frozen_child('print(json.dumps(dict(bench=c.bench(),sources=list(map(str,c.compiled_sources())),script=c.old.scripted_padding_adapter())))')
    if len(result['sources']) != 26 or result['bench'] != (BUNDLE/'bench.sv').read_text():
        raise ValueError('destination complete inherited bench/source set')
    return result


def composed_bench(mode):
    text=inherited()['bench']
    changes=[('starlink_pss_fft_bank_owned_retained_output_probe #(',
              'starlink_pss_fft_bank_owned_retained_destination_probe #('),
             ('module tb;','module tb;\n  defparam dut.CONTEXTUAL_DESTINATION_SUMMARY='+str(mode)+';'),
             ('endmodule',(RTL/'destination_witness.svh').read_text()+'\nendmodule')]
    for before,after in changes:
        if text.count(before)!=1: raise ValueError('destination bench boundary')
        text=text.replace(before,after,1)
    for before,after in reversed(changes):
        if text.count(after)!=1: raise ValueError('destination bench inverse boundary')
        text=text.replace(after,before,1)
    if text!=inherited()['bench']: raise ValueError('destination whole bench inverse')
    for before,after in changes:text=text.replace(before,after,1)
    return text


def runtime_algebra(top=None):
    """Complete actual parallel cone, name-only transplanted beside old oracle."""
    from . import retained_destination_algebra as algebra
    if top is None:top=(RTL/FILES['top'][0]).read_text()
    text=algebra.bench()
    replacements=[('starlink_pss_retained_output_owner owner(',
                   'starlink_pss_retained_destination_owner owner('),
                  ('  wire retained_fault_now,retained_reusable,retained_reserved;',
                   '  wire known_port;\n  wire retained_fault_now,retained_reusable,retained_reserved;'),
                  ('.fault_reasons(retained_reasons));',
                   '.fault_reasons(retained_reasons),.reserved_state_known(known_port));'),
                  ("  wire reserved_known = owner.reserved === 1'b0 || owner.reserved === 1'b1;",
                   '  wire reserved_known = known_port;')]
    for before,after in replacements:
        if text.count(before)!=1:raise ValueError('destination runtime algebra binding')
        text=text.replace(before,after,1)
    mapping={'summary_destination_ready':'scalar_destination',
             'summary_destination_event':'scalar_destination_event',
             'summary_preflight_events':'scalar_events',
             'destination_original_common':'scalar_original',
             'destination_offered_common':'scalar_offered',
             'contextual_destination_common':'contextual_common',
             'retained_reserved_known':'known_port',
             'external_fault_now':'scalar_external_fault_now',
             'offered_external_fault_now':'scalar_offered_external_fault_now'}
    reverse={v:k for k,v in mapping.items()}
    for name in [x for x in mapping if x!='retained_reserved_known']:
        before=algebra.statement(text,mapping[name])
        runtime=algebra.statement(top,name)
        renamed=re.sub(r'\b[A-Za-z_]\w*\b',lambda m:mapping.get(m[0],m[0]),runtime)
        restored=re.sub(r'\b[A-Za-z_]\w*\b',lambda m:reverse.get(m[0],m[0]),renamed)
        if restored!=runtime:raise ValueError('destination runtime statement name inverse')
        if text.count(before)!=1:raise ValueError('destination runtime statement binding')
        text=text.replace(before,renamed,1)
    # Never transplant a changed detailed oracle or full original aggregate.
    for name in ('preflight_events_now','preparation_fault_now','destination_reserved',
                 'original_common_current_fault','offered_common_current_fault'):
        if algebra.statement(text,name)!=algebra.statement(algebra.bench(),name):
            raise ValueError('destination original oracle changed')
    return text


def run_sv(directory,text,sources,*,vectors=False):
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'bench.sv').write_text(text)
    if vectors:
        for path in (BUNDLE/'source_snapshot'/ACQ/'retained_output/baseline').glob('*.mem'):
            (directory/path.name).write_bytes(path.read_bytes())
    pins={str(p):sha(p) for p in sources}
    (directory/'sources.json').write_text(json.dumps(pins,sort_keys=True,indent=2)+'\n')
    command=['iverilog','-g2012','-s','tb','-o',str(directory/'sim.vvp'),str(directory/'bench.sv'),*map(str,sources)]
    try:compiled=subprocess.run(command,env=clean_env(),capture_output=True,text=True,timeout=30)
    except subprocess.TimeoutExpired as exc:
        (directory/'compile.timeout').write_text(str(exc)+'\n')
        (directory/'compile.partial.log').write_bytes((exc.stdout or b'')+(exc.stderr or b''))
        raise
    (directory/'compile.log').write_text(compiled.stdout+compiled.stderr)
    (directory/'compile.exit').write_text(str(compiled.returncode)+'\n')
    if compiled.returncode:raise AssertionError('destination compile: '+str(directory))
    try:run=subprocess.run(['vvp','sim.vvp'],cwd=directory,env=clean_env(),capture_output=True,text=True,timeout=90)
    except subprocess.TimeoutExpired as exc:
        (directory/'simulation.timeout').write_text(str(exc)+'\n')
        (directory/'simulation.partial.log').write_bytes((exc.stdout or b'')+(exc.stderr or b''))
        raise
    (directory/'simulation.log').write_text(run.stdout+run.stderr)
    (directory/'simulation.exit').write_text(str(run.returncode)+'\n')
    if any(sha(Path(p))!=pin for p,pin in pins.items()):raise ValueError('destination source changed')
    return run


def composed(directory,mode):
    verify_runtime();verify_original_bundle()
    sources=[Path(p) for p in inherited()['sources']]
    replaced=0
    for name,(filename,relative,_) in FILES.items():
        old=BUNDLE/'source_snapshot'/relative
        if sources.count(old)!=1:raise ValueError('destination compiled source replacement')
        sources[sources.index(old)]=RTL/filename;replaced+=1
    # Old owner is an independent same-input shadow, not the candidate's source.
    sources.append(BUNDLE/'source_snapshot'/FILES['owner'][1])
    if replaced!=3:raise ValueError('destination compile inverse')
    directory.parent.mkdir(parents=True,exist_ok=True)
    setup=directory.parent/(directory.name+'-input')
    setup.mkdir()
    script=setup/'OFFLINE_NOT_FFT.sv';script.write_text(inherited()['script'])
    run=run_sv(directory,composed_bench(mode),sources+[script],vectors=True)
    return run


def verify_composed_result(directory):
    return frozen_child('print(json.dumps(c.verify_result(Path('+repr(str(directory/'simulation.log'))+
                        '),Path('+repr(str(directory/'actual_words.csv'))+'),kind="OFFLINE_SCRIPT_NOT_FFT"),sort_keys=True))')
