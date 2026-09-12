"""Two-slot replay capacity with unchanged FFT and original publication gates."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_replay_sequence_experiment_v3 as base
import replay_capacity_buffer_transform as transform
import replay_capacity_buffer_bench_mapping as mapping
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_replay_capacity_buffer_impl'
BUFFER='starlink_pss_replay_capacity_buffer'
PARENT=Path('/dev/shm/starlink-private-replay.if3LELsS/prepared-v1')
PIN='7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4'

def mapped(text,changes):
    for old,new in changes:
        require(old in text,'observer source anchor')
        text=text.replace(old,new)
    return text

def relocate_stall(bench):
    start=bench.index('  task automatic aux_delay(')
    end=bench.index('  task automatic run_buffered_auxiliary;',start)
    task=bench[start:end]
    marker='      end else begin\n        while(!dut.forward_buffer_valid'
    require(task.count(marker)==1,'one elastic delay branch')
    cut=task.index(marker)
    before,after=task[:cut],task[cut:]
    for old,new in [('forward_buffer_valid','replay_valid'),('forward_buffer_data','replay_data'),('forward_buffer_position','replay_position')]:
        require(old in after,'stall payload mapping')
        after=after.replace(old,new)
    return bench[:start]+before+after+bench[end:]

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'private replay parent pin')
    require(transform.transform((RTL/(base.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact capacity integration')
    for old,new,changes in [
        ('private_replay_sequence_observer.svh','replay_capacity_kernel_observer.svh',mapping.OBSERVER_CHANGES),
        ('private_replay_sequence_boundaries_v2.svh','replay_capacity_kernel_boundaries.svh',mapping.BOUNDARY_CHANGES)]:
        require(mapped((RTL/old).read_text(),changes)==(RTL/new).read_text(),'explicit consumer-observer relocation')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==41 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'41 unchanged runtime modules')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BUFFER+'.v ',1))
    sources=[RTL/(NEW+'.v'),RTL/(BUFFER+'.v'),RTL/'replay_capacity_buffer_observer.svh',
             RTL/'replay_capacity_kernel_observer.svh',Path(__file__).resolve(),Path(transform.__file__),Path(mapping.__file__)]
    if auxiliary:sources.extend([RTL/'replay_capacity_kernel_boundaries.svh'])
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'exact integration selection')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    original=(RTL/'private_replay_sequence_observer.svh').read_text()
    require(bench.count(original)==1,'one original kernel observer')
    bench=bench.replace(original,(RTL/'replay_capacity_kernel_observer.svh').read_text(),1)
    bench=bench.replace('$fclose(log_file);','report_replay_capacity;\n    $fclose(log_file);',1)
    bench=bench.replace('\nendmodule','\n'+(RTL/'replay_capacity_buffer_observer.svh').read_text()+'\nendmodule',1)
    if auxiliary:
        original=(RTL/'private_replay_sequence_boundaries_v2.svh').read_text()
        require(bench.count(original)==1,'one original private replay campaign')
        bench=bench.replace(original,(RTL/'replay_capacity_kernel_boundaries.svh').read_text(),1)
        bench=relocate_stall(bench)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=43,parent_runtime_unchanged=41,replay_capacity_buffer=True)
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'replay capacity simulator failure')
    rows=re.findall(r'^REPLAY_CAPACITY_PASS checks=(\d+) inputs=(\d+) outputs=(\d+) cancelled=(\d+) full_cycles=(\d+) refills=(\d+) word_exact=1 current_veto=1$',log,re.M)
    require(len(rows)==1 and log.count('REPLAY_CAPACITY_PASS')==1,'one capacity witness')
    checks,inputs,outputs,cancelled,full,refills=map(int,rows[0])
    require(checks>=10000 and inputs>=9216 and outputs>=9216 and refills>=9000,'nonvacuous capacity')
    if not auxiliary:require(inputs==outputs==9216 and cancelled==0,'healthy word conservation')
    return dict(checks=checks,inputs=inputs,outputs=outputs,cancelled=cancelled,full_cycles=full,refills=refills,auxiliary=auxiliary)

def run(mode,prepared,pin,output):
    result=base.run(mode,prepared,pin,output)
    try:
        if mode!='synth':result['replay_capacity']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux')
    except Exception as error:
        result.update(passed=False,replay_capacity_error=repr(error));raise
    finally:(output/'replay_capacity_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
