"""Alternate private slots; wide writes independent of downstream READY."""
import argparse
import json
from pathlib import Path
import re
import shutil
import replay_capacity_buffer_experiment as base
import replay_capacity_ring_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_replay_capacity_ring_impl'
BUFFER='starlink_pss_replay_capacity_ring'
PARENT=Path('/dev/shm/starlink-replay-capacity.MDfTXxjB/prepared-v1')
PIN='18c6c503c4829fd5f12d9f6e847e200a9690aa3d0cd8ff15b1d082fde16359b9'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'capacity parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact ring integration')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==43 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'43 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BUFFER+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BUFFER+'.v'),RTL/'replay_capacity_ring_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==1,'one actual ring top')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    original=(RTL/'replay_capacity_buffer_observer.svh').read_text()
    require(bench.count(original)==1,'original conservation observer')
    bench=bench.replace(original,(RTL/'replay_capacity_ring_observer.svh').read_text(),1)
    require(bench.count('$fclose(log_file);')==1,'one terminal report')
    bench=bench.replace('$fclose(log_file);','report_replay_ring;\n    $fclose(log_file);',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=45,parent_runtime_unchanged=43,replay_capacity_ring=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    result=base.witness(log,auxiliary)
    rows=re.findall(r'^REPLAY_RING_PASS checks=(\d+) private_writes=(\d+) publication_fenced=1$',log,re.M)
    require(len(rows)==1 and log.count('REPLAY_RING_PASS')==1,'one private write witness')
    checks,writes=map(int,rows[0])
    require(checks>=10000,'nonvacuous ring checks')
    require(writes>=1 if auxiliary else writes==0,'cancelled private write coverage')
    result.update(private_offer_checks=checks,private_writes=writes)
    return result
def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['replay_ring']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,replay_ring_error=repr(error));raise
    finally:(output/'replay_ring_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
