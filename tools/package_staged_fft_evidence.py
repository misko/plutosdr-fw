"""Curate and read-back verify staged FFT sources, numerical evidence and route."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=ROOT.parent

def digest(data):return hashlib.sha256(data).hexdigest()

def package(output,campaign='output'):
    if output.exists():raise ValueError('no artifact overwrite')
    if campaign not in {'output','handover'}:raise ValueError('explicit campaign required')
    final_version=5 if campaign=='output' else 4
    sources={}
    def add(name,path):
        if name in sources or path.is_symlink() or not path.is_file():raise ValueError('invalid artifact member '+name)
        sources[name]=path
    for version in range(1,final_version+1):
        folder=RECOVERY/f'staged-{campaign}-prepared-v{version}'
        for p in sorted(folder.iterdir()):
            if p.is_file():add(f'prepared-v{version}/{p.name}',p)
        folder=RECOVERY/f'staged-{campaign}-actual-v{version}'
        for name in ['command.json','process.json','outcome.json','stdout.log','vivado.log','generated_fft.sha256']:
            if (folder/name).is_file():add(f'actual-v{version}/{name}',folder/name)
        sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
        for name in ['simulate.log','staged_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
            if (sim/name).is_file():add(f'actual-v{version}/sim/{name}',sim/name)
    for version in ([final_version] if campaign=='output' else [2,4]):
        for kind in ['synth','route']:
            folder=RECOVERY/f'staged-{campaign}-{kind}-v{version}'
            prefix=kind if campaign=='output' else f'{kind}-v{version}'
            for p in sorted(folder.iterdir()):
                if p.is_file():add(f'{prefix}/{p.name}',p)
            if kind=='route':
                for p in sorted((folder/'route').iterdir()):
                    if p.is_file():add(f'{prefix}/reports/{p.name}',p)
    for name in ['staged-mailbox-parent.Tc4Uke1L','staged-adapter-parent.qSJUuasQ']:
        folder=RECOVERY/name
        for p in sorted(folder.rglob('*')):
            if p.is_file() and (p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}):
                add('tests/'+name+'/'+str(p.relative_to(folder)),p)
    if campaign=='handover':
        for name in ['staged-handover-tests-v1','staged-handover-regression-v2','staged-handover-regression-v4',
                     'staged-handover-route-audit-tests-v4']:
            folder=RECOVERY/name
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}:
                    add('tests/'+name+'/'+str(p.relative_to(folder)),p)
            add('tests/'+name+'.xml',RECOVERY/(name+'.xml'))
    for p in sorted((ROOT/'tests').glob('test_starlink*')):
        if p.name in {'test_starlink_descriptor_commands_mailbox.py','test_starlink_staged_mailbox_control.py',
                      'test_starlink_staged_fft_lint.py','test_starlink_staged_fft_audit.py','test_starlink_handover_audit.py',
                      'test_starlink_route_report_audit.py'}:
            add('current/tests/'+p.name,p)
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl','route_starlink_staged_fft.py','audit_staged_fft_route.py','package_staged_fft_evidence.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    add('current/docs/starlink-staged-output-integration-20260911.md',ROOT/'docs/starlink-staged-output-integration-20260911.md')
    if campaign=='handover':
        add('current/docs/starlink-staged-handover-20260911.md',ROOT/'docs/starlink-staged-handover-20260911.md')
        add('reference/actual_words.csv',RECOVERY/'destination-actual-parent.LQnQo9ny/run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv')
    manifest={name:{'source':str(path),'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size} for name,path in sources.items()}
    def insert(archive,name,data):
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
    with tarfile.open(output,'w:gz') as archive:
        insert(archive,'manifest.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())
        for name,path in sorted(sources.items()):
            data=path.read_bytes()
            if digest(data)!=manifest[name]['sha256']:raise ValueError('source changed '+name)
            insert(archive,name,data)
    with tarfile.open(output,'r:gz') as archive:
        members=archive.getmembers()
        if {m.name for m in members}!=set(manifest)|{'manifest.json'} or len(members)!=len(manifest)+1:
            raise ValueError('archive member inventory')
        if not all(m.isfile() for m in members):raise ValueError('non-regular archive member')
        if json.load(archive.extractfile('manifest.json'))!=manifest:raise ValueError('manifest read-back')
        for name,value in manifest.items():
            data=archive.extractfile(name).read()
            if len(data)!=value['bytes'] or digest(data)!=value['sha256']:raise ValueError('archive read-back '+name)
    receipt={'path':str(output),'bytes':output.stat().st_size,'sha256':digest(output.read_bytes()),
             'members':len(manifest)+1,'all_members_verified':True,'full_receiver_or_deployment_claim':False}
    receipt_path=output.with_suffix('.json')
    if receipt_path.exists():raise ValueError('no receipt overwrite')
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--campaign',choices=['output','handover'],default='output')
    args=parser.parse_args();print(json.dumps(package(args.output,args.campaign),indent=2))
