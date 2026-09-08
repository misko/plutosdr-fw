"""Complete canonical pilot exporter against its independent fixed-point oracle."""

from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from .pilot_ddc import PilotDdcOracle, coefficients, mixer_lut, MIXER_STEP_64
from .ddc import x2_ddc_ci16, x4_ddc_ci16


RTL = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


def _compile(directory, *, source_rate=15, edge="upper"):
    assert shutil.which("iverilog") and shutil.which("vvp"), "Icarus Verilog is required"
    executable = directory / "ddc.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pilot_ddc", "-o", str(executable),
        "-P", f"tb_starlink_pilot_ddc.SOURCE_RATE_MSPS={source_rate}",
        "-P", f"tb_starlink_pilot_ddc.SOURCE_EDGE_UPPER={int(edge == 'upper')}",
        *(str(RTL / name) for name in ["starlink_pilot_ddc.v", "starlink_pilot_halfband2.v",
                                      "starlink_pilot_fir3.v", "starlink_pss_x2_ddc.v",
                                      "tb/tb_starlink_pilot_ddc.sv"]),
    ], check=True, capture_output=True, text=True, timeout=60)
    for name in ["pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"]:
        shutil.copyfile(RTL / name, directory / name)
    return directory, executable


@pytest.fixture(scope="module")
def simulator(tmp_path_factory):
    return _compile(tmp_path_factory.mktemp("pilot-ddc-rtl"))


@pytest.fixture(scope="module", params=[(30, "lower"), (30, "upper"), (60, "lower"), (60, "upper")])
def rate_chain(request, tmp_path_factory):
    rate, edge = request.param
    return rate, edge, _compile(tmp_path_factory.mktemp(f"pilot-{rate}-{edge}"), source_rate=rate, edge=edge)


def _run(simulator, records):
    directory, executable = simulator
    (directory / "stimulus.txt").write_text("".join(
        f"{gap} {op} {index:016x} {edge} {visit:08x} {i} {q} {support}\n"
        for gap, op, index, edge, visit, i, q, support in records
    ))
    result = subprocess.run(["vvp", str(executable)], cwd=directory, check=True,
                            capture_output=True, text=True, timeout=60)
    outputs, status = [], None
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[0] == "OUT":
            outputs.append((int(fields[1], 16), int(fields[2], 16),
                            *(int(v) for v in fields[3:])))
        elif fields[0] == "STATUS":
            status = tuple(int(v) for v in fields[1:])
        else:
            pytest.fail(f"unexpected simulator output: {line}")
    assert status is not None
    return outputs, status


def _records(samples, *, first_index=0, edge="upper", visit=1, gaps=(6, 7, 7)):
    return [(gaps[n % len(gaps)], 1, first_index+n, int(edge == "upper"), visit,
             int(i), int(q), 1) for n, (i, q) in enumerate(samples)]


def _expected(samples, *, first_index=0, edge="upper", visit=1):
    result = PilotDdcOracle(edge).process(samples, first_index=first_index)
    rows = [(int(index), visit, int(i), int(q), int(support))
            for index, (i, q), support in zip(result.accepted_input_indexes,
                                             result.samples_iq, result.support_valid)]
    return rows, result.saturation_events


