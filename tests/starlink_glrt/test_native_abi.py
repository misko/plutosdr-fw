"""Adversarial GLN1 wire decoding and native evidence association."""
import struct

import pytest

from tools.starlink_glrt_native_abi import RATE, SAMPLES, NativeResult


def words():
    result = [0]*32
    result[:9] = [0x474c4e31, 7, 19, 73, 1 << 23, 2**32-3, 2**32-91771, SAMPLES, 0]
    for offset, width, value in ((9, 2, -(1 << 50)), (11, 2, (1 << 50)-1),
        (13, 2, -791), (15, 2, 23), (17, 3, -(1 << 67)), (20, 3, (1 << 67)-1), (23, 2, 1 << 51)):
        result[offset:offset+width] = [(value >> (32*n)) & 0xffffffff for n in range(width)]
    result[25:30] = [RATE, SAMPLES, 1, SAMPLES, SAMPLES]
    return result


def decode(value):
    return NativeResult.decode(struct.pack("<32I", *value))


def test_signed_moments_high_source_index_and_negative_cfo():
    result = decode(words())
    assert result.start == 2**55+73
    assert result.reference_sum == (-(1 << 50), (1 << 50)-1)
    assert result.delay_sum == (-791, 23)
    assert result.reference_prefix_integral == (-(1 << 67), (1 << 67)-1)
    assert result.observed_energy == 1 << 51
    assert float(result.predicted_cfo_hz) == pytest.approx(-1282.0260599255562)
    result.require_complete()
    result.require_native_evidence(received_bytes=316800, expected_tag=19, expected_start=2**55+73)


@pytest.mark.parametrize("index,value", [(0, 0), (2, 0), (7, SAMPLES-1), (7, SAMPLES+1),
    (8, 1 << 11), (10, 0x00100000), (12, 0x00080000), (14, 0x00080000), (16, 0x00080000),
    (19, 0x10), (22, 0x10), (24, 1 << 21), (25, 2500000), (26, SAMPLES-1),
    (27, 2), (28, SAMPLES-1), (29, SAMPLES-1), (30, 1), (31, 1)])
def test_reject_corrupt_geometry_counts_extensions_and_reserved_fields(index, value):
    value_words = words()
    value_words[index] = value
    with pytest.raises(ValueError):
        decode(value_words)


def test_explicit_partial_fault_is_decodable_but_never_complete():
    value = words()
    value[7], value[8], value[28], value[29] = 38, 0x108, 60, 60
    result = decode(value)
    result.require_native_evidence(received_bytes=240, expected_tag=19, expected_start=result.start)
    with pytest.raises(ValueError):
        result.require_complete()
    value[7] = 61
    with pytest.raises(ValueError):
        decode(value)


def test_empty_failed_job_requires_zero_moments_and_capture_off_requires_zero_iq():
    value = words()
    value[7:9] = [0, 4]
    with pytest.raises(ValueError):
        decode(value)
    value[9:25] = [0]*16
    value[27:30] = [0, 0, 0]
    result = decode(value)
    assert result.count == 0
    with pytest.raises(ValueError):
        result.require_native_evidence(received_bytes=0, expected_tag=19, expected_start=result.start)
    value[28:30] = [1, 1]
    with pytest.raises(ValueError):
        decode(value)


@pytest.mark.parametrize("bytes_count,tag,start", [(316796, 19, 2**55+73), (316800, 18, 2**55+73),
    (316800, 19, 2**55+74), (True, 19, 2**55+73)])
def test_saved_native_evidence_requires_exact_job_and_byte_count(bytes_count, tag, start):
    with pytest.raises(ValueError):
        decode(words()).require_native_evidence(received_bytes=bytes_count, expected_tag=tag, expected_start=start)
