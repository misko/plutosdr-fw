"""Curated terminal experiment evidence; excludes vendor caches and live devices."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
OUT=ROOT/'reports/experiments/20260911-destination-and-slots-evidence.tgz'

def main():
    assert not OUT.exists()
    files={};aliases={}
    def add(path):
        name=str(path.relative_to(RECOVERY))
        if path.is_symlink():
            aliases[name]=str(path.readlink());return
        assert path.is_file() and not any(p.is_symlink() for p in path.parents)
        files[name]=path
    def tree(path):
        for item in sorted(path.rglob('*')):
            if item.is_file() or item.is_symlink():add(item)
    def top(path):
        for item in sorted(path.iterdir()):
            if item.is_file() and item.suffix in ('.py','.json','.log','.txt','.jou','.rpt','.xdc','.tcl','.dcp'):
                add(item)
    for name in ('retained-summary-actual-prelaunch-v1','destination-actual-prelaunch-parent-v1',
                 'destination-synthesis-prepared-parent-v1'):
        tree(RECOVERY/name)
    actual=RECOVERY/'destination-actual-parent.LQnQo9ny'
    assert json.loads((actual/'outcome.json').read_text())['functional_accepted'] is True
    top(actual);top(actual/'run')
    sim=actual/'run/project/retained_output_actual.sim/sim_1/behav/xsim'
    add(sim/'simulate.log');add(sim/'actual_words.csv')
    add(actual/'run/project/retained_output_actual.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd')
    prior=RECOVERY/'retained-summary-actual-parent.XYAbt6Np'
    add(prior/'run/results.json')
    add(prior/'run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv')
    for name,sub in [('destination-synth-parent.G1XLB1ik','synthesis'),
                     ('destination-route-parent.ZwqAjdhv','route'),
                     ('staged-slots-route-parent.0wh1bZVH','run'),
                     ('staged-slots-route-v2-parent.BCFXBat7','run')]:
        parent=RECOVERY/name
        execution=json.loads((parent/'execution.json').read_text())
        assert execution['vendor_exit']==0 and execution['timed_out'] is False
        top(parent);top(parent/sub)
        if (parent/'source_snapshot').exists():tree(parent/'source_snapshot')
        if (parent/'results.xml').exists():add(parent/'results.xml')
        if (parent/'pytest').exists():tree(parent/'pytest')
    tree(RECOVERY/'staged-slots-parent.quULATYQ')
    gate=RECOVERY/'destination-actual-prepare-parent.vbfomY3U'
    top(gate);top(gate/'final');tree(gate/'final/source_snapshot');add(gate/'final/results.xml')
    gate=RECOVERY/'destination-physical-prep-parent.NJlhw5AK'
    top(gate);tree(gate/'source_snapshot');add(gate/'results.xml')
    source=RECOVERY/'destination-actual-worktree-v1'
    for name in ('tests/test_starlink_descriptor_slots.py','tools/audit_starlink_descriptor_slots_route.py',
                 'docs/starlink-staged-control-contract-20260911.md','docs/starlink-retained-destination-physical-results-20260911.md'):
        add(source/name)
    for name in ('starlink_pss_descriptor_slots.v','descriptor_slots_timing_probe.v','route_descriptor_slots.tcl'):
        add(source/'hdl/library/starlink_pss_acquisition/staged_control'/name)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    pins={name:dict(sha256=sha(path),bytes=path.stat().st_size) for name,path in sorted(files.items())}
    manifest=dict(scope='Curated source snapshots, tests, complete numerical comparison, physical reports and checkpoints; not a deployable package.',
                  omitted='Vendor build caches, most inherited mock fixtures and complete receiver/RF evidence are not included.',
                  files=pins,symlink_aliases_not_followed=aliases)
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    with tarfile.open(OUT,'x:gz') as archive:
        info=tarfile.TarInfo('evidence-manifest.json');info.size=len(payload);info.mode=0o644
        archive.addfile(info,io.BytesIO(payload))
        for name,path in sorted(files.items()):
            info=archive.gettarinfo(str(path),arcname=name)
            assert info.isfile() and not Path(name).is_absolute() and '..' not in Path(name).parts
            with path.open('rb') as handle:archive.addfile(info,handle)
    assert OUT.stat().st_size<40*1024**2
    assert pins=={name:dict(sha256=sha(path),bytes=path.stat().st_size) for name,path in sorted(files.items())}
    with tarfile.open(OUT,'r:gz') as archive:
        members=archive.getmembers()
        assert len(members)==len(files)+1 and len({m.name for m in members})==len(members)
        for member in members:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            data=archive.extractfile(member).read()
            if member.name=='evidence-manifest.json':assert data==payload
            else:assert hashlib.sha256(data).hexdigest()==pins[member.name]['sha256'] and len(data)==pins[member.name]['bytes']
    receipt=dict(path=str(OUT),sha256=sha(OUT),bytes=OUT.stat().st_size,regular_files=len(files)+1,
                 every_member_verified=True,source_files_unchanged=True)
    with OUT.with_suffix('.json').open('x') as handle:json.dump(receipt,handle,indent=2)
    print(json.dumps(receipt))

if __name__=='__main__':main()
