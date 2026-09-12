"""Current product-publication factoring with actual FFT and unchanged arithmetic."""
import argparse
import json
from pathlib import Path
import re
import shutil
import output_retirement_receipt_experiment_v5 as base
import product_publication_cone_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_product_publication_cone_impl'
PARENT=Path('/dev/shm/starlink-output-retirement.NrVb3Jv3/prepared-v1')
PIN='10f92347fddc5e2a150f1fa852418211b58a3f168bc07b782fdf2bb2c10ac767'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'output retirement parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact combinational regrouping delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==39 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'39 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/'product_publication_cone_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]
    if auxiliary:sources.append(RTL/'product_publication_cone_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_publication_cone;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'product_publication_cone_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        marker='      $display("OUTPUT_RETIREMENT_BOUNDARIES_PASS cases=6 delayed_publication=1 pending_reset=1 checked_receipt=1");'
        require(bench.count(marker)==1,'exact auxiliary insertion')
        bench=bench.replace(marker,'      run_publication_cone_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'product_publication_cone_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=40,parent_runtime_unchanged=39,product_publication_cone=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'publication simulator failure')
    rows=re.findall(r'^PUBLICATION_CONE_PASS checks=(\d+) enabled=(\d+) faults=(\d+) current_exact=1 four_state_exact=1$',log,re.M)
    require(len(rows)==1 and log.count('PUBLICATION_CONE_PASS')==1,'one publication witness')
    checks,enabled,faults=map(int,rows[0])
    require(checks>=10000 and enabled>=18,'nonvacuous actual handoff comparisons')
    if auxiliary:
        cases=re.findall(r'^PUBLICATION_CONE_BOUNDARY_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(8))),'eight actual handoff boundaries')
        require(log.count('PUBLICATION_CONE_BOUNDARIES_PASS cases=8 metadata_groups=5 tail_bit=1 position=1 last=1')==1,'handoff boundary terminal')
        require(faults>=8,'actual bad handoffs observed')
    else:require(faults==0,'healthy current handoffs')
    return dict(checks=checks,enabled=enabled,faults=faults,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['product_publication_cone']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,publication_cone_error=repr(error));raise
    finally:(output/'publication_cone_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
