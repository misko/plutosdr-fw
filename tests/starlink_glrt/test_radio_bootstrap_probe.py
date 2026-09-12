"""Actual capture executable with pthread/FFTW bootstrap on a declared IIO fixture."""
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from tools.starlink_glrt_local_abi import LocalEvent, LocalIQSnapshot, LocalSearchSnapshot, LocalSourceClosure, attest_capture
from . import test_radio_iio_probe as baseline

pytestmark = pytest.mark.fftw


@pytest.fixture(scope='module')
def bootstrap_probe(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    fixture = root/'tests/starlink_glrt/iio_probe_fixture'
    out = tmp_path_factory.mktemp('bootstrap-probe')
    prefix = os.environ.get('GLRT_FFTW_PREFIX')
    includes = ['-I', str(Path(prefix)/'include')] if prefix else []
    libraries = ['-L', str(Path(prefix)/'lib'), '-Wl,-rpath,'+str(Path(prefix)/'lib')] if prefix else []
    names = ['glrt_radio_iio_probe.c', 'glrt_capture_source.c', 'glrt_tracking_session.c',
             'glrt_tracking_worker.c', 'glrt_tracking_seed.c', 'glrt_tracking_resolver.c',
             'glrt_tracking_iq_owner.c', 'glrt_tracking_recent_iq.c', 'glrt_tracking_live_bootstrap.c',
             'glrt_tracking_bootstrap.c', 'glrt_tracking_iq.c', 'glrt_native_trend.c',
             'glrt_native_schedule.c', 'glrt_tracking_schedule.c', 'glrt_native_solver.c']
    build = subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-DGLRT_PROBE_BOOTSTRAP', '-I', str(fixture), *includes,
        *(str(root/'tools'/name) for name in names), str(fixture/'backend.c'),
        *libraries, '-lfftw3', '-lm', '-o', str(out/'probe')], capture_output=True, text=True)
    assert build.returncode == 0, ('Native FFTW is required; install its development package or set '
                                 'GLRT_FFTW_PREFIX. No hardware substitution or skip.\n'+build.stderr)
    bank = root/'hdl/library/starlink_glrt'
    cubic = (bank/'native_cubic_60000000_upper.mem').read_bytes()
    direct = (bank/'native_direct_2500000_phase4_upper_interleaved.mem').read_bytes()
    refs = np.asarray([reference_rows(cubic, direct, 2500000, p) for p in range(4)], dtype='<i2')
    refs.tofile(out/'references.bin')
    return out/'probe', out/'references.bin'


def capture(bootstrap_probe, tmp_path, *, signal=False, references=None):
    binary, ref = bootstrap_probe
    env = {**os.environ, 'PROBE_TRACE':str(tmp_path/'trace')}
    if signal: env.update(PROBE_SIGNAL='1', PROBE_REFERENCE=str(ref))
    output = tmp_path/'capture'
    result = subprocess.run([str(binary), baseline.SERIAL, 'test-fw', '917',
        '16384' if signal else '4096', '80' if signal else '4', str(output),
        '--bootstrap', str(ref if references is None else references)],
        env=env, capture_output=True, text=True, timeout=10)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    return result, rows, output


def attest(root):
    snapshot = lambda name: LocalIQSnapshot.decode((root/(name+'_snapshot.txt')).read_text())
    closure = lambda name: LocalSourceClosure.decode((root/(name+'_extension_snapshot.txt')).read_text())
    search = lambda name: LocalSearchSnapshot.decode((root/(name+'_local_search_snapshot.txt')).read_text())
    raw = (root/'events.raw').read_bytes()
    return attest_capture(final=snapshot('final'), baseline=snapshot('baseline'), source=closure('final'),
        source_baseline=closure('baseline'), search=search('final'), search_baseline=search('baseline'),
        events=[LocalEvent.decode(raw[n:n+64]) for n in range(0, len(raw), 64)],
        received_bytes=(root/'iq.ci16').stat().st_size)


def test_compiled_option_preserves_original_owner_behavior(bootstrap_probe, tmp_path):
    baseline.test_one_owner_saves_exact_contiguous_iq_and_independently_attested_closure(bootstrap_probe[0], tmp_path, '')


