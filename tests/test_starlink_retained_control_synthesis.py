"""Bounded synthesis admission checks; Tcl stubs never invoke vendor tools."""
import importlib.util
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('retained_control_synthesis_copier', ROOT/'tools/prepare_starlink_retained_control_synthesis.py')
p = importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
QUALIFIED = RECOVERY/'retained-control-actual-prelaunch-v1'
ACTUAL = RECOVERY/'retained-control-actual-parent.HbyLZ8I2/run'


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp('synthesis_prepared')/'bundle'
    result = p.prepare(QUALIFIED, ACTUAL, root)
    assert result['vendor_invoked'] is False
    return root, result['inventory_sha256']


def run_tcl(path, text, *, contaminated=False):
    path.write_text(text)
    env=os.environ.copy()
    if contaminated:
        env.update(PYTHONHOME='/nonexistent/python-home', PYTHONPATH='/nonexistent/python-path',
                   PYTHONOPTIMIZE='2', LD_LIBRARY_PATH='/nonexistent/library')
    run=subprocess.run(['tclsh',str(path)],env=env,capture_output=True,text=True,timeout=30)
    path.with_suffix('.log').write_text(run.stdout+run.stderr)
    return run


def test_preparation_integrity_and_no_overwrite(prepared):
    root, digest = prepared
    assert p.digest(root/'SHA256SUMS') == digest
    result=subprocess.run(['sha256sum','-c','SHA256SUMS','--quiet'],cwd=root,capture_output=True,text=True)
    assert result.returncode == 0
    assert p.digest(root/'qualified/manifest.json') == p.EXPECTED
    with pytest.raises(ValueError,match='overwrite'):
        p.prepare(QUALIFIED,ACTUAL,root)


@pytest.mark.parametrize('kind',['relative','parent','symlink'])
def test_path_admission(prepared,tmp_path,kind):
    path={'relative':Path('relative'), 'parent':tmp_path/'..'/'out', 'symlink':tmp_path/'alias'}[kind]
    if kind=='symlink':path.symlink_to(prepared[0],target_is_directory=True)
    with pytest.raises(ValueError,match='path'):
        p.prepare(QUALIFIED,ACTUAL,path)


@pytest.mark.parametrize('parent',[QUALIFIED,ACTUAL,ROOT])
def test_new_child_output_rejects_before_copy(parent):
    output=parent/'retained_synthesis_forbidden_child'
    assert not output.exists()
    with pytest.raises(ValueError,match='outside qualified, actual and source roots'):
        p.prepare(QUALIFIED,ACTUAL,output)
    assert not output.exists()


@pytest.mark.parametrize('kind',['digest','source','clock','wrong_argc','relative_output','inside_prepared','overwrite'])
def test_runner_admission_rejects_before_create(prepared,tmp_path,kind):
    original,digest=prepared;bundle=tmp_path/'bundle';shutil.copytree(original,bundle)
    output=tmp_path/'run'
    if kind=='digest':digest='0'*64
    elif kind=='source':
        with (bundle/'qualified/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_core_job_cutover.v').open('a') as f:f.write('\n// mutated\n')
    elif kind=='clock':
        with (bundle/'clocks.xdc').open('a') as f:f.write('\nset_false_path -from [all_clocks]\n')
    elif kind=='relative_output':output=Path('relative_output')
    elif kind=='inside_prepared':output=bundle/'run'
    elif kind=='overwrite':output.mkdir()
    script=f'''proc version args {{return 2022.2}}
proc set_param args {{}}
proc create_project args {{error UNEXPECTED_VENDOR_BOUNDARY}}
set argc {3 if kind=='wrong_argc' else 2}
set argv [list {digest} {{{output}}}]
source {{{bundle/'synthesize_retained_control.tcl'}}}
'''
    run=run_tcl(tmp_path/'admission.tcl',script)
    assert run.returncode != 0 and 'UNEXPECTED_VENDOR_BOUNDARY' not in run.stdout+run.stderr
    assert not (output/'project').exists()


