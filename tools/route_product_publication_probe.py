"""Early physical feedback, explicitly not complete fault/receiver qualification."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import buffered_forward_experiment as actual
import product_publication_experiment as experiment
from staged_fft_experiment import sha,verify,require,fresh

def run(sim,synth,tests,output):
    a=json.loads((sim/'product_publication_outcome.json').read_text())
    s=json.loads((synth/'product_publication_outcome.json').read_text())
    require(a.get('passed') is True and s.get('passed') is True and a['returncode']==s['returncode']==0,'healthy actual/synthesis pass')
    require(a['mode']=='sim' and s['mode']=='synth' and a['prepared_sha']==s['prepared_sha'] and a['command'][-3]==s['command'][-3],'exact same synthesis/main source')
    prepared=Path(a['command'][-3]);verify(prepared,a['prepared_sha'])
    require(json.dumps(actual.audit(sim),sort_keys=True)==json.dumps(a['audit'],sort_keys=True),'fresh numerical audit')
    require(experiment.witness((sim/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())==a['product_publication'],'actual full publication predicate equivalence')
    tree=ET.parse(tests)
    require(len(list(tree.iter('testcase')))==20 and not any(list(tree.iter(x)) for x in ['failure','error','skipped']),'component checks pass')
    dcp=synth/'staged_output_synth.dcp';require(sha(dcp)==s['dcp_sha256'],'synthesis DCP identity')
    runner=actual.ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl'
    require(sha(runner)=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a','unchanged physical recipe')
    inputs=[sim/'product_publication_outcome.json',synth/'product_publication_outcome.json',tests,dcp,runner,Path(__file__).resolve()]
    before={str(p):sha(p) for p in inputs}
    fresh(output);shutil.copyfile(runner,output/'route.tcl');shutil.copyfile(Path(__file__).resolve(),output/'exploratory_runner.py')
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
        '-source',str(output/'route.tcl'),'-tclargs',str(dcp),s['dcp_sha256'],str(output/'route')]
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    result=dict(command=command,before=before,started=time.time(),exploratory_only=True,
        complete_fault_campaign_verified=False,physical_signoff=False,deployment_eligible=False,
        prepared=str(prepared),prepared_sha=a['prepared_sha'])
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid})+'\n')
            result['returncode']=process.wait()
        require(result['returncode']==0,'exploratory route execution')
        result['routed_dcp_sha']=sha(output/'route/retained_output_routed.dcp')
    except Exception as error:
        result['error']=repr(error);raise
    finally:
        result['elapsed']=time.time()-result['started']
        result['sources_unchanged']=before=={p:sha(Path(p)) for p in before}
        (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    verify(prepared,a['prepared_sha']);require(result['sources_unchanged'],'route source mutation')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['actual','synthesis','tests','output']:parser.add_argument(name,type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.actual,args.synthesis,args.tests,args.output),indent=2))
