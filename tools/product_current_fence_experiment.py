"""Actual FFT product publication fence; retain rejected parent and evidence."""
import argparse
import json
from pathlib import Path
import re
import shutil
import local_fault_experiment as base
import audit_local_fault_v3 as local_audit
import product_current_fence_transform as transform
from staged_fft_experiment import sha,require,verify

RTL=base.RTL
NEW='starlink_pss_fft_product_current_fence_impl'
PARENT=Path('/dev/shm/starlink-local-fault.jK1iY7XV/prepared-v1')
PIN='55f381e1950ed92a36f0af44d07d5e087d6b3d467597524e13004ccb71c7c394'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'local-fault parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact product fence delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text())
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==28 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'28 parent modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    sources=[RTL/(NEW+'.v'),Path(__file__).resolve(),Path(transform.__file__),Path(local_audit.__file__)]
    if auxiliary:sources.append(RTL/'product_current_fence_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==1,'actual DUT selection')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    if auxiliary:
        marker='      $display("LOCAL_FAULT_BOUNDARIES_PASS cases=6 delayed_fault_exercised=1 fresh_recovery=1");'
        require(bench.count(marker)==bench.count('\nendmodule')==1,'additional actual boundaries')
        bench=bench.replace(marker,'      run_product_current_fence_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'product_current_fence_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=29,parent_runtime_unchanged=28,product_current_fence=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    local=local_audit.witness(log,auxiliary)
    if auxiliary:
        cases=re.findall(r'^PRODUCT_CURRENT_FENCE_BOUNDARY_PASS boundary=(\d+) new_publications=0 fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(6))),'six actual current-fault boundaries')
        require(log.count('PRODUCT_CURRENT_FENCE_BOUNDARIES_PASS cases=6 current_fault_fenced=1 pending_reset=1 fresh_recovery=1')==1,'one current-fence terminal')
    return dict(local_fault=local,additional_boundaries=6 if auxiliary else 0)

def run(mode,prepared,pin,output):
    # The frozen local-fault v1 parser is not used. Registered-abort's runner
    # still checks numerics, original identities and all earlier fault cases.
    result=base.base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':
            log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
            result['product_current_fence']=witness(log,mode=='aux')
    except Exception as error:
        result.update(passed=False,product_fence_error=repr(error));raise
    finally:(output/'product_fence_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
