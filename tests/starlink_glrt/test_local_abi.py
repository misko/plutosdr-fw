"""C/host record validation, source support, loss and search coverage."""
import ctypes as C
import struct
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tools.starlink_glrt_local_abi import (
    MAGIC,
    PERIOD,
    RATE,
    WINDOW,
    LocalEvent,
    LocalIQSnapshot,
    LocalSearchSnapshot,
    LocalSourceClosure,
    attest_capture,
)

ROOT = Path(__file__).resolve().parents[2]
FIRST, VISIT = 2**60 + 17, 517


@pytest.fixture(scope="module")
def kernel_checks(tmp_path_factory):
    root = tmp_path_factory.mktemp("local-kernel-checks")
    (root / "wrapper.c").write_text('''#include <stdint.h>
#include <stdbool.h>
typedef uint32_t u32; typedef uint64_t u64; typedef int32_t s32;
#include "adi_starlink_glrt_local.h"
int event_valid(const u32 *w) { return gla_event_valid(w); }
int closure_complete(const u32 *w) { return gla_closure_complete(w); }
''')
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(ROOT / "linux/drivers/iio/adc"), str(root / "wrapper.c"),
                    "-o", str(root / "checks.so")], check=True)
    lib = C.CDLL(str(root / "checks.so"))
    for name in ("event_valid", "closure_complete"):
        getattr(lib, name).argtypes = [C.POINTER(C.c_uint32)]
        getattr(lib, name).restype = C.c_int
    return lib


def cwords(words):
    return (C.c_uint32 * 16)(*words)


def event_words(*, sequence=0, first=FIRST, decision=False, empty=False):
    flags = 3 if empty else (17 << 16) | (7 << 12) | (4 << 6) | int(decision)
    payload = [0] * 6 if empty else [(-2187) & 0xffffffff, 10000, 12000, 15000, 2000, 13000]
    return [MAGIC, VISIT, sequence, first & 0xffffffff, first >> 32, flags, *payload, WINDOW, 0, 0, 0]


def event(words):
    return LocalEvent.decode(struct.pack("<16I", *words))


def search(words, generation=1):
    return LocalSearchSnapshot.decode(f"GLA1 00010000 {generation} {RATE} {PERIOD} {WINDOW} "
                                      + " ".join(f"{w:08x}" for w in words))


def evidence():
    size = PERIOD + WINDOW
    last = FIRST + size - 1
    w = [0] * 64
    w[:8] = [FIRST & 0xffffffff, FIRST >> 32, last & 0xffffffff, last >> 32, size, 0, size, 0]
    w[12:16] = [size, 0, size, 0]
    w[19:24] = [24, VISIT, 16, 0, 0]
    w[62] = RATE
    header = f"GLA1 00010000 {RATE} {RATE} 5 0 {RATE} 0 3 3 0 0 0 0 "
    final = LocalIQSnapshot.decode(header + " ".join(f"{v:08x}" for v in w))
    b = [0] * 64
    b[20], b[62] = VISIT, RATE
    baseline = replace(final, generation=4, cpu_read=0, cpu_pushed=0, words=tuple(b))
    source_words = [7, 0, last & 0xffffffff, last >> 32] + [0] * 12
    source = LocalSourceClosure.decode(f"GLA1 00010000 5 {VISIT} {RATE} "
                                       + " ".join(f"{v:08x}" for v in source_words))
    source_baseline = replace(source, generation=4, words=(0,) * 16)
    stats = [0x113, 0, 0, 3, 3, 3, 2, 2, 0, 2, 1, 0, 0, VISIT, FIRST & 0xffffffff, FIRST >> 32]
    bstats = [0] * 16
    bstats[13] = VISIT
    events = [event(event_words()), event(event_words(sequence=1, decision=True)),
              event(event_words(sequence=2, first=FIRST + PERIOD, empty=True))]
    return {"final": final, "baseline": baseline, "source": source, "source_baseline": source_baseline,
            "search": search(stats, 2), "search_baseline": search(bstats), "events": events,
            "received_bytes": 4*size}


def test_exact_large_indices_negative_cfo_and_completed_coverage(kernel_checks):
    e = evidence()
    result = attest_capture(**e)
    assert result["completed"] == 2 and result["supported"] == 1
    assert result["completed_windows"] == [
        {"first_source_index": FIRST, "samples": WINDOW, "supported": True},
        {"first_source_index": FIRST + PERIOD, "samples": WINDOW, "supported": False}]
    assert e["events"][0].cfo_hz == -218700
    assert e["final"].source_center(PERIOD) == FIRST + PERIOD
    assert all(kernel_checks.event_valid(cwords(v.words)) for v in e["events"])
    assert kernel_checks.closure_complete(cwords(e["search"].words))


