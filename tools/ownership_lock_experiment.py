"""Replace only a duplicate descriptor lock; retain all inherited FFT audits."""
import argparse
import json
from pathlib import Path
import re
import shutil
import retry_admission_experiment_v7 as base
import ownership_lock_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_ownership_lock_impl'
PARENT=Path('/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/admission-grant-artifacts.5W9rCyb5/prepared-v1')
PIN='af22ae7a5bc32bb7a53f7d33043ada08ab9dd4ed02f9a16e76c3c1f69f2c82ec'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'retry admission parent')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact ownership-only delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==43 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'43 unchanged runtime parents')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/'ownership_lock_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one active top and witness')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_ownership_lock;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'ownership_lock_observer.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'one synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=44,parent_runtime_unchanged=43,ownership_lock=True,
        ownership_reference='Original completion-driven lock, both sides of every fast edge')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'ownership comparison failure')
    rows=re.findall(r'^OWNERSHIP_LOCK_PASS checks=(\d+) accepts=(\d+) releases=(\d+) bridge=(\d+) fault_holds=(\d+) original_lock_exact=1$',log,re.M)
    require(len(rows)==1 and log.count('OWNERSHIP_LOCK_PASS')==1,'one lock witness')
    checks,accepts,releases,bridge,faults=map(int,rows[0])
    require(checks>=10000 and accepts>=18 and releases>=18 and bridge>=18,'nonvacuous ownership lifetime')
    if not auxiliary:require(accepts==releases==18 and faults==0,'healthy ownership conservation')
    else:require(faults>0,'quarantined lock hold exercised')
    return dict(checks=checks,accepts=accepts,releases=releases,bridge=bridge,fault_holds=faults,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['ownership_lock']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,ownership_error=repr(error));raise
    finally:(output/'ownership_lock_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
