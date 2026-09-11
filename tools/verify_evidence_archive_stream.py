"""Read-only sequential verification of a manifest-bearing evidence archive."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

def digest_file(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):result.update(block)
    return result.hexdigest()

def verify(path):
    before=digest_file(path);seen=set()
    with gzip.open(path,'rb') as compressed:
        with tarfile.open(fileobj=compressed,mode='r|') as archive:
            first=archive.next()
            if first is None or first.name!='manifest.json' or not first.isfile():
                raise ValueError('first member must be regular manifest')
            manifest=json.load(archive.extractfile(first))
            if not isinstance(manifest,dict):raise ValueError('manifest object required')
            for name in manifest:
                if name=='manifest.json' or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                    raise ValueError('unsafe manifest name')
            # Iteration yields the first cached header too; consume by next().
            while True:
                member=archive.next()
                if member is None:break
                if not member.isfile() or member.name in seen or member.name not in manifest:
                    raise ValueError('unexpected, duplicate or nonregular member')
                expected=manifest[member.name]
                if member.size!=expected['bytes']:raise ValueError('member size mismatch')
                value=hashlib.sha256();count=0
                with archive.extractfile(member) as payload:
                    for block in iter(lambda:payload.read(1024*1024),b''):
                        count+=len(block);value.update(block)
                if count!=expected['bytes'] or value.hexdigest()!=expected['sha256']:
                    raise ValueError('member digest mismatch')
                seen.add(member.name)
        # Read the gzip trailer as well, checking its CRC without random seeks.
        while compressed.read(1024*1024):pass
    if seen!=set(manifest):raise ValueError('missing members')
    if digest_file(path)!=before:raise ValueError('archive changed during verification')
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':before,
            'members':len(seen)+1,'all_members_verified':True,
            'full_receiver_or_deployment_claim':False,
            'verification':'sequential payload SHA256, inventory, regular files, gzip CRC, stable archive SHA256',
            'verifier_sha256':digest_file(Path(__file__).resolve())}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path)
    parser.add_argument('--receipt',type=Path);args=parser.parse_args()
    result=verify(args.archive)
    if args.receipt:
        with args.receipt.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
