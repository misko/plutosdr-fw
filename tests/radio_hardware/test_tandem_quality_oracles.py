"""Synthetic offline goldens for the tandem-AGC RF-quality oracle."""

from __future__ import annotations

import json
import math

import pytest

from .tone_quality import (
    ToneQualityThresholds,
    analyze_common_tone,
    analyze_dual_iq_tone,
    decode_dual_iq,
)


def _wrap_phase(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


def _synthetic_dual_tone(
    *,
    samples: int = 32_768,
    sample_rate_hz: int = 3_000_000,
    tone_hz: float = 123_456.0,
    amplitudes: tuple[float, float] = (900.0, 720.0),
    phases: tuple[float, float] = (0.7, -0.4),
    dc: tuple[complex, complex] = (20.0 - 12.0j, -8.0 + 16.0j),
    noise_sigma: float = 2.0,
    seed: int = 46,
) -> bytes:
    np = pytest.importorskip("numpy")
    indexes = np.arange(samples, dtype=np.float64)
    carrier = np.exp(2j * np.pi * tone_hz * indexes / sample_rate_hz)
    rng = np.random.default_rng(seed)
    channels = []
    for amplitude, phase, offset in zip(amplitudes, phases, dc, strict=True):
        noise = noise_sigma * (rng.normal(size=samples) + 1j * rng.normal(size=samples))
        channels.append(amplitude * np.exp(1j * phase) * carrier + offset + noise)
    signal = np.asarray(channels)
    words = np.empty((samples, 4), dtype="<i2")
    words[:, 0] = np.rint(signal[0].real).astype("<i2")
    words[:, 1] = np.rint(signal[0].imag).astype("<i2")
    words[:, 2] = np.rint(signal[1].real).astype("<i2")
    words[:, 3] = np.rint(signal[1].imag).astype("<i2")
    return words.tobytes()


def test_common_tone_recovers_planted_dual_rx_metrics() -> None:
    raw = _synthetic_dual_tone()
    result = analyze_dual_iq_tone(
        raw,
        sample_rate_hz=3_000_000,
        expected_tone_hz=123_456.0,
        transient_samples=1_024,
    )

    assert result["quality_valid"], result["quality_reasons"]
    assert result["channel_order"] == ["rx0", "rx1"]
    assert result["sample_count"] == 32_768 - 1_024
    assert result["tone_frequency_hz"] == pytest.approx(123_456.0, abs=15.0)
    assert result["tone_frequency_error_hz"] == pytest.approx(0.0, abs=15.0)
    assert result["tone_dbfs"] == pytest.approx(
        [20.0 * math.log10(900.0 / 2_048.0), 20.0 * math.log10(720.0 / 2_048.0)],
        abs=0.15,
    )
    assert result["rms_dbfs"] == pytest.approx(result["tone_dbfs"], abs=0.05)
    assert result["dc_dbfs"] == pytest.approx(
        [
            20.0 * math.log10(abs(20.0 - 12.0j) / 2_048.0),
            20.0 * math.log10(abs(-8.0 + 16.0j) / 2_048.0),
        ],
        abs=0.3,
    )
    assert min(result["tone_snr_db"]) > 45.0
    assert result["clipping_fraction"] == [0.0, 0.0]
    assert result["amplitude_imbalance_db_rx0_over_rx1"] == pytest.approx(
        20.0 * math.log10(900.0 / 720.0), abs=0.05
    )
    assert result["coherence"] > 0.9999
    assert result["phase_difference_rad"] == pytest.approx(
        _wrap_phase(0.7 - (-0.4)), abs=0.002
    )
    assert result["within_capture_phase_std_deg"] < 0.1
    json.dumps(result, allow_nan=False)


def test_array_and_raw_entry_points_are_equivalent() -> None:
    raw = _synthetic_dual_tone(samples=8_192, tone_hz=100_000.0)
    options = {
        "sample_rate_hz": 3_000_000,
        "expected_tone_hz": 100_000.0,
        "transient_samples": 256,
        "phase_segments": 4,
    }
    from_raw = analyze_common_tone(raw, **options)
    from_matrix = analyze_common_tone(decode_dual_iq(raw), **options)
    assert from_raw == from_matrix


def test_tone_search_accepts_inverted_iq_but_preserves_measured_sign() -> None:
    raw = _synthetic_dual_tone(samples=16_384, tone_hz=-100_000.0)
    result = analyze_common_tone(
        raw,
        sample_rate_hz=3_000_000,
        expected_tone_hz=100_000.0,
        transient_samples=256,
        phase_segments=4,
    )
    assert result["quality_valid"], result["quality_reasons"]
    assert result["tone_frequency_hz"] == pytest.approx(-100_000.0, abs=1.0)
    assert result["tone_frequency_error_hz"] == pytest.approx(0.0, abs=1.0)


def test_quality_reasons_detect_weak_noisy_clipped_and_wrong_frequency() -> None:
    np = pytest.importorskip("numpy")
    raw = bytearray(
        _synthetic_dual_tone(
            samples=8_192,
            tone_hz=112_000.0,
            amplitudes=(8.0, 1_900.0),
            phases=(0.0, 0.0),
            noise_sigma=20.0,
        )
    )
    words = np.frombuffer(raw, dtype="<i2").reshape((-1, 4))
    words[::32, 2] = 2_047
    result = analyze_common_tone(
        raw,
        sample_rate_hz=3_000_000,
        expected_tone_hz=100_000.0,
        tone_search_width_hz=25_000.0,
        transient_samples=256,
        phase_segments=4,
        thresholds=ToneQualityThresholds(
            min_tone_dbfs=-40.0,
            max_frequency_error_hz=250.0,
        ),
    )

    assert not result["quality_valid"]
    assert "rx0_tone_snr_low" in result["quality_reasons"]
    assert "rx0_tone_too_weak" in result["quality_reasons"]
    assert "rx1_clipping" in result["quality_reasons"]
    assert "tone_frequency_error_high" in result["quality_reasons"]
    assert result["clipping_fraction"][1] > 0.0


@pytest.mark.parametrize(
    ("payload", "options", "message"),
    [
        (b"", {}, "empty"),
        (b"\x00\x00", {}, "multiple of four words"),
        (
            bytes(4 * 64 * 2),
            {"transient_samples": 0, "phase_segments": 8},
            "not enough samples",
        ),
    ],
)
def test_tone_oracle_rejects_malformed_or_too_short_payloads(
    payload: bytes, options: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        analyze_common_tone(
            payload,
            sample_rate_hz=3_000_000,
            expected_tone_hz=100_000.0,
            **options,
        )
