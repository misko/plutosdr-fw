"""Complete AXI/CDC receiver: native evidence DMA, isolation and return to GLR1."""
import hashlib
import struct

import pytest

from tools.starlink_glrt_native_abi import NativeResult
from tools.starlink_glrt_native_replay import verify as verify_original_iq

from .ddc import BANK_ROOT
from .test_capture_rtl import (
    captures as captures,  # noqa: PLC0414 -- re-export the pytest fixture
)
from .test_capture_rtl import read, run, snapshot, u64, wait, write
from .test_capture_rtl import (
    test_autonomous_glrt_event_words_and_irq_drain as check_reference_events,
)
from .test_cubic_reference_rtl import WIDTHS
from .test_native_control_rtl import record


def native_bank():
    data = (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "b04a2fab04e89229916afedfa1b34ba327d99d50968b2a81ddb48a4f8293f5e8"
    bank = []
    for text in data.splitlines():
        word, segment = int(text, 16), []
        for width in WIDTHS:
            pair = []
            for _ in range(2):
                value = word & ((1 << width)-1)
                pair.append(value-(1 << width) if value >> (width-1) else value)
                word >>= width
            segment.append(pair)
        assert word == 0
        bank.append(segment)
    return bank


def native_config(capture=1):
    return [write(a, v) for a, v in ((0x414, 17), (0x420, 2**32-7), (0x424, 91771), (0x428, capture))]


def native_head():
    return [read(a) for a in range(0x600, 0x680, 4)]


def native_finish():
    return [write(0x408, 8), wait(100), write(0x408, 4), read(0x410)]


def test_refinement_image_preserves_blind_reference_iq_scores_and_irq(captures, tmp_path):
    check_reference_events(60000000, lambda rate: captures(rate, native=True), tmp_path)


def test_coarse_stop_clear_then_exact_native_start_preserves_source_coordinates(captures, tmp_path):
    # A varying source makes a rebase, displaced pilot or wrong DMA prefix
    # observable. This is coordinate/arithmetic evidence, not RF acquisition.
    start = 40000
    rows = [(0, 11, 0, 3, 1), write(8, 4), wait(2000),
        write(0x20, 31), write(0x30, 128), write(8, 1), wait(12000),
        write(8, 2), *snapshot(), write(8, 4), wait(500), *native_config(),
        write(0x418, start), write(0x41c, 0), write(0x408, 1), wait(220000),
        *native_head(), *native_finish()]
    output, reads, final = run(
        captures(60000000, continuous=True, native=True, legacy=False, schedule=True),
        rows, tmp_path)
    coarse = dict(reads[:65])
    assert u64(coarse, 0x90) == u64(coarse, 0x98) == 128
    assert coarse[0xc8] == 0
    header = [value for address, value in reads if 0x600 <= address < 0x680]
    decoded = NativeResult.decode(struct.pack("<32I", *header))
    decoded.require_complete()
    assert decoded.start == start
    assert len(output) == 128 + 79200
    expected = []
    for index in range(start, start + 79200):
        pair = ((index*73+19) & 65535, (index & 65535) ^ 0xa5a5)
        expected.append(tuple(value if value < 32768 else value-65536 for value in pair))
    assert output[128:] == expected
    original = b"".join(struct.pack("<hh", *value) for value in output[128:])
    decoded.require_native_evidence(received_bytes=len(original), expected_tag=17,
                                    expected_start=start)
    replay = verify_original_iq(decoded, original,
        (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes())
    assert replay["exact_integer_match"] and not replay["precision_qualified"]
    assert dict(reads)[0x410] == 0 and final == (0, 0)


@pytest.mark.parametrize("legacy", [True, False])
def test_full_native_dma_uses_original_60m_coordinates_and_returns_to_base(captures, tmp_path, legacy):
    rows = [(0, 11, 0, 3, 0), wait(2000), *native_config(), (0, 14, 0, 6000, 0), wait(150000),
        *native_head(), *native_finish(), *snapshot(), *native_config(),
        (0, 14, 0, 6000, 0), wait(150000), *native_head(), *native_finish(),
        write(8, 4), wait(500), write(0x20, 19), write(0x30, 128), write(8, 1), wait(20000),
        write(8, 2), *snapshot(), read(0x400), read(0x404), read(0x458), read(0x45c), read(0x460)]
    output, reads, final = run(captures(60000000, continuous=True, native=True, legacy=legacy), rows, tmp_path)
    headers = [v for a, v in reads if 0x600 <= a < 0x680]
    assert len(headers) == 64
    bank = native_bank()
    for job_index, header in enumerate((headers[:32], headers[32:])):
        job = (header[3] | header[4] << 32, 2**32-7, 91771)
        values = [(job[0]+n, 700, -200) for n in range(79200)]
        assert header == record(job, 79200, bank, iq_values=values)
        decoded = NativeResult.decode(struct.pack("<32I", *header))
        decoded.require_complete()
        decoded.require_native_evidence(received_bytes=316800, expected_tag=17, expected_start=job[0])
        original = b"".join(struct.pack("<hh", *value) for value in output[job_index*79200:(job_index+1)*79200])
        replay = verify_original_iq(decoded, original, (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes())
        assert replay["exact_integer_match"] is True and replay["precision_qualified"] is False
    assert output[:158400] == [(700, -200)]*158400
    assert len(output) == 158400+128
    assert [v for a, v in reads if a == 0x410] == [0, 0]
    snapshots = [reads[i:i+65] for i, pair in enumerate(reads) if pair[0] == 0x80]
    assert len(snapshots) == 2
    first, last = (dict(values) for values in snapshots)
    assert all(first[a] == 0 for a in (0x80, 0x84, 0x88, 0x8c, 0x90, 0x94, 0x98, 0x9c, 0xc8, 0xd4, 0xd8))
    assert u64(last, 0x90) == u64(last, 0x98) == 128 and last[0xc8] == 0
    regs = dict(reads)
    assert [regs[a] for a in (0x400, 0x404, 0x458, 0x45c, 0x460)] == [0x474c4e31, 0x10000, 1, 60000000, 3]
    assert final == (0, 0)


@pytest.mark.parametrize("fifo_bits", [5, 8])
@pytest.mark.parametrize("backpressure", ["periodic", "full"])
@pytest.mark.parametrize("legacy", [True, False])
def test_varying_native_iq_preserves_order_across_stalls_and_fifo_wrap(captures, tmp_path, fifo_bits, backpressure, legacy):
    # The source emits a distinct deterministic CI16 word at each ADC index.
    # Periodic 20-cycle stalls build and drain the queue repeatedly, including
    # single-word replacements and many wraps at the actual board FIFO depth.
    pressure = (0, 4, 0, 3, 0) if backpressure == "periodic" else (0, 15, 0, 0, 0)
    required_coverage = 0b11011 if backpressure == "periodic" else 0b11101
    rows = [(0, 11, 0, 3, 1), wait(2000), *native_config(),
            (0, 14, 0, 6000, 0), pressure, wait(150000), (0, 4, 0, 1, 0), wait(500),
            (0, 16, 0, required_coverage, 0), *native_head(), *native_finish()]
    output, reads, final = run(captures(60000000, continuous=True, native=True, fifo_bits=fifo_bits, legacy=legacy), rows, tmp_path)
    header = [value for address, value in reads if 0x600 <= address < 0x680]
    decoded = NativeResult.decode(struct.pack("<32I", *header))
    decoded.require_complete()
    start = header[3] | header[4] << 32
    expected = []
    for index in range(start, start+79200):
        unsigned = ((index*73+19) & 65535, (index & 65535) ^ 0xa5a5)
        expected.append(tuple(value if value < 32768 else value-65536 for value in unsigned))
    assert output == expected
    original = b"".join(struct.pack("<hh", *value) for value in output)
    decoded.require_native_evidence(received_bytes=len(original), expected_tag=17, expected_start=start)
    replay = verify_original_iq(decoded, original, (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes())
    assert replay["exact_integer_match"] is True
    assert dict(reads)[0x410] == 0 and final == (0, 0)


@pytest.mark.parametrize("legacy", [True, False])
def test_native_dma_overflow_preserves_offered_words_across_invalid_clear(captures, tmp_path, legacy):
    rows = [(0, 11, 0, 3, 0), wait(2000), *native_config(), (0, 4, 0, 0, 0),
        (0, 14, 0, 6000, 0), wait(12000), read(0x40c), *native_head(),
        write(8, 4), write(0x408, 8), write(0x408, 4), wait(100),
        (0, 4, 0, 1, 0), wait(100), *native_head(), *native_finish(),
        write(8, 4), wait(500), *snapshot()]
    output, reads, final = run(captures(60000000, continuous=True, native=True, legacy=legacy), rows, tmp_path)
    headers = [v for a, v in reads if 0x600 <= a < 0x680]
    assert headers[:32] == [0]*32
    failed = headers[32:]
    assert failed[0] == 0x474c4e31 and failed[8] & 0x108 == 0x108
    assert failed[28] == failed[29] == 32 and 0 < failed[7] < 32
    assert output == [(700, -200)]*32
    regs = dict(reads)
    assert regs[0x410] == regs[0xc8] == 0 and final == (0, 0)