def test_frozen_mixer_and_halfband_roms():
    def signed18(v):
        return v if v < 1 << 17 else v - (1 << 18)
    mixer = [int(v, 16) for v in (RTL / "pilot_mixer_q16.mem").read_text().split()]
    decoded = [(signed18(v & ((1 << 18)-1)), signed18(v >> 18)) for v in mixer]
    np.testing.assert_array_equal(decoded, mixer_lut())
    halfband = [signed18(int(v, 16)) for v in (RTL / "pilot_halfband2_q17.mem").read_text().split()]
    np.testing.assert_array_equal(halfband, [*coefficients(31)[:15:2], coefficients(31)[15]])
    assert not np.any(coefficients(31)[1:15:2])


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("first_index", [0, 1, 2, 3, 4, 5, 63, (1 << 63) + 63])
def test_complete_exact_random_stream(simulator, edge, first_index):
    samples = np.random.default_rng(4711).integers(-32768, 32768, (2400, 2), dtype=np.int16)
    outputs, status = _run(simulator, _records(samples, edge=edge, first_index=first_index))
    expected, clips = _expected(samples, edge=edge, first_index=first_index)
    assert [row[:5] for row in outputs] == expected
    assert status[:5] == (0, 0, len(samples), len(expected), clips)
    assert status[5] <= 4


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("gaps", [(6, 7), (14, 6, 101, 7), (601, *([1] * 99))])
def test_pacer_chunking_does_not_change_iq(simulator, edge, gaps):
    samples = np.random.default_rng(9).integers(-30000, 30001, (2400, 2), dtype=np.int16)
    outputs, status = _run(simulator, _records(samples, gaps=gaps, edge=edge, first_index=17))
    expected, clips = _expected(samples, edge=edge, first_index=17)
    assert [row[:5] for row in outputs] == expected
    assert status[:5] == (0, 0, len(samples), len(expected), clips)
    if gaps[0] == 601:
        assert 80 <= status[5] < 128


def test_flush_changes_edge_visit_and_counter_without_cross_contamination(simulator):
    first = np.random.default_rng(16).integers(-32000, 32001, (1200, 2), dtype=np.int16)
    second = np.random.default_rng(17).integers(-32000, 32001, (1500, 2), dtype=np.int16)
    records = _records(first, edge="lower", visit=0x12345678)
    records += [(1500, 2, 0, 1, 0x12345679, 0, 0, 0)]
    records += _records(second, edge="upper", first_index=10_007, visit=0x12345679)
    outputs, status = _run(simulator, records)
    e1, c1 = _expected(first, edge="lower", visit=0x12345678)
    e2, c2 = _expected(second, edge="upper", first_index=10_007, visit=0x12345679)
    assert [row[:5] for row in outputs] == e1 + e2
    assert status[:5] == (0, 0, len(first)+len(second), len(e1)+len(e2), c1+c2)


@pytest.mark.parametrize("flush_delay", [1, 5, 15, 30])
def test_flush_fences_queued_and_inflight_samples(simulator, flush_delay):
    prefix = np.ones((15, 2), dtype=np.int16) * 10000
    samples = np.random.default_rng(58).integers(-20000, 20001, (1200, 2), dtype=np.int16)
    records = _records(prefix, gaps=(1,), edge="lower", visit=1)
    records += [(flush_delay, 2, 0, 1, 2, 0, 0, 0)]
    records += _records(samples, edge="upper", first_index=119, visit=2)
    outputs, status = _run(simulator, records)
    expected, _ = _expected(samples, edge="upper", first_index=119, visit=2)
    assert [row[:5] for row in outputs] == expected
    assert status[:4] == (0, 0, len(prefix)+len(samples), len(expected))


@pytest.mark.parametrize("bad, fault", [
    ((5, 1, 2, 1, 1, 0, 0, 1), 1),
    ((5, 1, (1 << 64)-1, 1, 1, 0, 0, 1), 1),
    ((5, 4, 0, 0, 1, 0, 0, 1), 4),
    ((5, 4, 0, 1, 2, 0, 0, 1), 4),
    ((5, 3, 0, 1, 1, 0, 0, 1), 8),
])
def test_fault_halts_until_flush_without_erasing_sticky_evidence(simulator, bad, fault):
    samples = np.zeros((900, 2), dtype=np.int16)
    records = [(1, 1, 0, 1, 1, 10000, 0, 1), bad]
    records += _records(samples, first_index=1)  # ignored while halted
    records += [(200, 2, 0, 1, 2, 0, 0, 0)]
    records += _records(samples, first_index=15, visit=2)
    outputs, status = _run(simulator, records)
    expected, _ = _expected(samples, first_index=15, visit=2)
    assert [row[:5] for row in outputs] == expected
    assert status[:4] == (fault, 0, 1+len(samples), len(expected))


