"""Retrospective owner/source binding with actual C journals and synthetic metadata."""
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal, retained
from tools.starlink_glrt_native_binding import bind_source, sha
from tools.starlink_glrt_native_journal import batch, records, review
from tools.starlink_glrt_native_recording import export_journal


def encoded(value):
    return json.dumps(value, allow_nan=False).encode()


def evidence(controller, pilot_words):
    radio = Radio(controller, pilot_words, frames=16)
    assert radio.run() == 0
    data = journal(radio)
    checked = review(data, epoch=3)
    entries, _ = records(data)
    # The radio executable, above the C controller fixture, retains this seed
    # before the controller writes its journal records.
    seed = batch(next(e.payload.decode().split(maxsplit=2)[2]
                      for e in entries if e.kind == 'descriptor'))
    data = b'GLRJ1\n'+retained('bootstrap_seed', seed.encode().encode())+data[6:]
    samples, visit = 100000, 1105016
    first = radio.origin-radio.origin%24
    words = [0]*64
    for offset, value in [(0,first), (2,first+24*(samples-1)), (4,samples), (6,samples),
                          (12,samples), (14,samples)]:
        words[offset:offset+2] = [value % 2**32, value >> 32]
    words[19], words[20], words[62], words[63] = 24, visit, 60000000, 1272
    words[21] = 2
    snapshot = ('GLF1 00010000 60000000 2500000 1 0 60000000 0 0 0 0 0 0 0 '
                +' '.join(f'{w:08x}' for w in words)+'\n').encode()
    p = dict(schema='starlink-glrt-lean-iio-capture/v1', serial='test-radio',
        uri='ip:192.168.1.14', firmware_version='test-native', base_abi='GLF1-1.0-upper-only',
        source_rate=60000000, output_rate_hz=2500000, samples=samples, visit=visit)
    iq = bytes(4*samples)
    s = dict(schema=p['schema'], status='complete', failures=[], iq_prefix_attested=True,
        lean_iq_closure_attested=True, event_transport_attested=False, received_bytes=len(iq),
        iq_sha256=sha(iq), native_signal_center_at_output_zero=first-1272,
        evidence_sha256={'protocol.json':sha(encoded(p)), 'final_snapshot.txt':sha(snapshot),
                         'iq.ci16':sha(iq)})
    remote = dict(serial='test-radio', firmware='test-native', fit_sha256='a'*64,
        boot_id='336a3c4c-8ab3-4758-ae9e-6967808e2a6d', all_buffer_enable='0', tx_lo_powerdown='1')
    episode = dict(seed=asdict(seed), controller_stopped_before_coarse_exit=True, process_exit=0,
        runtime=dict(result=0, configured=16, retained_popped=16, journal_bytes=len(data)),
        review=dict(heads=16, supported=checked['supported'], drained=asdict(checked['drained']),
                    final=asdict(checked['final'])))
    owner = dict(serial='test-radio', host='192.168.1.14', status='test_complete',
        before_capture={'remote':remote}, after={'remote':dict(remote)}, coarse=s, coarse_exit=0,
        host_spool_export_verified=True, episodes=[episode])
    return dict(journal=data, recording=encoded(export_journal(data, epoch=3)), owner=encoded(owner),
        protocol=encoded(p), summary=encoded(s), final_snapshot=snapshot,
        iq_sha256=sha(iq), iq_bytes=len(iq), episode_index=0)


def test_binding_preserves_exact_source_and_does_not_claim_physical_truth(controller, pilot_words):
    inputs = evidence(controller, pilot_words)
    result = bind_source(**inputs)
    assert result['head_count'] == 16 and result['supported_count'] == 16
    assert result['epoch'] == 3 and result['visit'] == 1105016
    assert int(result['native_origin']) > 2**53
    assert result['recording_export_sha256'] == sha(inputs['recording'])
    assert result['owner_receipt_sha256'] == sha(inputs['owner'])
    assert result['coarse_iq_sha256'] == inputs['iq_sha256']
    assert result['source_correspondence_verified']
    assert not any(result[k] for k in ('radio_signed_attestation', 'acquisition_verified',
        'original_native_iq_verified', 'physical_precision_qualified'))


@pytest.mark.parametrize('result', [-4, -5])
def test_failed_runtime_is_preserved_not_promoted(controller, pilot_words, result):
    inputs = evidence(controller, pilot_words)
    owner = json.loads(inputs['owner'])
    owner['status'] = 'failed'
    owner['episodes'][0]['runtime']['result'] = result
    owner['episodes'][0]['process_exit'] = 1
    inputs['owner'] = encoded(owner)
    output = bind_source(**inputs)
    assert output['runtime_result'] == result and output['owner_status'] == 'failed'


