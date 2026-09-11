"""MOCK_ONLY physical-preparation policy. No actual admission or vendor runs.

Positive flow fixtures contain synthetic marked text, never an unqualified
actual run. All candidate-CLI and vendor boundaries are explicit test doubles.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'tools/retained_destination_synthesis'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


p = module('summary_prepare_policy', ROOT/'tools/prepare_starlink_retained_destination_synthesis.py')
d = module('summary_derive_policy', ASSETS/'derive.py')
g = p.gate


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) if not isinstance(value, str) else value)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_env():
    return {k:v for k,v in os.environ.items() if k not in
            {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}


def test_explicit_unbound_source_still_rejects(tmp_path, monkeypatch):
    monkeypatch.setattr(g,'ACCEPTED_ACTUAL',None)
    monkeypatch.setattr(g,'EXPECTED',d.UNBOUND)
    monkeypatch.setattr(p,'EXPECTED',d.UNBOUND)
    def forbidden(*args, **kwargs):
        pytest.fail('unbound recipe reached copier/subprocess')
    monkeypatch.setattr(p.subprocess, 'check_output', forbidden)
    monkeypatch.setattr(p.shutil, 'copytree', forbidden)
    out=tmp_path/'must_remain_absent'
    with pytest.raises(ValueError, match='UNBOUND'):
        p.prepare(tmp_path/'no_qualified_actual', tmp_path/'no_completed_owner', out)
    assert not out.exists()


@pytest.mark.parametrize('kind', ['relative','parent','symlink','dangling','parent_symlink'])
def test_lexical_path_rejection_before_admission(tmp_path, kind):
    path=tmp_path/'alias'
    if kind=='relative':path=Path('relative')
    elif kind=='parent':path=tmp_path/'..'/'out'
    elif kind=='symlink':path.symlink_to(tmp_path, target_is_directory=True)
    elif kind=='dangling':path.symlink_to(tmp_path/'missing', target_is_directory=True)
    else:
        path.symlink_to(tmp_path/'missing', target_is_directory=True)
        path=path/'child'
    with pytest.raises(ValueError, match='path'):
        p.prepare(tmp_path/'qualified', tmp_path/'actual', path)


def test_output_existing_and_forbidden_child(tmp_path):
    with pytest.raises(ValueError,match='overwrite'):
        p.prepare(tmp_path/'qualified',tmp_path/'actual',tmp_path)
    for parent in (ROOT,tmp_path/'qualified',tmp_path/'actual'):
        with pytest.raises(ValueError,match='outside'):
            p.prepare(tmp_path/'qualified',tmp_path/'actual',parent/'new_uncreated')
        assert not (parent/'new_uncreated').exists()


def test_whole_reference_and_four_runtime_pins():
    pins=json.loads((ASSETS/'source_pins.json').read_text())
    assert len(pins['runtime'])==16
    assert sum('/baseline/' in n for n in pins['runtime'])==9
    four={n:sha for n,sha in pins['runtime'].items() if '/retained_output_summary_candidate/' in n}
    assert len(four)==2
    for name,sha in pins['reference_assets'].items():
        assert digest(ASSETS/name)==sha
    for name,sha in four.items():
        assert digest(ASSETS/'reference/runtime'/Path(name).name)==sha
    for kind in d.CASES:
        target,original,expected,_=d.recipe(kind)
        assert target.read_text()==expected
        assert d.inverse(kind,target.read_text())==original
    assert digest(ASSETS/'route_retained_output.tcl')=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a'
    assert digest(ASSETS/'reference/create_shared_realtime_xfft_ip.tcl')=='0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d'


@pytest.mark.parametrize('kind', ['helper','tcl'])
@pytest.mark.parametrize('change', ['comment','anchor','body','extra'])
def test_unreviewed_changes_fail_whole_inverse(kind,change):
    _,_,text,edits=d.recipe(kind)
    if change=='comment':text+='\n# UNREVIEWED\n'
    elif change=='anchor':text=text.replace(edits[-1][0][1],edits[-1][0][1]+'X')
    elif change=='body':text=text.replace('2022.2','2023.2') if kind=='tcl' else text.replace('timeout=30','timeout=300')
    else:text+=edits[0][0][1]
    with pytest.raises(ValueError,match='inverse'):
        d.inverse(kind,text)


@pytest.fixture
def mock_actual(tmp_path,monkeypatch):
    """Synthetic, explicitly labeled receipt exercise; no real actual artifacts."""
    root=tmp_path/'MOCK_ONLY_NOT_ACTUAL';qualified=root/'qualified';owner=root/'owner';actual=owner/'run'
    pins=json.loads((ASSETS/'source_pins.json').read_text())
    runtime={}
    for name in pins['runtime']:
        content='// MOCK_ONLY_NOT_RTL '+name+'\n'
        path=put(qualified/'source_snapshot'/name,content)
        put(actual/'inputs/source_snapshot'/name,content)
        runtime[name]=digest(path)
    put(root/'gate/source_pins.json',{'runtime':runtime})
    manifest={'actual_execution':False,'source_before_after_equal':True,
              'compiled':['source_snapshot/'+n for n in runtime], 'mock_only':True}
    put(qualified/'manifest.json',manifest);put(actual/'inputs/manifest.json',manifest)
    cli=put(qualified/'source_snapshot/tools/prepare_starlink_retained_destination_actual.py','# MOCK_ONLY_CLI_NOT_EXECUTED\n')
    expected=digest(qualified/'manifest.json')
    wrapper=put(actual/'project/retained_output_actual.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd',
                '-- MOCK_ONLY_NOT_GENERATED_IP\n')
    monkeypatch.setattr(g,'WRAPPER',digest(wrapper))
    execution={'vendor_exit':0,'timed_out':False,'interruption':None,'mock_only':True}
    outcome=dict(execution,original_check_exit=0,copied_check_exit=0,independent_result_exit=0,
        functional_accepted=True,generated_wrapper_matches_known=True,generated_wrapper_sha256=g.WRAPPER,
        physical_qualified=False,deployment_eligible=False)
    put(owner/'execution.json',execution);put(owner/'outcome.json',outcome)
    put(owner/'owner.py','# MOCK_ONLY_ORIGINAL_OWNER_NOT_EXECUTED\n')
    put(owner/'command.json',{'command':['MOCK_ONLY_NOT_VIVADO','-tclargs',str(qualified),p.PYTHON,expected,str(actual)]})
    put(owner/'stdout.log','MOCK_ONLY_NOT_ACTUAL\n'+g.MARKER+'\n')
    put(actual/'run_outcome.txt','MOCK_ONLY_NOT_ACTUAL\nrun_status=0\n')
    put(actual/'results.json',{'kind':'MOCK_ONLY_NOT_NUMERICAL_EVIDENCE','complete_result':{'service':[3645],'words':[]}})
    binding={'manifest_sha256':expected,'qualified':str(qualified),'actual':str(actual),'owner':str(owner),
        'owner_files':{n:digest(owner/n) for n in ('owner.py','execution.json','outcome.json','command.json','stdout.log','run/run_outcome.txt')},
        'results_sha256':digest(actual/'results.json'),'cli_sha256':digest(cli)}
    monkeypatch.setattr(g,'HERE',root/'gate');monkeypatch.setattr(g,'EXPECTED',expected)
    monkeypatch.setattr(g,'ACCEPTED_ACTUAL',binding);monkeypatch.setattr(p,'EXPECTED',expected)
    return root,qualified,owner,actual,binding


def test_mock_only_owner_and_result_contract(mock_actual):
    _,qualified,_,actual,binding=mock_actual
    assert g.admit(qualified,actual,binding['manifest_sha256'])['runtime_files']==16
    g.check_result(actual,(actual/'results.json').read_text())
    with pytest.raises(ValueError,match='numerical/service'):
        g.check_result(actual,'{}')


@pytest.mark.parametrize('change', ['vendor_exit','timeout','interrupted','owner_missing','original_source_fail',
    'copied_source_fail','collector_fail','functional_fail','ip_changed','wrong_command','runner_fail',
    'duplicate_terminal','missing_terminal','results_changed','runtime_changed','copied_runtime_changed',
    'manifest_changed','cli_changed','wrong_path','actual_ip_changed'])
def test_mock_only_actual_rejection(mock_actual,change):
    _,qualified,owner,actual,binding=mock_actual
    if change in {'vendor_exit','timeout','interrupted'}:
        path=owner/'execution.json';value=json.loads(path.read_text())
        key,new={'vendor_exit':('vendor_exit',1),'timeout':('timed_out',True),'interrupted':('interruption','KeyboardInterrupt')}[change]
        value[key]=new;put(path,value);binding['owner_files']['execution.json']=digest(path)
    elif change in {'original_source_fail','copied_source_fail','collector_fail','functional_fail','ip_changed'}:
        path=owner/'outcome.json';value=json.loads(path.read_text())
        key,new={'original_source_fail':('original_check_exit',1),'copied_source_fail':('copied_check_exit',1),
            'collector_fail':('independent_result_exit',1),'functional_fail':('functional_accepted',False),
            'ip_changed':('generated_wrapper_sha256','0'*64)}[change]
        value[key]=new;put(path,value);binding['owner_files']['outcome.json']=digest(path)
    elif change=='owner_missing':(owner/'owner.py').unlink()
    elif change=='wrong_command':
        path=owner/'command.json';value=json.loads(path.read_text());value['command'][-2]='0'*64
        put(path,value);binding['owner_files']['command.json']=digest(path)
    elif change=='runner_fail':
        path=put(actual/'run_outcome.txt','MOCK_ONLY\nrun_status=1\n');binding['owner_files']['run/run_outcome.txt']=digest(path)
    elif change in {'duplicate_terminal','missing_terminal'}:
        path=put(owner/'stdout.log','MOCK_ONLY\n'+(g.MARKER+'\n')*(2 if change=='duplicate_terminal' else 0))
        binding['owner_files']['stdout.log']=digest(path)
    elif change=='results_changed':put(actual/'results.json',{'mock_only':'wrong service result'})
    elif change in {'runtime_changed','copied_runtime_changed'}:
        source=qualified if change=='runtime_changed' else actual/'inputs'
        path=next(source.rglob('starlink_pss_core_job_cutover.v'));put(path,'// MOCK_ONLY mutation\n')
    elif change=='manifest_changed':put(actual/'inputs/manifest.json',{})
    elif change=='cli_changed':put(qualified/'source_snapshot/tools/prepare_starlink_retained_destination_actual.py','changed')
    elif change=='actual_ip_changed':put(next((actual/'project').rglob('*.vhd')),'-- MOCK_ONLY_CHANGED_IP\n')
    else:actual=owner/'not_the_original_run'
    with pytest.raises((ValueError,FileNotFoundError)):
        g.admit(qualified,actual,binding['manifest_sha256'])


def test_mock_only_helper_children_are_sanitized_and_parent_preserved(mock_actual,monkeypatch):
    root,qualified,_,actual,_=mock_actual
    # Only fake marked input files are copied. No real actual helper is invoked.
    calls=[]
    def invoke(command,**kwargs):
        calls.append((command,kwargs))
        assert kwargs['cwd']=='/'
        assert not {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'} & kwargs['env'].keys()
        assert command[0:2]==[p.PYTHON,'-B']
        return (actual/'results.json').read_text() if command[3]=='results' else '{"kind":"MOCK_ONLY_VERIFY"}'
    for name in ('PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'):
        monkeypatch.setenv(name,'MOCK_ONLY_CONTAMINATED')
    monkeypatch.setattr(p.subprocess,'check_output',invoke)
    out=root/'MOCK_ONLY_COPIED_RECIPE'
    result=p.prepare(qualified,actual,out)
    assert result['vendor_invoked'] is False and len(calls)==4
    assert all(os.environ[name]=='MOCK_ONLY_CONTAMINATED' for name in
               ('PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'))
    assert json.loads((out/'actual_result.json').read_text())['kind']=='MOCK_ONLY_NOT_NUMERICAL_EVIDENCE'
    assert not (out/'project').exists()


@pytest.fixture
def mock_tcl_bundle(tmp_path):
    """Manually assembled MOCK_ONLY Tcl sandbox, not a real copier admission."""
    root=tmp_path/'MOCK_ONLY_TCL_BUNDLE';root.mkdir()
    text=(ASSETS/'synthesize_retained_destination.tcl').read_text()
    text=text.replace(d.ACTUAL_MANIFEST,'a'*64)
    put(root/'synthesize_retained_destination.tcl',text)
    for name in ('clocks.xdc','threads.tcl'):
        shutil.copyfile(ASSETS/name,root/name)
    put(root/'qualified/source_snapshot/tools/prepare_starlink_retained_destination_actual.py',
        'import os,sys,json,hashlib\nfrom pathlib import Path\n'
        'assert not any(n in os.environ for n in ("PYTHONHOME","PYTHONPATH","PYTHONOPTIMIZE","LD_LIBRARY_PATH"))\n'
        'assert sys.argv[1]=="verify"\nroot=Path(sys.argv[2])\n'
        'for n,h in json.loads((root/"MOCK_ONLY_inventory.json").read_text()).items():\n'
        ' assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n\n'
        'print("MOCK_ONLY_VERIFY_NOT_ACTUAL")\n')
    names=['source_snapshot/'+n for n in json.loads((ASSETS/'source_pins.json').read_text())['runtime']]
    for name in names:put(root/'qualified'/name,'// MOCK_ONLY_NOT_RTL\n')
    put(root/'qualified/profile.tcl','set compiled_names {'+' '.join(names)+'}\nset vector_names {mock_vectors/upper_edge_pss_kernel_q17.mem}\n')
    put(root/'qualified/mock_vectors/upper_edge_pss_kernel_q17.mem','MOCK_ONLY_NOT_NUMERICAL\n')
    put(root/'qualified/MOCK_ONLY_inventory.json',{
        str(path.relative_to(root/'qualified')):digest(path)
        for path in sorted((root/'qualified').rglob('*')) if path.is_file()})
    put(root/'MOCK_ONLY.txt','No actual admission, generated IP or vendor execution.\n')
    rows=''.join(f'{digest(path)}  {path.relative_to(root)}\n' for path in sorted(root.rglob('*')) if path.is_file())
    put(root/'SHA256SUMS',rows)
    return root,digest(root/'SHA256SUMS')


def tcl_run(tmp_path,text,contaminated=False):
    path=put(tmp_path/'MOCK_ONLY.tcl',text)
    env=os.environ.copy()
    if contaminated:
        for name in ('PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'):env[name]='MOCK_ONLY_INVALID'
    run=subprocess.run(['tclsh',str(path)],env=env,capture_output=True,text=True,timeout=30)
    put(tmp_path/'MOCK_ONLY.log',run.stdout+run.stderr)
    return run


@pytest.mark.parametrize('change',['none','copied_clock','copied_runtime'])
def test_mock_tcl_create_failure_keeps_original_and_after_integrity(mock_tcl_bundle,tmp_path,change):
    bundle,sha=mock_tcl_bundle;out=tmp_path/'MOCK_ONLY_OUTPUT'
    action=''
    if change!='none':
        name='clocks.xdc' if change=='copied_clock' else 'inputs/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_core_job_cutover.v'
        action=f'set f [open [file join $output {name}] a];puts $f {{MOCK_ONLY_MUTATION}};close $f;'
    script=f'''proc version args {{return 2022.2}}
proc set_param {{n v}} {{if {{$n ne "general.maxThreads" || $v!=2}} {{error THREADS}}}}
proc create_project args {{global output;{action}error MOCK_ONLY_VENDOR_BOUNDARY}}
set argc 2
set argv [list {sha} {{{out}}}]
source {{{bundle/'synthesize_retained_destination.tcl'}}}
'''
    run=tcl_run(tmp_path,script,True)
    assert run.returncode!=0 and 'MOCK_ONLY_VENDOR_BOUNDARY' in run.stderr
    receipt=(out/'run_outcome.txt').read_text()
    assert 'run_status=1\n' in receipt and 'ip_status=0\n' in receipt
    assert f'after_status={0 if change=="none" else 1}\n' in receipt
    assert 'RETAINED_DESTINATION_SYNTHESIS_RECORDED' not in run.stdout
    assert not (out/'project').exists() and not (out/'retained_output_synth.dcp').exists()


@pytest.mark.parametrize('change',['none','missing_summary','summary0','summaryX','summaryZ','extra'])
def test_exact_eight_generics_and_actual_readback(tmp_path,change):
    text=(ASSETS/'synthesize_retained_destination.tcl').read_text()
    text=text[text.index('  set generics [list '):text.index('  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY')]
    rewrite={'missing_summary':'','summary0':'INPUT_OFFER_FAULT_SUMMARY=0',
             'summaryX':"INPUT_OFFER_FAULT_SUMMARY=1'bx",'summaryZ':"INPUT_OFFER_FAULT_SUMMARY=1'bz",'extra':'INPUT_OFFER_FAULT_SUMMARY=1 UNREVIEWED=1'}
    mapping='' if change=='none' else f'return [string map [list INPUT_OFFER_FAULT_SUMMARY=1 {{{rewrite[change]}}}] $actual]'
    script='''set kernel /MOCK_ONLY/kernel.mem
proc get_filesets args {return sources_1}
proc set_property {n value target} {global actual;set actual $value}
proc get_property args {global actual;'''+(mapping or 'return $actual')+'}\n'+text
    run=tcl_run(tmp_path,script)
    assert (run.returncode==0)==(change=='none')


def test_runtime_selection_and_settings_are_exact(tmp_path):
    text=(ASSETS/'synthesize_retained_destination.tcl').read_text()
    pins=json.loads((ASSETS/'source_pins.json').read_text())
    names=['source_snapshot/'+n for n in pins['runtime']]
    fragment=text[text.index('  set rtl_names {}'):text.index('  set kernels ')]
    script='set compiled_names {'+' '.join(names+['bench.sv','source_snapshot/retained_output/tb/bad.v'])+'}\n'+fragment+'puts [join $rtl_names "\\n"]\n'
    run=tcl_run(tmp_path,script)
    assert run.returncode==0 and set(run.stdout.splitlines())==set(names)
    assert all(word not in text for word in ('set_false_path','set_clock_groups','set_multicycle_path','route_design','launch_simulation'))
    for term in ('xc7z010clg400-1','AreaOptimized_high','-mode out_of_context',
                 'CONTROL_SET_OPT_THRESHOLD 4','general.maxThreads 2','source_100 10.0 island_175 5.714',
                 'report_cdc -details','report_exceptions','report_clock_interaction','report_unconstrained'):
        assert term in text


def test_optimizer_cannot_disable_admission(tmp_path):
    run=subprocess.run([p.PYTHON,'-O','-B',str(ROOT/'tools/prepare_starlink_retained_destination_synthesis.py'),
        str(tmp_path/'qualified'),str(tmp_path/'actual'),str(tmp_path/'out')],
        env=clean_env(),capture_output=True,text=True,timeout=30)
    assert run.returncode!=0 and 'unoptimized' in run.stderr and not (tmp_path/'out').exists()


@pytest.mark.parametrize('change',['digest','runtime','clock','argc','relative','overwrite','inside_prepared','unbound'])
def test_mock_tcl_admission_never_crosses_vendor_boundary(mock_tcl_bundle,tmp_path,change):
    bundle,sha=mock_tcl_bundle;out=tmp_path/'MOCK_ONLY_REJECTED'
    if change=='digest':sha='0'*64
    elif change=='runtime':put(next((bundle/'qualified').rglob('starlink_pss_core_job_cutover.v')),'MOCK_ONLY_CHANGED')
    elif change=='clock':put(bundle/'clocks.xdc','MOCK_ONLY_CHANGED_CLOCK')
    elif change=='relative':out=Path('relative')
    elif change=='overwrite':out.mkdir()
    elif change=='inside_prepared':out=bundle/'forbidden_child'
    elif change=='unbound':
        put(bundle/'synthesize_retained_destination.tcl',
            (ASSETS/'synthesize_retained_destination.tcl').read_text().replace(d.ACTUAL_MANIFEST,d.UNBOUND))
        rows=''.join(f'{digest(path)}  {path.relative_to(bundle)}\n' for path in sorted(bundle.rglob('*'))
                     if path.is_file() and path.name!='SHA256SUMS')
        put(bundle/'SHA256SUMS',rows);sha=digest(bundle/'SHA256SUMS')
    script=f'''proc version args {{return 2022.2}}
proc set_param args {{}}
proc create_project args {{error UNEXPECTED_VENDOR_BOUNDARY}}
set argc {3 if change=='argc' else 2}
set argv [list {sha} {{{out}}}]
source {{{bundle/'synthesize_retained_destination.tcl'}}}
'''
    run=tcl_run(tmp_path,script)
    assert run.returncode!=0 and 'UNEXPECTED_VENDOR_BOUNDARY' not in run.stderr+run.stdout
    assert not (out/'project').exists()


@pytest.mark.parametrize('change',['missing_owner_pin','wrong_manifest_binding','wrong_cli_result'])
def test_mock_binding_is_complete(mock_actual,change):
    _,qualified,_,actual,binding=mock_actual
    if change=='missing_owner_pin':binding['owner_files'].pop('owner.py')
    elif change=='wrong_manifest_binding':binding['manifest_sha256']='0'*64
    else:binding['results_sha256']='0'*64
    with pytest.raises(ValueError):g.admit(qualified,actual,p.EXPECTED)
