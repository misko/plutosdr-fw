"""Publish a closed native episode and its source evidence through one manifest.

Only local retained files are read; no radio access or RF restart is possible.
The final manifest is visible only after every payload has been fsynced.
Publication completion is distinct from the preserved radio runtime outcome.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from .starlink_glrt_native_binding import bind_source, decode, hash_stable_iq, sha
from .starlink_glrt_native_recording import export_journal


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def read_bounded(path, maximum):
    with path.open('rb') as stream:
        data = stream.read(maximum+1)
    if len(data) > maximum:
        raise ValueError('native publication input exceeds its bound')
    return data


def write_payload(path, data):
    with path.open('xb') as stream:
        # These are the explicitly published application evidence, not private
        # radio credentials. The read-only API runs as a different local user.
        os.fchmod(stream.fileno(), 0o644)
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_episode(*, journal: Path, owner: Path, protocol: Path, summary: Path,
                    final_snapshot: Path, iq: Path, episode_index: int, output: Path) -> dict:
    if type(episode_index) is not int or not 0 <= episode_index < 2:
        raise ValueError('publication requires one bounded native owner episode')
    inputs = {name: read_bounded(path, maximum) for name, path, maximum in (
        ('journal',journal,128*1024*1024), ('owner',owner,4*1024*1024),
        ('protocol',protocol,1024*1024), ('summary',summary,1024*1024),
        ('final_snapshot',final_snapshot,16384))}
    owner_data = decode(inputs['owner'])
    if episode_index >= len(owner_data['episodes']):
        raise ValueError('native owner episode missing')
    epoch = owner_data['episodes'][episode_index]['seed']['epoch']
    recording = encoded(export_journal(inputs['journal'],epoch=epoch))
    iq_digest, iq_bytes = hash_stable_iq(iq)
    binding = bind_source(**inputs, recording=recording, iq_sha256=iq_digest,
                          iq_bytes=iq_bytes, episode_index=episode_index)
    payloads = {'journal.glrj':inputs['journal'], 'recording.json':recording,
        'source-binding.json':encoded(binding), 'owner-receipt.json':inputs['owner'],
        'coarse-protocol.json':inputs['protocol'], 'coarse-summary.json':inputs['summary'],
        'coarse-final-snapshot.txt':inputs['final_snapshot']}
    manifest = {
        'schema':'starlink-glrt-native-recording-bundle/v1', 'publication_status':'complete',
        'serial':binding['serial'], 'boot_id':binding['boot_id'], 'fit_sha256':binding['fit_sha256'],
        'visit':binding['visit'], 'epoch':epoch, 'episode_index':episode_index,
        'runtime_result':binding['runtime_result'], 'owner_status':binding['owner_status'],
        'head_count':binding['head_count'], 'supported_count':binding['supported_count'],
        'evidence_mode':binding['evidence_mode'],
        'coarse_iq':{'sha256':iq_digest,'bytes':iq_bytes,'embedded':False},
        'artifacts':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in payloads.items()},
        'acquisition_verified':False, 'original_native_iq_verified':False,
        'physical_precision_qualified':False,
    }
    # Validate everything before creating output. An existing/partial output
    # cannot be silently resumed or mistaken for this publication.
    output.mkdir(exist_ok=False)
    output.chmod(0o755)
    sync_directory(output.parent)
    for name, data in payloads.items():
        write_payload(output/name, data)
    sync_directory(output)
    fd, temporary = tempfile.mkstemp(prefix='.manifest-',dir=output)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
        os.link(temporary, output/'manifest.json')
    finally:
        os.unlink(temporary)
    sync_directory(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('journal','owner','protocol','summary','final-snapshot','iq','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--episode-index',type=int,required=True)
    args = parser.parse_args()
    manifest = publish_episode(**vars(args))
    print(json.dumps({'manifest':str(args.output/'manifest.json'),
        'manifest_sha256':sha(encoded(manifest)), 'publication_status':manifest['publication_status'],
        'runtime_result':manifest['runtime_result'],'head_count':manifest['head_count']}))


if __name__ == '__main__':
    main()
