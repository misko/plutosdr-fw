"""Real pthread dispatch, retained numerical evidence and capture-owner lifetime."""
import ctypes as c
import csv
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from tools.starlink_glrt_native_replay import rotate
from . import test_tracking_seed as t
from .test_tracking_solver import moments


WRAPPER = t.WRAPPER+r'''
#include "glrt_tracking_session.h"
void *session_new(void) { void *p=calloc(1,sizeof(struct glrt_tracking_session));assert(p);return p; }
void session_free(struct glrt_tracking_session *s) { assert(!s->started || s->joined);free(s); }
uint64_t session_completed(struct glrt_tracking_session *s)
{
    uint64_t n;assert(!pthread_mutex_lock(&s->mutex));n=s->completed;
    assert(!pthread_mutex_unlock(&s->mutex));return n;
}
void session_summary(const struct glrt_tracking_session *s,uint64_t out[11])
{
    assert(s->joined);out[0]=s->attempts;out[1]=s->completed;out[2]=s->ready;
    out[3]=s->ignored;out[4]=s->busy_events;out[5]=s->stopped_events;
    out[6]=s->bytes;out[7]=s->iq_samples;out[8]=s->fatal;
    out[9]=s->initialized;out[10]=s->worker!=NULL;
}
void session_limit(struct glrt_tracking_session *s)
{
    assert(!pthread_mutex_lock(&s->mutex));assert(!s->attempts && !s->queued);
    s->bytes=8U*1024U*1024U;assert(!pthread_mutex_unlock(&s->mutex));
}
'''


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("tracking-session")
    (out/"wrapper.c").write_text(WRAPPER)
    names = t.SOURCES+["glrt_cpu_seed.c", "glrt_tracking_worker.c", "glrt_tracking_live_bootstrap.c",
                       "glrt_tracking_iq.c", "glrt_tracking_session.c"]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared",
        "-fPIC", "-I", str(root/"tools"), str(out/"wrapper.c"),
        *(str(root/"tools"/name) for name in names), "-lm", "-o", str(out/"session.so")], check=True)
    lib = c.CDLL(str(out/"session.so"))
    lib.seed_owner_new.argtypes = [c.c_size_t, c.c_uint32, c.c_uint64]
    lib.seed_owner_new.restype = lib.session_new.restype = c.c_void_p
    lib.seed_owner_free.argtypes = lib.session_free.argtypes = [c.c_void_p]
    lib.glrt_tracking_iq_owner_publish.argtypes = [c.c_void_p, c.c_uint32, c.c_uint64, c.c_void_p,
                                                 c.c_size_t, c.c_uint64, c.c_uint64]
    lib.glrt_tracking_iq_owner_close.argtypes = [c.c_void_p, c.c_int]
    lib.glrt_tracking_session_start.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_void_p, t.FFT_PORT, c.c_void_p]
    lib.glrt_tracking_session_offer.argtypes = [c.c_void_p, c.c_void_p]
    for name in ["wake", "stop", "join"]:
        getattr(lib, 'glrt_tracking_session_'+name).argtypes = [c.c_void_p]
    lib.session_completed.argtypes = lib.session_limit.argtypes = [c.c_void_p]
    lib.session_completed.restype = c.c_uint64
    lib.session_summary.argtypes = [c.c_void_p, c.c_void_p]
    bank = root/"hdl/library/starlink_glrt"
    cubic = (bank/'native_cubic_60000000_upper.mem').read_bytes()
    direct = (bank/'native_direct_2500000_phase4_upper_interleaved.mem').read_bytes()
    refs = np.asarray([reference_rows(cubic, direct, t.RATE, p) for p in range(4)], dtype=np.int16)
    return lib, refs


def run(session, tmp_path, mode):
    lib, refs = session
    first = 2**60+17 if mode == 'large' else 1_000_000
    words = t.event(first, 0)
    iq = np.zeros((443330, 2), dtype=np.int16)
    if mode != 'zero':
        for start in range(230022, len(iq)-t.N+1, 30000): iq[start:start+t.N] = refs[0, :, :2]
    owner = lib.seed_owner_new(500000, 3, first)
    assert lib.glrt_tracking_iq_owner_publish(owner, 3, first, iq.ctypes.data, len(iq),
                                             first+len(iq), time.monotonic_ns()) == 0
    service = lib.session_new(); directory = os.open(tmp_path, os.O_RDONLY|os.O_DIRECTORY)
    entered, release = threading.Event(), threading.Event()
    calls, errors, dispositions = [], [], []

    @t.FFT_PORT
    def fft(context, data, count):
        try:
            calls.append(count)
            if len(calls) == 1 and mode in ('busy', 'cancel', 'source_lost'):
                entered.set(); assert release.wait(2), 'test failed to release FFT'
            values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
            values[:] = np.fft.fft(values)
            return 0
        except Exception as error:
            errors.append(repr(error)); return -1

    started = joined = False
    try:
        assert lib.glrt_tracking_session_start(service, directory, owner, refs.ctypes.data, fft, None) == 0
        started = True
        if mode == 'limit': lib.session_limit(service)
        if mode == 'ignored': words[5] &= ~1
        if mode == 'malformed': words[5] |= 1 << 28
        if mode == 'stopped': assert lib.glrt_tracking_session_stop(service) == 0
        dispositions.append(lib.glrt_tracking_session_offer(service, words))
        if mode in ('busy', 'cancel', 'source_lost'):
            assert entered.wait(2)
            if mode == 'busy':
                extra = t.Words(*words); extra[2] += 1
                dispositions.append(lib.glrt_tracking_session_offer(service, extra))
                extra[2] += 1; extra[5] &= ~1
                dispositions.append(lib.glrt_tracking_session_offer(service, extra))
            elif mode == 'cancel': assert lib.glrt_tracking_session_stop(service) == 0
            else: assert lib.glrt_tracking_iq_owner_close(owner, 1) == 0
            release.set()
        if mode == 'immediate_stop': assert lib.glrt_tracking_session_stop(service) == 0
        if dispositions[0] == 1:
            deadline = time.monotonic()+3
            while not lib.session_completed(service) and time.monotonic() < deadline: time.sleep(.001)
            assert lib.session_completed(service) == 1
        assert lib.glrt_tracking_session_stop(service) == 0
        join_rc = lib.glrt_tracking_session_join(service); joined = True
        metrics = (c.c_uint64*11)(); lib.session_summary(service, metrics)
        assert not errors, errors
        rows = [json.loads(line) for line in (tmp_path/'bootstrap.jsonl').read_text().splitlines()]
        with (tmp_path/'bootstrap_events.csv').open() as f: event_rows = list(csv.DictReader(f))
        assert [int(row['disposition']) for row in event_rows] == dispositions
        assert all(int(row['observed_ns']) > 0 for row in event_rows)
        assert list(metrics)[9:] == [0, 0]  # joined before owner or worker storage is freed
        return join_rc, list(metrics), rows, (tmp_path/'bootstrap.iq.ci16').read_bytes(), calls, iq, first
    finally:
        release.set()
        if started and not joined:
            lib.glrt_tracking_session_stop(service); lib.glrt_tracking_session_join(service)
        lib.session_free(service); lib.seed_owner_free(owner); os.close(directory)


