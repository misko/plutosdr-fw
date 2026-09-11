"""Route the exact source-matched actual-FFT candidate; never deploy it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from staged_fft_experiment import ROOT, audit_sim, audit_handover_sim, audit_admission_sim, audit_completion_sim, audit_replay_sim, audit_writer_sim, audit_capture_sim, audit_finalcapture_sim, audit_sequence_sim, audit_certification_sim, audit_guardfacts_sim, audit_heldmeta_sim, audit_heldhandoff_sim, fresh, require, sha, verify

def run(actual,synthesis,output):
    a=json.loads((actual/'outcome.json').read_text())
    s=json.loads((synthesis/'outcome.json').read_text())
    for result,mode in [(a,'sim'),(s,'synth')]:
        require(result['mode']==mode and result.get('returncode')==0 and
                result.get('sources_unchanged') is True and 'error' not in result,'successful terminal source-bound parent required')
    require(a['prepared_sha']==s['prepared_sha'],'actual/synthesis source mismatch')
    # Regex rows are tuples in memory and lists after JSON serialization.
    # Compare canonical serialized values, retaining every field and value.
    audited=audit_heldhandoff_sim(actual) if 'heldhandoff' in a['audit'] else (audit_heldmeta_sim(actual) if 'heldmeta' in a['audit'] else (audit_guardfacts_sim(actual) if 'guardfacts' in a['audit'] else (
        audit_certification_sim(actual) if 'certification' in a['audit'] else (
        audit_sequence_sim(actual) if 'sequence' in a['audit'] else (
        audit_finalcapture_sim(actual) if 'finalcapture' in a['audit'] else (
        audit_capture_sim(actual) if 'capture' in a['audit'] else (
        audit_writer_sim(actual) if 'writer' in a['audit'] else (
        audit_replay_sim(actual) if 'replay' in a['audit'] else (
        audit_completion_sim(actual) if 'completion' in a['audit'] else (
        audit_admission_sim(actual) if 'admission' in a['audit'] else (
        audit_handover_sim(actual,fault_cases=len(a['audit']['handover']['faults'])) if 'handover' in a['audit'] else audit_sim(actual))))))))))))
    require(json.dumps(audited,sort_keys=True)==json.dumps(a['audit'],sort_keys=True),
            'actual numerical re-audit mismatch')
    prepared=Path(s['command'][-3]);verify(prepared,s['prepared_sha'])
    require(str(prepared)==a['command'][-3],'actual/synthesis prepared roots differ')
    dcp=synthesis/'staged_output_synth.dcp';dcp_sha=sha(dcp)
    runner=ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl'
    require(sha(runner)=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a','unchanged diagnostic routing recipe required')
    before={str(p):sha(p) for p in [dcp,runner,actual/'outcome.json',synthesis/'outcome.json',Path(__file__).resolve()]}
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
    args=parser.parse_args();print(json.dumps(run(args.actual,args.synthesis,args.output),indent=2))
