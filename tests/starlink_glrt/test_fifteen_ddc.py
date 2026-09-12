from __future__ import annotations

import json

import numpy as np
import pytest

from tools.generate_glrt_fifteen_ddc import BANK, MANIFEST, generate

from .ddc import BANK_ROOT, Ddc, RATES, group_delay, stages
from . import test_ddc_rtl as rtl

simulators = rtl.simulators
RATE = 15_000_000


def test_additive_coefficient_freeze_is_reproducible(tmp_path):
    generate(tmp_path)
    assert (tmp_path / BANK).read_bytes() == (BANK_ROOT / BANK).read_bytes()
    expected = json.loads((BANK_ROOT / MANIFEST).read_text())
    actual = json.loads((tmp_path / MANIFEST).read_text())
    assert actual == expected
    assert set(actual["banks"]) == {str(RATE)}
    assert not (tmp_path / "ddc_coefficients.json").exists()
    assert RATE not in RATES  # Standalone component success cannot enable RX.


@pytest.mark.parametrize("existing", [BANK, MANIFEST])
def test_generator_refuses_partial_or_complete_existing_freeze(tmp_path, existing):
    (tmp_path / existing).write_bytes(b"retained")
    with pytest.raises(SystemExit, match="do not overwrite"):
        generate(tmp_path)
    assert (tmp_path / existing).read_bytes() == b"retained"
    assert list(tmp_path.iterdir()) == [tmp_path / existing]


def test_native_coordinate_geometry():
    assert stages(RATE) == ((RATE, 3), (5_000_000, 2))
    assert group_delay(RATE) == 318
    assert 2 * group_delay(RATE) == 636


@pytest.mark.parametrize("frequency", [-1_100_000, -700_000, 0, 700_000, 1_100_000])
def test_passband_tones_preserve_native_signal_center(frequency):
    first = (1 << 40) + 11
    indexes = np.arange(24_000)
    tone = 20_000 * np.exp(2j * np.pi * frequency * indexes / RATE)
    iq = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    result = Ddc(RATE).process(iq, first)
    values = result.iq[result.supported].astype(float)
    centers = (result.indexes[result.supported] - np.uint64(first)).astype(np.int64) - 318
    actual = values[:, 0] + 1j * values[:, 1]
    expected = 20_000 * np.exp(2j * np.pi * frequency * centers / RATE)
    gain = np.mean(actual / expected)
    assert abs(abs(gain) - 1) < 0.0005
    assert abs(np.angle(gain)) < 0.0002


@pytest.mark.parametrize("frequency", [-6_100_000, -4_200_000, -2_000_000,
                                       2_000_000, 4_200_000, 6_100_000])
def test_structured_out_of_band_tones_do_not_alias_into_coarse_lane(frequency):
    tone = 20_000 * np.exp(2j * np.pi * frequency * np.arange(24_000) / RATE)
    iq = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    result = Ddc(RATE).process(iq, 0)
    supported = result.iq[result.supported].astype(float)
    amplitude = np.sqrt(np.mean(np.sum(supported**2, axis=1)))
    # Includes CI16 quantization in both stages, beyond coefficient-only checks.
    assert amplitude / 20_000 < 10**(-70 / 20)


@pytest.mark.parametrize("phase", range(6))
def test_every_native_decimation_phase_at_large_counter(phase, simulators, tmp_path):
    first = (1 << 48) + (phase - (1 << 48)) % 6
    rtl.test_exact_stream_at_native_pacing(RATE, first, simulators, tmp_path)
