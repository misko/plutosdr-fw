"""Archive terminal staged-command experiment evidence with member verification."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
OUT=ROOT/'reports/experiments/20260911-staged-command-evidence.tgz'

def main():
    assert not OUT.exists()
    physical=RECOVERY/'staged-commands-route-parent.jtHNJZ8K'
    assert json.loads((physical/'execution.json').read_text())['vendor_exit']==0
    assert json.loads((physical/'audit.json').read_text())['internal_timing_pass'] is True
    files={};aliases={}
    def add(p):
        name=str(p.relative_to(RECOVERY))
        if p.is_symlink():aliases[name]=str(p.readlink());return
        assert p.is_file() and not any(parent.is_symlink() for parent in p.parents)
        files[name]=p
    def tree(p):
        for item in sorted(p.rglob('*')):
            if item.is_file() or item.is_symlink():add(item)
    for parent in (physical,physical/'run'):
        for p in sorted(parent.iterdir()):
            if p.is_file():add(p)
    tree(physical/'source_snapshot');tree(physical/'pytest')
    tree(RECOVERY/'staged-commands-parent.gTQaWRvw')
    add(RECOVERY/'staged-commands-combined-regression-20260911.xml')
    source=RECOVERY/'destination-actual-worktree-v1'
    for name in ('tests/test_starlink_descriptor_commands.py','tests/test_starlink_descriptor_commands_negative.py',
                 'tools/audit_starlink_descriptor_commands_route.py','docs/starlink-staged-command-results-20260911.md'):
        add(source/name)
    for name in ('starlink_pss_descriptor_commands.v','descriptor_commands_timing_probe.v','route_descriptor_commands.tcl'):
        add(source/'hdl/library/starlink_pss_acquisition/staged_control'/name)
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    pins={n:dict(sha256=sha(p),bytes=p.stat().st_size) for n,p in sorted(files.items())}
    manifest=dict(scope='Staged-command component only; not receiver/board or deployment evidence.',
                  files=pins,symlink_aliases_not_followed=aliases)
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    with tarfile.open(OUT,'x:gz') as archive:
        info=tarfile.TarInfo('evidence-manifest.json');info.size=len(payload);info.mode=0o644
        archive.addfile(info,io.BytesIO(payload))
        for n,p in sorted(files.items()):
            info=archive.gettarinfo(str(p),arcname=n)
            assert info.isfile() and not Path(n).is_absolute() and '..' not in Path(n).parts
            with p.open('rb') as handle:archive.addfile(info,handle)
    assert OUT.stat().st_size<32*1024**2
    assert pins=={n:dict(sha256=sha(p),bytes=p.stat().st_size) for n,p in sorted(files.items())}
    with tarfile.open(OUT,'r:gz') as archive:
        members=archive.getmembers()
        assert len(members)==len(files)+1 and len({m.name for m in members})==len(members)
        for m in members:
            assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
            data=archive.extractfile(m).read()
            if m.name=='evidence-manifest.json':assert data==payload
            else:assert hashlib.sha256(data).hexdigest()==pins[m.name]['sha256'] and len(data)==pins[m.name]['bytes']
    receipt=dict(path=str(OUT),sha256=sha(OUT),bytes=OUT.stat().st_size,regular_files=len(files)+1,
                 every_member_verified=True,source_files_unchanged=True)
    with OUT.with_suffix('.json').open('x') as handle:json.dump(receipt,handle,indent=2)
    print(json.dumps(receipt))

if __name__=='__main__':main()
