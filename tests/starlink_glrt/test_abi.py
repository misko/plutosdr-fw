"""Adversarial transport metadata checks; fixtures do not claim IIO/RF evidence."""
from dataclasses import replace
import struct

import pytest

from tools.starlink_glrt_abi import Event, Snapshot


def wire(words=None, header=None):
    if words is None:
        words = [0]*64
        words[0], words[2], words[4], words[6] = 1004, 1492, 123, 123
        words[8], words[12], words[14] = 106, 1000, 250
        words[19], words[20], words[21], words[23] = 24, 29, 1, 1
        words[57:61] = [15729, 19661, 9831, 1]
        words[62:64] = [10_000_000, 212]
    if header is None:
        header = 'GLR1 00010000 10000000 2500000 1 0 10000000 0 0 0 0 0 0 0'.split()
    return ' '.join(header+[f'{w:08x}' for w in words])


def attest(snapshot, **kwargs):
    snapshot.require_iq_prefix(**(dict(expected_visit=29, expected_rate=10_000_000,
                                     received_bytes=492, expected_samples=123) | kwargs))


def test_geometry_and_exact_received_prefix():
    s = Snapshot.decode(wire())
    attest(s)
    assert s.source_center(0) == 792 and s.source_center(122) == 1280
    assert s.duration_seconds.numerator == 123 and s.duration_seconds.denominator == 2_500_000
    for index in (-1, 123, True, 1.5):
        with pytest.raises(ValueError):
            s.source_center(index)


@pytest.mark.parametrize('index,value', [(0, 'PIL1'), (1, '00010001'), (2, '30000000'),
    (3, '10000000'), (4, '0'), (5, '2'), (7, '1'), (8, '1'), (9, '-1'), (13, '4294967296'),
    (14, '100000000'), (14, '0x00000000'), (14, '-0000001')])
def test_malformed_header_or_word(index, value):
    fields = wire().split()
    fields[index] = value
    with pytest.raises(ValueError):
        Snapshot.decode(' '.join(fields))


@pytest.mark.parametrize('word,value', [(0, 1005), (2, 1496), (6, 122), (12, 200), (14, 200),
    (17, 1), (18, 4), (19, 25), (19, 8), (20, 30), (21, 257), (22, 1), (44, 1), (46, 1)])
def test_reject_inconsistent_or_faulted_prefix(word, value):
    words = list(Snapshot.decode(wire()).words)
    words[word] = value
    with pytest.raises(ValueError):
        attest(Snapshot.decode(wire(words)))


@pytest.mark.parametrize('kwargs', [dict(received_bytes=488), dict(received_bytes=496),
    dict(expected_samples=122), dict(expected_rate=25_000_000), dict(expected_visit=30)])
def test_request_or_received_byte_mismatch(kwargs):
    with pytest.raises(ValueError):
        attest(Snapshot.decode(wire()), **kwargs)


def record(*, sequence=0, visit=29, detected=True):
    # Raw ratio 1/2 exact versus 1/16 control, defined integer score.
    w = [visit, sequence, 0, 1100, 0, 32768, 4096, (int(detected) << 27)+511]
    w += [1 << 22, 0, 1 << 22, 0, 32768, 0, 4096, 0]
    return w


def test_event_raw_score_and_cfo():
    event = Event.decode(struct.pack('<16I', *record()))
    event.require_decision(threshold=19661, margin=9831, enabled=True)
    assert float(event.cfo_hz()) == pytest.approx(-443.89204545454544)
    assert event.cfo_hz(control=True) == 0
    assert event.observable_interval(Snapshot.decode(wire())) is None
    with pytest.raises(ValueError):
        event.require_decision(threshold=40000, margin=0, enabled=True)


@pytest.mark.parametrize('index,value', [(0, 0), (5, 32769), (6, 4095), (7, 1 << 28),
    (8, 0), (9, 1 << 23), (11, 1 << 23), (13, 1 << 19), (15, 1 << 19)])
def test_reject_corrupt_event(index, value):
    w = record()
    w[index] = value
    with pytest.raises(ValueError):
        Event.decode(struct.pack('<16I', *w))


def test_event_sequence_accounting_and_explicit_loss():
    baseline = Snapshot.decode(wire())
    words = list(baseline.words)
    words[38] = words[53] = words[55] = 2
    final = replace(baseline, words=tuple(words), cpu_read=2, cpu_pushed=2)
    events = [Event.decode(struct.pack('<16I', *record(sequence=k))) for k in range(2)]
    final.require_events(events, baseline=baseline)
    for bad in (events[:1], events[::-1], events+events):
        with pytest.raises(ValueError):
            final.require_events(bad, baseline=baseline)
    for attr in ('cpu_disabled', 'cpu_full', 'cpu_malformed', 'cpu_fault'):
        with pytest.raises(ValueError):
            replace(final, **{attr: 1}).require_events(events, baseline=baseline)
