"""Retime guard occupancy using its existing checked completion pulse."""
import argparse
import json
from pathlib import Path
import re
import shutil
import retry_admission_experiment_v7 as base
import guard_pulse_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_guard_pulse_impl'
PARENT=Path('/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/admission-grant-artifacts.5W9rCyb5/prepared-v1')
PIN='af22ae7a5bc32bb7a53f7d33043ada08ab9dd4ed02f9a16e76c3c1f69f2c82ec'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'retry admission parent')
    for kind,(old,new) in transform.NAMES.items():
        require(transform.transform((RTL/(old+'.v')).read_text(),kind)==(RTL/(new+'.v')).read_text(),'exact registered-receipt delta: '+kind)
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==43 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'43 unchanged runtime parents')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+' '.join(n[1]+'.v' for n in transform.NAMES.values())+' ',1))
    for source in [*(RTL/(n[1]+'.v') for n in transform.NAMES.values()),RTL/'guard_pulse_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one active top and witness')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_pulse_guards;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'guard_pulse_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:bench=mirror_guard_faults(bench)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'one synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=45,parent_runtime_unchanged=43,guard_pulse=True,
        guard_pulse_reference='Original guards, every output and effective private state on both sides of every fast edge')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def mirror_guard_faults(bench):
    for owner in range(2):
        for verb in ['force','release']:
            old=f"{verb} dut.owners[{owner}].result_guard.fault_reasons"+("=8'h04;" if verb=='force' else ';')
            extra=f"{verb} pulse_guard_reference[{owner}].original.fault_reasons"+("=8'h04;" if verb=='force' else ';')
            require(bench.count(old)==1,'one original guard storage injection/release')
            bench=bench.replace(old,'begin '+old+extra+' end ',1)
    return bench

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'guard pulse comparison failure')
    rows=re.findall(r'^GUARD_PULSE_PASS owner=(\d+) checks=(\d+) pulses=(\d+) storage_edges=(\d+) immediate_acks=(\d+) outputs_exact=1 effective_state_exact=1$',log,re.M)
    require(len(rows)==2 and [r[0] for r in rows]==['0','1'] and log.count('GUARD_PULSE_PASS')==2,'both original guard witnesses')
    owners=[]
    for o,c,p,s,a in rows:
        owner,checks,pulses,storage,acks=map(int,[o,c,p,s,a])
        require(checks>=10000 and pulses>=18 and storage>=18,'nonvacuous retimed storage')
        if not auxiliary:require(pulses==storage==18,'healthy pulse conservation')
        owners.append(dict(owner=owner,checks=checks,pulses=pulses,storage_edges=storage,immediate_acks=acks))
    return dict(owners=owners,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['guard_pulse']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,guard_pulse_error=repr(error));raise
    finally:(output/'guard_pulse_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
