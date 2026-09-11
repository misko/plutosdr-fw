"""GLA1 profile selects one local search and exactly the DMA-admitted IQ."""
import re

import numpy as np
import pytest

from .test_capture_rtl import arm, read, run, samples, snapshot, u64, wait, write
from .test_capture_rtl import captures as captures  # noqa: PLC0414
from .test_receiver_rtl import observation


def test_profile_identity_geometry_and_removed_legacy_engines(captures, tmp_path):
    executable = captures(2500000, legacy=False, local=True)
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', executable.read_text())
    for present in ("starlink_glrt_local_control", "starlink_glrt_local_search", "starlink_glrt_local_cadence",
                    "starlink_glrt_ddc"):
        assert modules.count(present) == 1
    for absent in ("starlink_glrt_native_engine", "starlink_glrt_acquisition", "starlink_glrt_candidate_select",
                   "starlink_glrt_correlator", "starlink_glrt_score", "starlink_glrt_fir_decimator"):
        assert absent not in modules
    addresses = (0, 0x5C, 0x68, 0xC00, 0xC04, 0xC14, 0xC18, 0xC1C, 0xC54, 0xC58, 0xC5C, 0xC70)
    output, reads, final = run(executable, [read(address) for address in addresses], tmp_path)
    assert not output and final == (0, 0)
    assert dict(reads) == dict(zip(addresses, (0x474C4131, 0x474C4131, 9, 0x474C4131, 0x10000,
        250000, 14000, 16, 2500000, 100, 16, 3333)))


def test_partial_stop_and_clear_preserve_exact_iq_and_local_accounting(captures, tmp_path):
    raw, _, _ = observation(2500000, "positive")
    rows = [*arm(visit=512), *samples(raw), wait(100), write(8, 2), wait(200), *snapshot(),
            write(0xC10, 2), *(read(address) for address in range(0xD00, 0xD40, 4)),
            read(0xC08), read(0xC0C), write(8, 4), wait(), read(0xC38), read(0xC48), read(0xC0C)]
    output, reads, final = run(captures(2500000, legacy=False, local=True), rows, tmp_path)
    np.testing.assert_array_equal(output, raw)
    assert final == (0, 0)
    before = dict(reads[:-3])
    assert u64(before, 0x90) == u64(before, 0x98) == len(raw)
    assert before[0xC4] == before[0xC8] == before[0x148] == 0
    assert before[0xD00] == 0x1B3  # closed, partial, aborted, settled and drained
    assert before[0xD04] == before[0xC0C] == 0
    assert before[0xD18] == before[0xD1C] == before[0xD2C] == 1
    assert before[0xD20] == before[0xD24] == before[0xD28] == before[0xD30] == 0
    assert before[0xD34] == 512
    assert u64(before, 0xD38) == u64(before, 0x80)
    assert reads[-3:] == [(0xC38, 0), (0xC48, 0), (0xC0C, 0)]


@pytest.mark.parametrize("count", [0, 1])
def test_visit_reservation_fences_early_clear_and_releases_after_abort(captures, tmp_path, count):
    raw = np.array([[517, -731]], dtype=np.int16)[:count]
    rows = [*arm(visit=513), *samples(raw), wait(100), write(8, 4), read(0x10),
            write(8, 2), wait(300), write(8, 4), wait(100), read(0x10), read(0xC0C),
            (0, 9, 0, 16, 0), wait(), write(0x20, 514), read(0x20), write(8, 1), read(0x10),
            write(8, 2), wait(300), write(8, 4), wait(), read(0x10), read(0xC0C)]
    output, reads, final = run(captures(2500000, legacy=False, local=True), rows, tmp_path)
    assert reads == [(0x10, 16), (0x10, 0), (0xC0C, 0), (0x20, 514),
                     (0x10, 0), (0x10, 0), (0xC0C, 0)]
    np.testing.assert_array_equal(np.asarray(output).reshape(-1, 2), raw)
    assert final == (0, 0)


@pytest.mark.parametrize("count", [1, 2, 31, 32])
def test_finite_limit_delivers_last_sample_before_search_closure(captures, tmp_path, count):
    raw = np.array([[517 + n, -731 - n] for n in range(count + 2)], dtype=np.int16)
    rows = [*arm(visit=519, limit=count), *samples(raw), wait(400), *snapshot(),
            write(0xC10, 2), *(read(a) for a in range(0xD00, 0xD40, 4)),
            read(0xC68), read(0xC6C)]
    output, reads, final = run(captures(2500000, legacy=False, local=True), rows, tmp_path)
    np.testing.assert_array_equal(output, raw[:count])
    state = dict(reads)
    assert u64(state, 0x90) == u64(state, 0x98) == count
    assert u64(state, 0xD38) == u64(state, 0x80)
    assert u64(state, 0xC68) == u64(state, 0x80) + count - 1
    assert state[0xD00] == 0x1B3 and state[0xD04] == state[0xD30] == 0
    assert state[0xD18] == state[0xD1C] == state[0xD2C] == 1
    assert final == (0, 0)


def test_physical_gap_aborts_search_after_the_exact_admitted_prefix(captures, tmp_path):
    raw = np.array([[517 + n, -731 - n] for n in range(31)], dtype=np.int16)
    rows = [*arm(visit=520), *samples(raw), wait(100), (0, 5, 0, 0x12345678, 0),
            wait(400), *snapshot(), write(0xC10, 2),
            *(read(a) for a in range(0xD00, 0xD40, 4)), read(0xC68), read(0xC6C)]
    output, reads, final = run(captures(2500000, legacy=False, local=True), rows, tmp_path)
    np.testing.assert_array_equal(output, raw)
    state = dict(reads)
    assert u64(state, 0x90) == u64(state, 0x98) == len(raw)
    assert u64(state, 0xD38) == u64(state, 0x80)
    assert u64(state, 0xC68) == u64(state, 0x80) + len(raw) - 1
    assert state[0xC8] & 2 and state[0xD04] & 4
    assert state[0xD00] & 0x193 == 0x193
    assert state[0xD24] == state[0xD28] == state[0xD30] == 0
    assert state[0xD1C] == state[0xD2C] == 1
    assert final == (0, 0)
