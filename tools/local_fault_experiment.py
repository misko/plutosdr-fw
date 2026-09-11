"""Local fault pipeline with exact source and bounded publication checks."""
import argparse
import json
from pathlib import Path
import re
import shutil
import registered_abort_experiment as base
import local_fault_transform as transform
from staged_fft_experiment import sha, require, verify
RTL=base.RTL
NEW='starlink_pss_fft_local_fault_pipeline_impl'
PARENT=Path('/dev/shm/starlink-registered-abort.CFsRfq40/prepared-v1')
PIN='23098219271638ad765ab8ebb5816baff0c5c62dd63d5c5cbffb3eb97d7c8d1e'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'output identity parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact private abort delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text())
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==27 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'27 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/'local_fault_observer.svh',Path(__file__).resolve(),base.base.main.ROOT/'tools/local_fault_transform.py']
    if auxiliary:sources.append(RTL/'local_fault_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact actual selection')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'local_fault_observer.svh').read_text()+'\nendmodule',1)
    bench=bench.replace('$fclose(log_file);','report_local_fault;\n    $fclose(log_file);',1)
    if auxiliary:
        marker='      $display("REGISTERED_ABORT_BOUNDARIES_PASS cases=6 private_delta_exercised=1 fresh_recovery=1");'
        require(bench.count(marker)==1,'exact new boundary insertion')
        bench=bench.replace(marker,'      run_local_fault_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'local_fault_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=28,parent_runtime_unchanged=27,local_fault_pipeline=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,**manifest['experiment']}

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'local fault simulator failure')
    rows=re.findall(r'^LOCAL_FAULT_PASS checks=(\\d+) delayed_edges=(\\d+) pending_checks=(\\d+) exact_sources=1 bounded_abort=1 publication_fenced=1$',log,re.M)
    require(len(rows)==1 and log.count('LOCAL_FAULT_PASS')==1,'one local fault witness')
    checks,delays,pending=map(int,rows[0])
    require(checks>=10000,'nonvacuous local fault observer')
    if auxiliary:
        cases=re.findall(r'^LOCAL_FAULT_BOUNDARY_PASS boundary=(\\d+) new_publications=0 fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(6))),'six actual delayed-fault boundaries')
        require(log.count('LOCAL_FAULT_BOUNDARIES_PASS cases=6 delayed_fault_exercised=1 fresh_recovery=1')==1,'one local boundary terminal')
        require(delays>=6 and pending>=6,'delayed global fault exercised')
    else:require(delays==pending==0,'healthy main unexpectedly faulted')
    return dict(checks=checks,delayed_edges=delays,pending_checks=pending,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':
            log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
            result['local_fault']=witness(log,mode=='aux')
    except Exception as error:
        result.update(passed=False,local_fault_error=repr(error));raise
    finally:
        (output/'local_fault_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path);prep.add_argument('--auxiliary',action='store_true')
    execute=sub.add_parser('run');execute.add_argument('mode',choices=['sim','aux','synth']);execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
