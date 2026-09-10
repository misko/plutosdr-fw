"""Bind retained native journals to their owner's stopped coarse-IQ evidence.

This retrospective file adapter performs no radio access. It establishes
correspondence within retained commissioning evidence, not native-IQ truth,
new acquisition qualification, or a cryptographic attestation by the radio.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID

from .starlink_glrt_lean_abi import LeanSnapshot
from .starlink_glrt_native_journal import batch, records, review
from .starlink_glrt_native_recording import export_journal

EXCLUDED = '1040007c4a94000211000b009186843ef2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate binding evidence JSON field')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def bind_source(*, journal, recording, owner, protocol, summary, final_snapshot,
                iq_sha256, iq_bytes, episode_index):
    if type(episode_index) is not int or not 0 <= episode_index < 2:
        raise ValueError('binding requires one bounded owner episode')
    owner_data, p, s = map(decode, (owner, protocol, summary))
    exported = decode(recording)
    epoch = exported['epoch']
    if export_journal(journal, epoch=epoch) != exported:
        raise ValueError('recording export differs from the retained journal')
    before = owner_data['before_capture']['remote']
    after = owner_data['after']['remote']
    if before != after:
        raise ValueError('owner radio/boot/firmware or idle state changed')
    serial = before['serial']
    if (serial == EXCLUDED or not serial or owner_data['serial'] != serial
            or before['all_buffer_enable'] != '0' or before['tx_lo_powerdown'] != '1'
            or not re.fullmatch(r'[0-9a-f]{64}', before['fit_sha256'])):
        raise ValueError('owner identity or idle/TX state does not close')
    if str(UUID(before['boot_id'])) != before['boot_id']:
        raise ValueError('invalid owner boot identity')
    if (p['schema'] != 'starlink-glrt-lean-iio-capture/v1' or s['schema'] != p['schema']
            or p['serial'] != serial or p['uri'] != 'ip:'+owner_data['host']
            or p['firmware_version'] != before['firmware']
            or p['base_abi'] != 'GLF1-1.0-upper-only'
            or p['source_rate'] != 60000000 or p['output_rate_hz'] != 2500000
            or type(p['samples']) is not int or not 0 < p['samples'] <= 750000000
            or type(p['visit']) is not int or not 0 < p['visit'] < 2**32):
        raise ValueError('owner and coarse source identity or geometry differ')
    if (owner_data['coarse'] != s or owner_data['coarse_exit'] != 0
            or owner_data['host_spool_export_verified'] is not True
            or s['status'] != 'complete' or s['failures']
            or s['iq_prefix_attested'] is not True or s['lean_iq_closure_attested'] is not True
            or s['event_transport_attested'] is not False
            or iq_bytes != 4*p['samples'] or s['received_bytes'] != iq_bytes
            or not re.fullmatch(r'[0-9a-f]{64}', iq_sha256)
            or s['iq_sha256'] != iq_sha256):
        raise ValueError('retained coarse IQ or owner completion differs')
    for name, digest in [('protocol.json', sha(protocol)),
                         ('final_snapshot.txt', sha(final_snapshot)), ('iq.ci16', iq_sha256)]:
        if s['evidence_sha256'].get(name) != digest:
            raise ValueError('coarse evidence digest differs: '+name)
    source = LeanSnapshot.decode(final_snapshot.decode('ascii'))
    source.require_stopped_iq(expected_visit=p['visit'], expected_rate=60000000)
    origin = source.require_live_prefix(expected_visit=p['visit'], received_samples=p['samples'])
    if source.samples != p['samples'] or s['native_signal_center_at_output_zero'] != origin:
        raise ValueError('coarse native coordinate origin or sample count differs')
    last = origin+24*(p['samples']-1)
    episodes = owner_data['episodes']
    if episode_index >= len(episodes):
        raise ValueError('owner episode missing')
    episode = episodes[episode_index]
    if 'journal_sha256' in episode and episode['journal_sha256'] != sha(journal):
        raise ValueError('journal differs from owner sealed digest')
    checked = review(journal, epoch=epoch)
    entries, _ = records(journal)
    seeds = [batch(e.payload.decode('ascii')) for e in entries if e.kind == 'bootstrap_seed']
    if len(seeds) != 1 or asdict(seeds[0]) != episode['seed'] or seeds[0].epoch != epoch:
        raise ValueError('native seed differs from owner episode')
    runtime = episode['runtime']
    if (type(runtime['result']) is not int or not -5 <= runtime['result'] <= 0
            or runtime['configured'] != checked['drained'].configured
            or runtime['retained_popped'] != len(checked['heads'])
            or runtime['journal_bytes'] != len(journal)
            or episode['controller_stopped_before_coarse_exit'] is not True
            or episode['process_exit'] != (0 if runtime['result'] == 0 else 1)
            or episode['review']['drained'] != asdict(checked['drained'])
            or episode['review']['final'] != asdict(checked['final'])
            or episode['review']['heads'] != len(checked['heads'])
            or episode['review']['supported'] != checked['supported']):
        raise ValueError('owner native runtime or inventory differs')
    if any(not origin <= h.start <= h.start+79199 <= last for h in checked['heads']):
        raise ValueError('native pilot lies outside retained coarse source coordinates')
    return {
        'schema': 'starlink-glrt-native-source-binding/v1',
        'evidence_mode': 'retrospective_retained_owner_correspondence',
        'recording_export_sha256': sha(recording), 'journal_sha256': sha(journal),
        'owner_receipt_sha256': sha(owner), 'collector_protocol_sha256': sha(protocol),
        'collector_summary_sha256': sha(summary), 'collector_final_snapshot_sha256': sha(final_snapshot),
        'coarse_iq_sha256': iq_sha256, 'coarse_iq_bytes': iq_bytes,
        'serial': serial, 'host': owner_data['host'], 'boot_id': before['boot_id'],
        'firmware': before['firmware'], 'fit_sha256': before['fit_sha256'],
        'visit': p['visit'], 'epoch': epoch, 'episode_index': episode_index,
        'source_rate_hz': 60000000, 'output_rate_hz': 2500000,
        'output_samples': p['samples'], 'native_origin': str(origin),
        'native_last_output_center': str(last), 'native_samples_per_output_sample': 24,
        'native_group_delay_samples': 1272, 'runtime_result': runtime['result'],
        'owner_status': owner_data['status'], 'head_count': len(checked['heads']),
        'supported_count': checked['supported'], 'source_correspondence_verified': True,
        'radio_signed_attestation': False, 'acquisition_verified': False,
        'original_native_iq_verified': False, 'physical_precision_qualified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('journal', 'recording', 'owner', 'protocol', 'summary', 'final-snapshot', 'iq', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--episode-index', type=int, required=True)
    args = parser.parse_args()
    with args.iq.open('rb') as stream:
        before = os.fstat(stream.fileno())
        iq_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('coarse IQ changed while hashing')
        iq_bytes = before.st_size
    result = bind_source(**{name: getattr(args, name).read_bytes() for name in
        ('journal', 'recording', 'owner', 'protocol', 'summary', 'final_snapshot')},
        iq_sha256=iq_digest, iq_bytes=iq_bytes, episode_index=args.episode_index)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'output': str(args.output), 'epoch': result['epoch'],
                      'runtime_result': result['runtime_result'], 'head_count': result['head_count']}))


if __name__ == '__main__':
    main()
