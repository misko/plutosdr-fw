from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import freqz, lfilter

from .ddc import Ddc, RATES, coefficients, group_delay, quantize, stages


@pytest.mark.parametrize("rate", RATES)
def test_chunk_invariance_and_absolute_phase(rate):
    rng = np.random.default_rng(81730)
    values = rng.integers(-10000, 10001, (9000, 2), dtype=np.int16)
    first = (1 << 40) + 17
    whole = Ddc(rate).process(values, first)
    model = Ddc(rate)
    boundaries = [0, 1, 17, 143, 410, 2800, len(values)]
    pieces = [model.process(values[a:b], first + a) for a, b in zip(boundaries, boundaries[1:])]
    assert np.array_equal(np.concatenate([p.iq for p in pieces]), whole.iq)
    assert np.array_equal(np.concatenate([p.indexes for p in pieces]), whole.indexes)
    assert np.array_equal(np.concatenate([p.supported for p in pieces]), whole.supported)
    assert sum(p.clips for p in pieces) == whole.clips
    assert np.all(whole.indexes % (rate // 2_500_000) == 0)
    assert np.all(np.diff(whole.indexes) == rate // 2_500_000)


@pytest.mark.parametrize("rate", RATES)
def test_float_convolution_and_dc_gain(rate):
    rng = np.random.default_rng(19)
    values = rng.integers(-2000, 2001, (12000, 2), dtype=np.int16)
    result = Ddc(rate).process(values, 0)
    floating = values.astype(float)
    for fs, decimation in stages(rate):
        floating = lfilter(coefficients(fs) / 2**17, [1], floating, axis=0)[::decimation]
    assert np.max(abs(floating - result.iq)) < 1.5
    dc = Ddc(rate).process(np.full_like(values, 7000), 0)
    assert np.all(dc.iq[dc.supported] == 7000)
    assert dc.clips == 0


@pytest.mark.parametrize("rate", RATES)
def test_reset_support_and_impulse_group_delay(rate):
    delay = group_delay(rate)
    ratio = rate // 2_500_000
    # Choose impulse phase so its exact center lies on the export grid.
    impulse_index = (-delay) % ratio + 4000
    impulse_index += (-impulse_index-delay) % ratio
    values = np.zeros((12000, 2), dtype=np.int16)
    values[impulse_index, 0] = 20000
    result = Ddc(rate).process(values, 0)
    assert int(result.indexes[np.argmax(result.iq[:, 0])]) == impulse_index + delay
    assert np.array_equal(result.supported, result.indexes >= 2 * delay)
    model = Ddc(rate)
    model.process(values[:31], 7)
    with pytest.raises(ValueError, match="discontinuity"):
        model.process(values, 9)
    model.reset()
    fresh = model.process(values, 9)
    assert np.array_equal(fresh.supported, fresh.indexes - 9 >= 2 * delay)


@pytest.mark.parametrize("fs", [5_000_000, 10_000_000, 25_000_000, 60_000_000])
def test_frozen_filter_response(fs):
    h = coefficients(fs)
    frequency, response = freqz(h / 2**17, worN=262144, fs=fs)
    pas = abs(response[frequency <= 1_100_000])
    stop = 1_250_000 if fs == 5_000_000 else 3_900_000
    assert np.ptp(20 * np.log10(pas)) < 0.002
    assert -20 * np.log10(max(abs(response[frequency >= stop]))) > 78


def test_signed_ties_even_and_clipping():
    raw = np.array([-32769, -7, -5, -3, -1, 1, 3, 5, 7, 32769], dtype=np.int64) * 2**16
    actual, clips = quantize(raw)
    assert actual.tolist() == [-16384, -4, -2, -2, 0, 0, 2, 2, 4, 16384]
    assert clips == 0
    actual, clips = quantize(np.array([-32769, 32768], dtype=np.int64) * 2**17)
    assert actual.tolist() == [-32768, 32767] and clips == 2


@pytest.mark.parametrize("rate", [0, True, 15_000_000, 30_000_000, 61_000_000])
def test_reject_other_rates(rate):
    with pytest.raises(ValueError):
        Ddc(rate)
