"""Actual GLA1 decisions select causal resolver IQ and initialize no fake history."""
import ctypes as c
from fractions import Fraction
from pathlib import Path
import struct
import subprocess

import numpy as np
import pytest

from tools.starlink_glrt_local_abi import LocalEvent
from .test_tracking_resolver import FFT, FFT_PORT, N, Result, oracle

RATE, SAMPLES, MAX = 2_500_000, 13_316, 2**64-1
Words = c.c_uint32*16


class View(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in
                ("first", "end", "source_now", "observed_ns", "generation")]
    _fields_ += [(name, c.c_uint32) for name in ("epoch", "valid", "closed")]


class Window(c.Structure):
    _fields_ = [("event", Words), ("maximum_age", c.c_uint32), ("first_repeat", c.c_uint32),
                ("seed_fraction", c.c_uint32), ("first", c.c_uint64), ("seed_start", c.c_uint64),
                ("starts", c.c_size_t*4), ("selected", View), ("copied", View)]


WRAPPER = r'''
#include "glrt_tracking_seed.h"
#include <assert.h>
#include <stdlib.h>
struct owned { struct glrt_tracking_iq_owner owner; int16_t *storage; };
void *seed_owner_new(size_t capacity, uint32_t epoch, uint64_t first)
{
    struct owned *p=calloc(1,sizeof(*p));assert(p);
    p->storage=calloc(2*capacity,sizeof(*p->storage));assert(p->storage);
    assert(!glrt_tracking_iq_owner_init(&p->owner,p->storage,capacity,epoch,first));
    return p;
}
void seed_owner_free(void *pointer)
{
    struct owned *p=pointer;
    assert(!glrt_tracking_iq_owner_close(&p->owner,0));
    assert(!glrt_tracking_iq_owner_destroy(&p->owner));free(p->storage);free(p);
}
size_t seed_live_size(void) { return sizeof(struct glrt_tracking_bootstrap_live); }
size_t seed_window_size(void) { return sizeof(struct glrt_tracking_seed_window); }
void seed_live_summary(const struct glrt_tracking_bootstrap_live *s, uint64_t out[10])
{
    out[0]=s->core.seed_start;out[1]=s->core.seed_fraction;out[2]=s->core.trend.history.epoch;
    out[3]=s->core.valid;out[4]=s->core.pending;out[5]=s->core.ready;out[6]=s->core.jobs;
    out[7]=s->core.trend.history.count;out[8]=s->source_deadline;out[9]=s->core.trend.rate;
}
double seed_live_cfo(const struct glrt_tracking_bootstrap_live *s) { return s->core.seed_cfo; }
'''

SOURCES = ["glrt_tracking_seed.c", "glrt_tracking_resolver.c", "glrt_tracking_iq_owner.c",
           "glrt_tracking_recent_iq.c", "glrt_tracking_bootstrap.c", "glrt_native_trend.c",
           "glrt_native_schedule.c", "glrt_tracking_schedule.c", "glrt_native_solver.c"]


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("tracking-seed")
    (out/"wrapper.c").write_text(WRAPPER)
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared",
                    "-fPIC", "-I", str(root/"tools"), str(out/"wrapper.c"),
                    *(str(root/"tools"/name) for name in SOURCES), "-lm", "-o", str(out/"seed.so")], check=True)
    lib = c.CDLL(str(out/"seed.so"))
    lib.glrt_tracking_seed_plan.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(Window)]
    lib.glrt_tracking_seed_copy.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32, c.c_void_p,
                                          c.c_size_t, c.POINTER(Window)]
    lib.glrt_tracking_seed_resolve.argtypes = [c.POINTER(Window), c.c_void_p, c.c_void_p, c.c_void_p,
                                             FFT_PORT, c.c_void_p, c.c_uint64, c.POINTER(Result), c.c_void_p]
    lib.seed_owner_new.argtypes = [c.c_size_t, c.c_uint32, c.c_uint64]
    lib.seed_owner_new.restype = c.c_void_p
    lib.seed_owner_free.argtypes = [c.c_void_p]
    lib.glrt_tracking_iq_owner_publish.argtypes = [c.c_void_p, c.c_uint32, c.c_uint64, c.c_void_p,
                                                 c.c_size_t, c.c_uint64, c.c_uint64]
    lib.glrt_tracking_iq_owner_close.argtypes = [c.c_void_p, c.c_int]
    lib.seed_live_size.restype = lib.seed_window_size.restype = c.c_size_t
    lib.seed_live_summary.argtypes = [c.c_void_p, c.c_void_p]
    lib.seed_live_cfo.argtypes = [c.c_void_p]
    lib.seed_live_cfo.restype = c.c_double
    assert lib.seed_window_size() == c.sizeof(Window)
    return lib


