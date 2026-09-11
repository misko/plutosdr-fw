"""One bounded post-route physical pass on an audited retained checkpoint.

No RTL, clocks, exceptions, board settings, or radios are changed. This is
implementation evidence, not post-implementation functional equivalence proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from audit_staged_fft_route import audit, summarize
from staged_fft_experiment import ROOT, fresh, require, sha

BASE_SHA='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a'
OLD_STEPS='  opt_design\n  place_design\n  phys_opt_design\n  route_design\n'
NEW_STEPS='  phys_opt_design -directive AggressiveExplore\n'
PARENTS={
    'certification':'5e388b0bd65cab4b5f703ecb019c5f53c1959595f22c7613febbe57f46a77ec6',
    'guardfacts':'ab681d26848908f8a5454479611d14a74040ee00fafeff525f6b074ee71f287e',
}

def recipe(base):
    require(hashlib.sha256(base.encode()).hexdigest()==BASE_SHA,'frozen base recipe')
    require(base.count(OLD_STEPS)==1,'one implementation step block')
    return base.replace(OLD_STEPS,NEW_STEPS)

def constraints(path):
    return '\n'.join(line.strip() for line in path.read_text().splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))

def run(candidate, output):
    require(candidate in PARENTS,'explicit retained candidate')
    parent=ROOT.parent/f'staged-{candidate}-route-v1'
    parent_audit=audit(parent,record=False)
    require(parent_audit==json.loads((parent/'audit.json').read_text()),'parent audit changed')
    dcp=parent/'route/retained_output_routed.dcp'
    require(sha(dcp)==PARENTS[candidate],'pinned retained routed DCP')
    base=ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl'
    generated=recipe(base.read_text())
    inputs=[dcp,base,Path(__file__).resolve(),ROOT/'tools/audit_staged_fft_route.py',
            ROOT/'tools/staged_fft_experiment.py',parent/'outcome.json',parent/'audit.json',
            parent/'route/inherited_constraints.xdc']
    before={str(p):sha(p) for p in inputs}
    fresh(output)
    (output/'route.tcl').write_text(generated)
    shutil.copyfile(Path(__file__).resolve(),output/'probe_runner.py')
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal',
             '-log',str(output/'vivado.log'),'-source',str(output/'route.tcl'),
             '-tclargs',str(dcp),PARENTS[candidate],str(output/'route')]
    result={'candidate':candidate,'parent':str(parent),'before':before,
            'parent_audit':parent_audit,'command':command,'started':time.time(),
            'recipe_sha256':sha(output/'route.tcl'), 'rtl_changed':False,
            'post_implementation_functional_proof':False,'deployment_eligible':False}
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid,'started':result['started']})+'\n')
            try:result['returncode']=process.wait(timeout=660)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=30);raise
        require(result['returncode']==0,'postroute execution failed; inspect stdout.log')
        require((output/'route.tcl').read_text()==generated and
                (output/'route/probe.tcl').read_text()==generated,'generated recipe changed')
        require(constraints(output/'route/inherited_constraints.xdc')==
                constraints(parent/'route/inherited_constraints.xdc'),'inherited constraints changed')
        result['routed_dcp_sha256']=sha(output/'route/retained_output_routed.dcp')
        receipts=dict(line.split('=',1) for line in (output/'route/dcp_receipt.txt').read_text().splitlines())
        require(receipts=={'source_dcp_sha256':PARENTS[candidate],
                'routed_dcp_sha256':result['routed_dcp_sha256'],
                'runner_sha256':result['recipe_sha256']},'checkpoint receipts disagree')
        result['audit']=summarize(output/'route')
        require(audit(parent,record=False)==parent_audit,'parent re-audit changed')
        result['constraints_unchanged']=True
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}';raise
    finally:
        result['elapsed']=time.time()-result['started']
        result['sources_unchanged']=before=={str(p):sha(p) for p in inputs}
        if not result['sources_unchanged']:result['error']='source changed during postroute'
        if result.get('returncode')==0 and 'error' not in result:
            result['audit']['source_and_checkpoint_verified']=True
        (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    require(result['sources_unchanged'],'postroute source changed')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('candidate',choices=sorted(PARENTS));parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.candidate,args.output),indent=2))