def test_empty_real_event_dispatch_closes_thread_and_preserves_source_closure(bootstrap_probe, tmp_path):
    result, rows, root = capture(bootstrap_probe, tmp_path)
    assert result.returncode == 0, result.stdout+result.stderr
    worker, capture_status = rows
    assert capture_status['status'] == 'captured' and worker['joined'] == 1 and not worker['fatal']
    assert worker['attempts'] == worker['completed'] == worker['ready_proposals'] == 0
    assert worker['ignored'] == 1 and worker['hardware_submissions'] == 0
    assert attest(root)['supported'] == 0
    assert (root/'bootstrap.jsonl').read_bytes() == (root/'bootstrap.iq.ci16').read_bytes() == b''
    with (root/'bootstrap_events.csv').open() as f: events = list(csv.DictReader(f))
    assert [int(row['disposition']) for row in events] == [0]


def test_modeled_candidate_reaches_actual_background_fft_and_retained_future_proposal(bootstrap_probe, tmp_path):
    result, rows, root = capture(bootstrap_probe, tmp_path, signal=True)
    assert result.returncode == 0, result.stdout+result.stderr
    worker, capture_status = rows
    assert capture_status['status'] == 'captured' and worker['joined'] == 1 and not worker['fatal']
    assert worker['attempts'] == worker['completed'] == worker['ready_proposals'] == 1
    assert worker['ignored'] == 1 and worker['hardware_submissions'] == 0
    assert attest(root) == dict(source_rate=2500000, samples=1310720, first_source_index=100,
        opportunities=6, admitted=1, skipped=5, completed=1, supported=1, aborted=0,
        completed_windows=[dict(first_source_index=100, samples=14000, supported=True)])
    evidence = [json.loads(line) for line in (root/'bootstrap.jsonl').read_text().splitlines()]
    assert evidence[0]['kind'] == 1 and evidence[1]['kind'] == 2
    assert evidence[-2]['kind'] == 4 and evidence[-1]['kind'] == 0 and evidence[-1]['status'] == 1
    assert evidence[-1]['fft_calls'] == 68 and evidence[-1]['retained_past'] >= 8
    original, copied = (root/'iq.ci16').read_bytes(), (root/'bootstrap.iq.ci16').read_bytes()
    position = 0
    for row in evidence:
        assert row['iq_offset_samples'] == position
        count = row['iq_samples']
        if count:
            offset = row['first']-100
            assert copied[position*4:(position+count)*4] == original[offset*4:(offset+count)*4]
        position += count
    assert position*4 == len(copied)
    with (root/'bootstrap_events.csv').open() as f: events = list(csv.DictReader(f))
    assert [int(row['disposition']) for row in events] == [0, 1]
    assert (tmp_path/'trace').read_text() == '1 1 1\n'


@pytest.mark.parametrize('damage', ['missing', 'short', 'long', 'symlink', 'fifo'])
def test_bad_reference_file_fails_before_radio_context_or_capture(bootstrap_probe, tmp_path, damage):
    ref = tmp_path/'bad-reference'
    if damage == 'short': ref.write_bytes(b'\0'*105599)
    elif damage == 'long': ref.write_bytes(b'\0'*105601)
    elif damage == 'symlink': ref.symlink_to(bootstrap_probe[1])
    elif damage == 'fifo': os.mkfifo(ref)
    result, rows, output = capture(bootstrap_probe, tmp_path, references=ref)
    assert result.returncode == 1 and rows[-1]['failed_stage'] == 'bootstrap_references'
    assert not (tmp_path/'trace').exists() and not output.exists()


def test_signal_stop_joins_worker_before_capture_owner_teardown(bootstrap_probe, tmp_path):
    binary, ref = bootstrap_probe
    output = tmp_path/'capture'
    process = subprocess.Popen([str(binary), baseline.SERIAL, 'test-fw', '917', '16384', '320', str(output),
        '--bootstrap', str(ref)], env={**os.environ, 'PROBE_TRACE':str(tmp_path/'trace'),
        'PROBE_SIGNAL':'1', 'PROBE_REFERENCE':str(ref)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic()+3
        evidence = output/'bootstrap.jsonl'
        while time.monotonic() < deadline and process.poll() is None:
            if evidence.exists() and evidence.stat().st_size: break
            time.sleep(.001)
        assert process.poll() is None and evidence.exists() and evidence.stat().st_size
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        rows = [json.loads(line) for line in stdout.splitlines()]
        assert process.returncode == 1 and rows[-1]['failed_stage'] == 'interrupted', stdout+stderr
        assert rows[0]['joined'] == 1 and not rows[0]['fatal'] and rows[0]['attempts'] == rows[0]['completed']
        assert (tmp_path/'trace').read_text() == '1 1 1\n'
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=5)
