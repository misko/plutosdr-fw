"""Source-specific actual candidate adapter; original v5 evidence is not migrated."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from . import retained_output_actual as old
from . import retained_closed_input_candidate as candidate
from . import retained_output_actual_result as original_result

ROOT=old.ROOT
RTL=old.original.RTL.parent/'retained_control_actual'
RECIPE=Path(__file__).with_name('retained_control_actual_recipe.json')
RECIPE_SHA='302d34f16fe6d2dc6cb2ee9a7d64ac864a18ff9dbe98d6050544d86493259b25'
PINS={
 'starlink_pss_core_job_cutover.v':'6f3a42178b824c28f0f6bfe3c4aeb56a2c23b84fc9aa38ab3be0d5609c4cba19',
 'starlink_pss_fft_bank_owned_retained_output_probe.v':'62f7941bc76ac320bfdee235aeae9a5f3c3bd86e251e92f571162f8183a0abec',
 'starlink_pss_fft_retained_output_impl.v':'1d01972d11486772b627a3afdd594f06e41c0f98b830288e93b371af0506ef1e',
 'starlink_pss_result_guard_owner_view.v':'53c336df4dd378a27b12f7c4d382d25290c81c0881b8e6c4f914faa67482d320',
}
FULL='''duplicate_start_fault_now || input_guard_fault ||
    source_fault_fast[1] || vendor_fault_now || fast_fault || kernel_fault ||
    product_overflow || product_bank_fault || product_bank_framing_fault_now ||
    cutover_fault_now || (|cutover_reasons) || retained_fault_now || (|retained_reasons)'''


def verify_sources():
    old.verify_originals()
    if old.sha(RECIPE)!=RECIPE_SHA:raise ValueError('candidate recipe identity')
    for name,pin in PINS.items():
        path=candidate.RTL/name
        if path.is_symlink() or old.sha(path)!=pin:raise ValueError('candidate runtime identity')
        restored=candidate.inverse(name,path.read_text())
        if name in candidate.private.PINS:candidate.private.inverse(name,restored)


def adaptations():
    verify_sources()
    source=(old.original.RTL/'starlink_pss_fft_retained_output_impl.v').read_text()
    if source.count('wire completed_input_fault_now = '+FULL+';')!=1:
        raise ValueError('literal original full completed-input expression')
    full=re.sub(r'\b[a-z][a-z_]*\b',lambda m:'dut.retained.island.'+m[0],FULL)
    header='''  wire candidate_original_completed_input_fault;
  defparam dut.PRIVATE_DESCRIPTOR_OFFER=1;
  defparam dut.CLOSED_INPUT_CUTOVER=1;
  assign candidate_original_completed_input_fault = '''+full+';\n'
    changes=[('module tb;','module tb;\n'+header)]
    for g in ['`D.owners[0].result_guard',*[f'dut.retained.island.owners[{n}].result_guard' for n in range(2)]]:
        changes.append((f'.completed_input_fault_now({g}.completed_input_fault_now)',
                        '.completed_input_fault_now(candidate_original_completed_input_fault)'))
    # The three identical new bindings have distinct original contexts. Keep
    # inverse replacements unambiguous by retaining named provenance comments.
    changes=[(before,after+f' /* candidate binding {i} */' if i else after)
             for i,(before,after) in enumerate(changes)]
    changes.append(('endmodule',(RTL/'witness.svh').read_text()+'\nendmodule'))
    return changes


def bench():
    text=old.actual_bench()
    for before,after in adaptations():
        if text.count(before)!=1:raise ValueError('candidate literal bench boundary')
        text=text.replace(before,after,1)
    inverse_bench(text)
    return text


def inverse_bench(text):
    for before,after in reversed(adaptations()):
        if text.count(after)!=1:raise ValueError('candidate whole bench inverse boundary')
        text=text.replace(after,before,1)
    if text!=old.actual_bench():raise ValueError('candidate whole bench inverse mismatch')
    return text


def compiled_sources():
    verify_sources()
    return [candidate.RTL/p.name if p.parent==old.original.RTL and p.name in PINS else p
            for p in old.compiled_sources()]


def offline(directory,*,text=None):
    verify_sources();directory.mkdir(parents=True,exist_ok=False)
    for p in old.original.BASELINE.glob('*.mem'):(directory/p.name).write_bytes(p.read_bytes())
    (directory/'bench.sv').write_text(bench() if text is None else text)
    (directory/'OFFLINE_NOT_FFT.sv').write_text(old.scripted_padding_adapter())
    command=['iverilog','-g2012','-s','tb','-o',str(directory/'sim.vvp'),str(directory/'bench.sv'),
             str(directory/'OFFLINE_NOT_FFT.sv'),*map(str,compiled_sources())]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (directory/'compile.log').write_text(result.stdout+result.stderr)
    status={'compile':result.returncode,'kind':'OFFLINE_SCRIPT_NOT_FFT','service_executed':False}
    if result.returncode==0:
        run=subprocess.run(['vvp','sim.vvp'],cwd=directory,capture_output=True,text=True,timeout=60)
        (directory/'simulation.log').write_text(run.stdout+run.stderr);status['script_exit']=run.returncode
    (directory/'status.json').write_text(json.dumps(status,sort_keys=True)+'\n')
    return status


def verify_result(log,numerical,*,kind):
    verify_sources()
    result=original_result.verify_result(log,numerical,kind=kind)
    records={};admissions=[]
    for line in log.read_text().splitlines():
        if line.startswith('RCAND_'):
            records.setdefault(line.split()[0],[]).append(original_result._fields(line))
        if line.startswith('RACT_ADMIT '):admissions.append(original_result._fields(line))
    require=original_result._require
    require({k:len(v) for k,v in records.items()}=={'RCAND_FLAGS':1,'RCAND_JOB':40,'RCAND_OWNER':2,'RCAND_PROOF':1},'candidate marker inventory')
    require(records['RCAND_FLAGS']==[dict(private_offer=1,closed_input=1,wrapper_private=1,wrapper_closed=1)],'candidate flags')
    for receipt,admit in zip(records['RCAND_JOB'],admissions,strict=True):
        expected={k:admit[k] for k in ('context','job','inverse','start','cycle')}
        require(receipt==dict(expected,offered=1,sampled=1),'candidate accepted descriptor/admission join')
    owners=sorted(records['RCAND_OWNER'],key=lambda x:x.get('owner',-1))
    for n,x in enumerate(owners):
        require(set(x)=={'owner','accepted','real_ack','held'} and x['owner']==n and
            x['accepted']==[21,19][n] and x['real_ack']==[19,17][n] and x['held']>=1000,'candidate owner inventory')
    proof=records['RCAND_PROOF'][0]
    require(set(proof)=={'jobs','final_inputs','closed_pre','closed_post','public_pre'} and
        proof['jobs']==40 and proof['final_inputs']==38 and proof['closed_pre']>=1000 and
        proof['closed_post']>=1000 and proof['public_pre']>=19456,'candidate closed proof inventory')
    return dict(result,candidate=records)