def test_fifo_overflow_is_latched_and_never_claimed_continuous(simulator):
    samples = np.random.default_rng(1).integers(-10000, 10001, (600, 2), dtype=np.int16)
    outputs, status = _run(simulator, _records(samples, gaps=(1,)))
    expected, _ = _expected(samples)
    assert [row[:5] for row in outputs] == expected[:len(outputs)]
    assert status[0:2] == (2, 1)
    assert 128 <= status[2] < len(samples)
    assert status[3] == len(outputs)
    assert status[5] == 128


def test_invalid_input_support_taints_the_complete_composed_window(simulator):
    samples = np.random.default_rng(66).integers(-6000, 6001, (1500, 2), dtype=np.int16)
    records = _records(samples)
    records[600] = (*records[600][:7], 0)
    outputs, status = _run(simulator, records)
    expected, clips = _expected(samples)
    expected = [(index, visit, i, q, 0 if 600 <= index <= 1138 else support)
                for index, visit, i, q, support in expected]
    assert [row[:5] for row in outputs] == expected
    assert status[:5] == (0, 0, len(samples), len(expected), clips)


def test_full_dwell_runner_smoke(tmp_path):
    result = subprocess.run(["bash", str(RTL / "run_pilot_ddc_dwell.sh"), "6540", str(tmp_path)],
                            check=True, text=True, capture_output=True, timeout=60)
    assert "PILOT_DDC_DWELL_PASS accepted=6540 emitted=1090 supported=1000" in result.stdout


def _condition(samples, rate, edge, first_index):
    conditioner = x2_ddc_ci16 if rate == 30 else x4_ddc_ci16
    return conditioner(samples, first_input_index=first_index, edge=edge)


def test_composed_30_and_60_rate_chain_bit_exact(rate_chain):
    rate, edge, simulator = rate_chain
    samples = np.random.default_rng(996).integers(-32768, 32768, (9600, 2), dtype=np.int16)
    gaps = (3, 3, 4) if rate == 30 else (1, 2, 2)
    outputs, status = _run(simulator, _records(samples, first_index=25, edge=edge, gaps=gaps))
    canonical = _condition(samples, rate, edge, 25)
    expected, clips = _expected(canonical.samples_iq, first_index=int(canonical.output_indexes[0]), edge=edge)
    assert [row[:5] for row in outputs] == expected
    # This counter covers the new pilot branch, not the upstream conditioner.
    assert status[:5] == (0, 0, len(canonical.samples_iq), len(expected), clips)


@pytest.mark.parametrize("offset_hz", [-100_000, 0, 100_000])
def test_source_rate_frequency_and_delay_mapping(rate_chain, offset_hz):
    rate, edge, simulator = rate_chain
    canonical_rate = 15_000_000
    source_rate = rate * 1_000_000
    frequency = ((1 if edge == "upper" else -1) * (source_rate-canonical_rate)/2
                 + MIXER_STEP_64[edge]*canonical_rate/64 + offset_hz)
    first_index = 25
    phase = 2*np.pi*frequency*(first_index + np.arange(9600))/source_rate
    samples = np.rint(12000*np.column_stack((np.cos(phase), np.sin(phase)))).astype(np.int16)
    gaps = (3, 3, 4) if rate == 30 else (1, 2, 2)
    outputs, status = _run(simulator, _records(samples, first_index=first_index, edge=edge, gaps=gaps))
    canonical = _condition(samples, rate, edge, first_index)
    expected, clips = _expected(canonical.samples_iq, first_index=int(canonical.output_indexes[0]), edge=edge)
    assert [row[:5] for row in outputs] == expected
    assert status[:5] == (0, 0, len(canonical.samples_iq), len(expected), clips)
    valid = [row for row in outputs if row[4]]
    center_indexes = np.array([row[0]-269 for row in valid], dtype=float)
    iq = np.array([row[2]+1j*row[3] for row in valid])
    corrected = np.mean(iq*np.exp(-2j*np.pi*offset_hz*center_indexes/canonical_rate))
    assert 10000 < corrected.real < 14000
    assert abs(corrected.imag) < 3  # no duplicated upstream delay correction
