"""Recent CI16 ownership checked against a partition-independent deque oracle."""
from collections import deque
import ctypes as c
from pathlib import Path
import random
import subprocess

import pytest


class Ring(c.Structure):
    _fields_ = [("iq", c.POINTER(c.c_int16)), ("capacity", c.c_size_t),
        ("head", c.c_size_t), ("count", c.c_size_t), ("first", c.c_uint64),
        ("end", c.c_uint64), ("epoch", c.c_uint32), ("valid", c.c_uint32)]


@pytest.fixture(scope="module")
def recent_iq(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path_factory.mktemp("recent-iq")/"ring.so"
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
        "-shared", "-fPIC", str(root/"tools/glrt_tracking_recent_iq.c"),
        "-o", str(path)], check=True)
    lib = c.CDLL(str(path))
    lib.glrt_tracking_recent_iq_reset.argtypes = [c.POINTER(Ring), c.POINTER(c.c_int16),
        c.c_size_t, c.c_uint32, c.c_uint64]
    for name in ("append", "read"):
        getattr(lib,"glrt_tracking_recent_iq_"+name).argtypes = [c.POINTER(Ring),
            c.c_uint32, c.c_uint64, c.POINTER(c.c_int16), c.c_size_t]
    return lib


def fresh(lib, capacity=17, start=100, epoch=7):
    ring, storage = Ring(), (c.c_int16*(2*capacity))()
    assert lib.glrt_tracking_recent_iq_reset(c.byref(ring),storage,capacity,epoch,start) == 0
    return ring, storage


def append(lib, ring, samples, first=None, epoch=7):
    raw = (c.c_int16*(2*len(samples)))(*(word for pair in samples for word in pair))
    return lib.glrt_tracking_recent_iq_append(c.byref(ring),epoch,
        ring.end if first is None else first,raw,len(samples))


def read(lib, ring, first, count, epoch=7):
    raw = (c.c_int16*(2*count))(*([12345]*(2*count)))
    before = bytes(raw)
    rc = lib.glrt_tracking_recent_iq_read(c.byref(ring),epoch,first,raw,count)
    if rc: assert bytes(raw) == before
    return rc, list(zip(raw[::2],raw[1::2]))


@pytest.mark.parametrize("capacity", [1,2,17,3300])
@pytest.mark.parametrize("start", [0,2**60+7])
def test_random_block_partitions_and_wrapped_reads_match_deque(recent_iq, capacity, start):
    lib = recent_iq
    ring, storage = fresh(lib,capacity,start)
    expected = deque(maxlen=capacity)
    rng = random.Random(387+capacity)
    end = start
    for _ in range(100):
        count = rng.randrange(3*capacity+1)
        incoming = [(rng.randint(-32768,32767),rng.randint(-32768,32767)) for _ in range(count)]
        assert append(lib,ring,incoming) == 0
        expected.extend(incoming)
        end += count
        assert (ring.first,ring.end,ring.count) == (end-len(expected),end,len(expected))
        assert read(lib,ring,ring.first,ring.count) == (0,list(expected))
        offset = rng.randrange(len(expected)+1)
        length = rng.randrange(len(expected)-offset+1)
        assert read(lib,ring,ring.first+offset,length) == (0,list(expected)[offset:offset+length])
        if ring.first: assert read(lib,ring,ring.first-1,1)[0] == -4
        assert read(lib,ring,ring.end,1)[0] == -5
    assert len(storage) == 2*capacity  # storage remains owned through the entire run


def test_copied_pilot_survives_overwrite_and_rails_remain_exact(recent_iq):
    ring, storage = fresh(recent_iq,4)
    old = [(-32768,32767),(0,-1),(32767,-32768),(-7,13)]
    assert append(recent_iq,ring,old) == 0
    copied = read(recent_iq,ring,100,4)[1]
    assert append(recent_iq,ring,[(8,9)]*9) == 0
    assert copied == old
    assert read(recent_iq,ring,100,4)[0] == -4
    assert read(recent_iq,ring,ring.first,4) == (0,[(8,9)]*4)
    assert len(storage) == 8


@pytest.mark.parametrize("damage", ["gap","overlap","counter_overflow"])
def test_source_discontinuity_invalidates_history_until_explicit_reset(recent_iq, damage):
    start = 2**64-3 if damage == "counter_overflow" else 100
    ring, storage = fresh(recent_iq,start=start)
    assert append(recent_iq,ring,[(1,2)]) == 0
    position = ring.end+(1 if damage == "gap" else -1 if damage == "overlap" else 0)
    assert append(recent_iq,ring,[(3,4)]*3,first=position) == -3
    assert not ring.valid and ring.count == 0
    assert read(recent_iq,ring,start,1)[0] == -3
    assert append(recent_iq,ring,[(5,6)]) == -3
    assert recent_iq.glrt_tracking_recent_iq_reset(c.byref(ring),storage,17,8,500) == 0
    assert append(recent_iq,ring,[(7,8)],epoch=8) == 0
    assert read(recent_iq,ring,500,1,epoch=8) == (0,[(7,8)])


def test_stale_reader_and_writer_cannot_poison_new_epoch(recent_iq):
    ring, storage = fresh(recent_iq)
    assert append(recent_iq,ring,[(1,2),(3,4)]) == 0
    state, data = bytes(ring), bytes(storage)
    assert append(recent_iq,ring,[(9,10)],first=999,epoch=6) == -2
    assert read(recent_iq,ring,100,1,epoch=6)[0] == -2
    assert bytes(ring) == state and bytes(storage) == data
    assert read(recent_iq,ring,100,2) == (0,[(1,2),(3,4)])


@pytest.mark.parametrize("capacity,epoch", [(0,7),(17,0),(2**63,7)])
def test_invalid_capacity_or_epoch_disables_ring(recent_iq, capacity, epoch):
    ring, storage = fresh(recent_iq)
    assert recent_iq.glrt_tracking_recent_iq_reset(c.byref(ring),storage,capacity,epoch,100) == -1
    assert not ring.valid


def test_empty_and_malformed_reads_do_not_copy_or_mutate(recent_iq):
    ring, storage = fresh(recent_iq)
    assert read(recent_iq,ring,100,0) == (0,[])
    assert read(recent_iq,ring,100,1)[0] == -5
    assert read(recent_iq,ring,2**64-1,2)[0] == -1
    assert recent_iq.glrt_tracking_recent_iq_append(c.byref(ring),7,100,None,1) == -1
    assert recent_iq.glrt_tracking_recent_iq_read(c.byref(ring),7,100,None,1) == -1
    assert recent_iq.glrt_tracking_recent_iq_append(c.byref(ring),7,100,None,0) == 0
    assert ring.valid and ring.count == 0 and bytes(storage) == bytes(len(storage)*2)
