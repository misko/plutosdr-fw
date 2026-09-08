"""Real ADC-clock ingress, blind FPGA GLRT, AXI control and continuous IQ FIFO."""
from pathlib import Path
from dataclasses import replace
import struct
import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, Ddc, RATES
from .pilot import fixed_score, symbol_correlations
from .test_receiver_rtl import observation
from tools.starlink_glrt_abi import Snapshot, Event

IP_ROOT = BANK_ROOT.parent/"axi_starlink_glrt"


@pytest.fixture(scope="session")
def captures(tmp_path_factory):
    root = tmp_path_factory.mktemp("capture-compile")
    cache = {}
    def get(rate, continuous=False):
        key = rate, continuous
        if key not in cache:
            source = (IP_ROOT/"tb/tb_starlink_glrt_capture.sv").read_text()
            for token, filename in {
                "NATIVE_FILE": f"pilot_{rate}_upper_q7.mem", "ACQUISITION_FILE": "pilot_2500000_upper_q7.mem",
                "FIRST_FILE": f"ddc_{rate}_q17.mem", "FINAL_FILE": "ddc_5000000_q17.mem", "TWIDDLE_FILE": "glrt_dft512_q15.mem",
            }.items():
                source = source.replace(f'"{token}"', f'"{BANK_ROOT/filename}"')
            bench, executable = root/f"tb_{rate}_{int(continuous)}.sv", root/f"sim_{rate}_{int(continuous)}"
            bench.write_text(source)
            top = "tb_starlink_glrt_capture"
            process = subprocess.run(["iverilog", "-g2012", "-s", top, f"-P{top}.SOURCE_RATE_HZ={rate}",
                                      f"-P{top}.SOURCE_CONTINUOUS={int(continuous)}",
                                      "-o", str(executable), str(bench),
                                      *map(str, sorted(BANK_ROOT.glob("*.v"))),
                                      str(IP_ROOT/"axi_starlink_glrt.v"), str(IP_ROOT/"starlink_glrt_axi_lite.v")],
                                     capture_output=True, text=True)
            assert process.returncode == 0, process.stdout+process.stderr
            cache[key] = executable
        return cache[key]
    return get


def write(address, value, strobe=15, skew=0):
    return 1, 2, address, value, strobe+(skew << 8)


def read(address):
    return 1, 3, address, 0, 0


def wait(cycles=200):
    return cycles, 7, 0, 0, 0


def arm(visit=17, limit=0):
    return [write(8, 4), (0, 9, 0, 16, 0), wait(), write(0x20, visit),
            write(0x30, limit), write(8, 1, skew=3)]


def samples(values):
    return [(0, 1, 0, (int(i) & 65535) | ((int(q) & 65535) << 16), 0) for i, q in values]


def snapshot():
    return [write(8, 8), *(read(address) for address in range(0x80, 0x180, 4)), read(0x48)]


