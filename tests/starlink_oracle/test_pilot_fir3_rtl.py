"""Bit-accurate replay of the time-shared pilot FIR (requires Icarus Verilog)."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from .pilot_ddc import coefficients, _round_saturate


RTL = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.fixture(scope="module")
def simulator(tmp_path_factory):
    # Missing tools must fail explicitly, not silently skip an RTL gate.
    assert shutil.which("iverilog") and shutil.which("vvp"), "Icarus Verilog is required"
    directory = tmp_path_factory.mktemp("pilot-fir3-rtl")
    executable = directory / "fir3.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pilot_fir3",
        "-o", str(executable), str(RTL / "starlink_pilot_fir3.v"),
        str(RTL / "tb/tb_starlink_pilot_fir3.sv"),
    ], check=True, capture_output=True, text=True, timeout=60)
    shutil.copyfile(RTL / "pilot_fir3_q17.mem", directory / "pilot_fir3_q17.mem")
    return directory, executable


def _run(simulator, records):
    directory, executable = simulator
    (directory / "stimulus.txt").write_text("".join(
        f"{gap} {op} {index:016x} {phase} {i} {q} {support}\n"
        for gap, op, index, phase, i, q, support in records
    ))
    result = subprocess.run(["vvp", str(executable)], cwd=directory,
                            check=True, capture_output=True, text=True, timeout=60)
    outputs = []
    status = None
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[0] == "OUT":
            outputs.append((int(fields[1], 16), *(int(v) for v in fields[2:])))
        elif fields[0] == "STATUS":
            status = tuple(int(v) for v in fields[1:])
        else:
            pytest.fail(f"unexpected simulator output: {line}")
    assert status is not None
    return outputs, status


def _records(samples, *, first_index=0, gaps=(13,), support_after=0):
    return [
        (gaps[n % len(gaps)], 1, first_index + 2*n,
         ((first_index + 2*n) // 2) % 3, int(i), int(q), int(n >= support_after))
        for n, (i, q) in enumerate(samples)
    ]


def _expected(samples, *, first_index=0, support_after=0):
    bank = coefficients(255)
    sums = np.column_stack([
        np.convolve(samples[:, lane].astype(np.int64), bank)[:len(samples)]
        for lane in range(2)
    ])
    output = []
    for n in range(len(samples)):
        index = first_index + 2*n
        if index % 6:
            continue
        iq, saturation = _round_saturate(sums[n], 17)
        output.append((index, int(iq[0]), int(iq[1]),
                       int(n >= support_after + 254), saturation))
    return output


def test_coefficient_rom_exactly_matches_frozen_oracle():
    encoded = [int(s, 16) for s in (RTL / "pilot_fir3_q17.mem").read_text().split()]
    decoded = np.array([v if v < 1 << 17 else v - (1 << 18) for v in encoded])
    np.testing.assert_array_equal(decoded, coefficients(255)[:128])
    np.testing.assert_array_equal(coefficients(255), coefficients(255)[::-1])


@pytest.mark.parametrize("first_index", [0, 2, 4, (1 << 63) + 2])
@pytest.mark.parametrize("gaps", [(13,), (13, 13, 14), (14, 31, 100, 13)])
def test_exact_random_replay_all_phases_and_wraparound(simulator, first_index, gaps):
    samples = np.random.default_rng(1729).integers(-32768, 32768, (1800, 2), dtype=np.int16)
    outputs, status = _run(simulator, _records(
        samples, first_index=first_index, gaps=gaps, support_after=15))
    expected = _expected(samples, first_index=first_index, support_after=15)
    assert [row[:5] for row in outputs] == expected
    assert status == (0, 0, len(expected))
    if first_index == 0 and gaps == (13,):
        # 32 issue cycles, two write-port pauses, five arithmetic cycles.
        assert [row[5] for row in outputs] == [56 + 39*n for n in range(len(expected))]


def test_impulse_and_saturated_step(simulator):
    samples = np.zeros((1300, 2), dtype=np.int16)
    samples[0] = [32767, -32768]
    samples[300:650] = [32767, -32768]
    samples[650:1000] = [-32768, 32767]
    outputs, status = _run(simulator, _records(samples))
    expected = _expected(samples)
    assert [row[:5] for row in outputs] == expected
    assert sum(row[4] for row in expected) > 0
    assert status == (0, 0, len(expected))


@pytest.mark.parametrize("abort_after", [1, 5, 20, 35, 37, 38])
def test_flush_discards_inflight_and_zero_pads_new_epoch(simulator, abort_after):
    samples = np.random.default_rng(37).integers(-20000, 20001, (400, 2), dtype=np.int16)
    records = [(1, 1, 0, 0, 32767, -32768, 1),
               (abort_after, 2, 0, 0, 0, 0, 0)]
    records += _records(samples, first_index=1000)
    outputs, status = _run(simulator, records)
    expected = _expected(samples, first_index=1000)
    # With no intervening input writes, the first job completes after 37
    # cycles. A later flush cannot retroactively discard an emitted output.
    if abort_after > 37:
        expected = [(0, 0, 0, 0, 0)] + expected
    assert [row[:5] for row in outputs] == expected
    assert status == (0, 0, len(expected))


@pytest.mark.parametrize("bad_record, fault", [
    ((13, 1, 4, 1, 0, 0, 1), 1),  # source index gap
    ((13, 1, 3, 1, 0, 0, 1), 1),  # odd index
    ((13, 1, 2, 2, 0, 0, 1), 2),  # phase jump
    ((13, 1, 2, 3, 0, 0, 1), 2),  # invalid phase
])
def test_discontinuity_fails_closed_and_requires_flush(simulator, bad_record, fault):
    samples = np.ones((300, 2), dtype=np.int16) * 10000
    records = [(1, 1, 0, 0, 10000, 0, 1), bad_record,
               (100, 0, 0, 0, 0, 0, 0)]
    records += _records(samples)  # rejected while halted
    records += [(100, 2, 0, 0, 0, 0, 0)]
    records += _records(samples, first_index=1002)
    outputs, status = _run(simulator, records)
    expected = _expected(samples, first_index=1002)
    assert [row[:5] for row in outputs] == expected
    assert status == (fault, 0, len(expected))  # sticky fault survives clean restart


def test_overspeed_is_reported_not_silent_backpressure(simulator):
    outputs, status = _run(simulator, _records(np.ones((30, 2), dtype=np.int16), gaps=(12,)))
    assert not outputs
    assert status == (4, 1, 0)


def test_invalid_support_sample_taints_entire_filter_window(simulator):
    samples = np.ones((1000, 2), dtype=np.int16) * 4000
    records = _records(samples)
    record = records[400]
    records[400] = (*record[:6], 0)
    outputs, status = _run(simulator, records)
    expected = _expected(samples)
    expected = [(index, i, q, 0 if 400 <= index // 2 <= 654 else support, clips)
                for index, i, q, support, clips in expected]
    assert [row[:5] for row in outputs] == expected
    assert status == (0, 0, len(expected))