@pytest.mark.parametrize('mutation',['none','copied_clock','copied_runtime'])
def test_executed_create_failure_retains_after_integrity(prepared,tmp_path,mutation):
    bundle,digest=prepared;output=tmp_path/'run'
    changed=''
    if mutation!='none':
        name='clocks.xdc' if mutation=='copied_clock' else 'inputs/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_core_job_cutover.v'
        changed=f'set f [open [file join $output {name}] a];puts $f {{\n// MUTATED}};close $f'
    script=f'''# OFFLINE_STUB: stop before creating any project or generated FFT.
proc version args {{return 2022.2}}
proc set_param {{name value}} {{if {{$name ne "general.maxThreads" || $value!=2}} {{error THREADS}}}}
proc create_project args {{global output;{changed};error OFFLINE_EXPECTED_CREATE_FAILURE}}
set argc 2
set argv [list {digest} {{{output}}}]
source {{{bundle/'synthesize_retained_control.tcl'}}}
'''
    run=run_tcl(tmp_path/'failure.tcl',script,contaminated=True)
    assert run.returncode != 0 and 'OFFLINE_EXPECTED_CREATE_FAILURE' in run.stderr
    receipt=(output/'run_outcome.txt').read_text()
    assert 'run_status=1\n' in receipt and 'ip_status=0\n' in receipt
    assert f'after_status={0 if mutation=="none" else 1}\n' in receipt
    assert (output/'generated_ip_after.txt').read_text()=='not_generated\n'
    assert not (output/'retained_output_synth.dcp').exists()
    assert 'RETAINED_CONTROL_SYNTHESIS_RECORDED' not in run.stdout


@pytest.mark.parametrize('mutation',['none','missing_enable','wrong_round','extra_generic'])
def test_exact_generic_fragment(prepared,tmp_path,mutation):
    text=(prepared[0]/'synthesize_retained_control.tcl').read_text()
    begin='  set generics [list ';end='  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY'
    fragment=text[text.index(begin):text.index(end)]
    tail='ENABLE_RETAINED_OUTPUT=1 REGISTERED_SCHEDULING=1 BOUNDARY_ROUND_SAT=1 REGISTER_OPERANDS=1 LOCAL_FIRST_ADMISSION=1 PRIVATE_DESCRIPTOR_OFFER=1 CLOSED_INPUT_CUTOVER=1'
    if mutation=='missing_enable':fragment=fragment.replace('ENABLE_RETAINED_OUTPUT=1 ','')
    elif mutation=='wrong_round':fragment=fragment.replace('BOUNDARY_ROUND_SAT=1','BOUNDARY_ROUND_SAT=0')
    elif mutation=='extra_generic':fragment=fragment.replace('CLOSED_INPUT_CUTOVER=1]','CLOSED_INPUT_CUTOVER=1 UNREVIEWED=1]')
    script='''set kernel /frozen/kernel.mem
proc get_filesets args {return sources_1}
proc set_property {name value target} {global actual;set actual $value}
proc get_property args {global actual;return $actual}
'''+fragment+f'if {{$actual ne [list KERNEL_ROM_FILE=/frozen/kernel.mem {tail}]}} {{error WRONG_GENERIC_CONTRACT}}\n'
    run=run_tcl(tmp_path/'generics.tcl',script)
    assert (run.returncode==0)==(mutation=='none')


@pytest.mark.parametrize('mutation',['none','missing_clock','wrong_period'])
def test_clock_property_fragment(prepared,tmp_path,mutation):
    text=(prepared[0]/'synthesize_retained_control.tcl').read_text()
    begin='  foreach {name period} {source_100';end='  write_checkpoint '
    fragment=text[text.index(begin):text.index(end)]
    script=f'''proc get_clocks args {{
set n [lindex $args end]
if {{"{mutation}" eq "missing_clock" && $n eq "island_175"}} {{return {{}}}}
return $n
}}
proc get_property {{property clock}} {{
if {{$clock eq "source_100"}} {{return 10.0}}
return {6.0 if mutation=='wrong_period' else 5.714}
}}
'''+fragment
    run=run_tcl(tmp_path/'clocks.tcl',script)
    assert (run.returncode==0)==(mutation=='none')


def test_exact_runtime_language_and_observation_plan(prepared,tmp_path):
    text=(prepared[0]/'synthesize_retained_control.tcl').read_text()
    assert 'set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1] $compiled_file]' in text
    assert text.count('report_exceptions -file')==text.count('report_clock_interaction -file')==1
    assert 'foreach from {source_100 island_175}' in text and 'foreach to {source_100 island_175}' in text
    assert 'foreach kind {max min}' in text and '-max_paths 20' in text
    assert 'constraint_inputs.txt' in text and 'SCOPED_TO_REF SCOPED_TO_CELLS USED_IN' in text
    assert 'dcp_receipt.txt' in text and 'generated DCP changed after synthesis' in text
    assert all(word not in text for word in ('set_false_path','set_clock_groups','set_multicycle_path','route_design','launch_simulation'))
    # Execute the source-list selection against the unchanged qualified profile.
    start='  set rtl_names {}';end='  set kernels '
    fragment=text[text.index(start):text.index(end)]
    script=f'source {{{prepared[0]/"qualified/profile.tcl"}}}\n'+fragment+'puts [join $rtl_names "\\n"]\n'
    run=run_tcl(tmp_path/'runtime.tcl',script)
    assert run.returncode==0
    names=run.stdout.splitlines();assert len(names)==16
    assert sum('/baseline/' in n for n in names)==9
    assert sum('/retained_output_closed_candidate/' in n for n in names)==4
    assert all('/reference/' not in n and '/tb/' not in n and n.endswith('.v') for n in names)