@pytest.mark.parametrize("index,value", [(0, 0x474c5231), (1, 0), (4, 0xffffffff),
    (5, 1 << 28), (5, 3333 << 16), (5, 11 << 12), (5, 5 << 6), (5, 4),
    (6, 4001), (6, (-4001) & 0xffffffff), (7, 0), (7, 65537), (8, 65537),
    (9, 65537), (10, 65537), (11, 65537), (12, 13999), (13, 1), (14, 1), (15, 1)])
def test_kernel_and_host_reject_malformed_records(kernel_checks, index, value):
    w = event_words()
    w[index] = value
    if index == 4:
        w[3] = 0xffffffff
    assert not kernel_checks.event_valid(cwords(w))
    with pytest.raises(ValueError):
        event(w)


@pytest.mark.parametrize("index,value", [(5, 2), (5, 7), (6, 1), (7, 1), (8, 1), (11, 1)])
def test_empty_decision_has_no_candidate_payload(kernel_checks, index, value):
    w = event_words(empty=True)
    w[index] = value
    assert not kernel_checks.event_valid(cwords(w))
    with pytest.raises(ValueError):
        event(w)


@pytest.mark.parametrize("index,value", [(0, 0x13), (0, 0x117), (0, 0x11b), (0, 0x153),
    (0, 0x313), (1, 1), (2, 1), (3, 17), (4, 4), (5, 2), (6, 3), (7, 3),
    (8, 1), (9, 3), (10, 3), (11, 1), (12, 1), (13, 0)])
def test_kernel_and_host_reject_unsettled_or_unaccounted_search(kernel_checks, index, value):
    e = evidence()
    w = list(e["search"].words)
    w[index] = value
    assert not kernel_checks.closure_complete(cwords(w))
    with pytest.raises(ValueError):
        e["search"] = search(w)
        attest_capture(**e)


@pytest.mark.parametrize("change", ["missing", "duplicate", "reorder", "wrong_visit", "wrong_window",
    "noncadence", "outside_iq", "winner_payload", "rank", "cpu_loss", "bytes", "baseline", "source_pair"])
def test_coherent_counters_do_not_hide_bad_record_or_iq_binding(change):
    e = evidence()
    if change == "missing":
        e["events"].pop(0)
    elif change == "duplicate":
        e["events"][1] = e["events"][0]
    elif change == "reorder":
        e["events"].reverse()
    elif change in ("wrong_visit", "wrong_window", "noncadence", "outside_iq", "winner_payload", "rank"):
        n = 1 if change == "winner_payload" else 0
        w = list(e["events"][n].words)
        if change == "wrong_visit": w[1] += 1
        elif change == "wrong_window":
            w[3], w[4] = (FIRST-PERIOD) & 0xffffffff, (FIRST-PERIOD) >> 32
        elif change == "noncadence": w[3] += 1
        elif change == "outside_iq": w[3] += 2*PERIOD
        elif change == "winner_payload": w[9] += 1
        elif change == "rank": w[5] |= 1 << 9
        e["events"][n] = event(w)
    elif change == "cpu_loss":
        e["final"] = replace(e["final"], cpu_disabled=1, cpu_pushed=2)
    elif change == "bytes": e["received_bytes"] -= 4
    elif change == "baseline": e["search_baseline"] = e["search"]
    elif change == "source_pair": e["source"] = replace(e["source"], generation=3)
    with pytest.raises(ValueError):
        attest_capture(**e)


def test_counted_aborted_window_can_preserve_candidate_without_claiming_detection(kernel_checks):
    e = evidence()
    e["events"] = [e["events"][0]]
    e["final"] = replace(e["final"], cpu_read=1, cpu_pushed=1)
    w = list(e["search"].words)
    w[0], w[4], w[5], w[9], w[10], w[11] = 0x193, 1, 1, 0, 0, 2
    e["search"] = search(w)
    assert kernel_checks.closure_complete(cwords(w))
    result = attest_capture(**e)
    assert result["completed_windows"] == [] and result["aborted"] == 2


def test_skipped_window_is_not_reported_as_a_completed_negative(kernel_checks):
    e = evidence()
    e["events"] = e["events"][:2]
    e["final"] = replace(e["final"], cpu_read=2, cpu_pushed=2)
    w = list(e["search"].words)
    w[4], w[5], w[7], w[8], w[9] = 2, 2, 1, 1, 1
    e["search"] = search(w)
    assert kernel_checks.closure_complete(cwords(w))
    result = attest_capture(**e)
    assert len(result["completed_windows"]) == 1 and result["skipped"] == 1
