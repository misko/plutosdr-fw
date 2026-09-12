"""Pin and inspect the routed comparator cone without changing its constraints."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from staged_fft_experiment import sha,require,fresh

def run(route,output):
    routed=json.loads((route/'outcome.json').read_text())
    checkpoint=route/'route/retained_output_routed.dcp'
    require(routed.get('returncode')==0 and routed.get('sources_unchanged') is True,'completed source-matched route')
    require(sha(checkpoint)==routed['routed_dcp_sha'],'exact routed checkpoint')
    tcl=Path(__file__).with_name('probe_private_replay_sequence.tcl')
    before={str(p):sha(p) for p in [checkpoint,tcl,Path(__file__).resolve()]}
    fresh(output)
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
        '-source',str(tcl),'-tclargs',str(checkpoint),routed['routed_dcp_sha'],str(output/'reports')]
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    result=dict(command=command,before=before,started=time.time(),deployment_eligible=False)
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':process.pid})+'\n')
            result['returncode']=process.wait()
        require(result['returncode']==0,'netlist observation failed')
        raw=(output/'stdout.log').read_text()
        require('PRIVATE_REPLAY_ENDPOINTS_OBSERVED_NOT_FULL_SIGNOFF' in raw and 'ERROR:' not in raw,'completed observation')
        report=(output/'reports/endpoints.txt').read_text()
        measured={}
        for label in ['kernel_next_ce','kernel_index','kernel_history','descriptor_ce','descriptor_data','occupancy','identity','output_occupancy','output_publication','product_publication']:
            rows=re.findall(r'^'+label+r'\.slack=([-\d.]+)$',report,re.M)
            require(len(rows)==1,'one real endpoint path')
            measured[label]=float(rows[0])
            raw=(output/'reports'/f'{label}.rpt').read_text()
            found=re.search(r'Slack \((?:VIOLATED|MET)\)\s*:\s*([-\d.]+)ns',raw)
            require(found is not None and float(found[1])==measured[label],'path report matches property')
        pins={label:int(re.search(r'^'+label+r'\.pins=(\d+)$',report,re.M)[1]) for label in measured}
        require(all(value>0 for value in pins.values()),'all measured endpoints exist')
        result.update(passed=True,endpoint_slack_ns=measured,endpoint_pins=pins)
    except Exception as error:
        result.update(passed=False,error=repr(error));raise
    finally:
        result['elapsed']=time.time()-result['started']
        result['sources_unchanged']=before=={p:sha(Path(p)) for p in before}
        (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    require(result['sources_unchanged'],'observation input changed')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('route',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.route,args.output),indent=2))
