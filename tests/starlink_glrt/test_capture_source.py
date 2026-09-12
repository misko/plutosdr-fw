"""Direct-rate source ownership, checked against the public Python wire decoder."""
import ctypes as c
from pathlib import Path
import subprocess

import pytest

from tools.starlink_glrt_local_abi import LocalIQSnapshot


class Snapshot(c.Structure):
    _fields_ = [("generation", c.c_uint32), ("recovery_failed", c.c_uint32),
        ("readback_rate", c.c_uint32), ("dma_error", c.c_int32),
        ("cpu", c.c_uint64*5), ("cpu_fault", c.c_uint32), ("words", c.c_uint32*64)]


class Cursor(c.Structure):
    _fields_ = [("baseline", Snapshot), *[(key,c.c_uint64) for key in
        ("first","received","limit","last_source","admitted","delivered","cpu_read","cpu_pushed")],
        *[(key,c.c_uint32) for key in ("visit","generation","bound","valid")]]


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path_factory.mktemp("capture-source")/"source.so"
    subprocess.run(["cc","-std=c99","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC",
        str(root/"tools/glrt_capture_source.c"),"-o",str(path)],check=True)
    lib = c.CDLL(str(path))
    lib.glrt_capture_snapshot_parse.argtypes = [c.c_char_p,c.c_size_t,c.POINTER(Snapshot)]
    lib.glrt_capture_source_begin.argtypes = [c.POINTER(Cursor),c.c_uint32,c.c_uint64,c.POINTER(Snapshot)]
    lib.glrt_capture_source_take.argtypes = [c.POINTER(Cursor),c.POINTER(Snapshot),c.c_size_t,
        c.POINTER(c.c_uint64),c.POINTER(c.c_uint64)]
    return lib


def fields(*, first=2**60+17, admitted=0, delivered=0, latest=None, generation=5):
    words = [0]*64
    for n,value in ((0,first if admitted else 0),(2,first+admitted-1 if admitted else 0),
        (4,admitted),(6,delivered),(42,latest if latest is not None else first+admitted)):
        words[n:n+2] = [value & 0xffffffff,value >> 32]
    words[19] = 25 if admitted else 32
    words[20],words[62] = 17,2500000
    header = f"GLA1 00010000 2500000 2500000 {generation} 0 2500000 0 20 18 2 0 0 0".split()
    return header+[f"{v:08x}" for v in words]


def decode(api, f):
    text = " ".join(f)
    expected = LocalIQSnapshot.decode(text)
    s = Snapshot()
    assert api.glrt_capture_snapshot_parse(text.encode(),len(text),c.byref(s)) == 0
    assert tuple(s.words) == expected.words
    assert tuple(s.cpu) == tuple(getattr(expected,"cpu_"+key) for key in
        ("read","pushed","disabled","full","malformed"))
    assert (s.generation,s.dma_error,s.cpu_fault) == (expected.generation,expected.dma_error,expected.cpu_fault)
    return s


def take(api, cursor, snapshot, samples):
    first,now = c.c_uint64(777),c.c_uint64(888)
    rc = api.glrt_capture_source_take(c.byref(cursor),c.byref(snapshot),samples,c.byref(first),c.byref(now))
    if rc: assert first.value == now.value == 0
    return rc,first.value,now.value


def begin(api, limit=20000):
    cursor = Cursor()
    baseline = decode(api,fields())
    assert api.glrt_capture_source_begin(c.byref(cursor),17,limit,c.byref(baseline)) == 0
    return cursor


def test_delivered_blocks_keep_source_time_distinct_and_large_indices_exact(api):
    cursor = begin(api)
    first = 2**60+17
    for n in range(1,5):
        snap = decode(api,fields(admitted=20000,delivered=20000,
            latest=first+25000+n*300,generation=5+n))
        assert take(api,cursor,snap,5000) == (0,first+(n-1)*5000,first+25001+n*300)
    assert cursor.received == cursor.limit
    assert take(api,cursor,decode(api,fields(generation=10)),1)[0] == -1
    assert not cursor.valid and cursor.received == 20000


@pytest.mark.parametrize("index,value", [(0,"GLR1"),(1,"00020000"),(2,"5000000"),
    (3,"5000000"),(4,"0"),(4,"4294967296"),(5,"2"),(7,"1"),(7,"-2147483649"),
    (8,"18446744073709551616"),(8,"21"),(13,"4294967296"),(14,"0"),(14,"gggggggg"),
    (33,"00001000"),(37,"00000002"),(62,"00010000"),(63,"00004000"),
    (66,"00000800"),(71,"00010001"),(74,"00000002"),(75,"00000010"),
    (76,"004c4b40"),(77,"00000001")])
