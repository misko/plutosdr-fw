"""Inspect the pinned routed output bundle without changing timing constraints."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from staged_fft_experiment import ROOT, require, sha, fresh

DCP=Path('/dev/shm/starlink-output-metadata.MB5fY8/route-v3/route/retained_output_routed.dcp')
PIN='ee65ba286ece8625b60af30490ee33960f28e3eb93be60ac78e759968d8afcb1'


def run(output):
    script=ROOT/'tools/inspect_output_metadata_cdc.tcl'
    require(sha(DCP)==PIN,'pinned routed source')
    before={str(p):sha(p) for p in [DCP,script,Path(__file__).resolve()]}
    fresh(output)
    env=dict(os.environ)
    for name in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(name,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
             '-source',str(script),'-tclargs',str(DCP),PIN,str(output/'inspection')]
    result={'command':command,'before':before,'deployment_eligible':False,'constraints_changed':False}
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n');started=time.time()
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid,'started':started})+'\n')
            result['returncode']=process.wait(timeout=180)
        require(result['returncode']==0,'inspection failed; see stdout.log')
        require('OUTPUT_METADATA_CDC_INSPECTION_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE' in (output/'stdout.log').read_text(),'missing completion receipt')
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}';raise
    finally:
        result['elapsed']=time.time()-started
        result['sources_unchanged']=before=={p:sha(Path(p)) for p in before}
        (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    require(result['sources_unchanged'],'inspection sources changed')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    print(json.dumps(run(parser.parse_args().output),indent=2))
