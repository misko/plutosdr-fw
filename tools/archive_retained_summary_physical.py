#!/usr/bin/env python3
"""Lossless source-specific terminal evidence package; no vendor invocation.

All regular files from the selected terminal roots are retained. Symlinks are
recorded separately, not followed or placed in the portable archive. Verification
reads committed Git blobs, not the working-tree archive or extraction targets.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
ARCHIVE='reports/experiments/20260910-retained-summary-physical-evidence.tgz'
INVENTORY='reports/experiments/20260910-retained-summary-physical-evidence.json'
DIRECTORIES={
 'prepared':'retained-summary-synthesis-prepared-v1',
 'synthesis':'retained-summary-synth-parent.39BysdkS',
 'route':'retained-summary-route-parent.qxOkezJN',
 'offline_attempts/v1':'retained-summary-physical-offline-v1.u9eEozRe',
 'offline_attempts/v2':'retained-summary-physical-offline-v2.hhFvYRul',
 'offline_attempts/v3':'retained-summary-physical-offline-v3.AYQexGzb',
 'binding_tests':'retained-summary-physical-binding-v1.n3oNRuLP',
}
ACTUAL=RECOVERY/'retained-summary-actual-parent.XYAbt6Np'
ACTUAL_FILES=(
 'owner.py','execution.json','outcome.json','command.json','stdout.log',
 'before.json','after.json','copied-after.json','result-check.json','vivado.log','vivado.jou',
 'run/results.json','run/run_outcome.txt','run/inputs/manifest.json',
 'run/project/retained_output_actual.sim/sim_1/behav/xsim/simulate.log',
 'run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv',
 'run/project/retained_output_actual.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd',
)
DCP={
 'synthesis/synthesis/retained_output_synth.dcp':'2348ac8205738a178e11d3f51c8d5b46199ab8548a57573bae0edd785f3f5eb5',
 'route/route/retained_output_routed.dcp':'83d268fff699dae1ca3fca8bd1debddd04562590a284f982e05844bdb1059d38',
}
FAILED=RECOVERY/'retained-summary-publication-v1.rAkar9Ri'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inputs():
    files={};links=[]
    def record(name,path):
        require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                'unsafe archive name')
        require(name not in files,'duplicate selected member')
        if path.is_symlink():
            links.append({'name':name,'source':str(path),'target':os.readlink(path)})
        else:
            require(stat.S_ISREG(path.stat().st_mode),'nonregular selected input')
            files[name]={'source':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}
    for prefix,directory in DIRECTORIES.items():
        source=RECOVERY/directory
        require(source.is_dir() and not source.is_symlink(),'missing/aliased input root')
        for parent,dirs,names in os.walk(source,followlinks=False):
            for child in dirs[:]:
                path=Path(parent)/child
                if path.is_symlink():
                    record(prefix+'/'+path.relative_to(source).as_posix(),path);dirs.remove(child)
            for child in names:
                path=Path(parent)/child
                record(prefix+'/'+path.relative_to(source).as_posix(),path)
    for name in ACTUAL_FILES:
        record('actual_authority/'+name,ACTUAL/name)
    for name in ('package.log','archive_retained_summary_physical.failed-v1.py'):
        record('packaging_failure/'+name,FAILED/name)
    return dict(sorted(files.items())),sorted(links,key=lambda x:x['name'])


def verify_bytes(raw,inventory):
    require(len(raw)==inventory['archive_bytes'] and hashlib.sha256(raw).hexdigest()==inventory['archive_sha256'],
            'whole archive identity')
    names=set()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for member in archive:
            require(member.isfile() and not member.islnk() and not member.issym(),'nonregular archive member')
            require(member.name not in names,'duplicate archive member')
            path=PurePosixPath(member.name)
            require(not path.is_absolute() and '..' not in path.parts and str(path)==member.name,'unsafe archive path')
            require(member.name in inventory['members'],'extra archive member')
            expected=inventory['members'][member.name]
            stream=archive.extractfile(member)
            require(stream is not None and member.size==expected['bytes'],'member byte count')
            require(hashlib.file_digest(stream,'sha256').hexdigest()==expected['sha256'],'member hash '+member.name)
            names.add(member.name)
    require(names==set(inventory['members']),'missing archive member')
    require(all(inventory['members'][name]['sha256']==value for name,value in DCP.items()),'DCP pins')
    return len(names)


def package(output_dir):
    output=Path(output_dir)
    require(output.is_absolute() and output.is_dir() and not output.is_symlink(),'explicit output directory')
    archive=output/Path(ARCHIVE).name;receipt=ROOT/INVENTORY
    require(not archive.exists() and not receipt.exists(),'nonoverwrite package')
    before,links=inputs()
    require(all(before[name]['sha256']==value for name,value in DCP.items()),'source DCP identity')
    require(before['prepared/SHA256SUMS']['sha256']=='1760f6d51c2438bd22ff12dfeccb18aa83a528b54ac0b71992efa27c32160a2b',
            'root prepared inventory identity')
    with archive.open('xb') as destination:
        with gzip.GzipFile(filename='',fileobj=destination,mode='wb',mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT,dereference=True) as tar:
                for name,row in before.items():
                    path=Path(row['source']);info=tar.gettarinfo(str(path),arcname=name)
                    info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                    with path.open('rb') as source:tar.addfile(info,source)
    after,after_links=inputs()
    require(before==after and links==after_links,'original inputs changed during packaging')
    require(archive.stat().st_size <= 40*1024*1024,'archive exceeds 40MiB; preserve original and use portable parts')
    result={'kind':'terminal-retained-summary-physical-evidence-v1','source_before_after_equal':True,
        'archive':ARCHIVE,'archive_bytes':archive.stat().st_size,'archive_sha256':digest(archive),
        'construction_archive':str(archive),'archive_storage':'tracked archive copied through dedicated recovery worktree',
        'packager_sha256':digest(Path(__file__)),'members':before,'omitted_symlinks':links,
        'failed_partial_archive':{'path':str(FAILED/'partial-failed-v1.tgz'),
            'sha256':digest(FAILED/'partial-failed-v1.tgz'),
            'bytes':(FAILED/'partial-failed-v1.tgz').stat().st_size,
            'classification':'incomplete archive, original process 70376 exit 1, disk quota exceeded'},
        'actual_WDB':'Not duplicated; actual source/owner/CSV/log authority retained here. Original actual run stays intact.',
        'physical_timing_pass':False,'runtime_edited':False,'vendor_invoked_by_packager':False}
    count=verify_bytes(archive.read_bytes(),result)
    with receipt.open('x') as output:json.dump(result,output,indent=2,sort_keys=True);output.write('\n')
    print(json.dumps({'files':count,'archive_bytes':result['archive_bytes'],'archive_sha256':result['archive_sha256'],
        'omitted_symlinks':len(links),'source_before_after_equal':True}))


def verify_git(revision):
    require(bool(revision) and not revision.startswith('-'),'invalid revision')
    def blob(name):return subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
    inventory=json.loads(blob(INVENTORY))
    require(hashlib.sha256(blob('tools/archive_retained_summary_physical.py')).hexdigest()==inventory['packager_sha256'],
            'committed packaging source identity')
    count=verify_bytes(blob(ARCHIVE),inventory)
    print(json.dumps({'revision':revision,'git_object_members_verified':count,
                     'verification_scope':'committed inventory, packager, and every archived member',
                     'archive_stored_in_git':True,
                     'archive_sha256':inventory['archive_sha256'],'physical_timing_pass':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-git')
    parser.add_argument('--output-dir')
    args=parser.parse_args()
    if args.verify_git:verify_git(args.verify_git)
    else:
        require(args.output_dir is not None,'--output-dir is required; no /tmp archive construction')
        package(args.output_dir)
