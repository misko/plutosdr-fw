"""Actual C controller through narrow ports and a deterministic source clock.

The fake models finite admission, immutable queued heads and terminal counters.
It is an I/O/ownership test, not RTL or physical-signal precision evidence.
"""
import ctypes as c
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_glrt.test_native_solver import packet
from tests.starlink_glrt.test_native_trend import Batch
from tools.starlink_glrt_native_replay import coefficients
from tools.starlink_glrt_schedule_abi import ScheduleBatch

ROOT = Path(__file__).resolve().parents[2]
Read = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_char_p, c.c_void_p, c.c_size_t)
Write = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_char_p, c.c_void_p, c.c_size_t)
Retain = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_char_p, c.c_void_p, c.c_size_t)
Clock = c.CFUNCTYPE(c.c_double, c.c_void_p)


class Ports(c.Structure):
    _fields_ = [("context", c.c_void_p), ("read", Read), ("write", Write),
                ("retain", Retain), ("clock", Clock)]


@pytest.fixture(scope="module")
def controller(tmp_path_factory):
    out = tmp_path_factory.mktemp("native-controller")
    (out/"wrapper.c").write_text('#include "glrt_native_controller.h"\n'
                                'size_t controller_size(void) { return sizeof(struct glrt_native_controller); }\n')
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(ROOT/"tools"), str(out/"wrapper.c"),
                    *(str(ROOT/"tools"/f"glrt_native_{name}.c") for name in
                      ("controller", "trend", "schedule", "solver")),
                    str(ROOT/"tools/glrt_tracking_schedule.c"),
                    "-lm", "-o", str(out/"controller.so")], check=True)
    lib = c.CDLL(str(out/"controller.so"))
    lib.controller_size.restype = c.c_size_t
    lib.glrt_native_controller_init.argtypes = [c.c_void_p, c.POINTER(Ports), c.POINTER(Batch),
                                              c.c_uint32, c.c_double]
    lib.glrt_native_controller_init_sliced.argtypes = lib.glrt_native_controller_init.argtypes
    lib.glrt_native_controller_tick.argtypes = [c.c_void_p]
    lib.glrt_native_controller_request_stop.argtypes = [c.c_void_p]
    return lib


@pytest.fixture(scope="module")
def pilot_words():
    raw = np.asarray(coefficients((ROOT/"hdl/library/starlink_glrt/native_cubic_60000000_upper.mem")
                                 .read_bytes()), dtype=np.int64)
    # Exact zero-residual local reference: keeps ownership tests independent of
    # supplied estimates while using real C moment decoding and the solver.
    return packet(raw[:, :2], raw)


