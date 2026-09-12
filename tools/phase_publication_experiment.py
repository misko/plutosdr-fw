"""Remove only the phase-inactive preflight term from quiet publication."""
import argparse
import json
from pathlib import Path
import re
import shutil
import guard_pulse_experiment_v3 as base
import phase_publication_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_phase_publication_impl'
PARENT=Path('/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/guard-pulse-artifacts.EqZnBaxQ/prepared-v1')
PIN='96cef71c3f92a4a9f4dea6d477073aa92652604a6becd4e05a33e84fb89bf36e'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'guard pulse parent')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact publication delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==45 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'45 unchanged runtime parents')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v'+' ',1))
    for source in [RTL/(NEW+'.v'),RTL/'phase_publication_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one active top and witness')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_phase_publication;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'phase_publication_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:bench=mirror_publication_veto(bench)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'one synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=46,parent_runtime_unchanged=45,phase_publication=True,
        publication_reference='Original full predicate and unforced contextual expressions on both sides of each fast edge')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def mirror_publication_veto(bench):
    for verb in ['force','release']:
        tail="=1'b0;" if verb=='force' else ';'
        old=verb+' dut.output_replay_accept'+tail
        extra=verb+' phase_original_accept'+tail
        require(bench.count(old)==1,'one original publication veto injection/release')
        bench=bench.replace(old,'begin '+old+extra+' end ',1)
    return bench

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'publication comparison failure')
    rows=re.findall(r'^PHASE_PUBLICATION_PASS checks=(\d+) accepts=(\d+) preflight=(\d+) fault_differences=(\d+) exact=1$',log,re.M)
    require(len(rows)==log.count('PHASE_PUBLICATION_PASS')==1,'one publication witness')
    checks,accepts,preflight,differences=map(int,rows[0])
    require(checks>=10000 and accepts>=18,'nonvacuous publication comparisons')
    if auxiliary:require(preflight>0 and differences>0,'active preflight and different fault predicates observed')
    else:require(accepts==18,'healthy publication conservation')
    return dict(checks=checks,accepts=accepts,preflight=preflight,fault_differences=differences,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['phase_publication']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,phase_publication_error=repr(error));raise
    finally:(output/'phase_publication_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