def event(first=1_000_000, epoch=1234):
    return Words(0x474C4131, 3, 8, first % 2**32, first >> 32,
                 (epoch << 16) | (4 << 6) | 1, 123, 23000, 6000, 6000, 6000, 6000, 14000, 0, 0, 0)


def view(words, end=None, *, lag=0):
    first = words[3] | words[4] << 32
    end = first+447851 if end is None else end
    return View(first, end, end+lag, 100, 2, words[1], 1, 0)


def planned(seed, words=None, source=None):
    words = event() if words is None else words
    source = view(words) if source is None else source
    window = Window()
    assert seed.glrt_tracking_seed_plan(words, c.byref(source), RATE, c.byref(window)) == 1
    window.copied = source
    return window


@pytest.mark.parametrize("first", [0, 1_000_000, 2**60+17, MAX-3_000_000])
@pytest.mark.parametrize("epoch", [0, 1234, 3332])
def test_integer_window_selection_matches_independent_fraction_oracle(seed, first, epoch):
    words = event(first, epoch)
    origin = first+epoch+22
    for repeat in (63, 64, 65, 66, 133, 134, 135, 744):
        for margin in (0, 1, 3325):
            end = origin+round(Fraction(repeat*RATE, 750))+N+8+margin
            source = view(words, end)
            last = int(Fraction((end-origin-N-8)*750, RATE))
            window = Window()
            rc = seed.glrt_tracking_seed_plan(words, c.byref(source), RATE, c.byref(window))
            if last < 63:
                assert rc == -2 and bytes(window) == bytes(Window())
                continue
            assert rc == 1 and window.first_repeat == last-63
            exact = Fraction(origin)+Fraction((last-63)*RATE, 750)
            positions = [round(exact+Fraction(n*RATE, 750)) for n in range(4)]
            assert window.first == min(positions)-8
            assert list(window.starts) == [position-window.first for position in positions]
            assert window.seed_start*65536+window.seed_fraction == round(exact*65536)
            assert window.first+SAMPLES == max(positions)+N+8 <= source.end
            assert bytes(window.selected) == bytes(source) and bytes(window.copied) == bytes(View())


@pytest.mark.parametrize("damage,rc", [
    ("missing_view", -1), ("invalid", -1), ("closed", -1), ("epoch", -1), ("unobserved", -1),
    ("generation", -1), ("reversed", -1), ("future_iq", -1), ("zero_age", -1), ("large_age", -1),
    ("future_event", -2), ("partial_event", -2), ("expired", -2), ("too_few_pilots", -2),
    ("overwritten", -2), ("source_wrap", -2),
])
def test_unavailable_or_invalid_history_cannot_produce_a_plan(seed, damage, rc):
    words = event(); source = view(words); age = RATE
    if damage == "invalid": source.valid = 0
    elif damage == "closed": source.closed = 1
    elif damage == "epoch": source.epoch += 1
    elif damage == "unobserved": source.observed_ns = 0
    elif damage == "generation": source.generation = 0
    elif damage == "reversed": source.first = source.end+1
    elif damage == "future_iq": source.source_now = source.end-1
    elif damage == "zero_age": age = 0
    elif damage == "large_age": age = RATE+1
    elif damage == "future_event": source = View(0, 100, 100, 100, 2, 3, 1, 0)
    elif damage == "partial_event": source.end = source.source_now = source.first+13999
    elif damage == "expired": source.source_now = source.first+RATE+1
    elif damage == "too_few_pilots": source.end = source.source_now = source.first+210000
    elif damage == "overwritten": source.first = planned(seed).first+1
    elif damage == "source_wrap":
        words = event(MAX-13999); source = view(words, MAX)
    out = Window(); c.memset(c.byref(out), 0x55, c.sizeof(out))
    assert seed.glrt_tracking_seed_plan(words, None if damage == "missing_view" else c.byref(source),
                                       age, c.byref(out)) == rc
    assert bytes(out) == bytes(Window())


