"""Route the exact source-matched actual-FFT candidate; never deploy it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from staged_fft_experiment import audit_enginecapture_sim, audit_inputstage_sim, audit_preflightpublication_sim
from staged_fft_experiment import audit_ackcombined_sim, audit_ackcombined_aux
from staged_fft_experiment import forward_receipt_compiled, audit_forwardreceipt
from staged_fft_experiment import product_stage_compiled, audit_productstage
from staged_fft_experiment import final_capacity_compiled, audit_finalcapacity
from staged_fft_experiment import split_capacity_compiled, audit_splitcapacity
from staged_fft_experiment import output_metadata_compiled, audit_outputmetadata
from staged_fft_experiment import balanced_handoff_compiled, audit_balancedhandoff
from staged_fft_experiment import completion_slot_compiled, audit_completion_slot
from staged_fft_experiment import private_facts_compiled, audit_private_facts
from staged_fft_experiment import replay_quiet_compiled, audit_replay_quiet, replay_fence_compiled, audit_replay_fence, verify_replay_fence_configuration
from staged_fft_experiment import private_quarantine_compiled, audit_private_quarantine, verify_private_quarantine_configuration

from staged_fft_experiment import ROOT, audit_sim, audit_handover_sim, audit_admission_sim, audit_completion_sim, audit_replay_sim, audit_writer_sim, audit_capture_sim, audit_finalcapture_sim, audit_sequence_sim, audit_certification_sim, audit_guardfacts_sim, fresh, require, sha, verify

def ack_auxiliary_required(prepared,audit):
    compiled='module tb #(parameter integer ACK_ONLY=0);' in (prepared/'tb_fft_staged_output.sv').read_text()
    require(('ackcombined' in audit)==compiled,'main audit and compiled combined campaign differ')
    return compiled

def verify_ack_auxiliary(auxiliary,expected,prepared):
    require(auxiliary is not None,'combined ACK requires its auxiliary real-FFT proof')
    result=json.loads((auxiliary/'outcome.json').read_text())
    require(result.get('mode')=='ack' and result.get('returncode')==0 and
            result.get('sources_unchanged') is True and 'error' not in result,'successful source-bound ACK auxiliary required')
    require(result['prepared_sha']==expected and result['command'][-3]==str(prepared),
            'ACK auxiliary must use the same prepared sources')
    audited=audit_productstage(auxiliary,auxiliary=True) if product_stage_compiled(prepared) else (audit_forwardreceipt(auxiliary,auxiliary=True) if forward_receipt_compiled(prepared) else audit_ackcombined_aux(auxiliary))
    if final_capacity_compiled(prepared):audited=audit_finalcapacity(auxiliary,auxiliary=True)
    if split_capacity_compiled(prepared):audited=audit_splitcapacity(auxiliary,auxiliary=True)
    if output_metadata_compiled(prepared):audited=audit_outputmetadata(auxiliary,auxiliary=True)
    if balanced_handoff_compiled(prepared):audited=audit_balancedhandoff(auxiliary,auxiliary=True)
    if completion_slot_compiled(prepared):audited=audit_completion_slot(auxiliary,auxiliary=True)
    if private_facts_compiled(prepared):audited=audit_private_facts(auxiliary,auxiliary=True)
    if replay_quiet_compiled(prepared):audited=audit_replay_fence(auxiliary,auxiliary=True) if replay_fence_compiled(prepared) else audit_replay_quiet(auxiliary,auxiliary=True)
    if private_quarantine_compiled(prepared):audited=audit_private_quarantine(auxiliary,auxiliary=True)
    require(json.dumps(audited,sort_keys=True)==json.dumps(result['audit'],sort_keys=True),'ACK auxiliary re-audit mismatch')
    return audited

def run(actual,synthesis,output,ack_actual=None):
    a=json.loads((actual/'outcome.json').read_text())
    s=json.loads((synthesis/'outcome.json').read_text())
    for result,mode in [(a,'sim'),(s,'synth')]:
        require(result['mode']==mode and result.get('returncode')==0 and
                result.get('sources_unchanged') is True and 'error' not in result,'successful terminal source-bound parent required')
    require(a['prepared_sha']==s['prepared_sha'],'actual/synthesis source mismatch')
    # Regex rows are tuples in memory and lists after JSON serialization.
    # Compare canonical serialized values, retaining every field and value.
    audited=audit_enginecapture_sim(actual) if 'enginecapture' in a['audit'] else (audit_inputstage_sim(actual) if 'inputstage' in a['audit'] else (audit_preflightpublication_sim(actual) if 'preflightpublication' in a['audit'] else (audit_guardfacts_sim(actual) if 'guardfacts' in a['audit'] else (
        audit_certification_sim(actual) if 'certification' in a['audit'] else (
        audit_sequence_sim(actual) if 'sequence' in a['audit'] else (
        audit_finalcapture_sim(actual) if 'finalcapture' in a['audit'] else (
        audit_capture_sim(actual) if 'capture' in a['audit'] else (
        audit_writer_sim(actual) if 'writer' in a['audit'] else (
        audit_replay_sim(actual) if 'replay' in a['audit'] else (
        audit_completion_sim(actual) if 'completion' in a['audit'] else (
        audit_admission_sim(actual) if 'admission' in a['audit'] else (
        audit_handover_sim(actual,fault_cases=len(a['audit']['handover']['faults'])) if 'handover' in a['audit'] else audit_sim(actual)))))))))))))
    if 'ackcombined' in a['audit']:audited=audit_ackcombined_sim(actual)
    prepared=Path(s['command'][-3])
    require(('forwardreceipt' in a['audit'])==forward_receipt_compiled(prepared),
            'main audit and compiled forward receipt campaign differ')
    if forward_receipt_compiled(prepared):audited=audit_forwardreceipt(actual)
    require(('productstage' in a['audit'])==product_stage_compiled(prepared),
            'main audit and compiled product stage campaign differ')
    if product_stage_compiled(prepared):audited=audit_productstage(actual)
    require(('finalcapacity' in a['audit'])==final_capacity_compiled(prepared),
            'main audit and compiled final capacity campaign differ')
    if final_capacity_compiled(prepared):audited=audit_finalcapacity(actual)
    require(('splitcapacity' in a['audit'])==split_capacity_compiled(prepared),
            'main audit and compiled split capacity campaign differ')
    if split_capacity_compiled(prepared):audited=audit_splitcapacity(actual)
    require(('outputmetadata' in a['audit'])==output_metadata_compiled(prepared),
            'main audit and compiled output metadata campaign differ')
    if output_metadata_compiled(prepared):audited=audit_outputmetadata(actual)
    require(('balancedhandoff' in a['audit'])==balanced_handoff_compiled(prepared),
            'main audit and compiled balanced handoff campaign differ')
    if balanced_handoff_compiled(prepared):audited=audit_balancedhandoff(actual)
    require(('completion_slot' in a['audit'])==completion_slot_compiled(prepared),
            'main audit and compiled completion slot campaign differ')
    if completion_slot_compiled(prepared):audited=audit_completion_slot(actual)
    require(('private_facts' in a['audit'])==private_facts_compiled(prepared),
            'main audit and compiled private facts campaign differ')
    if private_facts_compiled(prepared):audited=audit_private_facts(actual)
    require(('replay_quiet' in a['audit'])==replay_quiet_compiled(prepared),'main audit and compiled replay quiet campaign differ')
    require(('replay_fence' in a['audit'])==replay_fence_compiled(prepared),'main audit and compiled replay fence campaign differ')
    if replay_quiet_compiled(prepared):audited=audit_replay_fence(actual) if replay_fence_compiled(prepared) else audit_replay_quiet(actual)
    if replay_fence_compiled(prepared):verify_replay_fence_configuration(prepared)
    require(('private_quarantine' in a['audit'])==private_quarantine_compiled(prepared),'main audit and compiled private quarantine campaign differ')
    if private_quarantine_compiled(prepared):
        verify_private_quarantine_configuration(prepared)
        audited=audit_private_quarantine(actual)
    require(json.dumps(audited,sort_keys=True)==json.dumps(a['audit'],sort_keys=True),
            'actual numerical re-audit mismatch')
    prepared=Path(s['command'][-3]);verify(prepared,s['prepared_sha'])
    require(str(prepared)==a['command'][-3],'actual/synthesis prepared roots differ')
    ack_audit=verify_ack_auxiliary(ack_actual,s['prepared_sha'],prepared) if ack_auxiliary_required(prepared,a['audit']) else None
    dcp=synthesis/'staged_output_synth.dcp';dcp_sha=sha(dcp)
    runner=ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl'
    require(sha(runner)=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a','unchanged diagnostic routing recipe required')
    before={str(p):sha(p) for p in [dcp,runner,actual/'outcome.json',synthesis/'outcome.json',Path(__file__).resolve()]}
    if ack_audit is not None:
        for p in [ack_actual/'outcome.json',ack_actual/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log']:
            before[str(p)]=sha(p)
    fresh(output)
    shutil.copyfile(runner,output/'route.tcl')
    # Preserve the exact orchestration source alongside the immutable recipe.
    shutil.copyfile(Path(__file__).resolve(),output/'route_runner.py')
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
             '-source',str(output/'route.tcl'),'-tclargs',str(dcp),dcp_sha,str(output/'route')]
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    started=time.time()
    result={'command':command,'started':started,'before':before,'actual_audit':a['audit'],
            'prepared_sha':s['prepared_sha'],'physical_signoff':False,'deployment_eligible':False}
    if ack_audit is not None:result['ack_auxiliary_audit']=ack_audit
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid,'started':started})+'\n')
            try:result['returncode']=process.wait(timeout=660)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=30);raise
        require(result['returncode']==0,'route execution failed; inspect stdout.log')
        result['routed_dcp_sha']=sha(output/'route/retained_output_routed.dcp')
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}';raise
    finally:
        result['elapsed']=time.time()-started
        try:
            require(before=={p:sha(Path(p)) for p in before},'route inputs changed')
            require(sha(output/'route_runner.py')==before[str(Path(__file__).resolve())],'copied route runner changed')
            verify(prepared,s['prepared_sha']);result['sources_unchanged']=True
        finally:(output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['actual','synthesis','output']:parser.add_argument(name,type=Path)
    parser.add_argument('--ack-actual',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.actual,args.synthesis,args.output,args.ack_actual),indent=2))
