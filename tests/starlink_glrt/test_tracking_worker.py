"""Bounded worker connects actual copied IQ, FFT resolution and pilot history."""
import ctypes as c
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from . import test_tracking_seed as t

CLOCK = c.CFUNCTYPE(c.c_uint64, c.c_void_p)
ACTION = c.CFUNCTYPE(c.c_int, c.c_void_p)
RETAIN = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_int, c.c_void_p)

WRAPPER = t.WRAPPER + r'''
#include "glrt_tracking_worker.h"
void *worker_new(void) { void *p=calloc(1,sizeof(struct glrt_tracking_worker));assert(p);return p; }
void worker_free(void *p) { free(p); }
int worker_test(struct glrt_tracking_worker *w, struct glrt_tracking_iq_owner *owner,
    const uint32_t *event,const int16_t *refs,glrt_resolver_fft fft,
    uint64_t (*clock)(void *),int (*cancel)(void *),int (*wait)(void *),
    int (*retain)(void *,enum glrt_tracking_worker_record,const struct glrt_tracking_worker *),
    void *context,uint64_t deadline,uint64_t budget,uint32_t lead)
{
    struct glrt_tracking_worker_config config={.owner=owner,.references=refs,.fft=fft,
        .fft_context=context,.ports={context,clock,cancel,wait,retain},
        .source_deadline=deadline,.wall_budget_ns=budget,.maximum_seed_age=2500000,.lead_samples=lead};
    return glrt_tracking_worker_run(w,&config,event);
}
void worker_summary(const struct glrt_tracking_worker *w,uint64_t out[16])
{
    out[0]=w->seed.first;out[1]=w->seed.seed_start;out[2]=w->seed.seed_fraction;
    out[3]=w->fft_calls;out[4]=w->retained_past;out[5]=w->waits;
    out[6]=w->live.core.trend.history.count;out[7]=w->live.core.valid;
    out[8]=w->live.core.pending;out[9]=w->live.core.ready;
    out[10]=w->trace.frame;out[11]=w->trace.job.start;out[12]=w->trace.handoff.rate;
    out[13]=w->trace.moments.count;out[14]=w->trace.accepted;out[15]=w->last_ns;
}
int worker_status(const struct glrt_tracking_worker *w) { return w->status; }
const int16_t *worker_iq(const struct glrt_tracking_worker *w, int kind)
{ return kind==GLRT_WORKER_SEED_IQ ? w->seed_iq : w->scratch; }
const struct glrt_tracking_iq_view *worker_view(const struct glrt_tracking_worker *w, int kind)
{ return kind==GLRT_WORKER_SEED_IQ ? &w->seed.copied : &w->trace.source; }
'''


@pytest.fixture(scope="module")
def worker(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("tracking-worker")
    (out/"wrapper.c").write_text(WRAPPER)
    sources = t.SOURCES+["glrt_tracking_worker.c", "glrt_tracking_live_bootstrap.c", "glrt_tracking_iq.c"]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared",
                    "-fPIC", "-I", str(root/"tools"), str(out/"wrapper.c"),
                    *(str(root/"tools"/name) for name in sources), "-lm", "-o", str(out/"worker.so")], check=True)
    lib = c.CDLL(str(out/"worker.so"))
    lib.seed_owner_new.argtypes = [c.c_size_t, c.c_uint32, c.c_uint64]
    lib.seed_owner_new.restype = lib.worker_new.restype = c.c_void_p
    lib.seed_owner_free.argtypes = lib.worker_free.argtypes = [c.c_void_p]
    lib.glrt_tracking_iq_owner_publish.argtypes = [c.c_void_p, c.c_uint32, c.c_uint64, c.c_void_p,
                                                 c.c_size_t, c.c_uint64, c.c_uint64]
    lib.glrt_tracking_iq_owner_close.argtypes = [c.c_void_p, c.c_int]
    lib.worker_test.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p, t.FFT_PORT,
                               CLOCK, ACTION, ACTION, RETAIN, c.c_void_p, c.c_uint64, c.c_uint64, c.c_uint32]
    lib.worker_summary.argtypes = [c.c_void_p, c.c_void_p]
    lib.worker_status.argtypes = [c.c_void_p]
    lib.worker_iq.argtypes = lib.worker_view.argtypes = [c.c_void_p, c.c_int]
    lib.worker_iq.restype = c.c_void_p
    lib.worker_view.restype = c.POINTER(t.View)
    bank = root/"hdl/library/starlink_glrt"
    refs = np.asarray([reference_rows((bank/'native_cubic_60000000_upper.mem').read_bytes(),
        (bank/'native_direct_2500000_phase4_upper_interleaved.mem').read_bytes(), t.RATE, phase)
        for phase in range(4)], dtype=np.int16)
    return lib, refs


def summary(lib, work):
    out = (c.c_uint64*16)(); lib.worker_summary(work, out); return list(out)


