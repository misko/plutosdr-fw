"""Targeted consumer relocation and registered-capacity proof, not full campaign."""
import argparse
import json
from pathlib import Path
import shutil
import replay_capacity_ring_experiment as experiment
import buffered_forward_experiment as actual
from staged_fft_experiment import sha,require,verify
def prepare(path):
    experiment.prepare(path,True)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count('    run_buffered_auxiliary;')==1,'one campaign entry')
    bench=bench.replace('    run_buffered_auxiliary;','    auxiliary_active=1;aux_fault(3);aux_reset_boundary(2,0);aux_reset_boundary(2,1);aux_reset_boundary(3,0);aux_reset_boundary(3,1);aux_delay(1);run_private_replay_sequence_boundaries;',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    source=Path(__file__).resolve();shutil.copyfile(source,path/source.name)
    manifest=json.loads((path/'snapshot.json').read_text())
    manifest['sources'][str(source)]=sha(source);manifest['experiment']['protocol_smoke_only']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,full_campaign=False)
def run(prepared,pin,output):
    result=actual.run('sim',prepared,pin,output)
    log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    result['private_replay_sequence']=experiment.base.base.witness(log,True)
    result['replay_capacity']=experiment.witness(log,True)
    require(result['replay_capacity']['full_cycles']>=100 and result['replay_capacity']['cancelled']>0,'full buffer and cancellations exercised')
    require(log.count('BUFFERED_DELAY_PASS case=1 fresh_reads=512 replay=512 products=512')==1,'consumer stall/recovery')
    result['full_campaign']=False
    (output/'smoke_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('path',type=Path)
    p=sub.add_parser('run');p.add_argument('path',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.path) if args.command=='prepare' else run(args.path,args.pin,args.output),indent=2))
