"""Short actual-FFT protocol campaign; not full inherited qualification."""
import argparse
import json
from pathlib import Path
import shutil
import output_retirement_receipt_experiment_v4 as experiment
import buffered_forward_experiment as actual
from staged_fft_experiment import sha,require,verify

def prepare(path):
    experiment.prepare(path,True)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count('    run_buffered_auxiliary;')==1,'one full campaign entry')
    bench=bench.replace('    run_buffered_auxiliary;','    auxiliary_active=1;run_output_retirement_boundaries;',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    source=Path(__file__).resolve();shutil.copyfile(source,path/source.name)
    manifest=json.loads((path/'snapshot.json').read_text())
    manifest['sources'][str(source)]=sha(source)
    manifest['experiment']['protocol_smoke_only']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,'full_campaign':False}
def run(prepared,pin,output):
    result=actual.run('sim',prepared,pin,output)
    result['output_protocol']=experiment.witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),True)
    result['full_campaign']=False
    (output/'smoke_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('path',type=Path)
    p=sub.add_parser('run');p.add_argument('path',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.path) if args.command=='prepare' else run(args.path,args.pin,args.output),indent=2))
