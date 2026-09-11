"""Actual FFT with balanced, same-edge forward-bank descriptor equality."""
import argparse
import json
from pathlib import Path
import re
import shutil
import product_current_fence_experiment as base
import balanced_forward_identity_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_balanced_forward_identity_impl'
BANK='starlink_pss_forward_return_balanced_identity'
PARENT=Path('/dev/shm/starlink-product-fence.1PzVkOAM/prepared-v1')
PIN='8ad0828780100466b1b384d97b8b18beb42e5ad59e37d18be9d639dd81673bea'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'product fence parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact top delta')
    require(transform.transform((RTL/'starlink_pss_forward_return_bank.v').read_text(),transform.BANK_CHANGES)==(RTL/(BANK+'.v')).read_text(),'exact combinational bank delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text())
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==29 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'29 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'balanced_forward_identity_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_balanced_forward_identity;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'balanced_forward_identity_observer.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=31,parent_runtime_unchanged=29,balanced_forward_identity=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'balanced comparison simulator failure')
    rows=re.findall(r'^BALANCED_FORWARD_IDENTITY_PASS checks=(\d+) captures=(\d+) same_edge=1 four_state_exact=1$',log,re.M)
    require(len(rows)==1 and log.count('BALANCED_FORWARD_IDENTITY_PASS')==1,'one balanced comparison witness')
    checks,captures=map(int,rows[0]);require(checks>=10000 and captures>=9216,'nonvacuous comparison')
    return dict(checks=checks,captures=captures,same_edge=True,four_state_exact=True)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['balanced_forward_identity']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    except Exception as error:
        result.update(passed=False,balanced_identity_error=repr(error));raise
    finally:(output/'balanced_identity_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
