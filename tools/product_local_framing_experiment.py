"""Source-pinned product-local framing experiment; not receiver deployment."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_replay_sequence_experiment_v3 as base
import product_local_framing_transform as transform
from staged_fft_experiment import sha, require, verify
RTL=base.RTL
NEW='starlink_pss_fft_product_local_framing_impl'
BANK='starlink_pss_product_mailbox_local_framing'
PARENT=Path('/dev/shm/starlink-private-replay.if3LELsS/prepared-v1')
PIN='7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'private replay parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact top delta')
    require(transform.transform((RTL/'starlink_pss_product_mailbox_staged_identity.v').read_text(),transform.BANK_CHANGES)==(RTL/(BANK+'.v')).read_text(),'exact bank delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==41 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'41 unchanged parent modules')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'product_local_framing_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]
    if auxiliary:sources.append(RTL/'product_local_framing_boundaries.svh')
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_product_local_framing;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'product_local_framing_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        marker='      run_private_replay_sequence_boundaries;'
        require(bench.count(marker)==1,'exact auxiliary insertion')
        bench=bench.replace(marker,marker+'\n      run_product_local_framing_boundaries;',1)
        bench=bench.replace('\nendmodule','\n'+(RTL/'product_local_framing_boundaries.svh').read_text()+'\nendmodule',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=43,parent_runtime_unchanged=41,product_local_framing=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'local framing simulator failure')
    rows=re.findall(r'^PRODUCT_LOCAL_FRAMING_PASS checks=(\d+) publications=(\d+) local_rejections=(\d+) actual_request_exact=1$',log,re.M)
    require(len(rows)==1 and log.count('PRODUCT_LOCAL_FRAMING_PASS')==1,'single local framing witness')
    checks,pubs,rejects=map(int,rows[0])
    require(checks>=10000 and pubs>=18,'nonvacuous actual publication')
    if auxiliary:
        cases=re.findall(r'^PRODUCT_LOCAL_FRAMING_BOUNDARY_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(6))),'six current local framing cases')
        require(rejects>=6,'local rejection edges exercised')
        require(log.count('PRODUCT_LOCAL_FRAMING_BOUNDARIES_PASS cases=6 local_checks=1 both_resets=1')==1,'local boundary completion')
    else:require(pubs==18 and rejects==0,'healthy exact publication count')
    return dict(checks=checks,publications=pubs,local_rejections=rejects,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['product_local_framing']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,local_framing_error=repr(error));raise
    finally:(output/'local_framing_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))

