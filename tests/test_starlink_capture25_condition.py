"""Offline numerical conditioning, not a received-PSS or FPGA timing claim."""

import hashlib

import numpy as np
import pytest

from tools.starlink_capture25_condition import (
    FILTER_HALF,
    FILTER_RATE_HZ,
    MAX_INPUT_SAMPLES,
    coefficients,
    condition_capture25,
)


def tone(frequency, count=4000, first=0, amplitude=10000):
    phase = 2 * np.pi * frequency * (first + np.arange(count)) / 25_000_000
    return np.rint(amplitude * np.column_stack((np.cos(phase), np.sin(phase)))).astype(np.int16)


def test_polyphases_match_direct_centered_resampling():
    raw = np.random.default_rng(417).integers(-1000, 1001, size=(503, 2), dtype=np.int16)
    first = 135
    result = condition_capture25(raw, first_index=first, downmix_hz=0)
    source = raw[:, 0].astype(float) + 1j * raw[:, 1]
    expected = []
    for index in range(len(result.samples_iq)):
        local = result.first_canonical_index + index - first * 3 // 5
        source_indexes = np.arange(len(raw))
        taps = FILTER_HALF + 5 * local - 3 * source_indexes
        selected = (taps >= 0) & (taps < len(coefficients()))
        expected.append(np.sum(source[selected] * coefficients()[taps[selected]]))
    expected = np.asarray(expected)
    quantized = np.rint(np.column_stack((expected.real, expected.imag))).astype(np.int16)
    np.testing.assert_array_equal(result.samples_iq, quantized)
    assert result.clipped_components == 0


def test_impulse_centers_and_complete_original_support():
    raw = np.zeros((601, 2), dtype=np.int16)
    raw[300, 0] = 30000
    result = condition_capture25(raw, first_index=1000, downmix_hz=0)
    peak = int(np.argmax(result.samples_iq[:, 0])) + result.first_canonical_index
    assert peak == 1300 * 3 // 5
    assert result.first_canonical_index == 600 + 48
    info = result.metadata()
    assert info["first_source_center_numerator"] == 5 * result.first_canonical_index
    assert info["source_center_denominator"] == 3
    assert info["source_dependency_start_index"] >= 1000
    assert info["source_dependency_stop_index"] <= 1601
    assert info["filter"]["returned_center_delay_source_samples"] == 0
    assert not result.samples_iq.flags.writeable


@pytest.mark.parametrize("count", range(161, 181))
def test_every_terminal_polyphase_has_exact_support_and_counter_bounds(count):
    first = ((1 << 64) - count) // 5 * 5
    result = condition_capture25(np.zeros((count, 2), np.int16), first_index=first)
    start_local = result.first_canonical_index - first * 3 // 5
    stop_local = start_local + len(result.samples_iq)
    assert start_local * 5 - FILTER_HALF >= 0
    assert (start_local - 1) * 5 - FILTER_HALF < 0
    assert (stop_local - 1) * 5 + FILTER_HALF <= 3 * (count - 1)
    assert stop_local * 5 + FILTER_HALF > 3 * (count - 1)
    assert result.source_dependency_start_index == first + (5 * start_local - FILTER_HALF + 2) // 3
    assert result.source_dependency_stop_index == first + (5 * (stop_local - 1) + FILTER_HALF) // 3 + 1
    assert result.source_dependency_stop_index <= 1 << 64


@pytest.mark.parametrize("frequency", [-6_500_000, -2_000_000, 0, 2_000_000, 6_500_000])
def test_declared_passband_preserves_tones_and_sign(frequency):
    raw = tone(5_000_000 + frequency)
    result = condition_capture25(raw, first_index=0)
    indexes = result.first_canonical_index + np.arange(len(result.samples_iq))
    expected = 10000 * np.exp(2j * np.pi * frequency * indexes / 15_000_000)
    actual = result.samples_iq[:, 0].astype(float) + 1j * result.samples_iq[:, 1]
    assert np.max(np.abs(actual - expected)) < 2.0
    assert result.clipped_components == 0


@pytest.mark.parametrize("frequency", [-11_000_000, -9_000_000, -7_500_000, 7_500_000, 9_000_000])
def test_stopband_does_not_alias_strong_tones(frequency):
    result = condition_capture25(tone(frequency, amplitude=20000), first_index=0, downmix_hz=0)
    # Includes the CI16 source and output quantization floors, not an impossible
    # floating-filter-only attenuation claim for tiny integer outputs.
    assert np.max(np.abs(result.samples_iq.astype(np.int32))) <= 2


@pytest.mark.parametrize("downmix", [5_000_000, 4_882_812.5, -123_456.75])
def test_absolute_phase_overlapping_windows_are_bit_exact(downmix):
    raw = np.random.default_rng(501).integers(-12000, 12001, (2000, 2), dtype=np.int16)
    first = ((1 << 60) // 5) * 5
    whole = condition_capture25(raw, first_index=first, downmix_hz=downmix)
    subset = condition_capture25(raw[350:1650], first_index=first + 350, downmix_hz=downmix)
    offset = subset.first_canonical_index - whole.first_canonical_index
    np.testing.assert_array_equal(subset.samples_iq, whole.samples_iq[offset:offset + len(subset.samples_iq)])


def test_declared_filter_response_gain_and_hash():
    info = condition_capture25(np.zeros((400, 2), np.int16), first_index=0).metadata()["filter"]
    assert len(coefficients()) == 481 and abs(coefficients().sum() - 3) < 1e-12
    assert info["measured_passband_max_absolute_db"] < 0.001
    assert info["measured_stopband_max_db"] < -80
    assert info["response_grid_spacing_hz"] == FILTER_RATE_HZ / 262144
    assert info["coefficient_sha256"] == hashlib.sha256(coefficients().astype("<f8").tobytes()).hexdigest()
    assert not info["full_15mhz_bandwidth_preserved"]


def test_rounding_saturation_is_counted_without_gain_normalization():
    raw = np.zeros((1200, 2), dtype=np.int16)
    raw[300:900] = 32767
    result = condition_capture25(raw, first_index=0, downmix_hz=0)
    assert result.clipped_components > 0
    assert result.samples_iq.max() == 32767
    assert not result.metadata()["implicit_amplitude_normalization"]


@pytest.mark.parametrize("first", [-5, 1, 1.0, True, 1 << 65])
def test_invalid_origins_fail(first):
    with pytest.raises(ValueError):
        condition_capture25(np.zeros((200, 2), np.int16), first_index=first)


@pytest.mark.parametrize("raw", [
    np.zeros((200, 2), float), np.zeros((200, 2), bool), np.zeros((200, 3), np.int16),
    np.zeros(200, np.int16), np.zeros((0, 2), np.int16), np.zeros((50, 2), np.int16),
    np.full((200, 2), 32768), np.full((200, 2), -32769),
])
def test_invalid_ci16_geometry_and_support_fail(raw):
    with pytest.raises(ValueError):
        condition_capture25(raw, first_index=0)


@pytest.mark.parametrize("frequency", [True, "5000000", float("nan"), float("inf"), 12_500_000])
def test_invalid_frequency_fails(frequency):
    with pytest.raises((ValueError, TypeError)):
        condition_capture25(np.zeros((200, 2), np.int16), first_index=0, downmix_hz=frequency)


def test_oversize_is_rejected_before_filter_allocation():
    raw = np.broadcast_to(np.array([[0, 0]], dtype=np.int16), (MAX_INPUT_SAMPLES + 1, 2))
    with pytest.raises(ValueError, match="bounded"):
        condition_capture25(raw, first_index=0)
