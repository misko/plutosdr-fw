"""Preserve RAM-backed receipt experiment with explicit pinned parent dependency."""
import argparse
import json
from pathlib import Path

from package_staged_fft_evidence import write_verified_archive
from staged_fft_experiment import ROOT, audit_forwardreceipt, require, sha, verify
from route_starlink_staged_fft import verify_ack_auxiliary


def package(artifacts,output):
    require(artifacts.is_absolute() and artifacts.is_dir(),'absolute artifact root required')
    main=artifacts/'sim-v1';aux=artifacts/'ack-v1';prepared=artifacts/'prepared-v1'
    synthesis=artifacts/'synth-v1';route=artifacts/'route-v1'
    expected='0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b'
    verify(prepared,expected)
    for folder,mode in [(main,'sim'),(aux,'ack'),(synthesis,'synth')]:
        outcome=json.loads((folder/'outcome.json').read_text())
        require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and
                'error' not in outcome and outcome['mode']==mode and outcome['prepared_sha']==expected and
                outcome['command'][-3]==str(prepared),'terminal same-source campaign required')
    audited=audit_forwardreceipt(main)
    require(json.dumps(audited,sort_keys=True)==json.dumps(json.loads((main/'outcome.json').read_text())['audit'],sort_keys=True),
            'main re-audit mismatch')
    verify_ack_auxiliary(aux,expected,prepared)
    outcome=json.loads((route/'outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,
            'terminal route required, not timing-pass claim')
    require(all(sha(Path(p))==value for p,value in outcome['before'].items()),'route source receipts changed')
    require(sha(route/'route/retained_output_routed.dcp')==outcome['routed_dcp_sha'],'routed checkpoint changed')
    require((route/'audit.json').is_file(),'independent route audit required')
    sources={}
    def add(name,path):
        require(name not in sources,'duplicate member');sources[name]=path
    def tree(prefix,folder,suffixes=None):
        require(folder.is_dir(),'required folder '+str(folder))
        for path in sorted(folder.rglob('*')):
            if not path.is_symlink() and path.is_file() and (suffixes is None or path.suffix in suffixes):
                add(prefix+'/'+str(path.relative_to(folder)),path)
    tree('prepared',prepared)
    for label,folder in [('main',main),('auxiliary',aux)]:
        for name in ['command.json','process.json','outcome.json','stdout.log','vivado.log','generated_fft.sha256']:
            add(label+'/'+name,folder/name)
        for name in ['simulate.log','staged_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
            add(label+'/sim/'+name,folder/'project/staged_fft.sim/sim_1/behav/xsim'/name)
    for label,folder in [('synthesis',synthesis),('route',route)]:
        for path in sorted(folder.iterdir()):
            if path.is_file():add(label+'/'+path.name,path)
    tree('route/reports',route/'route')
    for name in ['component-v1','component-v2','component-v3','regression-v1','audit-v1','packaging-v1']:
        # V1 stopped at collection before pytest needed a scratch directory.
        if name!='component-v1' or (artifacts/name).is_dir():
            tree('tests/'+name,artifacts/name,{'.py','.sv','.v','.log','.xml','.json','.txt','.tcl','.xdc'})
        add('tests/'+name+'.xml',artifacts/(name+'.xml'))
    tree('current/tests',ROOT/'tests',{'.py'})
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl','route_starlink_staged_fft.py',
                 'audit_staged_fft_route.py','package_staged_fft_evidence.py','package_forward_receipt_evidence.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    add('current/docs/forward-receipt.md',ROOT/'docs/starlink-forward-completion-receipt-20260911.md')
    parent=ROOT.parent/'staged-ackcombined-prepared-v1'
    for name in ['SHA256SUMS','starlink_pss_fft_staged_output_impl.v','tb_fft_staged_output.sv']:
        add('reference/ackcombined/'+name,parent/name)
    # Historical regression fixtures remain a pinned, already-pushed dependency;
    # do not duplicate that 16 MB archive inside each subsequent experiment.
    receipt=Path('/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/reports/experiments/20260911-staged-ackcombined-evidence.json')
    parent_receipt=json.loads(receipt.read_text())
    require(parent_receipt['sha256']=='afbc76a605af0b9c16bda45e46cef498eac793b8dbb342023f39d6bccd71fdd9',
            'pinned historical fixture dependency')
    add('reference/parent-archive-receipt.json',receipt)
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('artifacts',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(package(args.artifacts,args.output),indent=2))
