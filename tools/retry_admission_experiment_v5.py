"""Actual FFT and original grant oracle for a retrying held-job request."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_replay_sequence_experiment_v3 as base
import retry_admission_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_retry_admission_impl'
CERT='starlink_pss_admission_retry_certificate'
PARENT=Path('/dev/shm/starlink-private-replay.if3LELsS/prepared-v1')
PIN='7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'lean private replay parent')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact request delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==41 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'41 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+CERT+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(CERT+'.v'),RTL/'retry_admission_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one top and observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_retry_admission;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'retry_admission_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        fragment=RTL/'retry_admission_boundaries_v3.svh'
        shutil.copyfile(fragment,path/fragment.name);manifest['sources'][str(fragment)]=sha(fragment)
        require(bench.count('    run_buffered_auxiliary;')==1,'one full inherited campaign call')
        bench=bench.replace('    run_buffered_auxiliary;','    auxiliary_active=1;\n    run_retry_admission_boundaries;\n    run_buffered_auxiliary;',1)
        bench=bench.replace('\nendmodule','\n'+fragment.read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=43,parent_runtime_unchanged=41,retry_admission=True,
        grant_reference='Original live-capacity request/certificate with exact current job acceptance')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'retry grant comparison failed')
    rows=re.findall(r'^RETRY_ADMISSION_PASS checks=(\d+) grants=(\d+) rejected_snapshots=(\d+) capacity_waits=(\d+) original_accept_exact=1 held_identity=1 once_per_request=1$',log,re.M)
    require(len(rows)==1 and log.count('RETRY_ADMISSION_PASS')==1,'one original grant witness')
    checks,grants,rejected,waits=map(int,rows[0])
    require(checks>=10000 and grants>=36,'nonvacuous complete grant comparison')
    if not auxiliary:require(grants==36,'exact healthy admissions')
    else:
        cases=re.findall(r'^RETRY_ADMISSION_BOUNDARY_PASS case=(\d+) inverse=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==[(str(i),str(i//2 if i<4 else (i%2 if i<8 else 0))) for i in range(10)],'ten held-request boundaries')
        require(log.count('RETRY_ADMISSION_BOUNDARIES_PASS cases=10 capacity_stalls=4 one_sided_resets=4 timeout=1 descriptor_fault=1')==1,'complete direct admission campaign')
        require(rejected>=100 and waits>=50,'actual retry and delayed capacity exercised')
    return dict(checks=checks,grants=grants,rejected_snapshots=rejected,capacity_waits=waits,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['retry_admission']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,retry_admission_error=repr(error));raise
    finally:(output/'retry_admission_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