def test_selection_uses_retained_end_not_receiver_time(seed):
    words = event(); source = view(words)
    a = planned(seed, words, source)
    source.source_now += 65536
    b = planned(seed, words, source)
    assert (a.first, a.seed_start, list(a.starts)) == (b.first, b.seed_start, list(b.starts))
    assert a.selected.source_now+65536 == b.selected.source_now
    source.first = b.first
    assert planned(seed, words, source).first == source.first  # inclusive retained boundary


def test_c_gate_preserves_existing_python_event_contract(seed):
    rng = np.random.default_rng(474)  # deterministic malformed-field corpus
    cases = [event()]
    for flags in [0, 1, 3, 5, 9, 57, 0xFFF0001, 3332 << 16 | 1, 3333 << 16 | 1,
                  4 << 6 | 1, 5 << 6 | 1, 10 << 12 | 1, 11 << 12 | 1, 1 << 28]:
        words = event(); words[5] = flags
        if flags == 3:
            for i in range(6, 12): words[i] = 0
        cases.append(words)
    for index in [0, 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]:
        for value in [0, 1, 4000, 4001, 2**32-4000, 2**32-4001, 65536, 65537, 2**32-1,
                      *rng.integers(0, 2**32, 30).tolist()]:
            words = event(); words[index] = value; cases.append(words)
    for words in cases:
        try:
            decoded = LocalEvent.decode(struct.pack("<16I", *words))
            expected = int(decoded.decision and not decoded.reasons)
        except ValueError:
            expected = -1
        out = Window(); c.memset(c.byref(out), 0x55, c.sizeof(out))
        source = view(words)
        assert seed.glrt_tracking_seed_plan(words, c.byref(source), RATE, c.byref(out)) == expected
        if expected != 1: assert bytes(out) == bytes(Window())
    assert seed.glrt_tracking_seed_plan(None, None, RATE, c.byref(Window())) == -1
    # Ignored records and malformed records never touch the owner or output IQ.
    words = event(); words[5] &= ~1
    assert seed.glrt_tracking_seed_copy(None, words, RATE, None, 0, c.byref(Window())) == 0


@pytest.mark.parametrize("mode", ["normal", "wrapped_ring", "closed", "lost", "stale", "short_output", "expired"])
def test_seed_copies_exact_owned_iq_and_fences_failed_views(seed, mode):
    words = event(2**60+17); first = words[3] | words[4] << 32
    count = 447851; capacity = 230000 if mode == "wrapped_ring" else 500000
    iq = np.arange(count*2, dtype=np.int64).astype(np.int16).reshape(-1, 2)
    owner = seed.seed_owner_new(capacity, words[1], first)
    out = np.full((SAMPLES, 2), 1234, dtype=np.int16)
    try:
        for offset in range(0, count, 16384):
            block = np.ascontiguousarray(iq[offset:offset+16384]); end = first+offset+len(block)
            assert seed.glrt_tracking_iq_owner_publish(owner, words[1], first+offset, block.ctypes.data,
                                                       len(block), end+1000, 100+offset) == 0
        if mode in ("closed", "lost"):
            assert seed.glrt_tracking_iq_owner_close(owner, int(mode == "lost")) == 0
        if mode == "stale": words[1] += 1
        window = Window(); c.memset(c.byref(window), 0x55, c.sizeof(window))
        rc = seed.glrt_tracking_seed_copy(owner, words, 1 if mode == "expired" else RATE,
            out.ctypes.data, SAMPLES-int(mode == "short_output"), c.byref(window))
        if mode in ("normal", "wrapped_ring"):
            assert rc == 1
            np.testing.assert_array_equal(out, iq[window.first-first:window.first-first+SAMPLES])
            assert window.copied.end == first+count and window.copied.source_now == first+count+1000
            assert window.copied.generation == window.selected.generation and window.copied.valid
        else:
            assert rc < 0 and bytes(window) == bytes(Window()) and np.all(out == 1234)
    finally:
        seed.seed_owner_free(owner)


def resolve(seed, window, reference, iq, *, damage=None):
    workspace = (c.c_double*(FFT*3))()
    live = c.create_string_buffer(seed.seed_live_size())
    result = Result(); calls = []
    c.memset(live, 0x55, len(live)); c.memset(c.byref(result), 0x55, c.sizeof(result))

    @FFT_PORT
    def fft(context, data, count):
        calls.append(count)
        if damage == "fft_fail" and len(calls) == 3: return -1
        values = np.ctypeslib.as_array(data, shape=(count*2,)).view(np.complex128)
        values[:] = np.fft.fft(values)
        return 0

    deadline = window.copied.source_now+(0 if damage == "deadline" else RATE*2)
    rc = seed.glrt_tracking_seed_resolve(c.byref(window), workspace,
        reference.ctypes.data, iq.ctypes.data, fft, None, deadline, c.byref(result), live)
    summary = (c.c_uint64*10)(); seed.seed_live_summary(live, summary)
    return rc, result, live, list(summary), calls


