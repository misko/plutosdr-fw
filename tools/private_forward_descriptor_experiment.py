"""Actual FFT with a private descriptor enable and an independent parent bank."""
import argparse
import json
from pathlib import Path
import re
import shutil
import product_retirement_receipt_experiment as base
import private_forward_descriptor_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_private_forward_descriptor_impl'
BANK='starlink_pss_forward_return_private_descriptor'
PARENT=Path('/dev/shm/starlink-product-retirement.TajliU73/prepared-v1')
PIN='40dbfcc7a30e1d66f0c4e1319a4d5ac5dd1dd9b29f0b3e14e2c64bc570d74e48'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'retirement parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact top delta')
    require(transform.transform((RTL/'starlink_pss_forward_return_private_status.v').read_text(),transform.BANK_CHANGES)==(RTL/(BANK+'.v')).read_text(),'exact private descriptor bank delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text())
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==36 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'36 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'private_forward_descriptor_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_private_forward_descriptor;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'private_forward_descriptor_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        source=RTL/'private_forward_descriptor_boundaries.svh'
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
        marker='      $display("PRODUCT_RETIREMENT_BOUNDARIES_PASS cases=5 delayed_publication=1 pending_reset=1 checked_receipt=1");'
        require(bench.count(marker)==1,'exact descriptor auxiliary insertion')
        bench=bench.replace(marker,'      run_private_descriptor_boundaries;\n'+marker,1)
        bench=bench.replace('\nendmodule','\n'+source.read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=38,parent_runtime_unchanged=36,private_forward_descriptor=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'descriptor simulator failure')
    rows=re.findall(r'^PRIVATE_FORWARD_DESCRIPTOR_PASS checks=(\d+) loads=(\d+) fault_loads=(\d+) private_differences=(\d+) controls_exact=1 valid_payload_exact=1 quarantined_difference=1$',log,re.M)
    require(len(rows)==1 and log.count('PRIVATE_FORWARD_DESCRIPTOR_PASS')==1,'one descriptor witness')
    checks,loads,fault_loads,differences=map(int,rows[0])
    require(checks>=10000 and loads>=18,'nonvacuous bank reference comparison')
    if auxiliary:
        cases=re.findall(r'^PRIVATE_DESCRIPTOR_BOUNDARY_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(6))),'six descriptor boundaries')
        require(log.count('PRIVATE_DESCRIPTOR_BOUNDARIES_PASS cases=6 rejected_reservation=1 private_delta=1 fresh_recovery=1')==1,'descriptor boundary terminal')
        require(fault_loads>=6 and differences>=6,'quarantined private delta exercised')
    else:require(fault_loads==differences==0 and loads==18,'healthy descriptor conservation')
    return dict(checks=checks,loads=loads,fault_loads=fault_loads,private_differences=differences,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['private_forward_descriptor']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,private_descriptor_error=repr(error));raise
    finally:(output/'private_descriptor_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
