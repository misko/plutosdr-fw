"""30-MS/s component qualification, independent of whole-board enablement."""
from __future__ import annotations

import json

import numpy as np
import pytest

from tools.generate_glrt_thirty_ddc import BANK, MANIFEST, generate

from .ddc import BANK_ROOT, Ddc, RATES, group_delay, stages
from . import test_ddc_rtl as rtl

simulators = rtl.simulators
RATE = 30_000_000


def test_additive_coefficient_freeze_is_reproducible(tmp_path):
    generate(tmp_path)
    assert (tmp_path / BANK).read_bytes() == (BANK_ROOT / BANK).read_bytes()
    assert json.loads((tmp_path / MANIFEST).read_text()) == json.loads((BANK_ROOT / MANIFEST).read_text())
    assert not (tmp_path / "ddc_coefficients.json").exists()
    assert RATE not in RATES


@pytest.mark.parametrize("existing", [BANK, MANIFEST])
def test_generator_refuses_existing_freeze(tmp_path, existing):
    (tmp_path / existing).write_bytes(b"retained")
    with pytest.raises(SystemExit, match="do not overwrite"):
        generate(tmp_path)
    assert (tmp_path / existing).read_bytes() == b"retained"
    assert list(tmp_path.iterdir()) == [tmp_path / existing]


def test_native_coordinate_geometry():
    assert stages(RATE) == ((RATE, 6), (5_000_000, 2))
    assert group_delay(RATE) == 636


@pytest.mark.parametrize("frequency", [-1_100_000, -700_000, 0, 700_000, 1_100_000])
def test_passband_tones_preserve_native_signal_center(frequency):
    first = (1 << 40) + 11
    tone = 20_000 * np.exp(2j * np.pi * frequency * np.arange(48_000) / RATE)
    iq = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    result = Ddc(RATE).process(iq, first)
    values = result.iq[result.supported].astype(float)
    centers = (result.indexes[result.supported] - np.uint64(first)).astype(np.int64) - 636
    actual = values[:, 0] + 1j * values[:, 1]
    expected = 20_000 * np.exp(2j * np.pi * frequency * centers / RATE)
    gain = np.mean(actual / expected)
    assert abs(abs(gain) - 1) < 0.0005
    assert abs(np.angle(gain)) < 0.0002


@pytest.mark.parametrize("frequency", [-14_200_000, -10_100_000, -6_100_000, -4_200_000, -2_000_000,
                                       2_000_000, 4_200_000, 6_100_000, 10_100_000, 14_200_000])
def test_out_of_band_tones_do_not_alias_into_coarse_lane(frequency):
    tone = 20_000 * np.exp(2j * np.pi * frequency * np.arange(48_000) / RATE)
    iq = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    result = Ddc(RATE).process(iq, 0)
    supported = result.iq[result.supported].astype(float)
    amplitude = np.sqrt(np.mean(np.sum(supported**2, axis=1)))
    assert amplitude / 20_000 < 10**(-70 / 20)


@pytest.mark.parametrize("phase", range(12))
def test_every_native_phase_at_pacer_drain_rate(phase, simulators, tmp_path):
    first = (1 << 48) + (phase - (1 << 48)) % 12
    values = np.random.default_rng(99318).integers(-32768, 32768, (9000, 2), dtype=np.int16)
    # Actual pacer permits 12 samples every 39 fabric clocks, slightly faster
    # than nominal radio arrival. Sweep all absolute phases through this bound.
    rows = ["0 0 0 0 0 0 0"] * (39 * len(values) // 12 + 80)
    cycle = 0
    for j, (i, q) in enumerate(values):
        index = first + j
        p = index % 12
        rows[cycle] = f"1 0 0 {index:x} {p} {i} {q}"
        cycle += 39 * (p + 1) // 12 - 39 * p // 12
    reference = Ddc(RATE).process(values, first)
    output, status = rtl.run(simulators(RATE), rows, tmp_path)
    expected = [(int(index), int(i), int(q), int(support)) for index, (i, q), support in
                zip(reference.indexes, reference.iq, reference.supported)]
    assert output == expected
    assert status == (len(values), len(expected), reference.clips, 0, 0)
