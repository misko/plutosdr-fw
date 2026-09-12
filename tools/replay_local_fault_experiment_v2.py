"""Remove duplicate current cancellation from shared guard, not publication."""
import argparse
import json
from pathlib import Path
import re
import shutil
import replay_capacity_ring_experiment as base
import replay_local_fault_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_replay_local_fault_impl'
BUFFER='starlink_pss_replay_local_fault_ring'
PARENT=Path('/dev/shm/starlink-replay-capacity.MDfTXxjB/ring-prepared-v1')
PIN='9ecb17d829e521ad9986d93bcd730029c4371ea8dcc08bd2a08bbc1fa4401d70'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'ring parent pin')
    for old,new,changes in [(base.NEW,NEW,transform.TOP_CHANGES),(base.BUFFER,BUFFER,transform.BANK_CHANGES)]:
        require(transform.transform((RTL/(old+'.v')).read_text(),changes)==(RTL/(new+'.v')).read_text(),'exact additive fault partition')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==45 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'45 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BUFFER+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BUFFER+'.v'),RTL/'replay_local_fault_observer_v2.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one actual integration')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_replay_local_fault;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'replay_local_fault_observer_v2.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=47,parent_runtime_unchanged=45,replay_local_fault=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    result=base.witness(log,auxiliary)
    rows=re.findall(r'^REPLAY_CANCELLATION_PARTITION_PASS checks=(\d+) external_only=(\d+) current_veto=1 registered_cause=1$',log,re.M)
    require(len(rows)==1 and log.count('REPLAY_CANCELLATION_PARTITION_PASS')==1,'one actual fault partition witness')
    checks,external=map(int,rows[0]);require(checks>=10000,'nonvacuous partition checks')
    require(external>=1 if auxiliary else external==0,'external-only current cancellation exercised')
    result.update(partition_checks=checks,external_only=external)
    return result

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['replay_local_fault']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,replay_local_fault_error=repr(error));raise
    finally:(output/'replay_local_fault_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
