from __future__ import annotations

import numpy as np
import pytest

from .pilot_ddc import (
    FILTER_HISTORY_INPUT_SAMPLES,
    FIR_FRACTION_BITS,
    GROUP_DELAY_INPUT_SAMPLES,
    INPUT_RATE_HZ,
    MIXER_STEP_64,
    PASSBAND_EDGE_HZ,
    PilotDdcOracle,
    STOPBAND_EDGE_HZ,
    _round_saturate,
    coefficients,
    float_reference,
)


def _tone(edge: str, offset_hz: float, *, first: int = 0, count: int = 24000) -> np.ndarray:
    frequency = MIXER_STEP_64[edge] * INPUT_RATE_HZ / 64 + offset_hz
    phase = 2 * np.pi * frequency * (first + np.arange(count)) / INPUT_RATE_HZ
    return np.rint(np.column_stack((np.cos(phase), np.sin(phase))) * 12000).astype(np.int16)


def test_quantized_cascade_passband_alias_rejection_and_exact_delay() -> None:
    halfband = coefficients(31)
    thirdband = coefficients(255)
    assert not halfband.flags.writeable and not thirdband.flags.writeable
    np.testing.assert_array_equal(halfband, halfband[::-1])
    np.testing.assert_array_equal(thirdband, thirdband[::-1])
    assert sum(halfband) == sum(thirdband) == 1 << FIR_FRACTION_BITS
    expanded = np.zeros(2 * len(thirdband) - 1)
    expanded[::2] = thirdband / (1 << FIR_FRACTION_BITS)
    effective = np.convolve(halfband / (1 << FIR_FRACTION_BITS), expanded)
    assert len(effective) - 1 == FILTER_HISTORY_INPUT_SAMPLES
    assert (len(effective) - 1) // 2 == GROUP_DELAY_INPUT_SAMPLES
    assert np.sum(np.arange(len(effective)) * effective) == pytest.approx(269, abs=1e-9)
    response = np.fft.rfft(effective, 262144)
    frequency = np.linspace(0, INPUT_RATE_HZ / 2, len(response))
    db = 20 * np.log10(np.maximum(np.abs(response), 1e-30))
    passband = db[frequency <= PASSBAND_EDGE_HZ]
    assert float(passband.max() - passband.min()) < 0.01
    assert float(db[frequency >= STOPBAND_EDGE_HZ].max()) < -70


@pytest.mark.parametrize("edge", ("lower", "upper"))
@pytest.mark.parametrize("first", (0, 1, 17, 63))
def test_fixed_point_matches_float_and_chunking_never_changes_phase(edge: str, first: int) -> None:
    rng = np.random.default_rng(1701)
    samples = rng.integers(-8000, 8001, (2400, 2), dtype=np.int16)
    full = PilotDdcOracle(edge).process(samples, first_index=first)
    reference = float_reference(samples, first_index=first, edge=edge)
    np.testing.assert_array_equal(full.accepted_input_indexes, reference.accepted_input_indexes)
    np.testing.assert_array_equal(full.support_valid, reference.support_valid)
    assert np.max(np.abs(full.samples_iq - reference.samples_iq)) < 3
    assert full.saturation_events == 0
    stream = PilotDdcOracle(edge)
    boundaries = (0, 1, 2, 5, 8, 127, 538, 1001, 1600, len(samples))
    pieces = [stream.process(samples[a:b], first_index=first + a)
              for a, b in zip(boundaries, boundaries[1:])]
    np.testing.assert_array_equal(np.concatenate([item.samples_iq for item in pieces]), full.samples_iq)
    np.testing.assert_array_equal(
        np.concatenate([item.accepted_input_indexes for item in pieces]), full.accepted_input_indexes
    )
    np.testing.assert_array_equal(
        np.concatenate([item.support_valid for item in pieces]), full.support_valid
    )


@pytest.mark.parametrize("edge", ("lower", "upper"))
@pytest.mark.parametrize("offset", (-1_100_000, -100_000, 0, 100_000, 1_100_000))
def test_pilot_band_tones_survive_with_known_filter_delay(edge: str, offset: float) -> None:
    result = PilotDdcOracle(edge).process(_tone(edge, offset), first_index=0)
    valid = result.support_valid
    values = result.samples_iq[valid, 0].astype(float) + 1j * result.samples_iq[valid, 1]
    centers = result.accepted_input_indexes[valid].astype(float) - GROUP_DELAY_INPUT_SAMPLES
    recovered = values * np.exp(-2j * np.pi * offset * centers / INPUT_RATE_HZ)
    assert np.mean(recovered).real == pytest.approx(12000, abs=10)
    assert abs(np.mean(recovered).imag) < 2
    assert result.saturation_events == 0


@pytest.mark.parametrize("edge", ("lower", "upper"))
@pytest.mark.parametrize("offset", (1_600_000, 2_500_000, 4_700_000, 6_500_000))
def test_out_of_band_tones_do_not_alias_into_glrt(edge: str, offset: float) -> None:
    result = PilotDdcOracle(edge).process(_tone(edge, offset), first_index=0)
    values = result.samples_iq[result.support_valid].astype(float)
    assert np.sqrt(np.mean(np.sum(values * values, axis=1))) < 4


def test_hop_reset_discards_old_filter_history_but_preserves_absolute_phase() -> None:
    oracle = PilotDdcOracle("upper")
    oracle.process(_tone("upper", 0, count=2400), first_index=0)
    with pytest.raises(ValueError, match="reset"):
        oracle.process(np.zeros((100, 2), dtype=np.int16), first_index=9000)
    oracle.reset()
    result = oracle.process(np.zeros((1200, 2), dtype=np.int16), first_index=9017)
    assert not np.any(result.samples_iq)
    assert not result.support_valid[0]
    assert result.support_valid[-1]
    assert np.all(result.accepted_input_indexes % 6 == 0)
    assert result.accepted_input_indexes[result.support_valid][0] >= 9017 + 538


def test_rounding_is_symmetric_ties_even_and_clipping_is_counted() -> None:
    rounded, saturations = _round_saturate(np.array([-7, -5, -3, -1, 1, 3, 5, 7]), 1)
    np.testing.assert_array_equal(rounded, (-4, -2, -2, 0, 0, 2, 2, 4))
    assert saturations == 0
    rounded, saturations = _round_saturate(np.array([-100000, 100000]), 1)
    np.testing.assert_array_equal(rounded, (-32768, 32767))
    assert saturations == 2


def test_invalid_inputs_are_not_silently_wrapped_or_resampled() -> None:
    oracle = PilotDdcOracle("lower")
    for samples in (np.zeros((2, 2)), np.zeros((2, 3), dtype=np.int16),
                    np.full((2, 2), 65535, dtype=np.uint16)):
        with pytest.raises(ValueError):
            oracle.process(samples, first_index=0)
    with pytest.raises(ValueError, match="uint64"):
        oracle.process(np.zeros((2, 2), dtype=np.int16), first_index=(1 << 64) - 1)
    with pytest.raises(ValueError, match="edge"):
        PilotDdcOracle("center")
