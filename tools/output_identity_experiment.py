"""Actual FFT with inverse-output identity staging; no receiver promotion."""
import argparse
import json
from pathlib import Path
import re
import shutil
import buffered_forward_experiment as main
import buffered_forward_auxiliary as aux
import output_identity_transform as transform
from staged_fft_experiment import sha, require, verify
RTL=main.RTL
NEW='starlink_pss_fft_output_identity_impl'
BANK='starlink_pss_output_mailbox_staged_identity.v'
PARENT=Path('/dev/shm/starlink-buffered-forward.mZfKEBtK/prepared-v1')
PIN='f4b18fe4f9a10f4b1ebd69e4546d81b064863ea4894694838e1d912e52f5b860'
OBSERVER=RTL/'output_identity_observer.svh'

def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'buffered reference pin')
    require(transform.transform((RTL/(main.NEW+'.v')).read_text(),transform.TOP_CHANGES)==(RTL/(NEW+'.v')).read_text(),'exact top derivation')
    require(transform.transform((RTL/'starlink_pss_output_reset_receipt.v').read_text(),transform.BANK_CHANGES)==(RTL/BANK).read_text(),'exact output bank derivation')
    main.prepare(path)
    profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==24 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'unchanged 24 parent modules')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+' ',1))
    manifest=json.loads((path/'snapshot.json').read_text())
    sources=[RTL/(NEW+'.v'),RTL/BANK,OBSERVER,Path(__file__).resolve(),main.ROOT/'tools/output_identity_transform.py']
    if auxiliary:sources += [aux.FRAGMENT,main.ROOT/'tools/buffered_forward_auxiliary.py']
    for source in sources:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(main.NEW+' #(')==1,'one actual DUT')
    bench=bench.replace(main.NEW+' #(',NEW+' #(',1)
    if auxiliary:bench=aux.augment(bench,aux.FRAGMENT.read_text())
    require(bench.count('\nendmodule')==bench.count('$fclose(log_file);')==1,'observer insertion')
    bench=bench.replace('\nendmodule','\n'+OBSERVER.read_text()+'\nendmodule',1).replace('$fclose(log_file);','report_output_identity;\n    $fclose(log_file);',1)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+main.NEW+' ')==1,'synthesis top selection')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+main.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment']={'runtime_modules':26,'parent_runtime_unchanged':24,'output_identity':True,'auxiliary':auxiliary}
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,**manifest['experiment']}

def witness(log):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'actual simulation failure')
    rows=re.findall(r'^OUTPUT_IDENTITY_PASS checks=(\d+) words=(\d+) finals=(\d+) first_refills=(\d+) actual_word_exact=1 actual_publication=1$',log,re.M)
    require(len(rows)==1 and log.count('OUTPUT_IDENTITY_PASS')==1,'one output identity witness')
    checks,words,finals,refills=map(int,rows[0])
    require(checks>=10000 and words>=9216 and finals>=18 and refills>=18,'nonvacuous actual word coverage')
    return dict(checks=checks,words=words,finals=finals,first_refills=refills,actual_word_exact=True)

def run(mode,prepared,pin,output):
    profile=json.loads((prepared/'snapshot.json').read_text())['experiment']
    require(mode in {'sim','aux','synth'} and profile['output_identity'] and profile['auxiliary']==(mode=='aux'),'matching experiment mode')
    result=main.run('sim' if mode=='aux' else mode,prepared,pin,output)
    try:
        if mode!='synth':
            log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
            result['output_identity']=witness(log)
            if mode=='aux':result['auxiliary']=aux.witness(log)
    except Exception as error:
        result.update(passed=False,identity_error=repr(error));raise
    finally:
        (output/'identity_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
        if mode=='aux':(output/'auxiliary_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path);prep.add_argument('--auxiliary',action='store_true')
    execute=sub.add_parser('run');execute.add_argument('mode',choices=['sim','aux','synth']);execute.add_argument('prepared',type=Path);execute.add_argument('pin');execute.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))
