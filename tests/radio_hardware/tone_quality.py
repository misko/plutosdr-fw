"""Self-contained dual-RX common-tone quality measurements.

The hardware tests receive interleaved ``RX0 I/Q, RX1 I/Q`` signed 16-bit
words whose useful ADC range is 12 bits.  This module deliberately has no SPF
dependency so that the firmware repository owns its hardware acceptance
oracle.  All returned values are JSON-safe Python scalars and lists.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToneQualityThresholds:
    """Absolute acceptance envelope for one stable dual-RX tone frame."""

    min_tone_snr_db: float = 10.0
    min_tone_dbfs: float = -70.0
    max_tone_dbfs: float = -3.0
    max_clipping_fraction: float = 0.0
    min_coherence: float = 0.98
    max_phase_std_deg: float = 5.0
    max_frequency_error_hz: float = 250.0


DEFAULT_TONE_QUALITY_THRESHOLDS = ToneQualityThresholds()


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("tone-quality analysis requires numpy") from exc
    return numpy


def decode_dual_iq(raw_dual_iq: bytes | bytearray | memoryview) -> Any:
    """Decode interleaved dual-RX CS16 bytes into a ``(2, samples)`` matrix."""

    np = _numpy()
    words = np.frombuffer(raw_dual_iq, dtype="<i2")
    if words.size % 4:
        raise ValueError("dual-RX CS16 payload is not a multiple of four words")
    if not words.size:
        raise ValueError("dual-RX CS16 payload is empty")
    interleaved = words.reshape((-1, 4))
    return np.stack(
        (
            interleaved[:, 0].astype(np.float64)
            + 1j * interleaved[:, 1].astype(np.float64),
            interleaved[:, 2].astype(np.float64)
            + 1j * interleaved[:, 3].astype(np.float64),
        )
    )


def _signal_matrix(value: Any) -> Any:
    np = _numpy()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return decode_dual_iq(value)
    matrix = np.asarray(value)
    if matrix.ndim != 2 or matrix.shape[0] != 2:
        raise ValueError(f"signal must have shape (2, samples), got {matrix.shape}")
    if matrix.shape[1] == 0:
        raise ValueError("signal contains no samples")
    return matrix


def _parabolic_peak(power: Any, index: int) -> float:
    """Refine one FFT-bin peak with a bounded log-parabolic interpolation."""

    np = _numpy()
    if index <= 0 or index >= power.size - 1:
        return float(index)
    left, center, right = np.log(np.maximum(power[index - 1 : index + 2], 1e-30))
    denominator = left - 2.0 * center + right
    if abs(float(denominator)) < 1e-15:
        return float(index)
    offset = 0.5 * float(left - right) / float(denominator)
    return float(index + np.clip(offset, -0.5, 0.5))


def _circular_phase_stats(phases: Any) -> tuple[float, float, float]:
    np = _numpy()
    resultant = np.mean(np.exp(1j * phases))
    length = float(np.clip(abs(resultant), 0.0, 1.0))
    standard_deviation = math.sqrt(-2.0 * math.log(max(length, 1e-15)))
    return float(np.angle(resultant)), standard_deviation, length


def _refine_matched_frequency(
    signal: Any,
    *,
    coarse_frequency_hz: float,
    sample_rate_hz: int,
    search_min_hz: float,
    search_max_hz: float,
) -> float:
    """Maximize joint matched-tone power within one coarse FFT bin.

    FFT interpolation is accurate enough to locate the carrier, but a
    sub-hertz error across a long frame leaks real tone power into the fitted
    residual and understates SNR.  A small bounded golden-section refinement
    makes the amplitude/residual split stable without a scipy dependency.
    """

    np = _numpy()
    sample_count = int(signal.shape[1])
    half_bin_hz = sample_rate_hz / sample_count
    left = max(search_min_hz, coarse_frequency_hz - half_bin_hz)
    right = min(search_max_hz, coarse_frequency_hz + half_bin_hz)
    indexes = np.arange(sample_count, dtype=np.float64)

    def joint_power(frequency_hz: float) -> float:
        oscillator = np.exp(-2j * np.pi * frequency_hz * indexes / sample_rate_hz)
        amplitudes = np.mean(signal * oscillator[None, :], axis=1)
        return float(np.sum(np.abs(amplitudes) ** 2))

    golden_ratio = (math.sqrt(5.0) - 1.0) / 2.0
    inner_left = right - golden_ratio * (right - left)
    inner_right = left + golden_ratio * (right - left)
    power_left = joint_power(inner_left)
    power_right = joint_power(inner_right)
    for _ in range(24):
        if power_left < power_right:
            left = inner_left
            inner_left = inner_right
            power_left = power_right
            inner_right = left + golden_ratio * (right - left)
            power_right = joint_power(inner_right)
        else:
            right = inner_right
            inner_right = inner_left
            power_right = power_left
            inner_left = right - golden_ratio * (right - left)
            power_left = joint_power(inner_left)
    return float((left + right) / 2.0)


def analyze_common_tone(
    signal_or_raw: Any,
    *,
    sample_rate_hz: int,
    expected_tone_hz: float,
    tone_search_width_hz: float = 25_000.0,
    transient_samples: int = 1_024,
    phase_segments: int = 8,
    thresholds: ToneQualityThresholds = DEFAULT_TONE_QUALITY_THRESHOLDS,
    adc_full_scale: float = 2_048.0,
) -> Mapping[str, Any]:
    """Measure a common tone in dual-RX IQ.

    ``signal_or_raw`` may be the raw interleaved CS16 payload returned by IIO
    or a complex array with shape ``(2, samples)``.  Differential phase uses
    the bench convention ``angle(RX0) - angle(RX1)``.
    """

    np = _numpy()
    matrix = _signal_matrix(signal_or_raw)
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    if tone_search_width_hz <= 0:
        raise ValueError("tone_search_width_hz must be positive")
    if adc_full_scale <= 1:
        raise ValueError("adc_full_scale must be greater than one")
    if transient_samples < 0:
        raise ValueError("transient_samples cannot be negative")
    if phase_segments < 2:
        raise ValueError("phase_segments must be at least two")
    if abs(expected_tone_hz) + tone_search_width_hz >= sample_rate_hz / 2:
        raise ValueError("tone search band must fit strictly inside Nyquist")
    remaining = int(matrix.shape[1]) - transient_samples
    if remaining < phase_segments * 32:
        raise ValueError("not enough samples after transient removal")
    if not np.isfinite(matrix).all():
        raise ValueError("signal contains non-finite values")

    raw = matrix[:, transient_samples:].astype(np.complex128, copy=False)
    dc = np.mean(raw, axis=1)
    signal = raw - dc[:, None]
    sample_count = int(signal.shape[1])

    window = np.hanning(sample_count)
    spectrum = np.fft.fft(signal * window[None, :], axis=1)
    frequencies = np.fft.fftfreq(sample_count, d=1.0 / sample_rate_hz)
    # AD9361/DDS IQ convention can invert between otherwise valid images.  A
    # common-tone quality gate must accept either signed spectral placement
    # while preserving the measured sign for diagnostics.
    search_mask = (
        np.abs(np.abs(frequencies) - abs(expected_tone_hz)) <= tone_search_width_hz
    )
    search_indices = np.flatnonzero(search_mask)
    if search_indices.size < 6:
        raise ValueError("tone search band contains fewer than three FFT bins")
    combined_power = np.sum(np.abs(spectrum) ** 2, axis=0)
    masked_power = np.where(search_mask, combined_power, -1.0)
    peak_bin = int(np.argmax(masked_power))
    refined_peak_bin = _parabolic_peak(combined_power, peak_bin)
    coarse_frequency_hz = float(
        frequencies[peak_bin]
        + (refined_peak_bin - peak_bin) * sample_rate_hz / sample_count
    )
    signed_expected_hz = math.copysign(abs(expected_tone_hz), coarse_frequency_hz)
    search_min_hz = signed_expected_hz - tone_search_width_hz
    search_max_hz = signed_expected_hz + tone_search_width_hz
    tone_frequency_hz = _refine_matched_frequency(
        signal,
        coarse_frequency_hz=coarse_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        search_min_hz=search_min_hz,
        search_max_hz=search_max_hz,
    )

    sample_index = np.arange(sample_count, dtype=np.float64)
    oscillator = np.exp(-2j * np.pi * tone_frequency_hz * sample_index / sample_rate_hz)
    amplitudes = np.mean(signal * oscillator[None, :], axis=1)
    fitted_tone = amplitudes[:, None] * np.exp(
        2j * np.pi * tone_frequency_hz * sample_index / sample_rate_hz
    )
    residual = signal - fitted_tone

    numerical_floor = np.finfo(np.float64).tiny
    tone_power = np.abs(amplitudes) ** 2
    residual_power = np.mean(np.abs(residual) ** 2, axis=1)
    rms = np.sqrt(np.mean(np.abs(signal) ** 2, axis=1))
    with np.errstate(divide="ignore"):
        tone_dbfs = 20.0 * np.log10(
            np.maximum(np.abs(amplitudes), numerical_floor) / adc_full_scale
        )
        rms_dbfs = 20.0 * np.log10(np.maximum(rms, numerical_floor) / adc_full_scale)
        dc_dbfs = 20.0 * np.log10(
            np.maximum(np.abs(dc), numerical_floor) / adc_full_scale
        )
        tone_snr_db = 10.0 * np.log10(
            np.maximum(tone_power, numerical_floor)
            / np.maximum(residual_power, numerical_floor)
        )
        amplitude_imbalance_db = 20.0 * np.log10(
            max(float(abs(amplitudes[0])), numerical_floor)
            / max(float(abs(amplitudes[1])), numerical_floor)
        )

    segment_length = sample_count // phase_segments
    segment_amplitudes = []
    segment_phases = []
    for segment_index in range(phase_segments):
        start = segment_index * segment_length
        end = start + segment_length
        indexes = np.arange(start, end, dtype=np.float64)
        segment_oscillator = np.exp(
            -2j * np.pi * tone_frequency_hz * indexes / sample_rate_hz
        )
        segment_amplitude = np.mean(
            signal[:, start:end] * segment_oscillator[None, :], axis=1
        )
        segment_amplitudes.append(segment_amplitude)
        segment_phases.append(
            float(np.angle(segment_amplitude[0] * np.conj(segment_amplitude[1])))
        )
    segment_amplitudes = np.asarray(segment_amplitudes)
    segment_phases_array = np.asarray(segment_phases)
    phase_difference, phase_std, phase_resultant_length = _circular_phase_stats(
        segment_phases_array
    )
    cross = np.mean(segment_amplitudes[:, 0] * np.conj(segment_amplitudes[:, 1]))
    coherence_denominator = np.mean(np.abs(segment_amplitudes[:, 0]) ** 2) * np.mean(
        np.abs(segment_amplitudes[:, 1]) ** 2
    )
    coherence = (
        float(np.clip(abs(cross) ** 2 / coherence_denominator, 0.0, 1.0))
        if coherence_denominator > 0
        else 0.0
    )
    clipping_fraction = np.mean(
        (raw.real <= -adc_full_scale)
        | (raw.real >= adc_full_scale - 1)
        | (raw.imag <= -adc_full_scale)
        | (raw.imag >= adc_full_scale - 1),
        axis=1,
    )

    frequency_error_hz = abs(tone_frequency_hz) - abs(expected_tone_hz)
    phase_std_deg = math.degrees(phase_std)
    reasons: list[str] = []
    for channel in range(2):
        if tone_snr_db[channel] < thresholds.min_tone_snr_db:
            reasons.append(f"rx{channel}_tone_snr_low")
        if tone_dbfs[channel] < thresholds.min_tone_dbfs:
            reasons.append(f"rx{channel}_tone_too_weak")
        if tone_dbfs[channel] > thresholds.max_tone_dbfs:
            reasons.append(f"rx{channel}_tone_too_strong")
        if clipping_fraction[channel] > thresholds.max_clipping_fraction:
            reasons.append(f"rx{channel}_clipping")
    if coherence < thresholds.min_coherence:
        reasons.append("cross_channel_coherence_low")
    if phase_std_deg > thresholds.max_phase_std_deg:
        reasons.append("within_capture_phase_unstable")
    if abs(frequency_error_hz) > thresholds.max_frequency_error_hz:
        reasons.append("tone_frequency_error_high")
    if (
        abs(abs(float(frequencies[peak_bin])) - abs(expected_tone_hz))
        >= tone_search_width_hz - sample_rate_hz / sample_count
    ):
        reasons.append("tone_peak_at_search_edge")

    return {
        "channel_order": ["rx0", "rx1"],
        "sample_count": sample_count,
        "tone_frequency_hz": tone_frequency_hz,
        "tone_frequency_error_hz": frequency_error_hz,
        "tone_dbfs": [float(value) for value in tone_dbfs],
        "rms_dbfs": [float(value) for value in rms_dbfs],
        "dc_dbfs": [float(value) for value in dc_dbfs],
        "tone_snr_db": [float(value) for value in tone_snr_db],
        "clipping_fraction": [float(value) for value in clipping_fraction],
        "amplitude_imbalance_db_rx0_over_rx1": float(amplitude_imbalance_db),
        "coherence": coherence,
        "phase_difference_rad": phase_difference,
        "phase_difference_deg": math.degrees(phase_difference),
        "within_capture_phase_std_rad": phase_std,
        "within_capture_phase_std_deg": phase_std_deg,
        "within_capture_phase_resultant_length": phase_resultant_length,
        "segment_phase_rad": segment_phases,
        "quality_valid": not reasons,
        "quality_reasons": reasons,
    }


def analyze_dual_iq_tone(
    raw_dual_iq: bytes | bytearray | memoryview, **options: Any
) -> Mapping[str, Any]:
    """Explicit raw-payload alias for callers at the IIO boundary."""

    return analyze_common_tone(raw_dual_iq, **options)
