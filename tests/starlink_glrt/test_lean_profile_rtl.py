"""GLF1 removes legacy scoring while retaining real IQ and timing proposals."""
import re

import numpy as np

from .ddc import Ddc
from .test_capture_rtl import (
    arm,
    extension_snapshot,
    read,
    run,
    samples,
    snapshot,
    u64,
    wait,
    write,
)
from .test_capture_rtl import (
    captures as captures,  # noqa: PLC0414 -- pytest fixture re-export
)
from .test_receiver_rtl import observation


def test_lean_elaboration_has_one_native_engine_and_no_legacy_scorers(captures):
    executable = captures(60000000, native=True, legacy=False)
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', executable.read_text())
    assert modules.count("starlink_glrt_native_engine") == 1
    assert modules.count("starlink_glrt_ddc") == 1
    assert modules.count("starlink_glrt_acquisition") == 1
    assert modules.count("starlink_glrt_candidate_select") == 1
    for removed in ("starlink_glrt_correlator", "starlink_glrt_score", "starlink_glrt_vector_stage"):
        assert removed not in modules


def test_lean_positive_pilot_preserves_iq_without_fabricating_legacy_results(captures, tmp_path):
    raw, _, _ = observation(60000000, "positive")
    rows = [*arm(visit=301), write(0x44, 7), *samples(raw), wait(75000), write(8, 2),
            wait(1000), *snapshot(), *extension_snapshot(), read(0), read(0x68),
            *(read(address) for address in range(0x200, 0x240, 4))]
    output, reads, final = run(captures(60000000, native=True, legacy=False), rows, tmp_path)
    oracle = Ddc(60000000).process(raw, 16)
    np.testing.assert_array_equal(output, oracle.iq[oracle.supported])
    regs = dict(reads)
    assert regs[0] == regs[0x5c] == 0x474c4631 and regs[0x68] == 7
    assert u64(regs, 0xf0) > 0 and u64(regs, 0xf8) > 0  # proposals, selections
    assert u64(regs, 0x90) == u64(regs, 0x98) == len(output)
    assert regs[0xc4] == regs[0xc8] == regs[0x148] == 0
    for address in (0x108, 0x110, 0x118, 0x154, 0x15c, 0x310, 0x320, 0x328, 0x330, 0x338):
        assert u64(regs, address) == 0
    assert regs[0x174] == 0 and regs[0x300] == 7 and regs[0x304] == 0
    assert all(regs[address] == 0 for address in range(0x200, 0x240, 4))
    assert final == (0, 0)
