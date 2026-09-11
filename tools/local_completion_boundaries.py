"""Additional actual-FFT cancellation at completion snapshot/consume/receipt."""
import argparse
import json
from pathlib import Path
import re
import shutil
import local_completion_experiment as base
from staged_fft_experiment import sha, require, verify
FRAGMENT=base.RTL/'local_completion_boundaries.svh'

def prepare(path):
    base.prepare(path,auxiliary=True)
    manifest=json.loads((path/'snapshot.json').read_text())
    for source in [FRAGMENT,Path(__file__).resolve()]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=path/'tb_fft_buffered_forward.sv';text=bench.read_text()
    marker='      $display("BUFFERED_AUX_PASS faults=6 resets=8 delays=2 fresh_recovery=1 actual_fft=1");'
    require(text.count(marker)==text.count('\nendmodule')==1,'exact completion boundary insertion')
    text=text.replace(marker,'      run_local_completion_boundaries;\n'+marker,1)
    text=text.replace('\nendmodule','\n'+FRAGMENT.read_text()+'\nendmodule',1)
    bench.write_text(text)
    manifest['experiment']['completion_boundaries']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,'completion_boundaries':10}

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'completion boundary simulation failure')
    rows=re.findall(r'^LOCAL_COMPLETION_BOUNDARY_PASS boundary=(\d+) phase=(\d+) cancelled_reuse=0 fresh_reads=512 fresh_releases=1$',log,re.M)
    require(rows==[(str(n),str(n//3 if n<6 else 1 if n>=8 else 0)) for n in range(10)],'ten exact completion boundaries')
    require(log.count('LOCAL_COMPLETION_BOUNDARIES_PASS cases=10 current_fault_fenced=1 fresh_recovery=1')==1,'one boundary terminal')
    return {'cases':10,'current_fault_fenced':True,'fresh_recovery':True}

def run(prepared,pin,output):
    result=base.run('aux',prepared,pin,output)
    try:result['completion_boundaries']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    except Exception as error:
        result.update(passed=False,boundary_error=repr(error));raise
    finally:(output/'boundary_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path)
    execute=sub.add_parser('run');execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output) if args.command=='prepare' else run(args.prepared,args.pin,args.output),indent=2))