@pytest.mark.parametrize("first_repeat", [69, 70, 71])
@pytest.mark.parametrize("shift,cfo", [(-8, -511246), (3, 511246), (8, 399999)])
def test_full_resolver_initializes_exact_seed_without_claiming_tracking_support(seed, first_repeat, shift, cfo):
    words = event(2**60+17)
    origin = (words[3] | words[4] << 32)+(words[5] >> 16)+22
    source = view(words, origin+int(Fraction((first_repeat+63)*RATE, 750))+N+9)
    window = planned(seed, words, source)
    assert window.first_repeat == first_repeat
    rng = np.random.default_rng(13316)
    reference = rng.integers(-1200, 1201, (N, 2), dtype=np.int16)
    iq = rng.integers(-50, 51, (SAMPLES, 2), dtype=np.int16)
    signal = (reference[:, 0]+1j*reference[:, 1])*np.exp(2j*np.pi*cfo*np.arange(N)/RATE)
    for start in window.starts:
        iq[start+shift:start+shift+N] = np.rint(np.column_stack((signal.real, signal.imag)))
    rc, result, live, summary, calls = resolve(seed, window, reference, iq)
    assert rc == 1 and calls == [FFT]*68
    np.testing.assert_allclose([(p.shift, p.cfo, p.coherence) for p in result.hypotheses],
                               oracle(reference, iq, list(window.starts)), rtol=2e-12, atol=2e-8)
    assert result.best.shift == shift and abs(result.best.cfo-cfo) < 5
    assert summary == [window.seed_start+shift, window.seed_fraction, words[1], 1, 0, 0, 0, 0,
                       source.source_now+RATE*2, RATE]
    assert seed.seed_live_cfo(live) == result.best.cfo


@pytest.mark.parametrize("damage", ["first", "fraction", "repeat", "start", "seed_start", "closed",
    "invalid", "epoch", "overwritten", "short_iq", "future_iq", "source_regression", "time_regression",
    "generation_regression", "expired_copy", "deadline", "fft_fail", "empty_reference"])
def test_forged_stale_or_failed_resolver_cannot_initialize_bootstrap(seed, damage):
    window = planned(seed)
    if damage == "first": window.first += 1
    elif damage == "fraction": window.seed_fraction ^= 1
    elif damage == "repeat": window.first_repeat += 1
    elif damage == "start": window.starts[1] += 1
    elif damage == "seed_start": window.seed_start += 1
    elif damage == "closed": window.copied.closed = 1
    elif damage == "invalid": window.copied.valid = 0
    elif damage == "epoch": window.copied.epoch += 1
    elif damage == "overwritten": window.copied.first = window.first+1
    elif damage == "short_iq": window.copied.end = window.first+SAMPLES-1
    elif damage == "future_iq": window.copied.end = window.copied.source_now+1
    elif damage == "source_regression":
        window.copied.source_now -= 1; window.copied.end -= 1
    elif damage == "time_regression": window.copied.observed_ns -= 1
    elif damage == "generation_regression": window.copied.generation -= 1
    elif damage == "expired_copy": window.copied.source_now = window.event[3]+RATE+1
    reference = np.ones((N, 2), dtype=np.int16)
    if damage == "empty_reference": reference[:] = 0
    iq = np.ones((SAMPLES, 2), dtype=np.int16)
    rc, result, live, _, calls = resolve(seed, window, reference, iq, damage=damage)
    assert rc == -1 and bytes(result) == bytes(Result()) and bytes(live) == bytes(len(live))
    assert len(calls) == (3 if damage == "fft_fail" else 0)


def test_numerical_zero_result_does_not_fabricate_accepted_history(seed):
    window = planned(seed)
    reference = np.ones((N, 2), dtype=np.int16); iq = np.zeros((SAMPLES, 2), dtype=np.int16)
    rc, result, _, summary, calls = resolve(seed, window, reference, iq)
    assert rc == 1 and result.best.coherence == 0 and calls == [FFT]*68
    assert summary[3:8] == [1, 0, 0, 0, 0]  # initialized candidate, no job/history/handoff
