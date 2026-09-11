"""Add explicit current-fault/reset/replay campaigns to actual buffered FFT."""
import argparse
import json
from pathlib import Path
import re
import shutil
import buffered_forward_experiment as experiment
from staged_fft_experiment import sha, require, verify

FRAGMENT=experiment.RTL/'buffered_forward_fault_campaign.svh'

def augment(text,fragment):
    changes=[('module tb;','module tb;\n  reg auxiliary_active=0;'),
             ('if(resetn && fft_resetn) begin','if(resetn && fft_resetn && !auxiliary_active) begin'),
             ('if(dut.fast_running) begin','if(dut.fast_running && !auxiliary_active) begin'),
             ('output_ready=mode%2==0 || slow_cycles%17<9;','output_ready=auxiliary_active ? aux_ready : (mode%2==0 || slow_cycles%17<9);'),
             ('$fclose(log_file);','run_buffered_auxiliary;\n    $fclose(log_file);'),
             ('#3000000;','#6000000;'),('\nendmodule','\n'+fragment+'\nendmodule')]
    for before,after in changes:
        require(text.count(before)==1,'exact auxiliary insertion: '+before)
        text=text.replace(before,after,1)
    return text

def prepare(path):
    experiment.prepare(path)
    manifest=json.loads((path/'snapshot.json').read_text())
    for source in [FRAGMENT,Path(__file__).resolve()]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=path/'tb_fft_buffered_forward.sv'
    bench.write_text(augment(bench.read_text(),FRAGMENT.read_text()))
    manifest['experiment']['auxiliary_campaign']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,'runtime_unchanged_from_buffered_main':True}

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'auxiliary simulation failure')
    faults=re.findall(r'^BUFFERED_FAULT_PASS case=(\d+) rejected_publications=0 fresh_reads=512 fresh_releases=1$',log,re.M)
    resets=re.findall(r'^BUFFERED_RESET_PASS boundary=(\d+) side=(\d+) stale_outputs=0 fresh_reads=512 fresh_releases=1$',log,re.M)
    delays=re.findall(r'^BUFFERED_DELAY_PASS case=(\d+) fresh_reads=512 replay=512 products=512$',log,re.M)
    require(faults==list(map(str,range(6))),'six distinct current fault campaigns')
    require(resets==[(str(b),str(s)) for b in range(4) for s in range(2)],'eight reset boundaries')
    require(delays==['0','1'],'status and elastic delay campaigns')
    require(log.count('BUFFERED_AUX_PASS faults=6 resets=8 delays=2 fresh_recovery=1 actual_fft=1')==1,'one complete auxiliary terminal')
    return {'fault_cases':6,'reset_boundaries':8,'delays':2,'fresh_recovery':True,'actual_fft':True}

def run(prepared,pin,output):
    result=experiment.run('sim',prepared,pin,output)
    try:
        result['auxiliary']=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    except Exception as error:
        result.update(passed=False,auxiliary_error=repr(error));raise
    finally:(output/'auxiliary_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path)
    execute=sub.add_parser('run');execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output) if args.command=='prepare' else run(args.prepared,args.pin,args.output),indent=2))
