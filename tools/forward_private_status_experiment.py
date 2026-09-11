"""Actual FFT with registered private bank status and immediate public faults."""
import argparse
import json
from pathlib import Path
import re
import shutil
import balanced_forward_identity_experiment as base
import forward_private_status_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_forward_private_status_impl'
BANK='starlink_pss_forward_return_private_status'
PARENT=Path('/dev/shm/starlink-balanced-forward.TAQ78ZtF/prepared-v1')
PIN='3fdb6238d577ede67da2c3d4778d3ddb1a9e07f19a311f72482051d95d2a15a1'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'balanced parent pin')
    require(transform.top((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact private-status top delta')
    require(transform.transform((RTL/(base.BANK+'.v')).read_text(),transform.BANK_CHANGES)==(RTL/(BANK+'.v')).read_text(),'existing bank state unchanged')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==31 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'31 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'forward_private_status_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]
    if auxiliary:sources.append(RTL/'forward_private_status_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact actual private-status insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_forward_private_status;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'forward_private_status_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        marker='      $display("PRODUCT_CURRENT_FENCE_BOUNDARIES_PASS cases=6 current_fault_fenced=1 pending_reset=1 fresh_recovery=1");'
        require(bench.count(marker)==1,'exact new auxiliary insertion')
        bench=bench.replace(marker,'      run_forward_private_status_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'forward_private_status_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=33,parent_runtime_unchanged=31,forward_private_status=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'private status simulator failure')
    rows=re.findall(r'^FORWARD_PRIVATE_STATUS_PASS checks=(\d+) new_fault_edges=(\d+) private_completions=(\d+) guard_delays=(\d+) current_publication_fenced=1 registered_reuse_fenced=1 bounded_global_fault=1$',log,re.M)
    require(len(rows)==1 and log.count('FORWARD_PRIVATE_STATUS_PASS')==1,'one private-status witness')
    checks,edges,completions,delays=map(int,rows[0]);require(checks>=10000,'nonvacuous private-status monitor')
    if auxiliary:
        cases=re.findall(r'^FORWARD_PRIVATE_STATUS_BOUNDARY_PASS boundary=(\d+) new_publications=0 fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(11))),'eleven private-status boundaries')
        require(log.count('FORWARD_PRIVATE_STATUS_BOUNDARIES_PASS cases=11 private_delta_exercised=1 fresh_recovery=1')==1,'one private-status boundary terminal')
        require(edges>=11 and completions>=2 and delays>=1,'private delta exercised')
    else:require(edges==completions==delays==0,'healthy main faulted')
    return dict(checks=checks,new_fault_edges=edges,private_completions=completions,guard_delays=delays,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['forward_private_status']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,private_status_error=repr(error));raise
    finally:(output/'private_status_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
