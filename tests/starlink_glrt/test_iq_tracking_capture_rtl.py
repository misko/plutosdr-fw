"""GLI1: ARM acquisition IQ export concurrent with native 30/60-MS/s GLT1."""
import re
from fractions import Fraction

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from tools.starlink_glrt_tracking_abi import TrackingBatch, TrackingResult

from .ddc import BANK_ROOT, Ddc, group_delay
from .test_capture_rtl import captures as captures, read, run, snapshot, u64, wait, write
from .test_native_engine_rtl import expected
from .test_native_queued_engine_rtl import signed
from .test_tracking_capture_rtl import decode_snapshot, groups, head, pattern, tracking_snapshot


@pytest.mark.parametrize("rate", [30_000_000, 60_000_000])
def test_profile_has_one_tracker_and_no_acquisition_or_legacy_engine(rate, captures, tmp_path):
    executable = captures(rate, continuous=True, legacy=False, tracking=True)
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', executable.read_text())
    assert modules.count("starlink_glrt_native_engine") == 1
    assert modules.count("starlink_glrt_tracking_control") == 1
    assert not any(name in modules for name in (
        "starlink_glrt_local_control", "starlink_glrt_native_control",
        "starlink_glrt_acquisition", "starlink_glrt_correlator"))
    addresses = (0, 4, 0x14, 0x18, 0x1c, 0x28, 0x2c, 0x5c, 0x68,
                 0x400, 0x800, 0x804, 0x880, 0x884, 0xc00)
    output, reads, final = run(executable, [read(a) for a in addresses], tmp_path)
    assert not output and final == (0, 0)
    assert dict(reads) == dict(zip(addresses, (
        0x474c4931, 0x10000, rate, 2500000, rate//2500000,
        group_delay(rate), 2*group_delay(rate), 0x474c4931, 17,
        0, 0x474c5431, 0x10000, rate*33//25000, rate, 0), strict=True))


@pytest.mark.parametrize("rate", [30_000_000, 60_000_000])
@pytest.mark.parametrize("termination", ["complete", "gap", "cancel"])
def test_native_moments_and_filtered_iq_share_continuous_source_and_drain(
    rate, termination, captures, tmp_path
):
    start = rate//2500
    period = round(Fraction(rate*65536, 750))
    fields = [71, start, 0, 24576, period & 0xffffffff, period >> 32,
              4096 << 16, 0, 0, 0, 17, 2, rate//100, 0]
    rows = [(0, 11, 0, 3, 1), write(8, 4), wait(2000), write(0x20, 517), write(8, 1),
            write(0x808, 16), *(write(0x814+4*n, v) for n, v in enumerate(fields)),
            write(0x808, 1), wait(400000 if termination == "complete" else 210000)]
    if termination == "gap": rows += [(0, 5, 0, 0x12345678, 0), wait(100)]
    if termination == "cancel": rows += [write(0x808, 2), wait(500)]
    rows += [write(8, 2), wait(500), *snapshot(), *tracking_snapshot(),
             *head(), write(0x808, 32), *head(), write(0x808, 32), *tracking_snapshot(),
             write(0x808, 4), wait(100), write(8, 4), wait(100), read(0x10), read(0x810)]
    output, reads, final = run(captures(rate, continuous=True, legacy=False, tracking=True), rows, tmp_path)
    assert final == (0, 0) and reads[-2:] == [(0x10, 0), (0x810, 0)]
    base = dict(reads[:65])
    first, last = u64(base, 0x80), u64(base, 0x88)
    assert u64(base, 0x90) == u64(base, 0x98) == len(output)
    assert last == first+(len(output)-1)*(rate//2500000)
    assert (base[0xc8] & 2 != 0) == (termination == "gap")
    native_first = first-2*group_delay(rate)
    raw = np.asarray([pattern(n) for n in range(native_first, last+1)], dtype=np.int16)
    filtered = Ddc(rate).process(raw, native_first)
    np.testing.assert_array_equal(output, filtered.iq[filtered.supported])
    before, after = map(decode_snapshot, groups(reads, 0x900, 24))
    assert (before.configured, before.admitted, before.committed, before.queued) == (2, 2, 2, 2)
    after.require_drained()
    batch = TrackingBatch(rate, 1, 71, start, 24576, period, 4096*65536, 0, 17, 2, rate//100)
    cubic = (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes()
    direct = (BANK_ROOT/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes()
    for frame, words in enumerate(groups(reads, 0xa00, 32)):
        result = TrackingResult.from_sysfs("GLT1 00010000 00000001 "+" ".join(f"{v:08x}" for v in words))
        result.require_association(batch, sequence=frame)
        if termination == "complete" or frame == 0:
            result.require_complete()
        else:
            assert 0 < result.count < rate*33//25000 and result.fault
        bank = reference_rows(cubic, direct, rate, result.reference_phase)
        coefficients = [[n, *c, int(n == len(bank)-1), 0] for n, c in enumerate(bank)]
        values = [(result.start+n, *pattern(result.start+n)) for n in range(result.count)]
        oracle = expected((result.start, 17, 4096), values, coefficients)
        assert [signed(words[n:n+2]) for n in (9, 11, 13, 15)] == oracle[5:9]
        assert [signed(words[n:n+3]) for n in (17, 20)] == oracle[9:11]
        assert words[23]+(words[24] << 32) == oracle[11]