class Radio:
    def __init__(self, controller, pilot_words, frames=128):
        self.lib = controller
        self.template = pilot_words
        self.state = c.create_string_buffer(controller.controller_size())
        self.time = 0.0
        self.origin = 2**60
        self.latest = self.origin
        self.epoch = 3
        self.valid = True
        self.fault = 0
        self.configured = self.admitted = self.popped = self.cancelled = 0
        self.highwater = 0
        self.pending = []
        self.queue = []
        self.events = []
        self.descriptors = []
        self.errors = []
        self.fail_retain = None
        self.fail_write = None
        self.bad_head = False
        self.reject = False
        self.gap = False
        self.submit_return_error = False
        self.pop_return_error = False
        self.retention_delay = 0
        self.gap_on_descriptor = False
        self.ports = Ports(None, Read(self.read), Write(self.write), Retain(self.retain), Clock(lambda _: self.time))
        self.seed = Batch(epoch=3, tag=7, start=self.origin+300000, fraction=0,
                          period=80000*65536, step=7310173*65536, delta=0, seed=17,
                          repeats=16, expires=self.origin+300000+16*80000)
        assert controller.glrt_native_controller_init(self.state, c.byref(self.ports),
                                                      c.byref(self.seed), frames, 2) == 0

    def advance(self, samples=3000):
        self.latest += samples
        self.time = (self.latest-self.origin)/60000000
        while self.pending and self.pending[0][0]+79199 <= self.latest:
            start, b, repeat = self.pending.pop(0)
            w = list(self.template)
            w[1:9] = [self.admitted, b.tag, start % 2**32, start >> 32,
                       b.seed, b.prediction(repeat)[1], 79200, 0]
            w[27] = repeat
            if self.reject:
                w[9:25] = [0]*16
            self.admitted += 1
            self.queue.append(w)
            self.highwater = max(self.highwater, len(self.queue))

    def snapshot(self):
        ready = len({b.tag for _, b, _ in self.pending}) < 2
        status = int(ready) | 2 | (4 if self.pending else 0) | (8 if self.queue else 0)
        status |= (16 if self.valid else 0) | (0 if self.gap else 32)
        w = [0x474c5331, 1, self.epoch, self.latest % 2**32, self.latest >> 32,
             status, self.fault, self.configured, self.admitted, 0, 0, 0, 0,
             self.cancelled, self.admitted, self.popped, len(self.queue), self.highwater, 0, 0]
        return ("GLS1SNAP 00010000 " + " ".join(f"{x:08x}" for x in w)+"\n").encode()

    def read(self, _, name, output, size):
        try:
            name = name.decode()
            if name == "native_schedule_snapshot":
                data = self.snapshot()
            else:
                assert name == "native_schedule_result" and self.queue
                w = list(self.queue[0])
                if self.bad_head:
                    w[2] += 1000
                data = ("GLS1 00010000 " + " ".join(f"{x:08x}" for x in (self.epoch, *w))+"\n").encode()
            assert len(data) <= size
            c.memmove(output, data, len(data))
            self.events.append(("read", name, data))
            return len(data)
        except Exception as e:
            self.errors.append(e)
            return -1

    def retain(self, _, name, data, size):
        name, data = name.decode(), c.string_at(data, size)
        self.events.append(("retain", name, data))
        if name == self.fail_retain:
            return -1
        if name == "descriptor" and self.retention_delay:
            self.advance(self.retention_delay)
        if name == "descriptor" and self.gap_on_descriptor:
            self.gap = True
        return 0

    def write(self, _, name, data, size):
        try:
            name, data = name.decode(), c.string_at(data, size)
            self.events.append(("write", name, data))
            if name == self.fail_write:
                return -1
            if name == "native_schedule_submit":
                b = ScheduleBatch(*[int(v, 16) for v in data.split()])
                assert any(kind == "retain" and key == "descriptor" and body.endswith(data)
                           for kind, key, body in self.events)
                assert b.prediction(0)[0] > self.latest, "submitted an already late descriptor"
                assert len({old.tag for _, old, _ in self.pending}) < 2
                self.descriptors.append(b)
                self.configured += b.repeats
                self.pending.extend((b.prediction(r)[0], b, r) for r in range(b.repeats))
                if self.submit_return_error:
                    return -1
            elif name == "native_schedule_pop":
                epoch, seq = (int(x, 16) for x in data.split())
                assert self.queue and epoch == self.epoch and seq == self.queue[0][1]
                assert self.events[-2][:2] == ("retain", "estimate")
                assert self.events[-3][:2] == ("retain", "head")
                self.queue.pop(0)
                self.popped += 1
                if self.pop_return_error:
                    return -1
            else:
                assert name == "native_schedule_command"
                if data.strip() == b"2":
                    self.cancelled += len(self.pending)
                    self.pending.clear()
                else:
                    assert data.strip() == b"4" and not self.pending and not self.queue
                    assert self.events[-2][:2] == ("retain", "drained")
                    self.configured = self.admitted = self.popped = self.cancelled = self.highwater = 0
                    self.valid = False
                    self.fault = 0
            return size
        except Exception as e:
            self.errors.append(e)
            return -1

    def tick(self):
        rc = self.lib.glrt_native_controller_tick(self.state)
        assert not self.errors, self.errors
        return rc

    def run(self):
        for _ in range(10000):
            rc = self.tick()
            if rc != 1:
                return rc
            self.advance()
        pytest.fail("controller did not finish its bounded run")

    def writes(self, suffix):
        return [body for kind, name, body in self.events
                if kind == "write" and name == "native_schedule_"+suffix]