def test_owner_sealed_journal_digest_is_enforced_when_available(controller, pilot_words):
    inputs = evidence(controller, pilot_words)
    owner = json.loads(inputs['owner'])
    owner['episodes'][0]['journal_sha256'] = sha(inputs['journal'])
    inputs['owner'] = encoded(owner)
    assert bind_source(**inputs)['head_count'] == 16
    owner['episodes'][0]['journal_sha256'] = '0'*64
    inputs['owner'] = encoded(owner)
    with pytest.raises(ValueError, match='sealed digest'):
        bind_source(**inputs)


@pytest.mark.parametrize('corruption', ['boot', 'serial', 'busy', 'tx', 'iq', 'bytes', 'protocol',
    'snapshot', 'owner_coarse', 'runtime', 'seed', 'epoch', 'export', 'writer', 'outside',
    'owner_inventory', 'missing_episode'])
def test_mismatched_source_or_owner_cannot_bind(controller, pilot_words, corruption):
    inputs = evidence(controller, pilot_words)
    owner = json.loads(inputs['owner'])
    if corruption == 'boot': owner['after']['remote']['boot_id'] = '00000000-0000-0000-0000-000000000000'
    elif corruption == 'serial': owner['serial'] = 'other-radio'
    elif corruption == 'busy': owner['before_capture']['remote']['all_buffer_enable'] = '1'
    elif corruption == 'tx': owner['before_capture']['remote']['tx_lo_powerdown'] = '0'
    elif corruption == 'iq': inputs['iq_sha256'] = 'b'*64
    elif corruption == 'bytes': inputs['iq_bytes'] -= 4
    elif corruption == 'protocol': inputs['protocol'] = inputs['protocol'].replace(b'1105016', b'1105017')
    elif corruption == 'snapshot': inputs['final_snapshot'] += b'\n'
    elif corruption == 'owner_coarse': owner['coarse']['iq_sha256'] = 'b'*64
    elif corruption == 'runtime': owner['episodes'][0]['runtime']['journal_bytes'] += 1
    elif corruption == 'seed': owner['episodes'][0]['seed']['start'] += 1
    elif corruption == 'epoch':
        value = json.loads(inputs['recording']);value['epoch'] = 4;inputs['recording'] = encoded(value)
    elif corruption == 'export':
        value = json.loads(inputs['recording']);value['measurements'][0]['cfo_hz'] += 1
        inputs['recording'] = encoded(value)
    elif corruption == 'writer': owner['episodes'][0]['controller_stopped_before_coarse_exit'] = False
    elif corruption == 'owner_inventory': owner['episodes'][0]['review']['heads'] = 15
    elif corruption == 'missing_episode': inputs['episode_index'] = 1
    elif corruption == 'outside':
        # Translate both collector endpoints consistently beyond all native jobs.
        fields = inputs['final_snapshot'].split(); delta = 2400000
        for offset in (0,2):
            n = 14+offset;value = int(fields[n],16)+(int(fields[n+1],16)<<32)+delta
            fields[n:n+2] = [f'{value%2**32:08x}'.encode(),f'{value>>32:08x}'.encode()]
        inputs['final_snapshot'] = b' '.join(fields)+b'\n'
        summary = json.loads(inputs['summary'])
        summary['native_signal_center_at_output_zero'] += delta
        summary['evidence_sha256']['final_snapshot.txt'] = sha(inputs['final_snapshot'])
        inputs['summary'] = encoded(summary);owner['coarse'] = summary
    inputs['owner'] = encoded(owner)
    with pytest.raises(ValueError):
        bind_source(**inputs)


def test_cli_hashes_actual_iq_and_refuses_existing_output(controller, pilot_words, tmp_path):
    inputs = evidence(controller, pilot_words)
    command = [sys.executable, '-m', 'tools.starlink_glrt_native_binding']
    for name in ('journal', 'recording', 'owner', 'protocol', 'summary', 'final_snapshot'):
        path = tmp_path/name;path.write_bytes(inputs[name])
        command += ['--'+name.replace('_','-'), str(path)]
    iq = tmp_path/'iq.ci16';iq.write_bytes(bytes(inputs['iq_bytes']))
    output = tmp_path/'binding.json'
    command += ['--iq',str(iq),'--episode-index','0','--output',str(output)]
    root = Path(__file__).resolve().parents[2]
    first = subprocess.run(command,cwd=root,check=True,text=True,capture_output=True)
    assert json.loads(first.stdout)['head_count'] == 16
    original = output.read_bytes()
    again = subprocess.run(command,cwd=root,text=True,capture_output=True)
    assert again.returncode != 0 and output.read_bytes() == original
    iq.write_bytes(bytes(inputs['iq_bytes']-4)+b'bad!')
    command[-1] = str(tmp_path/'bad.json')
    corrupt = subprocess.run(command,cwd=root,text=True,capture_output=True)
    assert corrupt.returncode != 0 and not (tmp_path/'bad.json').exists()