def run(worker, mode):
    lib, refs = worker
    first = 2**60+17 if mode == "large" else 1_000_000
    words = t.event(first, 0)
    if mode == "ignored": words[5] &= ~1
    iq = np.zeros((1_000_000, 2), dtype=np.int16)
    if mode != "zero":
        for offset in range(230022, len(iq)-t.N+1, 30000):
            iq[offset:offset+t.N] = refs[0, :, :2]
    owner = lib.seed_owner_new(1_000_000, 3, first)
    work = lib.worker_new()
    state = dict(now=1_000_000, calls=0, cancelled=False, retained=[], errors=[], end=443330, waits=0)
    lag = 300000 if mode.startswith("wait") else 0
    budget = 50_000_000
    deadline = first+2*t.RATE

    def publish(count):
        offset = state['end']; end = offset+count
        block = np.ascontiguousarray(iq[offset:end])
        assert lib.glrt_tracking_iq_owner_publish(owner, 3, first+offset, block.ctypes.data,
            len(block), first+end, state['now']) == 0
        state['end'] = end

    @CLOCK
    def clock(context): return state['now']

    @ACTION
    def cancel(context): return int(state['cancelled'])

    @ACTION
    def wait(context):
        try:
            state['waits'] += 1; state['now'] += 1_000_000
            if mode == "wait_resume" and state['waits'] == 1: publish(300000)
            if mode == "wait_cancel": state['cancelled'] = True
            return -1 if mode == "wait_error" else 0
        except Exception as error:
            state['errors'].append(repr(error)); return -1

    @t.FFT_PORT
    def fft(context, data, count):
        try:
            state['calls'] += 1; state['now'] += 100_000
            values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
            values[:] = np.fft.fft(values)
            if state['calls'] == 3:
                if mode == "fft_cancel": state['cancelled'] = True
                if mode == "fft_timeout": state['now'] += budget
                if mode == "clock_regression": state['now'] = 1
                if mode == "source_closed": assert lib.glrt_tracking_iq_owner_close(owner, 0) == 0
                if mode == "source_deadline": publish(2000)
                if mode == "fft_error": return -1
            return 0
        except Exception as error:
            state['errors'].append(repr(error)); return -1

    @RETAIN
    def retain(context, kind, pointer):
        try:
            assert pointer == work
            s = summary(lib, work)
            if kind in (1, 3):
                start, samples = (s[0], t.SAMPLES) if kind == 1 else (s[11], t.N)
                copied = c.string_at(lib.worker_iq(work, kind), samples*4)
                assert copied == iq[start-first:start-first+samples].tobytes()
                source = lib.worker_view(work, kind).contents
                assert start+samples <= source.end <= source.source_now
                assert source.valid and not source.closed and source.observed_ns <= state['now']
                if kind == 3:
                    assert s[13] == t.N and s[14] == int(mode != "zero")
            if kind == 2: assert s[6:10] == [0, 1, 0, 0]
            if kind == 4:
                assert s[6] >= 8 and s[7:10] == [1, 0, 1] and s[12] == t.RATE
                if mode == "handoff_late": publish(20000)
                if mode == "handoff_closed": assert lib.glrt_tracking_iq_owner_close(owner, 0) == 0
                if mode == "handoff_cancel": state['cancelled'] = True
            state['retained'].append((kind, s))
            state['now'] += 100_000
            return int(mode == f'retention_{kind}')
        except Exception as error:
            state['errors'].append(repr(error)); return -1

    try:
        block = np.ascontiguousarray(iq[:state['end']])
        assert lib.glrt_tracking_iq_owner_publish(owner, 3, first, block.ctypes.data,
            len(block), first+len(block)+lag, state['now']) == 0
        if mode == "cancelled": state['cancelled'] = True
        if mode == "source_deadline": deadline = first+state['end']+1000
        rc = lib.worker_test(work, owner, words, refs.ctypes.data, fft, clock, cancel, wait, retain,
                             None, deadline, budget, 0 if mode == "bad_lead" else 2500)
        final = summary(lib, work)
        assert not state['errors'], state['errors']
        assert lib.worker_status(work) == rc
        return rc, final, state
    finally:
        lib.worker_free(work); lib.seed_owner_free(owner)


@pytest.mark.parametrize("mode", ["positive", "large", "wait_resume"])
def test_owned_seed_resolves_builds_real_history_and_retains_future_proposal(worker, mode):
    rc, final, state = run(worker, mode)
    assert rc == 1 and final[3] == state['calls'] == 68
    kinds = [kind for kind, _ in state['retained']]
    assert kinds[:2] == [1, 2] and kinds[-1] == 4
    assert all(kind == 3 for kind in kinds[2:-1]) and len(kinds)-3 == final[4]
    assert final[4] == (18 if mode == "wait_resume" else 8)
    assert final[5] == (1 if mode == "wait_resume" else 0)
    assert final[6] == final[4] and final[7:10] == [1, 0, 1] and final[12] == t.RATE


@pytest.mark.parametrize("mode,expected,calls", [
    ("zero", -6, 68), ("ignored", 0, 0), ("cancelled", -4, 0), ("bad_lead", -1, 0),
    ("fft_cancel", -4, 3), ("fft_timeout", -3, 3), ("clock_regression", -7, 3),
    ("fft_error", -1, 3), ("source_closed", -2, 68), ("source_deadline", -3, 68),
    ("wait_timeout", -3, 68), ("wait_cancel", -4, 68), ("wait_error", -7, 68),
    ("retention_1", -5, 0), ("retention_2", -5, 68), ("retention_3", -5, 68),
    ("retention_4", -5, 68), ("handoff_late", -8, 68), ("handoff_closed", -2, 68),
    ("handoff_cancel", -4, 68),
])
def test_failure_cancellation_or_stale_retained_proposal_cannot_authorize_handoff(worker, mode, expected, calls):
    rc, final, state = run(worker, mode)
    assert rc == expected and final[3] == state['calls'] == calls
    assert final[7:10] == [0, 0, 0] and final[12] == 0
    if mode == "zero":
        assert final[6] == 0 and final[4] == 8 and all(kind != 4 for kind, _ in state['retained'])
    if mode == "wait_timeout": assert state['now'] >= 51_000_000 and final[5] > 0
