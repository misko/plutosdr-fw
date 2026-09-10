"""Recording exports exercise real C journals, with no hardware or RF access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal, retained
from tools.starlink_glrt_native_journal import records, review
from tools.starlink_glrt_native_recording import export_journal, write_recording


def completed(controller, pilot_words):
    radio = Radio(controller, pilot_words, frames=16)
    assert radio.run() == 0
    return journal(radio)


def test_export_preserves_all_integer_evidence_and_fits(controller, pilot_words):
    data = completed(controller, pilot_words)
    result = export_journal(data, epoch=3)
    checked = review(data, epoch=3)
    assert result['journal_sha256'] == hashlib.sha256(data).hexdigest()
    assert result['head_count'] == result['supported_count'] == 16
    assert result['rejected_count'] == 0
    assert result['drained']['popped'] == 16 and result['final']['configured'] == 0
    assert result['pilot_samples'] == 79200 and result['source_rate_hz'] == 60000000
    assert result['epoch_scope'] == 'journal_local_requires_radio_boot_binding'
    assert not any(result[name] for name in ('solver_replayed', 'original_native_iq_verified',
        'acquisition_verified', 'physical_precision_qualified'))
    for row, head, fit in zip(result['measurements'], checked['heads'], checked['estimates']):
        assert all(row[k] == v for k, v in fit.items())
        assert isinstance(row['native_start_sample'], str)
        assert int(row['native_start_sample']) == head.start
        for key in ('reference_sum', 'delay_sum', 'reference_prefix_integral'):
            assert tuple(map(int, row[key])) == getattr(head, key)
        assert int(row['observed_energy']) == head.observed_energy
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def rewrite(data, edit):
    entries, _ = records(data)
    pairs = [(e.kind, e.payload) for e in entries]
    edit(pairs)
    return b'GLRJ1\n'+b''.join(retained(k, p) for k, p in pairs)


def test_rejected_estimates_remain_visible(controller, pilot_words):
    data = completed(controller, pilot_words)
    def reject(pairs):
        n = next(i for i, (kind, _) in enumerate(pairs) if kind == 'estimate')
        words = pairs[n][1].split(); words[-1] = b'16'
        pairs[n] = ('estimate', b' '.join(words)+b'\n')
    result = export_journal(rewrite(data, reject), epoch=3)
    assert result['head_count'] == 16 and result['supported_count'] == 15
    assert result['rejected_count'] == 1 and not result['measurements'][0]['supported']
    assert result['measurements'][0]['rejection'] == 16


def test_acquisition_loss_is_exportable_without_claiming_success(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.reject = True
    assert radio.run() == -4
    result = export_journal(journal(radio), epoch=3)
    assert result['supported_count'] == 0
    assert result['head_count'] == result['rejected_count'] > 0
    assert result['drained']['popped'] == result['head_count']
    assert not result['acquisition_verified'] and not result['physical_precision_qualified']


def test_duplicate_frame_cannot_become_two_recorded_measurements(controller, pilot_words):
    data = completed(controller, pilot_words)
    def duplicate(pairs):
        heads = [i for i, (kind, _) in enumerate(pairs) if kind == 'head']
        first = pairs[heads[0]][1].split()
        second = pairs[heads[1]][1].split()
        # Keep sequence but repeat the original start, phase and repeat ordinal.
        for n in (6, 7, 8, 9, 30):
            second[n] = first[n]
        pairs[heads[1]] = ('head', b' '.join(second)+b'\n')
    with pytest.raises(ValueError, match='repeat order'):
        export_journal(rewrite(data, duplicate), epoch=3)


def test_faulted_head_cannot_publish_a_supported_estimate(controller, pilot_words):
    data = completed(controller, pilot_words)
    def fault(pairs):
        n = next(i for i, (kind, _) in enumerate(pairs) if kind == 'head')
        words = pairs[n][1].split(); words[11] = b'00000001'
        pairs[n] = ('head', b' '.join(words)+b'\n')
    with pytest.raises(ValueError, match='arithmetic failed'):
        export_journal(rewrite(data, fault), epoch=3)


@pytest.mark.parametrize('epoch', [0, True, -1, 2**32, 4])
def test_export_rejects_invalid_or_mismatched_epoch(controller, pilot_words, epoch):
    with pytest.raises(ValueError):
        export_journal(completed(controller, pilot_words), epoch=epoch)


def test_invalid_journal_creates_no_artifact(tmp_path):
    source = tmp_path/'journal'; source.write_bytes(b'GLRJ1\nhead 100\npartial')
    output = tmp_path/'recording.json'
    with pytest.raises(ValueError):
        write_recording(source, output, epoch=3)
    assert not output.exists() and list(tmp_path.iterdir()) == [source]


def test_cli_exports_once_without_overwriting_existing_recording(controller, pilot_words, tmp_path):
    source = tmp_path/'journal'; source.write_bytes(completed(controller, pilot_words))
    output = tmp_path/'recording.json'
    command = [sys.executable, '-m', 'tools.starlink_glrt_native_recording',
               '--journal', str(source), '--epoch', '3', '--output', str(output)]
    root = Path(__file__).resolve().parents[2]
    run = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
    assert json.loads(run.stdout)['head_count'] == 16
    before = output.read_bytes()
    again = subprocess.run(command, cwd=root, capture_output=True, text=True)
    assert again.returncode != 0 and output.read_bytes() == before
    assert not list(tmp_path.glob('.native-recording-*'))
