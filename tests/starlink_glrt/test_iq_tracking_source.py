"""Native GLI1 snapshots map to signal-center IQ without losing source time."""
import ctypes as C
from pathlib import Path
import subprocess

import pytest

from .test_capture_source import Snapshot, Cursor


class NativeCursor(C.Structure):
    _fields_ = [("coarse", Cursor), ("native_latest", C.c_uint64), ("native_rate", C.c_uint32)]


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = tmp_path_factory.mktemp("gli1-source")
    tools = Path(__file__).resolve().parents[2]/"tools"
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    str(tools/"glrt_capture_source.c"), str(tools/"glrt_iq_tracking_source.c"),
                    "-o", str(root/"source.so")], check=True, capture_output=True)
    lib = C.CDLL(str(root/"source.so"))
    for name in ("glrt_capture_snapshot_parse", "glrt_iq_tracking_snapshot_parse"):
        getattr(lib,name).argtypes = [C.c_char_p,C.c_size_t,C.POINTER(Snapshot)]
    lib.glrt_iq_tracking_source_begin.argtypes = [C.POINTER(NativeCursor),C.c_uint32,C.c_uint64,C.POINTER(Snapshot)]
    lib.glrt_iq_tracking_source_take.argtypes = [C.POINTER(NativeCursor),C.POINTER(Snapshot),C.c_size_t,
                                               C.POINTER(C.c_uint64),C.POINTER(C.c_uint64)]
    return lib


def pair(w, index, value):
    w[index] = value & 0xffffffff
    w[index+1] = value >> 32


def snapshot(api, rate, *, first=2**56+17, count=0, latest=0, generation=1):
    ratio = rate//2500000
    w = [0]*64
    if count:
        pair(w,0,(first+53)*ratio)
        pair(w,2,(first+53+count-1)*ratio)
        pair(w,4,count);pair(w,6,count)
    pair(w,42,latest)
    w[19] = 25 if count else 32
    w[20],w[62],w[63] = 17,rate,53*ratio
    text = f"GLI1 00010000 {rate} 2500000 {generation} 0 {rate} 0 0 0 0 0 0 0 "+" ".join(f"{v:08x}" for v in w)
    value = Snapshot()
    assert api.glrt_iq_tracking_snapshot_parse(text.encode(),len(text),C.byref(value)) == 0
    assert api.glrt_capture_snapshot_parse(text.encode(),len(text),C.byref(Snapshot())) == -1
    assert list(value.words) == w  # Raw native evidence is never relabeled.
    return value


def take(api, cursor, state, count):
    first,now = C.c_uint64(777),C.c_uint64(888)
    rc = api.glrt_iq_tracking_source_take(C.byref(cursor),C.byref(state),count,C.byref(first),C.byref(now))
    return rc,first.value,now.value


@pytest.mark.parametrize("rate", [30000000,60000000])
def test_every_native_phase_maps_exact_large_coordinates_and_delayed_iq(api, rate):
    ratio,first = rate//2500000,2**56+17
    cursor = NativeCursor()
    baseline = snapshot(api,rate)
    assert api.glrt_iq_tracking_source_begin(C.byref(cursor),17,100000,C.byref(baseline)) == 0
    for phase in range(ratio):
        latest = (first+2000+phase)*ratio+phase
        state = snapshot(api,rate,count=1000,latest=latest,generation=phase+2)
        raw = bytes(state)
        assert take(api,cursor,state,20) == (0,first+20*phase,latest//ratio+1)
        assert bytes(state) == raw
    assert cursor.coarse.received == 20*ratio and cursor.native_latest == latest


@pytest.mark.parametrize("rate", [30000000,60000000])
@pytest.mark.parametrize("damage", ["rate","readback","delay","first_phase","last_phase","underflow",
    "native_regression","native_wrap","transport","cpu_activity","acquisition_activity","delivery"])
def test_bad_native_geometry_or_health_fences_without_advancing_iq(api, rate, damage):
    ratio,first = rate//2500000,2**56+17
    cursor = NativeCursor()
    baseline = snapshot(api,rate)
    assert api.glrt_iq_tracking_source_begin(C.byref(cursor),17,100000,C.byref(baseline)) == 0
    latest = (first+2000)*ratio+5
    state = snapshot(api,rate,count=1000,latest=latest,generation=2)
    assert take(api,cursor,state,20)[0] == 0
    state = snapshot(api,rate,count=1000,latest=latest+1,generation=3)
    if damage == "rate": state.words[62] = 2500000
    elif damage == "readback": state.readback_rate = 2500000
    elif damage == "delay": state.words[63] += 1
    elif damage == "first_phase": state.words[0] += 1
    elif damage == "last_phase": state.words[2] += 1
    elif damage == "underflow": pair(state.words,0,ratio)
    elif damage == "native_regression": pair(state.words,42,latest-1)
    elif damage == "native_wrap": pair(state.words,42,2**64-1)
    elif damage == "transport": state.words[18] = 1
    elif damage == "cpu_activity": state.cpu[0] = state.cpu[1] = 1
    elif damage == "acquisition_activity": state.words[24] = 1
    elif damage == "delivery": state.words[6] = 39
    assert take(api,cursor,state,20) == (-1,0,0)
    assert not cursor.coarse.valid and cursor.coarse.received == 20
    assert cursor.native_latest == latest
