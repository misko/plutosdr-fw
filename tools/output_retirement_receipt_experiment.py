"""Actual FFT with private final retirement from registered bank ownership."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_forward_descriptor_experiment as base
import output_retirement_receipt_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_output_retirement_receipt_impl'
PARENT=Path('/dev/shm/starlink-private-descriptor.HOUYTEyQ/prepared-v1')
PIN='ec24a2e7946f68f5d906cbc4435f4613b436e2550d998d57955a15ae9b2a3e6e'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'parallel reference parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact private retirement delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==38 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'38 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/'output_retirement_receipt_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]
    if auxiliary:sources.append(RTL/'output_retirement_receipt_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_output_retirement_receipt;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'output_retirement_receipt_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        marker='      $display("PRIVATE_DESCRIPTOR_BOUNDARIES_PASS cases=6 rejected_reservation=1 private_delta=1 fresh_recovery=1");'
        require(bench.count(marker)==1,'exact auxiliary insertion')
        bench=bench.replace(marker,'      run_product_retirement_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'output_retirement_receipt_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=39,parent_runtime_unchanged=38,output_retirement_receipt=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'retirement simulator failure')
    rows=re.findall(r'^OUTPUT_RETIREMENT_RECEIPT_PASS checks=(\d+) publications=(\d+) retires=(\d+) extra_holds=(\d+) exact_publication=1 no_post_publication_write=1 receipt_retirement=1$',log,re.M)
    require(len(rows)==1 and log.count('OUTPUT_RETIREMENT_RECEIPT_PASS')==1,'one retirement witness')
    checks,pubs,retires,holds=map(int,rows[0]);require(checks>=10000 and min(pubs,retires,holds)>=18,'nonvacuous actual retirement')
    if auxiliary:
        cases=re.findall(r'^OUTPUT_RETIREMENT_BOUNDARY_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(5))),'five actual retirement boundaries')
        require(log.count('OUTPUT_RETIREMENT_BOUNDARIES_PASS cases=5 delayed_publication=1 pending_reset=1 checked_receipt=1')==1,'retirement boundary terminal')
    else:require(pubs==retires==holds==18,'healthy publication/retirement conservation')
    return dict(checks=checks,publications=pubs,retires=retires,extra_holds=holds,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['output_retirement_receipt']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,retirement_error=repr(error));raise
    finally:(output/'output_retirement_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
