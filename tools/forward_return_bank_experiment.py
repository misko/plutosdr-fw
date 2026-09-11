"""Frozen actual-FFT observer experiment; no receiver control integration claim."""
import argparse
import json
from pathlib import Path
import re
import shutil
import staged_fft_experiment as base

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BANK='starlink_pss_forward_return_bank.v'
FRAGMENT='forward_return_actual_observer.svh'
PARENT=Path('/dev/shm/starlink-scalar-fault.xuB1HWdl/prepared-v1')
HEADER='module tb #(parameter integer ACK_ONLY=0);\n'
REPORT='      report_sticky_fault; // DISTRIBUTED STICKY FAULT REPORT\n'

def prepare(path):
    base.require(base.sha(PARENT/'SHA256SUMS')=='b7a4a2bc1d143a8d30d0207261de5a73dfc989550c30d65082bfc63f8e57abeb','parent pin')
    base.prepare(path)
    original=(path/'tb_fft_staged_output.sv').read_text()
    base.require(original==(PARENT/'tb_fft_staged_output.sv').read_text(),'unchanged actual bench')
    base.require(original.count(HEADER)==original.count(REPORT)==1,'exact observer insertion sites')
    observer=(RTL/FRAGMENT).read_text()
    # Place instances after the original signal declarations; inserting an
    # instance before the reg clock declaration creates an implicit wire.
    bench=original.replace('\nendmodule','\n'+observer+'\nendmodule',1).replace(REPORT,REPORT+'      report_forward_return_observer;\n',1)
    (path/'tb_fft_staged_output.sv').write_text(bench)
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    base.require(len(names)==22 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'all original runtime unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+BANK+' ',1))
    manifest=json.loads((path/'snapshot.json').read_text())
    for source in [RTL/BANK,RTL/FRAGMENT,Path(__file__).resolve()]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=base.sha(source)
    manifest['files']={p.name:base.sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':base.sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=base.sha(path/'SHA256SUMS');base.verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,'runtime_modules':23,'original_runtime_unchanged':True,'observer_only':True}

def witness(text):
    rows=re.findall(r'^FORWARD_RETURN_ACTUAL_PASS blocks=(\d+) words=(\d+) reservations=(\d+) seals=(\d+) stalls=(\d+) runtime_unchanged=1 observer_only=1$',text,re.M)
    base.require(len(rows)==1 and text.count('FORWARD_RETURN_ACTUAL_PASS')==1,'one complete observer witness')
    blocks,words,reservations,seals,stalls=map(int,rows[0])
    base.require(18<=blocks<=seals<=reservations and words>=blocks*512 and stalls>=100,'nonvacuous actual observer coverage')
    return dict(blocks=blocks,words=words,reservations=reservations,seals=seals,stalls=stalls,observer_only=True,receiver_integration=False)

def run(mode,prepared,pin,output):
    base.require(mode in {'sim','ack'},'observer is simulation-only; separately qualify actual integration')
    result=base.run(mode,prepared,pin,output)
    evidence=witness((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    (output/'forward_return_observer.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return {'baseline':result,'observer':evidence}

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path)
    execute=sub.add_parser('run');execute.add_argument('mode',choices=['sim','ack']);execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
