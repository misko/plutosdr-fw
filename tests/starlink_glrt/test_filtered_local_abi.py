"""Filtered acquisition records retain native geometry and reject GLA1 confusion."""
from fractions import Fraction
import struct

import pytest

from tools.starlink_glrt_local_abi import FilteredLocalEvent, LocalEvent, U64_MAX, WINDOW


def record(rate, first=None):
    stride, delay = {5000000: (2, 100), 15000000: (6, 318)}[rate]
    first = 2 * delay if first is None else first + (-first) % stride
    return [0x474c4132, 517, 8, first % 2**32, first >> 32,
            (17 << 16) | (4 << 12) | (3 << 6) | 1, (-1234) % 2**32,
            65000, 10000, 9000, 1000, 11000, WINDOW, rate, stride, delay]


def decode(words):
    return FilteredLocalEvent.decode(struct.pack('<16I', *words))


@pytest.mark.parametrize('rate', [5000000, 15000000])
@pytest.mark.parametrize('first', [None, 2**53 + 19, 2**64 - 100000])
@pytest.mark.parametrize('offset', [0, 17 * 65536 + 1, 3300 * 65536 + 32768, (WINDOW - 1) * 65536])
def test_exact_native_mapping_and_fir_support(rate, first, offset):
    words = record(rate, first)
    event = decode(words)
    assert event.words == tuple(words)
    assert event.native_rate == rate and event.cfo_hz == -123400
    expected = Fraction(event.first - event.filter_delay) + Fraction(offset, 65536) * event.stride
    assert Fraction(event.native_q16(offset), 65536) == expected
    event.require_native_support(event.required_native_first, event.native_last + 1)
    with pytest.raises(ValueError, match='support'):
        event.require_native_support(event.required_native_first + 1, event.native_last + 1)
    with pytest.raises(ValueError, match='support'):
        event.require_native_support(event.required_native_first, event.native_last)
    with pytest.raises(ValueError, match='identity'):
        LocalEvent.decode(struct.pack('<16I', *words))


@pytest.mark.parametrize('rate', [5000000, 15000000])
@pytest.mark.parametrize('damage', ['magic', 'visit', 'rate', 'stride', 'delay', 'phase',
    'warmup', 'wrap', 'window', 'flags', 'cfo', 'score', 'empty', 'candidate_reason'])
def test_filtered_geometry_and_payload_fail_closed(rate, damage):
    words = record(rate)
    if damage == 'magic': words[0] = 0x474c4131
    if damage == 'visit': words[1] = 0
    if damage == 'rate': words[13] = 30000000
    if damage == 'stride': words[14] += 1
    if damage == 'delay': words[15] += 1
    if damage == 'phase': words[3] += 1
    if damage == 'warmup': words[3] -= words[14]
    if damage == 'wrap':
        first = U64_MAX - U64_MAX % words[14]
        words[3:5] = [first % 2**32, first >> 32]
    if damage == 'window': words[12] -= 1
    if damage == 'flags': words[5] |= 1 << 28
    if damage == 'cfo': words[6] = 4001
    if damage == 'score': words[7] = 65537
    if damage == 'empty': words[5] = 3
    if damage == 'candidate_reason': words[5] = (words[5] & ~1) | 4
    with pytest.raises(ValueError): decode(words)


@pytest.mark.parametrize('offset', [-1, WINDOW * 65536, 1.5, True])
def test_mapping_rejects_nonlocal_or_noninteger_coordinates(offset):
    with pytest.raises(ValueError, match='offset'):
        decode(record(15000000)).native_q16(offset)


def test_empty_filtered_decision_remains_explicit():
    words = record(5000000)
    words[5:12] = [3, 0, 0, 0, 0, 0, 0]
    event = decode(words)
    assert event.decision and event.reasons == 1 and event.native_rate == 5000000
    with pytest.raises(ValueError): FilteredLocalEvent.decode(struct.pack('<16I', *words)[:-1])
