"""Actual FFT with parallel product reference comparisons and late selection."""
import argparse
import json
from pathlib import Path
import re
import shutil
import forward_private_status_experiment as base
import parallel_product_identity_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_parallel_product_identity_impl'
BANK='starlink_pss_product_identity_parallel_reference'
PARENT=Path('/dev/shm/starlink-private-status.KesvWZyz/prepared-v1')
PIN='8470f72fc4ac863b35ce398bf55d559d88394bb7a2934a3527eb30678d5cb2cd'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'private status parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact top delta')
    require(transform.transform((RTL/'starlink_pss_product_identity_split_capacity.v').read_text(),transform.BANK_CHANGES)==(RTL/(BANK+'.v')).read_text(),'exact combinational identity-stage delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text())
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==33 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'33 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'parallel_product_identity_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_parallel_product_identity;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'parallel_product_identity_observer.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=35,parent_runtime_unchanged=33,parallel_product_identity=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'parallel reference comparison simulator failure')
    rows=re.findall(r'^PARALLEL_PRODUCT_IDENTITY_PASS checks=(\d+) captures=(\d+) first_refills=(\d+) four_state_exact=1 same_edge_capture=1$',log,re.M)
    require(len(rows)==1 and log.count('PARALLEL_PRODUCT_IDENTITY_PASS')==1,'one parallel reference comparison witness')
    checks,captures,refills=map(int,rows[0]);require(checks>=10000 and captures>=9216 and refills>=18,'nonvacuous comparison')
    return dict(checks=checks,captures=captures,first_refills=refills,same_edge_capture=True,four_state_exact=True)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['parallel_product_identity']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    except Exception as error:
        result.update(passed=False,parallel_identity_error=repr(error));raise
    finally:(output/'parallel_identity_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
