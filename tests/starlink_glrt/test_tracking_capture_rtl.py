"""Integrated GLA1 IQ capture, shared acquisition RAM and native GLT1 tracking."""
import re
from fractions import Fraction

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from tools.starlink_glrt_tracking_abi import (
    TrackingBatch,
    TrackingResult,
    TrackingSnapshot,
)

from .ddc import BANK_ROOT
from .test_capture_rtl import captures as captures  # noqa: PLC0414
from .test_capture_rtl import read, run, snapshot, u64, wait, write
from .test_native_engine_rtl import expected
from .test_native_queued_engine_rtl import signed


def pattern(index):
    pair = ((index*73+19) & 65535, (index & 65535) ^ 0xa5a5)
    return tuple(v if v < 32768 else v-65536 for v in pair)


def head():
    return [read(a) for a in range(0xa00, 0xa80, 4)]


def tracking_snapshot():
    return [write(0x808, 8), *(read(a) for a in range(0x900, 0x960, 4))]


def configuration(start=1000, repeats=3, tag=71):
    period = round(Fraction(2500000*65536, 750))
    fields = [tag, start, 0, 24576, period, 0, 4096 << 16, 0, 0, 0, 17, repeats, 30000, 0]
    return [write(0x814+4*n, value) for n, value in enumerate(fields)]+[write(0x808, 1)]


def groups(reads, first, count):
    return [[v for _, v in reads[n:n+count]] for n, (address, _) in enumerate(reads) if address == first]


def decode_snapshot(words):
    return TrackingSnapshot.from_sysfs("GLT1SNAP 00010000 "+" ".join(f"{v:08x}" for v in words))


@pytest.mark.parametrize("command,strobe", [(0, 15), (3, 15), (0x80000002, 15), (2, 7)])
def test_registered_commands_reject_partial_and_aliased_writes(captures, tmp_path, command, strobe):
    # CANCEL is legal while idle. Invalid commands must not become CANCEL
    # merely because bit 1 is set, or because the previous command was valid.
    rows = [write(0x808, 2), read(0x810), write(0x808, command, strobe=strobe),
            read(0x810), write(0x808, 4), wait(20), read(0x810),
            write(0x808, 2), read(0x810)]
    output, reads, final = run(
        captures(2500000, continuous=True, legacy=False, local=True, tracking=True), rows, tmp_path
    )
    assert not output and final == (0, 0)
    assert reads == [(0x810, 0), (0x810, 1), (0x810, 0), (0x810, 0)]


def test_first_tracking_image_has_one_native_engine_and_shared_acquisition(captures, tmp_path):
    executable = captures(2500000, continuous=True, legacy=False, local=True, tracking=True)
    source = executable.read_text()
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', source)
    for name in ("tracking_control", "native_engine", "native_schedule_control", "native_result_queue",
                 "local_search", "local_control"):
        assert modules.count("starlink_glrt_"+name) == 1
    assert "starlink_glrt_native_control" not in modules
    assert "starlink_glrt_fir_decimator" not in modules
    addresses = (0, 0x68, 0x400, 0x800, 0x804, *range(0x880, 0x89c, 4), 0xc00)
    output, reads, final = run(executable, [read(a) for a in addresses], tmp_path)
    assert not output and final == (0, 0)
    assert dict(reads) == dict(zip(addresses, (0x474c4131, 25, 0, 0x474c5431, 0x10000,
        3300, 2500000, 64, 0xdc509401, 1, 4, 24, 0x474c4131), strict=True))
    # Inspect the elaborated parameter, not a source-text claim about sharing.
    assert re.search(r'\.param/l "SHARED_WINDOW".*C4<0*1>;', source)
    assert re.search(r'\.param/l "SERIAL_ROTATE".*C4<0*1>;', source)
    assert re.search(r'\.scope generate, "g_serial"', source)


