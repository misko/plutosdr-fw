"""C251 common IQ admission, real detector, AXI snapshots and export faults."""
import numpy as np
import pytest

from .test_pilot_capture_rtl import (
    arm, compile_simulator, read, run, snapshot, u64, write,
)
from tests.test_starlink_coarse25_fold_rtl import expected_map
from tools.starlink_coarse25_fixed import scores as fixed_scores


@pytest.fixture(scope="module")
def simulator(tmp_path_factory):
    # Shorter map for lifecycle regressions; deployed/default RTL stays 29.
    return compile_simulator(tmp_path_factory.mktemp("coarse25-capture"),
                             coarse25=True, coarse_groups=1)


def iq(values, first=0, spacing=40):
    return [(spacing-1, 1, first+n,
             (int(i) & 65535) | ((int(q) & 65535) << 16), 0)
            for n, (i, q) in enumerate(values)]


def coarse_snapshot():
    return [*snapshot(), *(read(a) for a in range(0xa0, 0xd4, 4))]


@pytest.mark.parametrize("first", [0, (1 << 63)+37])
def test_bypass_exact_iq_and_honest_geometry(simulator, first):
    values = np.random.default_rng(778).integers(-32768, 32768, (1024, 2), dtype=np.int16)
    out, reads, final = run(simulator, [*(read(a) for a in (0, 4, 0x14, 0x18, 0x1c, 0x24, 0x28, 0x2c)),
                                      *arm(), *iq(values, first), write(8, 2), *coarse_snapshot()])
    np.testing.assert_array_equal(out, values)
    regs = dict(reads)
    assert [regs[a] for a in (0, 4, 0x14, 0x18, 0x1c, 0x24, 0x28, 0x2c)] == [
        0x43323531, 0x10000, 2500000, 2500000, 1, 0, 0, 0]
    assert u64(regs, 0x30) == first and u64(regs, 0x38) == first+1023
    assert u64(regs, 0x40) == u64(regs, 0x48) == 1024
    assert u64(regs, 0x50) == 0 and regs[0x78] == 0
    assert regs[0xa0] == 0 and regs[0xc8] == 0
    assert final == (0, 0)


def test_real_detector_second_map_exact_and_snapshot_immutable(simulator):
    values = np.random.default_rng(715).integers(-4000, 4000, (20016, 2), dtype=np.int16)
    out, reads, final = run(simulator, [*arm(), (25000, 7, 0, 0, 0), *iq(values, 9001),
                                      (40000, 7, 0, 0, 0), write(8, 2), *coarse_snapshot(),
                                      (10000, 7, 0, 0, 0), read(0xa0), read(0xa8)])
    np.testing.assert_array_equal(out, values)
    regs = dict(reads)
    scores = fixed_scores(values)
    expected = expected_map(scores[10000:20000], 10000)
    actual = (u64(regs, 0xa8), regs[0xb0], regs[0xb4], regs[0xb8],
              u64(regs, 0xbc), regs[0xc4], (regs[0xa4] >> 1) & 1)
    assert actual == expected
    assert regs[0xa0] == 2 and regs[0xa4] & 1 and regs[0xc8] == 0
    assert regs[0xcc] == 10000 and regs[0xd0] == 0x10010
    assert regs[0x78] == 0 and final == (0, 0)
    assert reads[-2:] == [(0xa0, 2), (0xa8, 10000)]


@pytest.mark.parametrize("kind,mask", [("overflow", 4), ("index", 8), ("gap", 2), ("flush", 16)])
def test_fault_keeps_iq_prefix_and_expires_detector(simulator, kind, mask):
    values = np.arange(200, dtype=np.int16).reshape(-1, 2)
    if kind == "overflow":
        records = [(1, 4, 0, 0, 0), *iq(values)]
        count = 32
    else:
        records = [(1, 4, 0, 0, 0), *iq(values[:20])]
        records += iq(values[20:21], 21) if kind == "index" else [(1, 5 if kind == "gap" else 6, 0, 0, 0)]
        count = 20
    out, reads, final = run(simulator, [*arm(), *records, (100, 7, 0, 0, 0),
                                      (1, 4, 0, 1, 0), (100, 7, 0, 0, 0), *coarse_snapshot()])
    np.testing.assert_array_equal(out, values[:count])
    regs = dict(reads)
    assert regs[0x78] == mask and u64(regs, 0x40) == u64(regs, 0x48) == count
    assert regs[0xa0] == 0 and regs[0xa4] & 8 and final == (0, 1)


def test_stop_drain_clear_rearm_limit(simulator):
    values = np.ones((100, 2), dtype=np.int16)*321
    out, reads, final = run(simulator, [*arm(), (1, 4, 0, 0, 0), *iq(values[:16], 101),
                                      write(8, 2), (1, 4, 0, 1, 0), (100, 7, 0, 0, 0),
                                      write(8, 4), write(0x20, 18), write(0x9c, 20), write(8, 1),
                                      *iq(values, 900), *coarse_snapshot()])
    np.testing.assert_array_equal(out, values[:36])
    regs = dict(reads)
    assert u64(regs, 0x30) == 900 and u64(regs, 0x38) == 919
    assert u64(regs, 0x40) == u64(regs, 0x48) == 20
    assert regs[0x80] == 18 and regs[0xa0] == 0 and regs[0xc8] == 0
    assert final == (0, 0)
