"""GLA1 profile selects one local search and exactly the DMA-admitted IQ."""
import re

import numpy as np

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
