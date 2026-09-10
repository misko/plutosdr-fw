"""GLS1 evidence retains faults and binds heads to exact finite predictions."""
import struct
from dataclasses import replace

import pytest

from tools.starlink_glrt_native_abi import NativeResult
from tools.starlink_glrt_schedule_abi import (
    MAGIC, RATE, SAMPLES, ScheduleBatch, ScheduledResult, ScheduleSnapshot,
)


def batch():
    return ScheduleBatch(3, 19, 2**55+1001, 32768, 80000*65536+16384,
                         2**48-32768, 65536+32768, 0xfffffff9, 4, 2**55+400000)


def words(*, count=SAMPLES, fault=0, repeat=1):
    b = batch()
    start, step = b.prediction(repeat)
    w = [MAGIC, 7, b.tag, start % 2**32, start >> 32, b.seed, step, count, fault]
    for value, width in ((-123,64), (456,64), (-(2**40),64), (2**40,64),
                         (-(2**67),96), (2**67,96), (2**51,64)):
        w += [(value >> shift) % 2**32 for shift in range(0, width, 32)]
    return w+[RATE, SAMPLES, repeat, 0, 0, 0, 0]


def envelope(prefix, w):
    return prefix+" 00010000 "+" ".join(f"{v:08x}" for v in w)+"\n"


def decode(w):
    return ScheduledResult.decode(struct.pack("<32I", *w), epoch=3)


def test_head_roundtrip_signed_wide_moments_exact_prediction_and_acknowledgement():
    w = words()
    result = ScheduledResult.from_sysfs(envelope("GLS1", [3]+w))
    assert result == decode(w)
    assert result.reference_sum == (-123,456)
    assert result.delay_sum == (-(2**40),2**40)
    assert result.reference_prefix_integral == (-(2**67),2**67)
    assert result.observed_energy == 2**51
    assert result.start == 2**55+81002 and result.phase_step == 1
    result.require_complete()
    result.require_association(batch(), sequence=7)
    assert result.acknowledgement() == "00000003 00000007\n"
    assert tuple(int(v,16) for v in batch().encode().split()) == tuple(vars(batch()).values())
    with pytest.raises(ValueError):
        NativeResult.decode(struct.pack("<32I", *w))


@pytest.mark.parametrize("fault", [1, 128, 256, 512, 768])
def test_faulted_partial_head_remains_decodable_but_cannot_be_used_as_complete(fault):
    result = decode(words(count=10, fault=fault))
    result.require_association(batch(), sequence=7)
    with pytest.raises(ValueError):
        result.require_complete()
    assert result.acknowledgement() == "00000003 00000007\n"


@pytest.mark.parametrize("index,value", [(0,0x474c4e31), (2,0), (7,SAMPLES+1),
    (7,SAMPLES-1), (8,1024), (10,0x100000), (19,0x20), (24,0x200000),
    (25,2500000), (26,64), (27,64), (28,1), (31,1)])
def test_malformed_heads_do_not_reach_acknowledgement(index, value):
    w = words(); w[index] = value
    with pytest.raises(ValueError):
        decode(w)


def test_empty_and_wrapping_partial_results():
    w = words(count=0,fault=1)
    with pytest.raises(ValueError):
        decode(w)
    w[9:25] = [0]*16
    assert decode(w).count == 0
    w[7] = 2; w[3:5] = [0xffffffff]*2
    with pytest.raises(ValueError):
        decode(w)


@pytest.mark.parametrize("change", [dict(epoch=4),dict(tag=20),dict(start=2**55+1002),
    dict(fraction=0),dict(step=123456789),dict(seed=3),dict(repeats=1),
    dict(expires=2**55+81002+SAMPLES-2)])
def test_stale_or_misassociated_descriptor_is_rejected(change):
    with pytest.raises(ValueError):
        decode(words()).require_association(replace(batch(), **change), sequence=7)


def test_sequence_cannot_be_reused_for_a_newer_head():
    with pytest.raises(ValueError):
        decode(words()).require_association(batch(), sequence=8)


@pytest.mark.parametrize("change", [dict(epoch=0),dict(tag=True),dict(fraction=65536),
    dict(period=(SAMPLES+127)*65536),dict(delta=-1),dict(repeats=65),dict(start=511)])
def test_invalid_batch_cannot_be_encoded(change):
    with pytest.raises(ValueError):
        replace(batch(), **change)


def snapshot_words():
    # Eight opportunities: five admitted and three explicit exclusions.
    return [MAGIC,1,3,9,7,0,0,8,5,1,1,1,0,0,5,5,0,2,0,0]


def test_coherent_snapshot_proves_complete_terminal_accounting():
    snapshot = ScheduleSnapshot.from_sysfs(envelope("GLS1SNAP",snapshot_words()))
    assert snapshot.latest_index == 7*2**32+9
    snapshot.require_drained()
    assert snapshot.high_water == 2


@pytest.mark.parametrize("index,value", [(1,0),(5,256),(6,16),(7,7),(14,6),
    (14,3),(15,6),(16,1),(17,65)])
def test_incoherent_or_unknown_snapshot_is_rejected(index,value):
    w = snapshot_words(); w[index] = value
    with pytest.raises(ValueError):
        ScheduleSnapshot.from_sysfs(envelope("GLS1SNAP",w))


def test_retained_head_and_pending_opportunities_are_not_drained():
    for index,value in ((5,4),(7,9),(15,4)):
        w = snapshot_words(); w[index] = value
        if index == 15:
            w[16] = 1
        snapshot = ScheduleSnapshot.from_sysfs(envelope("GLS1SNAP",w))
        with pytest.raises(ValueError):
            snapshot.require_drained()


@pytest.mark.parametrize("alter", [lambda s:s.replace("00010000","00020000"),
    lambda s:s+" 00000000",lambda s:s.replace("474c5331","0x474c5331"),
    lambda s:s.replace("00000003","+0000003",1),lambda s:s[:-10]])
def test_sysfs_envelope_is_strict(alter):
    with pytest.raises(ValueError):
        ScheduledResult.from_sysfs(alter(envelope("GLS1",[3]+words())))
