"""Actual DDC + AXI control + stalled AXIS export, without radio access."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from .pilot_ddc import PilotDdcOracle, mixer_lut

LIB = Path(__file__).resolve().parents[2] / "hdl/library"


def compile_simulator(directory, rate_msps=15, *, watchdog_cycles=3_000_000):
    assert shutil.which("iverilog") and shutil.which("vvp"), "Icarus is required"
    executable = directory / "capture.vvp"
    files = [LIB / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
             LIB / "axi_starlink_pilot_capture/tb/tb_starlink_pilot_capture.sv",
             LIB / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"]
    files += [LIB / "starlink_pss_acquisition" / name for name in
              ("starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v")]
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pilot_capture",
                    "-P", f"tb_starlink_pilot_capture.SOURCE_RATE_MSPS={rate_msps}",
                    "-P", f"tb_starlink_pilot_capture.WATCHDOG_CYCLES={watchdog_cycles}",
                    "-o", str(executable), *map(str, files)],
                   check=True, capture_output=True, text=True, timeout=60)
    for name in ("pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"):
        shutil.copyfile(LIB / "starlink_pss_acquisition" / name, directory / name)
    return rate_msps, directory, executable


@pytest.fixture(scope="module", params=[15, 30, 60])
def simulator(request, tmp_path_factory):
    return compile_simulator(tmp_path_factory.mktemp(f"pilot-capture-{request.param}"),
                             request.param)


def write(address, value, *, strobe=15, skew=0):
    return (1, 2, address, value, strobe | (skew << 8))


def read(address):
    return (1, 3, address, 0, 0)


def arm(visit=17):
    return [write(8, 4), write(0x20, visit), write(8, 1, skew=3)]


def samples(values, first=0):
    return [(6, 1, first+n, (int(i) & 65535) | ((int(q) & 65535) << 16), 0)
            for n, (i, q) in enumerate(values)]


def snapshot():
    return [write(8, 8), *(read(address) for address in range(0x30, 0x9c, 4))]


def run(simulator, records, *, timeout=60):
    _, directory, executable = simulator
    (directory / "stimulus.txt").write_text("".join(
        f"{delay} {op} {index:016x} {value:08x} {arg}\n"
        for delay, op, index, value, arg in records))
    result = subprocess.run(["vvp", str(executable)], cwd=directory, check=True,
                            capture_output=True, text=True, timeout=timeout)
    out, reads, final = [], [], None
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[0] == "OUT":
            word = int(fields[1], 16)
            out.append(tuple(v if v < 32768 else v-65536 for v in (word & 65535, word >> 16)))
        elif fields[0] == "READ":
            reads.append((int(fields[1], 16), int(fields[2], 16)))
        elif fields[0] == "FINAL":
            final = tuple(map(int, fields[1:]))
        else:
            pytest.fail(f"Unexpected simulator output: {line}")
    assert final is not None
    return out, reads, final


def u64(regs, address):
    return regs[address] | (regs[address+4] << 32)


@pytest.mark.parametrize("first", [0, 5, (1 << 63) + 5])
def test_exact_export_snapshot_and_static_geometry(simulator, first):
    values = np.random.default_rng(129).integers(-12000, 12000, (3000, 2), dtype=np.int16)
    out, reads, final = run(simulator, [read(0), read(0x14), read(0x18), read(0x1c),
                                      read(0x24), *arm(), *samples(values, first),
                                      (2000, 7, 0, 0, 0), write(8, 2), *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=first)
    supported = expected.support_valid
    np.testing.assert_array_equal(out, expected.samples_iq[supported])
    regs = dict(reads)
    rate = simulator[0]
    assert (regs[0], regs[0x14], regs[0x18], regs[0x1c], regs[0x24]) == (
        0x50494c31, rate*1_000_000, 2_500_000, rate*2//5, 1)
    assert u64(regs, 0x30) == int(expected.accepted_input_indexes[supported][0])
    assert u64(regs, 0x38) == int(expected.accepted_input_indexes[supported][-1])
    assert u64(regs, 0x40) == u64(regs, 0x48) == len(out)
    assert u64(regs, 0x50) == int((~supported).sum())
    assert u64(regs, 0x60) == len(values)
    assert u64(regs, 0x68) == len(expected.samples_iq)
    assert regs[0x78] == 0 and regs[0x80] == 17 and regs[0x98] == 1
    assert final == (0, 0)


def test_backpressure_retains_prefix_and_drains_after_overflow(simulator):
    values = np.random.default_rng(33).integers(-3000, 3000, (1400, 2), dtype=np.int16)
    out, reads, final = run(simulator, [*arm(), (1, 4, 0, 0, 0), *samples(values),
                                      (2000, 7, 0, 0, 0), *snapshot(),
                                      (1, 4, 0, 1, 0), (100, 7, 0, 0, 0), *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid][:32])
    captures = [dict(reads[n:n+27]) for n in range(0, len(reads), 27)]
    before, after = captures
    assert u64(before, 0x40) == 32 and u64(before, 0x48) == 0
    assert u64(after, 0x40) == u64(after, 0x48) == 32
    assert before[0x78] == after[0x78] == 4
    assert u64(after, 0x58) == int(expected.accepted_input_indexes[expected.support_valid][32])
    assert before[0x88] == before[0x84] == 32 and after[0x88] == 0
    assert final == (0, 1)


@pytest.mark.parametrize("fault,mask", [(write(0x20, 19), 32),
                                       ((1, 5, 0, 0, 0), 2),
                                       ((1, 6, 0, 0, 0), 16),
                                       (write(8, 4), 32)])
def test_faults_stop_admission_but_keep_promised_axis_data(simulator, fault, mask):
    values = np.ones((600, 2), dtype=np.int16) * 1000
    out, reads, final = run(simulator, [*arm(), (1, 4, 0, 0, 0), *samples(values),
                                      (2000, 7, 0, 0, 0), fault,
                                      (100, 7, 0, 0, 0), (1, 4, 0, 1, 0),
                                      (100, 7, 0, 0, 0), *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid])
    assert dict(reads)[0x78] == mask and final == (0, 1)


def test_stop_drain_clear_rearm_and_snapshot_isolation(simulator):
    values = np.ones((600, 2), dtype=np.int16) * 500
    out, reads, final = run(simulator, [*arm(), (1, 4, 0, 0, 0), *samples(values),
                                      (2000, 7, 0, 0, 0), write(8, 2), *snapshot(),
                                      (1, 4, 0, 1, 0), (100, 7, 0, 0, 0), read(0x48),
                                      *arm(18), *samples(values, 5003),
                                      (2000, 7, 0, 0, 0), write(8, 2), *snapshot()])
    a = PilotDdcOracle("upper").process(values, first_index=0)
    b = PilotDdcOracle("upper").process(values, first_index=5003)
    np.testing.assert_array_equal(out, np.concatenate((a.samples_iq[a.support_valid],
                                                      b.samples_iq[b.support_valid])))
    assert reads[27] == (0x48, 0), "old snapshot must not follow live delivery counter"
    regs = dict(reads[28:])
    assert regs[0x80] == 18 and regs[0x78] == 0 and regs[0x98] == 1
    assert u64(regs, 0x48) == int(b.support_valid.sum())
    assert final == (0, 0)


@pytest.mark.parametrize("command", [write(8, 1), write(8, 3), write(8, 4, strobe=1),
                                    write(0x24, 0), write(0xfc, 1)])
def test_invalid_commands_fail_closed(simulator, command):
    _, reads, final = run(simulator, [command, read(0x10)])
    assert reads == [(0x10, 32)] and final == (0, 1)


def test_registered_command_decode_rejects_every_reserved_bit_and_partial_strobe(simulator):
    commands = [write(8, 1 | (1 << bit), skew=bit % 4) for bit in range(1, 32)]
    commands += [write(8, 4, strobe=strobe, skew=strobe % 4) for strobe in range(15)]
    records = []
    for command in commands:
        records += [command, read(0x10), write(8, 4), read(0x10)]
    _, reads, final = run(simulator, records)
    assert reads == [(0x10, value) for _ in commands for value in (32, 0)]
    assert final == (0, 0)


def test_source_discontinuity_is_not_silently_stitched(simulator):
    values = np.ones((900, 2), dtype=np.int16)
    out, reads, final = run(simulator, [*arm(), *samples(values[:600]),
                                      *samples(values[600:], first=601),
                                      (2000, 7, 0, 0, 0), *snapshot()])
    regs = dict(reads)
    assert regs[0x78] == 1 and regs[0x74] & 255 == 1 and final == (0, 1)
    assert u64(regs, 0x40) == u64(regs, 0x48) == len(out)


@pytest.mark.parametrize("limit", [1, 32, 300])
def test_hardware_bounded_supported_sample_count(simulator, limit):
    values = np.random.default_rng(99).integers(-1000, 1000, (3000, 2), dtype=np.int16)
    out, reads, final = run(simulator, [write(8, 4), write(0x20, 3), write(0x9c, limit),
                                      write(8, 1), *samples(values), (2000, 7, 0, 0, 0),
                                      *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid][:limit])
    regs = dict(reads)
    assert u64(regs, 0x40) == u64(regs, 0x48) == limit
    assert regs[0x78] == 0 and final == (0, 0)


def test_full_fifo_simultaneous_push_pop_is_lossless(simulator):
    values = np.random.default_rng(67).integers(-2000, 2000, (1800, 2), dtype=np.int16)
    # 732 source samples emit exactly 32 supported results, filling the FIFO.
    # Then assert ready exactly on each new DDC result to exercise full+pop.
    out, reads, final = run(simulator, [*arm(), (1, 4, 0, 0, 0), *samples(values[:732]),
                                      (2000, 7, 0, 0, 0), (1, 4, 0, 2, 0),
                                      *samples(values[732:], first=732),
                                      (2000, 7, 0, 0, 0), write(8, 2),
                                      (1, 4, 0, 1, 0), (100, 7, 0, 0, 0), *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid])
    regs = dict(reads)
    assert regs[0x84] == 32 and regs[0x78] == 0 and final == (0, 0)


def test_periodic_dma_stalls_preserve_every_sample(simulator):
    values = np.random.default_rng(72).integers(-12000, 12000, (3600, 2), dtype=np.int16)
    records = arm()
    for first in range(0, len(values), 40):
        records.append((1, 4, 0, (first // 40) % 2, 0))
        records.extend(samples(values[first:first+40], first=first))
    out, reads, final = run(simulator, [*records, (1, 4, 0, 1, 0),
                                      (2000, 7, 0, 0, 0), write(8, 2), *snapshot()])
    expected = PilotDdcOracle("upper").process(values, first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid])
    regs = dict(reads)
    assert 1 < regs[0x84] < 32 and regs[0x78] == 0 and final == (0, 0)


def cw_samples(count):
    rotations = mixer_lut()[(12 * np.arange(count)) % 64]
    return np.column_stack((rotations[:, 0] >> 3, (-rotations[:, 1]) >> 3)).astype(np.int16)


@pytest.mark.parametrize("command,fault", [(2, 0), (3, 32)])
def test_registered_stop_or_bad_write_during_live_source_preserves_prefix(simulator, command, fault):
    out, reads, final = run(simulator, [*arm(), (1, 10, 8, command, 15),
                                      (2000, 7, 0, 0, 0), *snapshot()])
    expected = PilotDdcOracle("upper").process(cw_samples(2400), first_index=0)
    supported = expected.samples_iq[expected.support_valid]
    assert 12 <= len(out) < len(supported), "command must stop a live supported stream"
    np.testing.assert_array_equal(out, supported[:len(out)])
    regs = dict(reads)
    assert u64(regs, 0x40) == u64(regs, 0x48) == len(out)
    assert u64(regs, 0x30) == 540
    assert u64(regs, 0x38) == 540 + 6 * (len(out) - 1)
    assert regs[0x78] == fault and final == (0, bool(fault))


def test_procedural_dwell_stimulus_and_auto_stop(simulator):
    limit = 1000
    count = 6 * limit + 600  # continue driving after the supported limit
    out, reads, final = run(simulator, [write(8, 4), write(0x20, 17),
                                       write(0x9c, limit), write(8, 1),
                                       (1, 9, 0, count, 0), (2000, 7, 0, 0, 0),
                                       *snapshot()])
    expected = PilotDdcOracle("upper").process(cw_samples(count), first_index=0)
    np.testing.assert_array_equal(out, expected.samples_iq[expected.support_valid][:limit])
    regs = dict(reads)
    assert u64(regs, 0x40) == u64(regs, 0x48) == limit
    assert u64(regs, 0x30) == 540 and u64(regs, 0x38) == 540 + 6 * (limit - 1)
    assert regs[0x78] == 0 and regs[0x70] == 0 and final == (0, 0)