def test_wire_rejection_agrees_with_public_decoder_and_leaves_output_untouched(api,index,value):
    f = fields();f[index] = value
    text = " ".join(f)
    with pytest.raises(ValueError): LocalIQSnapshot.decode(text)
    out = Snapshot();c.memset(c.byref(out),0xa5,c.sizeof(out));before = bytes(out)
    assert api.glrt_capture_snapshot_parse(text.encode(),len(text),c.byref(out)) == -1
    assert bytes(out) == before


@pytest.mark.parametrize("damage", ["nul","short","extra","empty","too_long"])
def test_truncated_or_ambiguous_text_fails(api,damage):
    text = " ".join(fields()).encode()
    text = {"nul":text+b"\0","short":text[:-9],"extra":text+b" 0","empty":b"",
        "too_long":b" "*4096+text}[damage]
    assert api.glrt_capture_snapshot_parse(text,len(text),c.byref(Snapshot())) == -1


@pytest.mark.parametrize("damage", ["visit","dma","readback","recovery","cpu_loss","cpu_regression",
    "source_drop","transport","legacy","missing_prefix","short_delivery","excess_admitted",
    "wrong_last","origin_change","latest_regression","admitted_regression","delivered_regression",
    "generation_same","generation_old","source_overflow"])
def test_failure_fences_cursor_without_advancing_retained_count(api,damage):
    cursor = begin(api)
    first = 2**60+17
    one = decode(api,fields(admitted=18000,delivered=18000,latest=first+21000,generation=6))
    one.cpu[0] += 1;one.cpu[1] += 1
    assert take(api,cursor,one,4096)[0] == 0
    two = decode(api,fields(admitted=20000,delivered=20000,latest=first+22000,generation=7))
    two.cpu[0] += 1;two.cpu[1] += 1
    if damage == "visit": two.words[20] += 1
    elif damage == "dma": two.dma_error = -5
    elif damage == "readback": two.readback_rate = 5000000
    elif damage == "recovery": two.recovery_failed = 1
    elif damage == "cpu_loss": two.cpu[2] += 1
    elif damage == "cpu_regression": two.cpu[0] -= 1;two.cpu[1] -= 1
    elif damage == "source_drop": two.words[44] += 1
    elif damage == "transport": two.words[18] = 1
    elif damage == "legacy": two.words[50] = 1
    elif damage == "missing_prefix": two.words[19] &= ~8
    elif damage == "short_delivery": two.words[6] = 8191
    elif damage == "excess_admitted": two.words[4] += 1;two.words[2] += 1
    elif damage == "wrong_last": two.words[2] += 1
    elif damage == "origin_change": two.words[0] += 1;two.words[2] += 1
    elif damage == "latest_regression": two.words[42] -= 1500
    elif damage == "admitted_regression": two.words[4] -= 3000;two.words[2] -= 3000;two.words[6] -= 3000
    elif damage == "delivered_regression": two.words[6] -= 3000
    elif damage == "generation_same": two.generation = 6
    elif damage == "generation_old": two.generation = 5
    elif damage == "source_overflow": two.words[42] = two.words[43] = 0xffffffff
    assert take(api,cursor,two,4096)[0] == -1
    assert not cursor.valid and cursor.received == 4096
    assert take(api,cursor,one,4096)[0] == -1


def test_snapshot_generation_wrap_and_negative_dma_decode(api):
    cursor = Cursor();base = decode(api,fields(generation=2**32-1))
    assert api.glrt_capture_source_begin(c.byref(cursor),17,100,c.byref(base)) == 0
    assert take(api,cursor,decode(api,fields(admitted=100,delivered=100,generation=1)),100)[0] == 0
    f = fields();f[7] = "-2147483648"
    snap = decode(api,f)
    assert snap.dma_error == -(2**31)
    assert api.glrt_capture_source_begin(c.byref(cursor),17,100,c.byref(snap)) == -1


@pytest.mark.parametrize("damage", ["active","queued","prefix","wrong_visit","zero_samples","wrong_geometry"])
def test_only_requested_idle_prearm_baseline_can_start_cursor(api,damage):
    s = decode(api,fields());cursor = Cursor();limit = 100
    if damage in ("active","queued","prefix"): s.words[19] |= {"active":1,"queued":2,"prefix":8}[damage]
    elif damage == "wrong_visit": s.words[20] = 18
    elif damage == "zero_samples": limit = 0
    elif damage == "wrong_geometry": s.words[62] = 5000000
    assert api.glrt_capture_source_begin(c.byref(cursor),17,limit,c.byref(s)) == -1
    assert not cursor.valid
