"""Source-matched local completion candidate, with the real buffered FFT."""
import argparse
import json
from pathlib import Path
import re
import shutil
import buffered_forward_experiment as main
import buffered_forward_auxiliary as aux
import local_completion_transform as transform
from staged_fft_experiment import sha, require, verify

RTL=main.RTL
NEW='starlink_pss_fft_completion_local_impl'
PARENT=Path('/dev/shm/starlink-buffered-forward.mZfKEBtK/prepared-v1')
PARENT_PIN='f4b18fe4f9a10f4b1ebd69e4546d81b064863ea4894694838e1d912e52f5b860'
OBSERVER=RTL/'local_completion_observer.svh'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PARENT_PIN,'buffered parent pin')
    require(transform.transform((RTL/(main.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact local delta')
    main.prepare(path)
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==24 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'24 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    manifest=json.loads((path/'snapshot.json').read_text())
    sources=[RTL/(NEW+'.v'),OBSERVER,Path(__file__).resolve(),main.ROOT/'tools/local_completion_transform.py']
    if auxiliary:sources += [aux.FRAGMENT,main.ROOT/'tools/buffered_forward_auxiliary.py']
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(main.NEW+' #(')==1,'one real DUT')
    bench=bench.replace(main.NEW+' #(',NEW+' #(',1)
    if auxiliary:bench=aux.augment(bench,aux.FRAGMENT.read_text())
    require(bench.count('\nendmodule')==1 and bench.count('$fclose(log_file);')==1,'observer insertion')
    bench=bench.replace('\nendmodule','\n'+OBSERVER.read_text()+'\nendmodule',1).replace('$fclose(log_file);','report_local_completion;\n    $fclose(log_file);',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+main.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+main.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment']={'runtime_modules':25,'parent_runtime_unchanged':24,'local_completion':True,'auxiliary':auxiliary}
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,**manifest['experiment']}

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'actual simulator failure')
    rows=re.findall(r'^LOCAL_COMPLETION_PASS checks=(\d+) owned=(\d+) permits=(\d+) private_differences=(\d+) original_authority_exact=1 public_veto_unchanged=1$',log,re.M)
    require(len(rows)==1 and log.count('LOCAL_COMPLETION_PASS')==1,'one local completion witness')
    checks,owned,permits,differences=map(int,rows[0])
    require(checks>=10000 and owned>=36 and permits>=36 and differences>=100,'nonvacuous local comparison')
    return dict(checks=checks,owned=owned,permits=permits,private_differences=differences,original_authority_exact=True)

def run(mode,prepared,pin,output):
    profile=json.loads((prepared/'snapshot.json').read_text())['experiment']
    require(mode in {'sim','aux','synth'} and profile['local_completion'] and profile['auxiliary']==(mode=='aux'),'explicit matching profile')
    result=main.run('sim' if mode=='aux' else mode,prepared,pin,output)
    try:
        if mode!='synth':
            log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
            result['local_completion']=witness(log)
            if mode=='aux':result['auxiliary']=aux.witness(log)
    except Exception as error:
        result.update(passed=False,local_error=repr(error));raise
    finally:
        (output/'local_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
        if mode=='aux':(output/'auxiliary_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path);prep.add_argument('--auxiliary',action='store_true')
    execute=sub.add_parser('run');execute.add_argument('mode',choices=['sim','aux','synth']);execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