@pytest.mark.parametrize(("termination", "stop_phase"), [
    ("complete", 0), ("gap", 0), ("cancel", 0),
    # Sweep one complete 2.5-MS/s sample interval at the 100-MHz core clock.
    # Every partial result must remain independently covered by exported IQ.
    *(("mid-pilot", phase) for phase in range(40)),
])
def test_exact_native_results_coexist_with_iq_and_stop_keeps_queued_evidence(
    captures, tmp_path, termination, stop_phase
):
    completed = termination == "complete"
    count = 3 if completed else 2
    rows = [(0, 11, 0, 3, 1), write(8, 4), wait(2000), write(0x20, 517), write(8, 1),
        write(0x808, 16), *configuration(), wait(450000 if completed else 200000+stop_phase)]
    if termination == "gap": rows += [(0, 5, 0, 0x12345678, 0), wait(100)]
    if termination == "cancel": rows += [write(0x808, 2), wait(500)]
    rows += [write(8, 2), wait(500), *snapshot(), *tracking_snapshot()]
    for _ in range(count): rows += [*head(), write(0x808, 32)]
    rows += [*tracking_snapshot(), write(0x808, 4), wait(100), write(8, 4), wait(100),
             read(0x10), read(0xc0c), read(0x810)]
    output, reads, final = run(captures(2500000, continuous=True, legacy=False, local=True, tracking=True), rows, tmp_path)
    assert final == (0, 0)
    base = dict(reads[:65])
    first = u64(base, 0x80)
    assert u64(base, 0x90) == u64(base, 0x98) == len(output)
    np.testing.assert_array_equal(output, [pattern(first+n) for n in range(len(output))])
    assert (base[0xc8] & 2 != 0) == (termination == "gap")
    assert reads[-3:] == [(0x10, 0), (0xc0c, 0), (0x810, 0)]
    before, after = map(decode_snapshot, groups(reads, 0x900, 24))
    assert before.epoch == 1 and before.faults == 8 and before.configured == 3
    assert (before.admitted, before.committed, before.queued) == (count, count, count)
    assert before.unavailable == (0 if completed or termination == "cancel" else 1)
    assert before.cancelled == (1 if termination == "cancel" else 0)
    after.require_drained()
    b = TrackingBatch(2500000, 1, 71, 1000, 24576, round(Fraction(2500000*65536, 750)),
                      4096*65536, 0, 17, 3, 30000)
    cubic = (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes()
    direct = (BANK_ROOT/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes()
    records = groups(reads, 0xa00, 32)
    assert len(records) == count
    for frame, w in enumerate(records):
        result = TrackingResult.from_sysfs("GLT1 00010000 00000001 "+" ".join(f"{v:08x}" for v in w))
        result.require_association(b, sequence=frame)
        if completed or frame == 0: result.require_complete()
        else: assert 0 < result.count < 3300 and result.fault & (0x100 if termination == "cancel" else 0x200)
        raw = reference_rows(cubic, direct, 2500000, result.reference_phase)
        coefficients = [[n, *c, int(n == 3299), 0] for n, c in enumerate(raw)]
        values = [(result.start+n, *pattern(result.start+n)) for n in range(result.count)]
        oracle = expected((result.start, 17, 4096), values, coefficients)
        assert [signed(w[n:n+2]) for n in (9, 11, 13, 15)] == oracle[5:9]
        assert [signed(w[n:n+3]) for n in (17, 20)] == oracle[9:11]
        assert w[23]+(w[24] << 32) == oracle[11]
        # Retained independent IQ covers every source sample used by the tracker.
        np.testing.assert_array_equal(output[result.start-first:result.start-first+result.count],
                                      [value[1:] for value in values])


def test_stop_drain_restart_changes_epoch_without_resetting_native_coordinates(captures, tmp_path):
    rows = [(0, 11, 0, 3, 1), write(8, 4), wait(2000), write(0x20, 518), write(8, 1),
            write(0x808, 16), *configuration(repeats=1), wait(200000), write(8, 2), wait(500),
            *snapshot(), *head(), *tracking_snapshot(), write(0x808, 32), write(0x808, 4),
            wait(100), write(8, 4), wait(100), write(0x20, 519), write(8, 1), write(0x808, 16),
            *configuration(start=10000, repeats=1, tag=72), wait(400000), write(8, 2), wait(500),
            *snapshot(), *head(), *tracking_snapshot(), write(0x808, 32), write(0x808, 4),
            wait(100), write(8, 4), wait(100), read(0x10), read(0xc0c), read(0x810)]
    output, reads, final = run(captures(2500000, continuous=True, legacy=False, local=True, tracking=True), rows, tmp_path)
    assert final == (0, 0) and reads[-3:] == [(0x10, 0), (0xc0c, 0), (0x810, 0)]
    states = list(map(decode_snapshot, groups(reads, 0x900, 24)))
    assert [s.epoch for s in states] == [1, 2]
    assert all((s.configured, s.admitted, s.committed, s.queued, s.faults) == (1, 1, 1, 1, 8) for s in states)
    positions = [n for n, (a, _) in enumerate(reads) if a == 0x80]
    base = [dict(reads[n:n+64]) for n in positions]
    assert len(base) == 2 and u64(base[1], 0x80) > u64(base[0], 0x80)+u64(base[0], 0x90)
    expected_iq = [pattern(u64(s, 0x80)+n) for s in base for n in range(u64(s, 0x90))]
    np.testing.assert_array_equal(output, expected_iq)
    for n, w in enumerate(groups(reads, 0xa00, 32)):
        result = TrackingResult.from_sysfs(f"GLT1 00010000 {n+1:08x} "+" ".join(f"{v:08x}" for v in w))
        b = TrackingBatch(2500000, n+1, 71+n, 1000 if n == 0 else 10000, 24576,
                         round(Fraction(2500000*65536, 750)), 4096*65536, 0, 17, 1, 30000)
        result.require_association(b, sequence=0)
        result.require_complete()
