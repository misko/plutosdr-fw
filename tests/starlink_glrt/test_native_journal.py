"""Independent review of C-produced journals and retained, stopped-writer recovery."""
import ctypes as c

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tools.starlink_glrt_native_journal import descriptors, records, recover, review


def journal(radio):
    return b"GLRJ1\n"+b"".join(name.encode()+b" "+str(len(raw)).encode()+b"\n"+raw
                              for kind, name, raw in radio.events if kind == "retain")


def retained(kind, raw):
    return kind.encode()+b" "+str(len(raw)).encode()+b"\n"+raw


class Port:
    def __init__(self, radio):
        self.radio = radio
        self.evidence = []

    def read(self, name):
        buf = c.create_string_buffer(512)
        n = self.radio.read(None, name.encode(), buf, 512)
        assert not self.radio.errors
        if n < 0:
            raise OSError("read failed")
        return buf.raw[:n].decode()

    def command(self, name, value):
        text = (str(value).strip()+"\n").encode()
        # Fake C controller enforces a preceding estimate; recovery needs only
        # the separately retained associated raw head. Preserve its assertion
        # and additionally require the real recovery retention here.
        if name == self.radio.prefix+"pop":
            assert self.evidence and self.evidence[-1][0] == "head"
            self.radio.events.extend([("retain", "head", self.evidence[-1][1].encode()),
                                      ("retain", "estimate", b"recovery-only")])
        if name == self.radio.prefix+"command" and value == 4:
            self.radio.events.append(("retain", "drained", self.evidence[-1][1].encode()))
        n = self.radio.write(None, name.encode(), text, len(text))
        assert not self.radio.errors, self.radio.errors
        if n < 0:
            raise OSError("uncertain command")

    def retain(self, kind, raw):
        self.evidence.append((kind, raw))


def test_independent_review_accepts_complete_journal_from_actual_c_controller(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    assert radio.run() == 0
    checked = review(journal(radio), epoch=3)
    assert len(checked["heads"]) == checked["supported"] == 128
    assert [e["frame"] for e in checked["estimates"]] == list(range(128))
    assert checked["drained"].popped == 128 and checked["final"].configured == 0


@pytest.mark.parametrize("corruption", ["truncated_header", "truncated_payload", "bad_length", "bad_kind",
                                       "unknown_tag", "nan", "missing_estimate", "missing_drain",
                                       "future_owner", "extra_final", "epoch", "duplicate_tag"])
def test_incomplete_or_misassociated_evidence_cannot_pass_review(controller, pilot_words, corruption):
    radio = Radio(controller, pilot_words, frames=16)
    assert radio.run() == 0
    entries, _ = records(journal(radio))
    pairs = [(entry.kind, entry.payload) for entry in entries]
    if corruption == "truncated_header": pairs.append(("head", b"incomplete"))
    elif corruption == "truncated_payload": pairs.append(("head", b"incomplete"))
    elif corruption == "unknown_tag":
        at = next(i for i, (k, _) in enumerate(pairs) if k == "head")
        fields = pairs[at][1].split(); fields[5] = b"00000008"
        pairs[at] = ("head", b" ".join(fields)+b"\n")
    elif corruption == "nan":
        at = next(i for i, (k, _) in enumerate(pairs) if k == "estimate")
        fields = pairs[at][1].split(); fields[3] = b"nan"
        pairs[at] = ("estimate", b" ".join(fields)+b"\n")
    elif corruption in ("missing_estimate", "missing_drain"):
        wanted = "estimate" if corruption == "missing_estimate" else "drained"
        pairs.pop(next(i for i, (k, _) in enumerate(pairs) if k == wanted))
    elif corruption == "future_owner":
        at = next(i for i, (k, _) in enumerate(pairs) if k == "descriptor")
        pairs.append(pairs.pop(at))
    elif corruption == "extra_final": pairs.append(pairs[-1])
    elif corruption == "duplicate_tag":
        at = next(i for i, (k, _) in enumerate(pairs) if k == "descriptor")
        pairs.insert(at+1, pairs[at])
    data = b"GLRJ1\n"+b"".join(retained(k, raw) for k, raw in pairs)
    if corruption == "truncated_header": data = data[:-13]
    elif corruption == "truncated_payload": data = data[:-1]
    elif corruption == "bad_length": data = data.replace(b"initial 201", b"initial 9999") if b"initial 201" in data else b"GLRJ1\nhead 9999\n"
    elif corruption == "bad_kind": data += b"forged 0\n"
    with pytest.raises(ValueError):
        review(data, epoch=4 if corruption == "epoch" else 3)


def stopped(radio):
    assert radio.tick() == 1
    radio.advance(600000)
    assert len(radio.queue) > 1
    # Simulate process death before any reads or POP; hardware remains live.
    return journal(radio)


@pytest.mark.parametrize("tail", [b"", b"head 312\nGLS1", b"hea"])
def test_recovery_retains_and_associates_heads_after_process_death(controller, pilot_words, tail):
    radio = Radio(controller, pilot_words)
    data = stopped(radio)+tail
    port = Port(radio)
    queued = len(radio.queue)
    result = recover(port, data, epoch=3, writer_stopped=True, retain=port.retain, deadline=1,
                     clock=lambda: radio.time, sleep=lambda _: radio.advance())
    assert result.configured == 0 and not result.status & 16
    assert len([k for k, _ in port.evidence if k == "head"]) == queued
    assert not radio.queue and not radio.pending


def test_uncertain_pop_reconciles_one_advancement_without_repeating_ack(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    data = stopped(radio)
    radio.pop_return_error = True
    queued = len(radio.queue)
    port = Port(radio)
    recover(port, data, epoch=3, writer_stopped=True, retain=port.retain, deadline=1,
            clock=lambda: radio.time)
    assert len(radio.writes("pop")) == queued
    assert not radio.queue


@pytest.mark.parametrize("failure", ["writer_live", "epoch", "unknown_owner", "retention", "pop", "deadline"])
def test_failed_recovery_never_clears_unretained_or_unassociated_heads(controller, pilot_words, failure):
    radio = Radio(controller, pilot_words)
    data = stopped(radio)
    port = Port(radio)
    if failure == "unknown_owner": data = b"GLRJ1\n"
    if failure == "pop": radio.fail_write = "native_schedule_pop"
    def retain(kind, raw):
        if failure == "retention" and kind == "head": raise OSError("storage full")
        port.retain(kind, raw)
    with pytest.raises((ValueError, OSError, TimeoutError)):
        recover(port, data, epoch=4 if failure == "epoch" else 3,
                writer_stopped=failure != "writer_live", retain=retain,
                deadline=-1 if failure == "deadline" else 1, clock=lambda: radio.time)
    assert radio.queue and b"4\n" not in radio.writes("command")


def test_partial_descriptor_is_not_an_authorization_to_pop(controller, pilot_words):
    radio = Radio(controller, pilot_words)
    data = stopped(radio)
    entries, _ = records(data)
    descriptor = next(entry for entry in entries if entry.kind == "descriptor")
    data = data[:data.index(retained("descriptor", descriptor.payload))]+b"descriptor 200\nframe 0 3"
    entries, partial = records(data, allow_partial=True)
    assert partial and not descriptors(entries, epoch=3)
