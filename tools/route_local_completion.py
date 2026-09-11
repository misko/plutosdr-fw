"""Route local completion facts after actual reference and cancellation checks."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import buffered_forward_experiment as main
import buffered_forward_auxiliary as auxiliary
import local_completion_experiment as local
import local_completion_boundaries as boundaries
from staged_fft_experiment import sha, verify, require, fresh

def evidence(actual,synthesis,aux):
    outcomes=[json.loads((p/'outcome.json').read_text()) for p in [actual,synthesis,aux]]
    for result,mode in zip(outcomes,['sim','synth','sim']):
        require(result.get('passed') is True and result.get('returncode')==0 and result['mode']==mode and 'error' not in result,'successful actual/synthesis evidence')
        verify(Path(result['command'][-3]),result['prepared_sha'])
    a,s,x=outcomes
    require(a['prepared_sha']==s['prepared_sha'] and a['command'][-3]==s['command'][-3],'main/synthesis exact source match')
    prepared=Path(a['command'][-3]);aux_prepared=Path(x['command'][-3])
    names=re.search(r'set runtime_names \{([^}]+)\}',(prepared/'profile.tcl').read_text())[1].split()
    require(len(names)==25 and (prepared/'profile.tcl').read_bytes()==(aux_prepared/'profile.tcl').read_bytes(),'exact runtime profiles')
    require(all((prepared/n).read_bytes()==(aux_prepared/n).read_bytes() for n in names),'auxiliary runtime matches routed design')
    for folder,result in [(actual,a),(aux,x)]:
        require(json.dumps(main.audit(folder),sort_keys=True)==json.dumps(result['audit'],sort_keys=True),'fresh numerical re-audit')
    extra=auxiliary.witness((aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    saved=json.loads((aux/'auxiliary_outcome.json').read_text())
    require(saved.get('passed') is True and saved.get('auxiliary')==extra,'complete auxiliary proof')
    require(sha(synthesis/'staged_output_synth.dcp')==s['dcp_sha256'],'synthesis checkpoint identity')
    local_evidence={}
    for folder in [actual,aux]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'local_outcome.json').read_text())
        local_evidence[folder.name]=local.witness(log)
        require(receipt.get('passed') is True and receipt.get('local_completion')==local_evidence[folder.name],'actual local authority comparison')
    boundary_evidence=boundaries.witness((aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    boundary_receipt=json.loads((aux/'boundary_outcome.json').read_text())
    require(boundary_receipt.get('passed') is True and boundary_receipt.get('completion_boundaries')==boundary_evidence,'completion cancellation proof')
    return {'local_completion':local_evidence,'completion_boundaries':boundary_evidence,'main':a['audit'],'auxiliary':extra,'prepared':str(prepared),'prepared_sha':a['prepared_sha'],
            'aux_prepared':str(aux_prepared),'aux_prepared_sha':x['prepared_sha']}

def run(actual,synthesis,aux,output):
    checked=evidence(actual,synthesis,aux)
    runner=main.ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl'
    require(sha(runner)=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a','unchanged routing recipe')
    dcp=synthesis/'staged_output_synth.dcp';dcp_sha=sha(dcp)
    inputs=[dcp,runner,Path(__file__).resolve(),actual/'outcome.json',synthesis/'outcome.json',aux/'outcome.json',aux/'auxiliary_outcome.json']
    before={str(p):sha(p) for p in inputs}
    fresh(output);shutil.copyfile(runner,output/'route.tcl');shutil.copyfile(Path(__file__).resolve(),output/'route_runner.py')
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
             '-source',str(output/'route.tcl'),'-tclargs',str(dcp),dcp_sha,str(output/'route')]
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    started=time.time();result={'command':command,'started':started,'before':before,'evidence':checked,
                               'physical_signoff':False,'deployment_eligible':False}
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid,'started':started})+'\n')
            result['returncode']=process.wait()
        require(result['returncode']==0,'route execution failure')
        result['routed_dcp_sha']=sha(output/'route/retained_output_routed.dcp')
    except Exception as error:
        result['error']=repr(error);raise
    finally:
        result['elapsed']=time.time()-started
        try:
            require(before=={p:sha(Path(p)) for p in before},'route input changed')
            require(evidence(actual,synthesis,aux)==checked,'source evidence changed during route')
            result['sources_unchanged']=True
        finally:(output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['actual','synthesis','auxiliary','output']:parser.add_argument(name,type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.actual,args.synthesis,args.auxiliary,args.output),indent=2))
