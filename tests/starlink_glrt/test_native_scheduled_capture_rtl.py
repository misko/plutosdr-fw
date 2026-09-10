"""Complete ADC/CDC/AXI path with one shared full-pilot engine and GLS1 RAM."""
import re

from .test_capture_rtl import captures as captures  # noqa: PLC0414
from .test_capture_rtl import read, run, wait, write
from .test_native_capture_rtl import native_bank
from .test_native_capture_rtl import (
    test_full_native_dma_uses_original_60m_coordinates_and_returns_to_base as manual_dma_check,
)
from .test_native_control_rtl import record


def test_scheduled_image_has_one_engine_and_retains_manual_dma(captures, tmp_path):
    def scheduled(rate, **kwargs):
        return captures(rate, **kwargs, schedule=True)
    executable = scheduled(60000000, native=True, legacy=False)
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', executable.read_text())
    for component in ("native_engine", "native_schedule", "native_result_queue", "native_schedule_control"):
        assert modules.count("starlink_glrt_"+component) == 1
    assert "starlink_glrt_correlator" not in modules and "starlink_glrt_score" not in modules
    manual_dma_check(scheduled, tmp_path, False)


def test_three_scheduled_pilots_through_real_axi_head_reads(captures, tmp_path):
    fields = {0x814: 71, 0x818: 50000, 0x81c: 0, 0x820: 0,
              0x824: (80000 << 16) % 2**32, 0x828: (80000 << 16) >> 32,
              0x82c: (4096 << 16), 0x830: 0, 0x834: 0, 0x838: 0,
              0x83c: 17, 0x840: 3, 0x844: 300000, 0x848: 0}
    rows = [(0, 11, 0, 3, 0), wait(2000), read(0x800), read(0xa00),
            write(0x808, 16), *(write(a, v, skew=a % 3) for a, v in fields.items()),
            write(0x808, 1), wait(500000), read(0x410), read(0x430), read(0x438)]
    for _ in range(3):
        rows += [*(read(a) for a in range(0xa00, 0xa80, 4)), write(0x808, 32)]
    rows += [write(0x808, 8), *(read(a) for a in range(0x900, 0x950, 4)),
             read(0xa00), read(0x810), read(0x10), read(0), read(0x68)]
    output, reads, final = run(captures(60000000, continuous=True, native=True, legacy=False,
                                      schedule=True), rows, tmp_path)
    assert not len(output) and final == (0, 0)
    assert reads[:2] == [(0x800, 0x474c5331), (0xa00, 0)]
    head_words = [v for a, v in reads[2:-5] if 0xa00 <= a < 0xa80]
    assert len(head_words) == 96
    bank = native_bank()
    for frame in range(3):
        start = 50000+80000*frame
        expected = record((start, 17, 4096), 79200, bank, capture=0, tag=71, sequence=frame,
                          iq_values=[(start+n, 700, -200) for n in range(79200)])
        expected[0] = 0x474c5331
        expected[27] = frame
        assert head_words[32*frame:32*(frame+1)] == expected
    snapshot = [v for a, v in reads if 0x900 <= a < 0x950]
    assert snapshot[6:18] == [0, 3, 3, 0, 0, 0, 0, 0, 3, 3, 0, 3]
    regs = dict(reads)
    assert all(regs[a] == 0 for a in (0x410, 0x430, 0x438, 0xa00, 0x810, 0x10))
    assert regs[0] == 0x474c4631 and regs[0x68] == 7


def test_coarse_clear_invalidates_idle_schedule_epoch_even_with_continuous_adc(captures, tmp_path):
    # A rebased, empty scheduler cannot serve as a continuity witness across
    # GLR CLEAR: CLEAR resets source_seen although the ADC counter continues.
    # The native-IQ handoff must retain this distinction from a physical gap.
    snap = [write(0x808, 8), *(read(a) for a in range(0x900, 0x950, 4))]
    rows = [(0, 11, 0, 3, 0), write(8, 4), wait(2000),
        write(0x20, 31), write(0x30, 128), write(8, 1), wait(12000),
        write(8, 2), wait(500), write(0x808, 16), *snap,
        write(8, 4), wait(500), *snap, write(0x808, 4), wait(100), read(0x810)]
    output, reads, final = run(captures(60000000, continuous=True, native=True,
        legacy=False, schedule=True), rows, tmp_path)
    words = [value for address, value in reads if 0x900 <= address < 0x950]
    before, after = words[:20], words[20:]
    assert len(words) == 40 and len(output) == 128
    assert before[2] == after[2] == 1
    assert before[5] & 16 and before[6] == 0
    assert not after[5] & 16 and after[6] == 8
    assert before[18:] == after[18:] == [0, 0]
    assert (after[3] | after[4] << 32) > (before[3] | before[4] << 32)
    assert dict(reads)[0x810] == 0 and final == (0, 0)
