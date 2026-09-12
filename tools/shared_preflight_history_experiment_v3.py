"""Same-cycle shared diagnostic history; original guards remain reference."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_replay_sequence_experiment_v3 as base
import shared_preflight_history_transform as transform
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_shared_preflight_history_impl'
GUARD='starlink_pss_result_guard_shared_preflight'
PARENT=Path('/dev/shm/starlink-private-replay.if3LELsS/prepared-v1')
PIN='7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4'

def mirror_guard_storage_faults(bench):
    for owner in range(2):
        old=f"force dut.owners[{owner}].result_guard.fault_reasons=8'h04;"
        new=f"begin if(dut.shared_preflight_history!==0)$fatal(1,\"direct guard storage injection has preflight history\"); force dut.owners[{owner}].result_guard.private_fault_reasons=8'h04; force shared_guard_reference[{owner}].original.fault_reasons=8'h04; end"
        require(bench.count(old)==1,'one inherited guard register fault per owner')
        bench=bench.replace(old,new,1)
        old=f'release dut.owners[{owner}].result_guard.fault_reasons;'
        new=f'release dut.owners[{owner}].result_guard.private_fault_reasons;release shared_guard_reference[{owner}].original.fault_reasons;'
        require(bench.count(old)==1,'one inherited guard register release per owner')
        bench=bench.replace(old,new,1)
    return bench

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'lean private replay parent')
    for old,new,changes in [(base.NEW,NEW,transform.TOP_CHANGES),('starlink_pss_result_guard_owner_view',GUARD,transform.GUARD_CHANGES)]:
        require(transform.transform((RTL/(old+'.v')).read_text(),changes)==(RTL/(new+'.v')).read_text(),'exact shared history delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==41 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'41 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+GUARD+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(GUARD+'.v'),RTL/'shared_preflight_guard_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'one top and observer insertion')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    bench=bench.replace('$fclose(log_file);','report_shared_preflight_guards;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'shared_preflight_guard_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:bench=mirror_guard_storage_faults(bench)
    if auxiliary:
        fragment=RTL/'shared_preflight_history_boundaries.svh'
        shutil.copyfile(fragment,path/fragment.name);manifest['sources'][str(fragment)]=sha(fragment)
        require(bench.count('    run_buffered_auxiliary;')==1,'one full inherited campaign call')
        bench=bench.replace('    run_buffered_auxiliary;','    run_buffered_auxiliary;\n    run_shared_preflight_boundaries;',1)
        bench=bench.replace('\nendmodule','\n'+fragment.read_text()+'\nendmodule',1)
    # Model the existing sticky register's procedural conditional exactly:
    # an X predicate does not take an if branch, so the previous bit holds.
    # The old Boolean-OR observer was equivalent only for known inputs.
    old_oracle='    local_expected_fault=dut.fast_fault || dut.result_fault || (|dut.local_fault_snapshot);'
    new_oracle='    local_expected_fault=dut.fast_fault;\n    if(dut.result_fault || (|dut.local_fault_snapshot))local_expected_fault=1;'
    require(bench.count(old_oracle)==1,'one inherited sticky-fault arithmetic observer')
    bench=bench.replace(old_oracle,new_oracle,1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=43,parent_runtime_unchanged=41,shared_preflight_history=True,
        guard_reference='Every original output and private state on both sides of each edge; equivalent injected storage faults mirrored')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'shared guard comparison failed')
    rows=re.findall(r'^SHARED_PREFLIGHT_GUARD_PASS owner=(\d+) checks=(\d+) preflight_edges=(\d+) outputs_exact=1 private_state_exact=1$',log,re.M)
    require(len(rows)==2 and [r[0] for r in rows]==['0','1'] and log.count('SHARED_PREFLIGHT_GUARD_PASS')==2,'both original guard witnesses')
    require(all(int(r[1])>=10000 for r in rows),'nonvacuous complete guard comparison')
    if not auxiliary:require(all(int(r[2])==0 for r in rows),'healthy preflight faults absent')
    else:
        cases=re.findall(r'^SHARED_PREFLIGHT_BOUNDARY_PASS case=(\d+) cause=(\d+) raw_reset=(\d+) fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==[(str(i),str(i if i<6 else 3),str(int(i>=8))) for i in range(10)],'ten direct shared preflight boundaries')
        require(log.count('SHARED_PREFLIGHT_BOUNDARIES_PASS cases=10 causes=6 metadata_unknown=2 raw_resets=2 original_guards_exact=1')==1,'complete shared history campaign')
        require(all(int(r[2])>=6 for r in rows),'actual preflight faults compared by both original guards')
    return dict(owners=[dict(owner=int(o),checks=int(c),preflight_edges=int(p)) for o,c,p in rows],auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['shared_preflight_history']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,shared_preflight_error=repr(error));raise
    finally:(output/'shared_preflight_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