@pytest.mark.parametrize('flag',['PRIVATE_DESCRIPTOR_OFFER','CLOSED_INPUT_CUTOVER'])
@pytest.mark.parametrize('value',['0',"1'bx"])
def test_both_candidate_generic_readbacks_reject(prepared,tmp_path,flag,value):
    text=(prepared[0]/'synthesize_retained_control.tcl').read_text()
    begin='  set generics [list ';end='  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY'
    fragment=text[text.index(begin):text.index(end)]
    assert fragment.count(flag+'=1')==1
    # Readback disagrees with the requested option, not a fitted hardware value.
    script='''set kernel /frozen/kernel.mem
proc get_filesets args {return sources_1}
proc set_property {name value target} {global actual;set actual $value}
proc get_property args {global actual;return [string map {'''+flag+'=1 '+flag+'='+value+'''} $actual]}
'''+fragment
    run=run_tcl(tmp_path/'flag_readback.tcl',script)
    assert run.returncode!=0 and 'exact retained/R1/B1/O1/L1/private-offer/closed-input generics' in run.stderr


@pytest.mark.parametrize('actual_kind',['absent','old_v5'])
def test_no_preparation_without_candidate_actual_result(tmp_path,actual_kind):
    actual=tmp_path/'absent_actual' if actual_kind=='absent' else RECOVERY/'retained-actual-frame-parent.2nhHxm1Q/run'
    out=tmp_path/'must_remain_absent'
    with pytest.raises(subprocess.CalledProcessError):p.prepare(QUALIFIED,actual,out)
    assert not out.exists()


def test_whole_source_template_inverses():
    cases=[
      ('tools/prepare_starlink_retained_output_synthesis.py','tools/prepare_starlink_retained_control_synthesis.py',
       '266515161a0d6b522348a6e53d0d925113c23352ca140264bbbec9b647044d02',[
        ('Small source-specific copier; existing frozen v5 CLI remains the authority.','Candidate-only copier; frozen candidate CLI and completed actual result required.'),
        ('c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8',p.EXPECTED),
        ("'synthesize_retained_output.tcl': BASE+'retained_output_actual/synthesize_retained_output.tcl'","'synthesize_retained_control.tcl': BASE+'retained_control_actual/synthesize_retained_control.tcl'"),
        ('prepare_starlink_retained_output_synthesis.py','prepare_starlink_retained_control_synthesis.py'),
        ('test_starlink_retained_output_synthesis.py','test_starlink_retained_control_synthesis.py'),
        ('prepare_starlink_retained_output_actual.py','prepare_starlink_retained_control_actual.py')]),
      ('hdl/library/starlink_pss_acquisition/retained_output_actual/synthesize_retained_output.tcl',
       'hdl/library/starlink_pss_acquisition/retained_control_actual/synthesize_retained_control.tcl',
       '79aca85d52146627a2584fa2d3443ead35492ecfc279f156717794535f67f660',[
        ('# Exact v5-qualified retained runtime.','# Exact candidate runtime; requires separately approved actual result.'),
        ('synthesize_retained_output.tcl','synthesize_retained_control.tcl'),
        ('prepare_starlink_retained_output_actual.py','prepare_starlink_retained_control_actual.py'),
        ('c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8',p.EXPECTED),
        ('if {[string match */retained_output/*.v $name] && ![string match */tb/* $name]}',
         'if {([string match */retained_output/*.v $name] || [string match */retained_output_closed_candidate/*.v $name]) && ![string match */tb/* $name]}'),
        ('LOCAL_FIRST_ADMISSION=1]','LOCAL_FIRST_ADMISSION=1 PRIVATE_DESCRIPTOR_OFFER=1 CLOSED_INPUT_CUTOVER=1]'),
        ('exact retained/R1/B1/O1/L1 generics','exact retained/R1/B1/O1/L1/private-offer/closed-input generics'),
        ('RETAINED_OUTPUT_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS','RETAINED_CONTROL_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS')])]
    for original,candidate,sha,edits in cases:
        assert p.digest(ROOT/original)==sha
        text=(ROOT/candidate).read_text()
        for before,after in reversed(edits):
            assert after in text;text=text.replace(after,before)
        assert text==(ROOT/original).read_text()
