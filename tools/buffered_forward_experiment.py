"""Pinned actual-FFT integration experiment, never a radio deployment tool."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import buffered_forward_transform as transform
import staged_fft_experiment as base

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-private-forward.hbi1EUk2/prepared-v2')
PARENT_PIN='99af4fda00461dce42479a9d8ff6b053af08d0d5ada504877f2957d204b24114'
OLD='starlink_pss_fft_staged_output_impl'
NEW='starlink_pss_fft_buffered_forward_impl'

def prepare(path):
    base.require(base.sha(PARENT/'SHA256SUMS')==PARENT_PIN,'parent inventory')
    base.require(transform.transform((RTL/(OLD+'.v')).read_text())==(RTL/(NEW+'.v')).read_text(),'exact top derivation')
    base.prepare(path)
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    base.require(len(names)==22 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'reference runtime unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {starlink_pss_forward_return_bank.v '+NEW+'.v ',1))
    manifest=json.loads((path/'snapshot.json').read_text())
    for source in [RTL/'starlink_pss_forward_return_bank.v',RTL/(NEW+'.v'),RTL/'tb_fft_buffered_forward.sv',
                   Path(__file__).resolve(),ROOT/'tools/buffered_forward_transform.py']:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=base.sha(source)
    tcl=(path/'staged_fft_experiment.tcl').read_text()
    base.require(tcl.count('tb_fft_staged_output.sv')==1 and tcl.count('set_property top '+OLD+' ')==1,'Tcl exact selection')
    tcl=tcl.replace('tb_fft_staged_output.sv','tb_fft_buffered_forward.sv').replace('set_property top '+OLD+' ','set_property top '+NEW+' ')
    (path/'buffered_forward_experiment.tcl').write_text(tcl)
    manifest['files']={p.name:base.sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    manifest['experiment']={'runtime_modules':24,'reference_modules_unchanged':22,'buffer_integrated':True,'parent_pin':PARENT_PIN}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':base.sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=base.sha(path/'SHA256SUMS');base.verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,**manifest['experiment']}

def audit(output):
    sim=output/'project/staged_fft.sim/sim_1/behav/xsim'
    log=(sim/'simulate.log').read_text()
    base.require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'simulation failure')
    rows=re.findall(r'^BUFFERED_CONTEXT_PASS mode=(\d+) reads=1536 replay=1536 reservations=3 seals=3 closes=3 max_service=(\d+) stalls=(\d+) base=([0-9a-f]{16})$',log,re.M)
    base.require(len(rows)==6 and [int(r[0]) for r in rows]==list(range(6)),'complete buffered contexts')
    bases=['00000000000003e8']*2+['a5a5a5a5a5a5a000']*2+['5a5a5a5a5a5a5000']*2
    base.require([r[3] for r in rows]==bases,'full timestamp contexts')
    base.require(all(0<int(r[1])<=5215 and (int(r[0])%2==0 or int(r[2])>=500) for r in rows),'service/stall coverage')
    base.require(log.count('BUFFERED_FFT_PASS contexts=6 seven_stream_words=64512 no_board_or_continuous_claim')==1,'one terminal success')
    old=base.RECOVERY/'destination-actual-parent.LQnQo9ny/run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv'
    base.require(base.sha(old)=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa','numerical authority pin')
    reference={}
    with old.open() as f:
        for row in csv.DictReader(f):
            if row['context']=='0' and row['stream'] in {'inputF','inputI','rawF','rawI','product','privateI','read'}:
                key=(row['stream'],row['job'],row['position'])
                base.require(key not in reference,'duplicate reference')
                reference[key]=(int(row['data'],16),int(row['exponent'],16))
    base.require(len(reference)==10752,'seven-stream reference inventory')
    seen=set()
    with (sim/'buffered_words.csv').open() as f:
        for row in csv.DictReader(f):
            key=(row['stream'],row['job'],row['position']);identity=(row['context'],*key)
            base.require(row['context'] in set(map(str,range(6))) and identity not in seen,'duplicate/unknown output')
            base.require(reference.get(key)==(int(row['data'],16),int(row['exponent'],16)),'numerical mismatch '+str(identity))
            seen.add(identity)
    base.require(len(seen)==64512,'complete output inventory')
    return {'contexts':rows,'numerical_words':len(seen),'csv_sha256':base.sha(sim/'buffered_words.csv'),
            'buffer_integrated':True,'actual_fft':True,'continuous_rx':False,'physical_signoff':False}

def run(mode,prepared,pin,output):
    base.require(mode in {'sim','synth'},'explicit supported mode')
    base.verify(prepared,pin);base.fresh(output)
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    cmd=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
         '-source',str(prepared/'buffered_forward_experiment.tcl'),'-tclargs',mode,str(prepared),pin,str(output)]
    started=time.time();result={'mode':mode,'command':cmd,'prepared_sha':pin,'started':started}
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            p=subprocess.Popen(cmd,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':p.pid,'started':started})+'\n')
            result['returncode']=p.wait()
        base.require(result['returncode']==0,'vendor command failure')
        base.require('STAGED_FFT_EXPERIMENT_FINISHED mode='+mode in (output/'stdout.log').read_text(),'vendor terminal marker')
        base.verify(prepared,pin)
        if mode=='sim':result['audit']=audit(output)
        else:
            base.require((output/'staged_output_synth.dcp').is_file(),'synthesis DCP')
            result['dcp_sha256']=base.sha(output/'staged_output_synth.dcp')
        result['passed']=True
    except Exception as error:
        result.update(passed=False,error=repr(error));raise
    finally:
        result['elapsed_seconds']=time.time()-started
        (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path)
    execute=sub.add_parser('run');execute.add_argument('mode',choices=['sim','synth']);execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