@pytest.mark.parametrize('mode', ['positive', 'large', 'busy'])
def test_real_thread_retains_exact_seed_pilots_and_terminal_proposal(session, tmp_path, mode):
    rc, metrics, rows, raw, calls, iq, first = run(session, tmp_path, mode)
    assert rc == 0 and metrics[:3] == [1, 1, 1] and calls == [t.FFT]*68
    assert metrics[3:6] == ([1, 1, 0] if mode == 'busy' else [0, 0, 0])
    assert [row['kind'] for row in rows] == [1, 2]+[3]*8+[4, 0]
    assert rows[-1]['status'] == 1 and rows[-1]['history_count'] == 8
    assert rows[-1]['source_checked_ns'] >= rows[-1]['checked_source']['observed_ns']
    assert all(row['schema'] == 'glrt_bootstrap_diagnostic_v1' and row['attempt'] == 1 for row in rows)
    position = 0
    for row in rows:
        assert row['iq_offset_samples'] == position
        n = row['iq_samples']
        if n:
            a = row['first']-first
            assert raw[position*4:(position+n)*4] == iq[a:a+n].tobytes()
        position += n
    assert position == metrics[7] and len(raw) == position*4
    assert metrics[6] == len(raw)+(tmp_path/'bootstrap.jsonl').stat().st_size
    assert rows[1]['best_shift'] == 0 and abs(rows[1]['cfo_hz']) < 1e-6
    assert len(rows[1]['hypotheses']) == 17
    # Independent saved-IQ numerical replay verifies the serialized integer
    # words, not only the C worker's own accepted flags.
    for row in rows[2:10]:
        start = row['first']-first
        cut = iq[start:start+t.N]
        rotated = np.asarray([rotate(int(i), int(q), n*row['phase_step']) for n, (i, q) in enumerate(cut)], dtype=np.int64)
        expected = moments(rotated, session[1][row['reference_phase']].astype(np.int64))
        assert row['moments'] == list(expected.words) and row['accepted'] == 1 and row['rejection'] == 0
    handoff = rows[-2]
    assert handoff['history']['count'] == 8 and handoff['history']['last_supported'] == 63
    assert handoff['batch'][2] >= rows[-1]['checked_source']['source_now']+2500


@pytest.mark.parametrize('mode,status', [('zero', -6), ('cancel', -4), ('source_lost', -2), ('immediate_stop', -4)])
def test_failure_or_stop_retains_terminal_state_without_a_live_handoff(session, tmp_path, mode, status):
    rc, metrics, rows, raw, calls, _, _ = run(session, tmp_path, mode)
    assert rc == 0 and metrics[:3] == [1, 1, 0]
    assert rows[-1]['kind'] == 0 and rows[-1]['status'] == status
    assert not any(row['kind'] == 4 for row in rows)
    if mode == 'zero': assert rows[-1]['history_count'] == 0 and len(calls) == 68
    if mode == 'cancel': assert len(calls) == 1
    if mode == 'immediate_stop': assert len(calls) <= 1


@pytest.mark.parametrize('mode,join_rc,counters', [
    ('ignored', 0, [0, 0, 0, 1, 0, 0]), ('stopped', 0, [0, 0, 0, 0, 0, 1]),
    ('malformed', -1, [0, 0, 0, 0, 0, 0]), ('limit', -1, [1, 1, 0, 0, 0, 0]),
])
def test_rejected_admission_and_retention_limit_cannot_start_tracking(session, tmp_path, mode, join_rc, counters):
    rc, metrics, rows, raw, calls, _, _ = run(session, tmp_path, mode)
    assert rc == join_rc and metrics[:6] == counters
    assert not rows and not raw and not calls


def test_stop_restart_uses_new_evidence_and_leaves_previous_run_unchanged(session, tmp_path):
    a, b = tmp_path/'first', tmp_path/'second'; a.mkdir(); b.mkdir()
    first = run(session, a, 'positive')
    saved = {p.name:p.read_bytes() for p in a.iterdir()}
    second = run(session, b, 'positive')
    assert first[0] == second[0] == 0
    assert saved == {p.name:p.read_bytes() for p in a.iterdir()}