def run(simulator, rows, tmp_path):
    (tmp_path/"stimulus.txt").write_text("".join(f"{delay} {op} {idx:x} {value:x} {arg}\n"
                                               for delay, op, idx, value, arg in rows))
    process = subprocess.run(["vvp", str(simulator)], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    (tmp_path/"rtl_trace.txt").write_text(process.stdout+process.stderr)
    assert process.returncode == 0, process.stdout+process.stderr
    output, reads, final = [], [], None
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] == "OUT":
            word = int(words[1], 16)
            output.append(tuple(v if v < 32768 else v-65536 for v in (word & 65535, word >> 16)))
        elif words[0] == "READ":
            reads.append(tuple(int(w, 16) for w in words[1:]))
        elif words[0] == "FINAL":
            final = tuple(map(int, words[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)
    assert final is not None
    return output, reads, final


def u64(regs, offset):
    return regs[offset] | regs[offset+4] << 32


def decode_snapshot(regs, rate, event_count=0):
    # Real fabric words with a constructed kernel header. This exercises the
    # offline parser, not Linux/DMA/IIO or a physical receiver.
    header = f"GLR1 00010000 {rate} 2500000 {regs[0x48]} 0 {rate} 0 {event_count} {event_count} 0 0 0 0 "
    return Snapshot.decode(header+" ".join(f"{regs[a]:08x}" for a in range(0x80, 0x180, 4)))


@pytest.mark.parametrize("rate", RATES)
def test_true_source_rate_continuous_iq_and_snapshot(rate, captures, tmp_path):
    raw = np.random.default_rng(32900).integers(-10000, 10001, (8000, 2), dtype=np.int16)
    rows = [read(0), read(0x14), read(0x18), read(0x1c), *arm(), *samples(raw), wait(75000),
            write(8, 2), *snapshot()]
    output, reads, final = run(captures(rate), rows, tmp_path)
    oracle = Ddc(rate).process(raw, 16)
    np.testing.assert_array_equal(output, oracle.iq[oracle.supported])
    regs = dict(reads)
    assert (regs[0], regs[0x14], regs[0x18], regs[0x1c]) == (0x474c5231, rate, 2500000, rate//2500000)
    assert u64(regs, 0x80) == int(oracle.indexes[oracle.supported][0])
    assert u64(regs, 0x88) == int(oracle.indexes[oracle.supported][-1])
    assert u64(regs, 0x90) == u64(regs, 0x98) == len(output)
    assert u64(regs, 0xa0) == int((~oracle.supported).sum())
    assert u64(regs, 0xb0) == len(raw) and u64(regs, 0xb8) == len(oracle.iq)
    assert regs[0xc0] == oracle.clips and regs[0xc4] == regs[0xc8] == 0
    assert regs[0x148] == 0
    assert regs[0xd0] == 17 and regs[0x48] == 1 and final == (0, 0)
    decoded = decode_snapshot(regs, rate)
    decoded.require_iq_prefix(expected_visit=17, expected_rate=rate, received_bytes=4*len(output))
    assert decoded.source_center(0) == int(oracle.indexes[oracle.supported][0])-regs[0x17c]


@pytest.mark.parametrize("rate", [2500000, 60000000])
def test_autonomous_glrt_event_words_and_irq_drain(rate, captures, tmp_path):
    raw, epoch, _ = observation(rate, "positive")
    rows = [*arm(visit=301), write(0x44, 7), *samples(raw), wait(75000), write(8, 2),
            (1, 10, 0, 0, 0), *snapshot()]
    output, reads, final = run(captures(rate), rows, tmp_path)
    oracle_iq = Ddc(rate).process(raw, 16)
    np.testing.assert_array_equal(output, oracle_iq.iq[oracle_iq.supported])
    event_words = [value for address, value in reads if 0x200 <= address < 0x240]
    assert event_words and len(event_words) % 16 == 0
    events = np.array(event_words, dtype=np.uint32).reshape(-1, 16).tolist()
    near_truth = []
    for sequence, words in enumerate(events):
        assert words[0] == 301 and words[1]+(words[2] << 32) == sequence
        result_epoch = words[3]+(words[4] << 32)
        local_epoch = result_epoch-16
        score = fixed_score(symbol_correlations(raw, rate, "upper", local_epoch),
                            symbol_correlations(raw, rate, "upper", local_epoch, 17))
        e, c = score["exact"], score["control"]
        decision = int(e["score"] >= 19661 and e["score"] >= c["score"]+9831 and not e["zero"])
        flags = e["bin"]+(c["bin"] << 9)+(score["block_shift"] << 18)+(e["zero"] << 23)+(c["zero"] << 24)
        flags += (e["clamped"] << 25)+(c["clamped"] << 26)+(decision << 27)
        assert words[5:8] == [e["score"], c["score"], flags]
        assert [words[j]+(words[j+1] << 32) for j in (8, 10, 12, 14)] == [e["energy"], c["energy"], e["peak"], c["peak"]]
        if decision and abs(local_epoch-epoch) <= rate//2500000:
            near_truth.append(result_epoch)
    assert near_truth
    regs = dict(reads)
    assert regs[0xc8] == regs[0x148] == regs[0x14c] == 0
    assert u64(regs, 0x118) == u64(regs, 0x154) == u64(regs, 0x15c) == len(events)
    assert regs[0x150] & 31 == 0 and final == (0, 0)
    decoded = decode_snapshot(regs, rate, len(events))
    decoded.require_iq_prefix(expected_visit=301, expected_rate=rate, received_bytes=4*len(output))
    event_records = [Event.decode(struct.pack("<16I", *words)) for words in events]
    decoded.require_events(event_records, baseline=replace(decoded, cpu_read=0, cpu_pushed=0))


def test_backpressure_fault_preserves_and_drains_promised_prefix(captures, tmp_path):
    raw = np.random.default_rng(683).integers(-5000, 5001, (300, 2), dtype=np.int16)
    output, reads, final = run(captures(2500000), [*arm(), write(0x44, 2), (1, 4, 0, 0, 0),
        *samples(raw), wait(), *snapshot(), (1, 4, 0, 1, 0), wait(), *snapshot()], tmp_path)
    np.testing.assert_array_equal(output, raw[:32])
    before, after = dict(reads[:65]), dict(reads[65:])
    assert u64(before, 0x90) == 32 and u64(before, 0x98) == 0
    assert u64(after, 0x90) == u64(after, 0x98) == 32
    assert before[0xc8] == after[0xc8] == 4 and u64(after, 0xa8) == 48
    assert before[0xd4] == before[0xd8] == 32 and after[0xd8] == 0
    assert final == (0, 1)


@pytest.mark.parametrize("limit", [1, 32, 300])
def test_exact_supported_output_limit(limit, captures, tmp_path):
    raw = np.random.default_rng(281).integers(-5000, 5001, (1000, 2), dtype=np.int16)
    output, reads, final = run(captures(2500000), [*arm(limit=limit), *samples(raw), wait(1000), *snapshot()], tmp_path)
    np.testing.assert_array_equal(output, raw[:limit])
    regs = dict(reads)
    assert u64(regs, 0x90) == u64(regs, 0x98) == limit and regs[0xc8] == 0
    assert final == (0, 0)


@pytest.mark.parametrize("bad", [write(8, 1), write(8, 3), write(8, 4, strobe=1), write(0x24, 0),
                                 write(0xffc, 1), write(0x34, 65537), write(8, 16)])
def test_invalid_commands_visible_without_starting_capture(bad, captures, tmp_path):
    output, reads, final = run(captures(2500000), [bad, write(0x44, 2), read(0x10)], tmp_path)
    assert not output and reads == [(0x10, 16)] and final == (0, 1)


def test_stop_snapshot_clear_rearm_preserves_source_counter(captures, tmp_path):
    raw = np.full((300, 2), 1300, dtype=np.int16)
    rows = [*arm(), *samples(raw), wait(1000), write(8, 2), *snapshot(),
            *arm(visit=18), *samples(raw), wait(1000), write(8, 2), *snapshot()]
    output, reads, final = run(captures(2500000), rows, tmp_path)
    np.testing.assert_array_equal(output, np.concatenate((raw, raw)))
    before, after = dict(reads[:65]), dict(reads[65:])
    assert u64(before, 0x80) == 16 and u64(after, 0x80) == 332
    assert before[0xd0] == 17 and after[0xd0] == 18
    assert u64(before, 0x90) == u64(after, 0x90) == 300
    assert before[0xc8] == after[0xc8] == 0 and final == (0, 0)


@pytest.mark.parametrize("fault", [(1, 5, 0, 0, 0), (1, 6, 0, 0, 0)])
def test_adc_gap_or_reset_stops_capture_without_stitching(fault, captures, tmp_path):
    raw = np.full((300, 2), 700, dtype=np.int16)
    rows = [*arm(), write(0x44, 2), *samples(raw), wait(200), fault,
            *samples(raw), wait(1000), *snapshot()]
    output, reads, final = run(captures(2500000), rows, tmp_path)
    np.testing.assert_array_equal(output, raw)
    regs = dict(reads)
    assert u64(regs, 0x90) == u64(regs, 0x98) == 300 and regs[0xc8] == 2
    assert final == (0, 1)


@pytest.mark.parametrize("fault", [write(0x20, 23), write(8, 4)])
def test_invalid_active_control_preserves_axis_promise(fault, captures, tmp_path):
    raw = np.full((16, 2), 1700, dtype=np.int16)
    rows = [*arm(), write(0x44, 2), (1, 4, 0, 0, 0), *samples(raw), wait(200), fault,
            wait(100), (1, 4, 0, 1, 0), wait(), *snapshot()]
    output, reads, final = run(captures(2500000), rows, tmp_path)
    np.testing.assert_array_equal(output, raw)
    regs = dict(reads)
    assert u64(regs, 0x90) == u64(regs, 0x98) == 16 and regs[0xc8] == 16
    assert final == (0, 1)


def arm_continuous(limit=0):
    return [(1, 11, 0, 3, 0), wait(2000), write(8, 4), wait(2000),
            write(0x20, 87), write(0x30, limit), write(0x44, 2), write(8, 1)]


@pytest.mark.parametrize('rate', RATES)
def test_board_continuous_source_finite_prefix(rate, captures, tmp_path):
    output, reads, final = run(captures(rate, True),
        [*arm_continuous(limit=100), wait(20000), *snapshot()], tmp_path)
    np.testing.assert_array_equal(output, np.tile([700, -200], (100, 1)))
    regs = dict(reads)
    decoded = decode_snapshot(regs, rate)
    decoded.require_iq_prefix(expected_visit=87, expected_rate=rate,
                              expected_samples=100, received_bytes=400)
    assert regs[0xc8] == 0 and final == (0, 0)


@pytest.mark.parametrize('rate', [2500000, 60000000])
@pytest.mark.parametrize('bad', [(1, 11, 0, 1, 0), (1, 11, 0, 2, 0), (1, 13, 0, 0, 0)])
def test_board_frame_error_missing_valid_or_stopped_clock_is_visible(rate, bad, captures, tmp_path):
    output, reads, final = run(captures(rate, True),
        [*arm_continuous(), wait(20000), bad, wait(6000), *snapshot()], tmp_path)
    assert len(output) > 0
    np.testing.assert_array_equal(output, np.tile([700, -200], (len(output), 1)))
    regs = dict(reads)
    assert regs[0xc8] == 2 and u64(regs, 0x90) == u64(regs, 0x98) == len(output)
    assert u64(regs, 0x88)-u64(regs, 0x80) == (len(output)-1)*(rate//2500000)
    assert final == (0, 1)


@pytest.mark.parametrize('rate', [2500000, 60000000])
def test_board_no_stale_source_arm_after_clock_stops(rate, captures, tmp_path):
    rows = [(1, 11, 0, 3, 0), wait(2000), write(8, 4), wait(2000), write(0x20, 87),
            (1, 13, 0, 0, 0), wait(6000), read(0x0c), write(8, 1), read(0x10)]
    output, reads, final = run(captures(rate, True), rows, tmp_path)
    assert not output and dict(reads)[0xc] & (1 << 11) == 0
    assert dict(reads)[0x10] == 16 and final == (0, 0)