def test_every_repeat_feedback_retains_before_submit_and_pop(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.run() == 0
    heads = [data for kind, name, data in radio.events if (kind, name) == ("retain", "head")]
    assert len(heads) == 128
    assert len(radio.descriptors) == 8
    assert [b.tag for b in radio.descriptors] == list(range(7, 15))
    assert [b.start for b in radio.descriptors] == [radio.seed.start+n*80000 for n in range(0, 128, 16)]
    assert radio.writes("command") == [b"4\n"]
    assert not radio.queue and not radio.pending and not radio.valid
    assert radio.events[-1][:2] == ("retain", "final")


@pytest.mark.parametrize("initial_repeats", [9, 12, 16])
def test_short_bootstrap_then_full_batches_preserve_every_frame(controller, pilot_words, initial_repeats):
    radio = Radio(controller, pilot_words, frames=64)
    radio.seed.repeats = initial_repeats
    radio.seed.expires = radio.seed.start+initial_repeats*80000-801
    assert controller.glrt_native_controller_init(radio.state, c.byref(radio.ports),
        c.byref(radio.seed), 64, 2) == 0
    assert radio.run() == 0
    estimates = [body.split() for kind, name, body in radio.events
                 if (kind, name) == ("retain", "estimate")]
    assert [int(row[2]) for row in estimates] == list(range(64))
    assert all(int(row[8]) == 0 for row in estimates)
    starts = [batch.prediction(repeat)[0] for batch in radio.descriptors
              for repeat in range(batch.repeats)]
    assert starts == [radio.seed.start+frame*80000 for frame in range(64)]
    assert radio.descriptors[0].repeats == initial_repeats
    assert all(batch.repeats == 16 for batch in radio.descriptors[1:-1])
    assert sum(batch.repeats for batch in radio.descriptors) == 64
    assert radio.writes("command") == [b"4\n"]


def test_eight_bootstrap_frames_leave_no_lead_for_the_first_feedback_batch(controller, pilot_words):
    radio = Radio(controller, pilot_words, frames=64)
    radio.seed.repeats = 8
    assert controller.glrt_native_controller_init(radio.state, c.byref(radio.ports),
        c.byref(radio.seed), 64, 2) == 0
    # The trend requires eight observations. The last one completes only 800
    # source samples before frame 8; submission requires at least 6,000 samples.
    assert radio.run() == -5
    assert len(radio.descriptors) == 1
    assert len(radio.writes("pop")) == 8
    assert radio.writes("command") == [b"2\n", b"4\n"]
    assert not radio.pending and not radio.queue and not radio.valid


@pytest.mark.parametrize("kind", ["initial", "descriptor", "head", "estimate", "drained", "final"])
def test_retention_failure_never_acknowledges_unretained_head(controller, pilot_words, kind):
    radio = Radio(controller, pilot_words, frames=16)
    radio.fail_retain = kind
    assert radio.run() == -6
    if kind in ("initial", "descriptor"):
        assert not radio.descriptors
    if kind in ("head", "estimate"):
        assert len(radio.queue) == 1 and not radio.writes("pop")
    assert radio.writes("command").count(b"2\n") == 1
    previous = list(radio.events)
    assert radio.tick() == -6 and radio.events == previous


def test_uncertain_submit_is_never_retried_and_cancelled(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.submit_return_error = True
    assert radio.run() == -1
    assert len(radio.writes("submit")) == 1
    assert radio.writes("command") == [b"2\n", b"4\n"]
    assert not radio.pending and not radio.queue


def test_uncertain_pop_cannot_pop_next_head_or_clear_evidence(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(600000)
    assert len(radio.queue) > 1
    radio.pop_return_error = True
    assert radio.tick() == -1
    assert len(radio.writes("pop")) == 1 and radio.queue
    assert radio.writes("command") == [b"2\n"]


def test_mismatched_head_is_retained_and_never_popped(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.bad_head = True
    assert radio.run() == -2
    assert radio.queue and not radio.writes("pop")
    assert any(e[:2] == ("retain", "head") for e in radio.events)


def test_rejected_bootstrap_loses_acquisition_without_predicting(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.reject = True
    assert radio.run() == -4
    assert len(radio.writes("submit")) == 1
    assert len(radio.writes("pop")) == 16
    assert radio.writes("command") == [b"2\n", b"4\n"]


def test_source_gap_cancels_future_but_drains_associated_evidence(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(600000)
    queued = len(radio.queue)
    radio.gap = True
    assert radio.run() == -3
    assert len(radio.writes("submit")) == 1
    assert len(radio.writes("pop")) == queued
    assert radio.writes("command") == [b"2\n", b"4\n"]


def test_requested_stop_drains_and_clears(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(600000)
    controller.glrt_native_controller_request_stop(radio.state)
    assert radio.run() == -5
    assert not radio.queue and not radio.pending and not radio.valid


def test_slow_descriptor_retention_cannot_submit_past_source_deadline(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.retention_delay = 600000
    assert radio.run() == -5
    assert not radio.writes("submit")


def test_source_gap_during_retention_cannot_submit(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    radio.gap_on_descriptor = True
    assert radio.run() == -3
    assert not radio.writes("submit")


def test_failed_cancel_leaves_queued_evidence_for_operator_recovery(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(600000)
    radio.gap = True
    radio.fail_write = "native_schedule_command"
    assert radio.tick() == -3
    assert radio.queue and not radio.writes("pop")
    assert radio.writes("command") == [b"2\n"]


def test_epoch_change_never_associates_or_acknowledges_foreign_heads(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(600000)
    radio.epoch += 1
    assert radio.tick() == -3
    assert radio.queue and not radio.writes("pop")


def test_elapsed_deadline_drains_and_stops_submissions(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.tick() == 1
    radio.advance(126000000)
    assert radio.run() == -5
    assert len(radio.writes("submit")) == 1
    assert len(radio.writes("pop")) == 16
    assert radio.writes("command") == [b"2\n", b"4\n"]
