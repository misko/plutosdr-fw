"""Tracking snapshot identity and terminal accounting in the radio C port."""
import ctypes as c

import pytest

from tools.starlink_glrt_tracking_abi import TrackingSnapshot, bank_id

from . import test_tracking_transport
from .test_tracking_schedule import RATES

transport = test_tracking_transport.transport


def text(words):
    return ("GLT1SNAP 00010000 "+" ".join(f"{w:08x}" for w in words)+"\n").encode()


def snapshot(rate):
    return [0x474c5431, 1, 7, 123, 1, 0x30, 0, 64, 50, 1, 2, 3, 4, 4,
            50, 50, 0, 40, 0, 0, rate, rate*33//25000, bank_id(rate), 4 if rate == 2500000 else 1]


def parse(lib, payload):
    output = (c.c_uint32*24)(*([91]*24))
    lib.glrt_tracking_snapshot_parse.argtypes = [c.c_char_p, c.c_size_t, c.POINTER(c.c_uint32)]
    lib.glrt_tracking_snapshot_drained.argtypes = [c.POINTER(c.c_uint32)]
    rc = lib.glrt_tracking_snapshot_parse(payload, len(payload), output)
    return rc, output


@pytest.mark.parametrize("rate", RATES)
def test_drained_and_inflight_snapshots_agree(transport, rate):
    w = snapshot(rate)
    rc, output = parse(transport, text(w))
    assert rc == 0 and list(output) == w and transport.glrt_tracking_snapshot_drained(output) == 1
    TrackingSnapshot.from_sysfs(text(w).decode()).require_drained()
    w[5] |= 4; w[14] -= 1; w[15] -= 2; w[16] = 1
    rc, output = parse(transport, text(w))
    assert rc == 0 and transport.glrt_tracking_snapshot_drained(output) == 0
    with pytest.raises(ValueError): TrackingSnapshot.from_sysfs(text(w).decode()).require_drained()


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("damage", ["magic", "generation", "status", "faults", "configured", "admitted",
    "committed", "popped", "queued", "high_water", "rate", "samples", "bank", "phases", "envelope", "nul"])
def test_malformed_snapshot_fails_without_publishing_partial_output(transport, rate, damage):
    w = snapshot(rate)
    fields = {"magic": (0, 0x474c5331), "generation": (1, 0), "status": (5, 0x100), "faults": (6, 16),
        "configured": (7, 63), "admitted": (8, 52), "committed": (14, 51), "popped": (15, 51),
        "queued": (16, 1), "high_water": (17, 65), "rate": (20, 25000000), "samples": (21, 1),
        "bank": (22, 0), "phases": (23, 2)}
    if damage in fields:
        index, value = fields[damage]; w[index] = value
    payload = text(w)
    if damage == "envelope": payload = payload.replace(b"GLT1SNAP", b"GLS1SNAP")
    if damage == "nul": payload += b"\0"
    rc, output = parse(transport, payload)
    assert rc == -1 and list(output) == [91]*24
    with pytest.raises(ValueError): TrackingSnapshot.from_sysfs(payload.decode())
