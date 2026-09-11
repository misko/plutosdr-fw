"""Archive the two bounded physical runs and their exact retained references."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from probe_staged_postroute import ROOT, PARENTS, audit, constraints, recipe, sha, summarize, require

def package(output):
    require(output.is_absolute() and not output.exists() and
            not output.with_suffix('.json').exists(),'new absolute archive/receipt required')
    sources={}
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'regular unique member')
        sources[name]=path
    for candidate,expected in PARENTS.items():
        parent=ROOT.parent/f'staged-{candidate}-route-v1'
        run=ROOT.parent/f'staged-{candidate}-postroute-v1'
        result=json.loads((run/'outcome.json').read_text())
        require(result.get('returncode')==0 and 'error' not in result and
                result.get('sources_unchanged') is True,'terminal source-bound run')
        require(all(sha(Path(p))==value for p,value in result['before'].items()),'run input changed')
        require(audit(parent,record=False)==result['parent_audit'],'parent re-audit changed')
        require(sha(parent/'route/retained_output_routed.dcp')==expected,'parent checkpoint changed')
        require(sha(run/'route/retained_output_routed.dcp')==result['routed_dcp_sha256'],'result checkpoint changed')
        generated=recipe((ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl').read_text())
        require((run/'route.tcl').read_text()==generated and
                (run/'route/probe.tcl').read_text()==generated,'physical recipe changed')
        require(constraints(run/'route/inherited_constraints.xdc')==
                constraints(parent/'route/inherited_constraints.xdc'),'constraints changed')
        observed=summarize(run/'route');observed['source_and_checkpoint_verified']=True
        require(observed==result['audit'],'physical reports changed')
        for kind,folder in [('postroute',run),('parent-route',parent),
                            ('prepared',ROOT.parent/f'staged-{candidate}-prepared-v1')]:
            for p in sorted(folder.rglob('*')):
                if p.is_file():add(f'{candidate}/{kind}/{p.relative_to(folder)}',p)
        actual=ROOT.parent/f'staged-{candidate}-actual-v1'
        for name in ['outcome.json','command.json','generated_fft.sha256',
                     'project/staged_fft.sim/sim_1/behav/xsim/simulate.log',
                     'project/staged_fft.sim/sim_1/behav/xsim/staged_words.csv']:
            add(f'{candidate}/actual/{name}',actual/name)
    for name in ['tools/probe_staged_postroute.py','tools/package_staged_postroute.py',
                 'tools/audit_staged_fft_route.py','tools/staged_fft_experiment.py',
                 'tools/retained_destination_synthesis/route_retained_output.tcl',
                 'tests/test_starlink_postroute_probe.py','tests/test_starlink_route_report_audit.py',
                 'docs/starlink-postroute-physical-20260911.md']:
        add('current/'+name,ROOT/name)
    add('tests/staged-postroute-tests-v1.xml',ROOT.parent/'staged-postroute-tests-v1.xml')
    manifest={name:{'sha256':sha(p),'bytes':p.stat().st_size} for name,p in sources.items()}
    def insert(archive,name,data):
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o644
        archive.addfile(item,io.BytesIO(data))
    with tarfile.open(output,'x:gz') as archive:
        insert(archive,'manifest.json',json.dumps(manifest,sort_keys=True,indent=2).encode())
        for name,p in sorted(sources.items()):
            data=p.read_bytes()
            require(hashlib.sha256(data).hexdigest()==manifest[name]['sha256'],'source changed during archive')
            insert(archive,name,data)
    with tarfile.open(output,'r:gz') as archive:
        members=archive.getmembers()
        require(len(members)==len(manifest)+1 and
                {m.name for m in members}==set(manifest)|{'manifest.json'} and
                all(m.isfile() for m in members),'exact regular inventory')
        require(json.load(archive.extractfile('manifest.json'))==manifest,'manifest readback')
        for name,info in manifest.items():
            data=archive.extractfile(name).read()
            require(len(data)==info['bytes'] and hashlib.sha256(data).hexdigest()==info['sha256'],
                    'member readback failed')
    receipt={'path':str(output),'bytes':output.stat().st_size,'sha256':sha(output),
             'members':len(manifest)+1,'all_members_verified':True,'deployment_eligible':False}
    output.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    print(json.dumps(package(parser.parse_args().output),indent=2))
