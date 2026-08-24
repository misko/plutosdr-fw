"""Planted offline tests for modulated-signal generation and analysis."""

from __future__ import annotations

import json
import math

import pytest

from .modulated_quality import (
    ModulatedQualityThresholds,
    analyze_modulated_capture,
    build_composite_blocker,
    decode_dual_rx_cs16,
    decode_tx2_cs16,
    encode_tx2_cs16,
    generate_cyclic_qpsk,
    quantify_blocker_degradation,
    root_raised_cosine_taps,
    scale_reference_for_tx,
    summarize_blocker_sweep,
)

SAMPLE_RATE_HZ = 1_024_000


@pytest.fixture(scope="module")
def reference():
    return generate_cyclic_qpsk(
        sample_rate_hz=SAMPLE_RATE_HZ,
        symbol_count=256,
        samples_per_symbol=4,
        rolloff=0.25,
        span_symbols=10,
        seed=46,
    )


def _capture(
    tx_samples,
    *,
    cycles: int = 3,
    timing_offset: int = 137,
    cfo_hz: float = 375.0,
    gains: tuple[complex, complex] = (
        900.0 * complex(math.cos(0.55), math.sin(0.55)),
        720.0 * complex(math.cos(-0.35), math.sin(-0.35)),
    ),
    noise_sigma: float = 1.5,
    seed: int = 91,
):
    np = pytest.importorskip("numpy")
    cycle = np.asarray(tx_samples, dtype=np.complex128)
    indexes = np.arange(cycles * cycle.size, dtype=np.float64)
    aligned = cycle[(indexes.astype(np.int64) + timing_offset) % cycle.size]
    carrier = np.exp(2j * np.pi * cfo_hz * indexes / SAMPLE_RATE_HZ)
    rng = np.random.default_rng(seed)
    channels = []
    for gain in gains:
        noise = noise_sigma * (
            rng.normal(size=indexes.size) + 1j * rng.normal(size=indexes.size)
        )
        channels.append(gain * aligned * carrier + noise)
    return np.asarray(channels)


def _encode_dual_rx(matrix) -> bytes:
    np = pytest.importorskip("numpy")
    values = np.asarray(matrix)
    words = np.empty((values.shape[1], 4), dtype="<i2")
    words[:, 0] = np.rint(values[0].real).astype("<i2")
    words[:, 1] = np.rint(values[0].imag).astype("<i2")
    words[:, 2] = np.rint(values[1].real).astype("<i2")
    words[:, 3] = np.rint(values[1].imag).astype("<i2")
    return words.tobytes()


def test_qpsk_generation_is_deterministic_balanced_and_cyclic(reference) -> None:
    np = pytest.importorskip("numpy")
    repeated = generate_cyclic_qpsk(
        sample_rate_hz=SAMPLE_RATE_HZ,
        symbol_count=256,
        samples_per_symbol=4,
        rolloff=0.25,
        span_symbols=10,
        seed=46,
    )
    different = generate_cyclic_qpsk(
        sample_rate_hz=SAMPLE_RATE_HZ,
        symbol_count=256,
        samples_per_symbol=4,
        rolloff=0.25,
        span_symbols=10,
        seed=47,
    )

    assert reference.reference_id == repeated.reference_id
    assert reference.reference_id != different.reference_id
    assert np.array_equal(reference.bits, repeated.bits)
    assert np.array_equal(reference.samples, repeated.samples)
    assert reference.samples.shape == (1_024,)
    assert np.mean(reference.samples) == pytest.approx(0.0j, abs=1e-12)
    assert np.mean(np.abs(reference.samples) ** 2) == pytest.approx(1.0, abs=1e-12)
    assert sorted(np.unique(reference.symbols, return_counts=True)[1]) == [64] * 4
    # Circular shaping has no filter startup tail: every repeated-cycle window
    # is exactly the same deterministic reference.
    tiled = np.tile(reference.samples, 3)
    assert np.array_equal(tiled[1_024:2_048], reference.samples)


def test_rrc_taps_are_symmetric_finite_and_unit_energy() -> None:
    np = pytest.importorskip("numpy")
    taps = root_raised_cosine_taps(samples_per_symbol=4, span_symbols=10, rolloff=0.25)
    assert taps.size == 41
    assert np.isfinite(taps).all()
    assert taps == pytest.approx(taps[::-1], abs=1e-15)
    assert np.sum(taps**2) == pytest.approx(1.0, abs=1e-14)
    sinc = root_raised_cosine_taps(samples_per_symbol=4, span_symbols=8, rolloff=0.0)
    assert np.isfinite(sinc).all()


def test_tx2_cs16_encoding_scales_with_headroom_without_clipping(reference) -> None:
    np = pytest.importorskip("numpy")
    scaled = scale_reference_for_tx(reference, peak_fraction=0.8)
    encoded = encode_tx2_cs16(scaled.tx_samples, headroom_db=3.0)
    decoded = decode_tx2_cs16(encoded.payload)

    assert encoded.sample_count == reference.cycle_samples
    assert len(encoded.payload) == reference.cycle_samples * 4
    assert 23_190 <= encoded.peak_code <= 23_200
    assert encoded.peak_code < 32_767
    expected = scaled.tx_samples * encoded.applied_scale
    # Independent I/Q rounding gives at most sqrt(0.5^2 + 0.5^2) complex error.
    assert decoded == pytest.approx(expected, abs=0.72)
    assert np.max(np.abs(decoded.real)) <= 32_767
    assert np.max(np.abs(decoded.imag)) <= 32_767


def test_sync_recovers_planted_timing_cfo_phase_gain_and_metrics(reference) -> None:
    raw = _encode_dual_rx(_capture(reference.samples))
    result = analyze_modulated_capture(
        raw,
        reference=reference,
        max_cfo_hz=2_000.0,
        adc_full_scale=2_048.0,
    )

    assert result["quality_valid"], result["quality_reasons"]
    assert result["timing_offset_samples"] == 137
    assert result["rx_timing_offsets_samples"] == [137, 137]
    assert result["timing_disagreement_samples"] == 0
    assert result["estimated_cfo_hz"] == pytest.approx(375.0, abs=0.5)
    assert result["desired_gain_linear"] == pytest.approx([900.0, 720.0], rel=0.002)
    assert result["amplitude_imbalance_db_rx0_over_rx1"] == pytest.approx(
        20.0 * math.log10(900.0 / 720.0), abs=0.02
    )
    assert result["phase_difference_rad_rx0_minus_rx1"] == pytest.approx(0.9, abs=0.003)
    assert max(result["evm_percent"]) < 0.4
    assert min(result["mer_db"]) > 45.0
    assert result["ser"] == [0.0, 0.0]
    assert result["ber"] == [0.0, 0.0]
    assert result["cross_channel_coherence"] > 0.9999
    assert result["clipping_fraction"] == [0.0, 0.0]
    json.dumps(result, allow_nan=False)


def test_phase_and_gain_do_not_inflate_evm_after_reference_equalization(
    reference,
) -> None:
    capture = _capture(
        reference.samples,
        timing_offset=733,
        cfo_hz=-625.0,
        gains=(350.0j, -1_100.0 + 200.0j),
        noise_sigma=0.2,
    )
    result = analyze_modulated_capture(
        capture,
        reference=reference,
        max_cfo_hz=2_000.0,
        adc_full_scale=4_096.0,
    )
    assert result["quality_valid"], result["quality_reasons"]
    assert result["timing_offset_samples"] == 733
    assert result["estimated_cfo_hz"] == pytest.approx(-625.0, abs=0.2)
    assert max(result["evm_percent"]) < 0.2
    assert result["ser"] == [0.0, 0.0]


def test_noise_increases_evm_reduces_mer_and_eventually_causes_errors(
    reference,
) -> None:
    clean = analyze_modulated_capture(
        _capture(reference.samples, noise_sigma=1.0),
        reference=reference,
        max_cfo_hz=2_000.0,
    )
    noisy = analyze_modulated_capture(
        _capture(reference.samples, noise_sigma=450.0),
        reference=reference,
        max_cfo_hz=2_000.0,
        adc_full_scale=4_096.0,
    )
    assert min(noisy["evm_percent"]) > max(clean["evm_percent"]) * 20
    assert max(noisy["mer_db"]) < min(clean["mer_db"])
    assert max(noisy["ber"]) > 0.0
    assert not noisy["quality_valid"]
    assert any(
        reason.endswith(("evm_high", "ber_high")) for reason in noisy["quality_reasons"]
    )


def test_clipping_is_detected_and_fails_the_envelope(reference) -> None:
    np = pytest.importorskip("numpy")
    capture = _capture(reference.samples, noise_sigma=0.0)
    clipped = np.clip(capture.real, -2_048, 2_047) + 1j * np.clip(
        capture.imag, -2_048, 2_047
    )
    clipped[:, ::23] = 2_047 + 2_047j
    result = analyze_modulated_capture(
        clipped,
        reference=reference,
        max_cfo_hz=2_000.0,
        adc_full_scale=2_048.0,
    )
    assert not result["quality_valid"]
    assert result["clipping_fraction"][0] > 0.0
    assert result["clipping_fraction"][1] > 0.0
    assert "rx0_clipping" in result["quality_reasons"]
    assert "rx1_clipping" in result["quality_reasons"]


def test_independent_rx_timing_shift_is_detected(reference) -> None:
    np = pytest.importorskip("numpy")
    capture = _capture(reference.samples, noise_sigma=0.2)
    capture[1] = np.roll(capture[1], 1)
    result = analyze_modulated_capture(
        capture,
        reference=reference,
        max_cfo_hz=2_000.0,
    )
    assert not result["quality_valid"]
    assert result["timing_disagreement_samples"] == 1
    assert "rx_timing_disagreement" in result["quality_reasons"]


def test_composite_blocker_power_offset_and_degradation_are_quantified(
    reference,
) -> None:
    baseline_waveform = scale_reference_for_tx(reference, peak_fraction=0.75)
    near_waveform = build_composite_blocker(
        reference,
        blocker_offset_hz=64_000.0,
        blocker_power_db=-3.0,
        blocker_seed=117,
        peak_fraction=0.75,
    )
    far_waveform = build_composite_blocker(
        reference,
        blocker_offset_hz=320_000.0,
        blocker_power_db=-3.0,
        blocker_seed=117,
        peak_fraction=0.75,
    )
    baseline = analyze_modulated_capture(
        _capture(baseline_waveform.tx_samples, gains=(1_000.0, 850.0), noise_sigma=1.0),
        reference=reference,
        max_cfo_hz=2_000.0,
    )
    near = analyze_modulated_capture(
        _capture(near_waveform.tx_samples, gains=(1_000.0, 850.0), noise_sigma=1.0),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=near_waveform.blocker_offset_hz,
        blocker_power_db=near_waveform.blocker_power_db,
        blocker_reference=near_waveform.blocker_reference,
    )
    far = analyze_modulated_capture(
        _capture(far_waveform.tx_samples, gains=(1_000.0, 850.0), noise_sigma=1.0),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=far_waveform.blocker_offset_hz,
        blocker_power_db=far_waveform.blocker_power_db,
        blocker_reference=far_waveform.blocker_reference,
    )

    near_degradation = quantify_blocker_degradation(baseline, near)
    far_degradation = quantify_blocker_degradation(baseline, far)
    assert near_degradation["blocker_offset_hz"] == 64_000.0
    assert near_degradation["blocker_power_db"] == -3.0
    assert near_degradation["worst_evm_increase_percentage_points"] > 10.0
    assert near_degradation["worst_mer_loss_db"] > 3.0
    assert (
        near_degradation["worst_evm_increase_percentage_points"]
        > (far_degradation["worst_evm_increase_percentage_points"])
    )
    assert near["blocker_detected"]
    assert near["measured_blocker_offset_hz"] == pytest.approx(64_000.0)
    assert near["measured_blocker_power_db"] == pytest.approx(-3.0, abs=0.1)
    assert min(near["blocker_correlation"]) > 0.99
    assert far["blocker_detected"]
    assert far["measured_blocker_offset_hz"] == pytest.approx(320_000.0)
    sweep = summarize_blocker_sweep(baseline, [far, near])
    assert sweep["point_count"] == 2
    assert [point["blocker_offset_hz"] for point in sweep["points"]] == [
        64_000.0,
        320_000.0,
    ]
    json.dumps(sweep, allow_nan=False)


def test_commanded_but_absent_blocker_is_not_accepted(reference) -> None:
    commanded = build_composite_blocker(
        reference,
        blocker_offset_hz=320_000.0,
        blocker_power_db=-10.0,
        blocker_seed=72,
    )
    desired_only = scale_reference_for_tx(reference)
    result = analyze_modulated_capture(
        _capture(desired_only.tx_samples, noise_sigma=0.5),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=commanded.blocker_offset_hz,
        blocker_power_db=commanded.blocker_power_db,
        blocker_reference=commanded.blocker_reference,
    )
    assert not result["quality_valid"]
    assert not result["blocker_detected"]
    assert "blocker_not_detected" in result["quality_reasons"]
    assert result["blocker_measurement"]["minimum_correlation"] < 0.1


def test_mirrored_blocker_fails_signed_offset_provenance(reference) -> None:
    commanded = build_composite_blocker(
        reference,
        blocker_offset_hz=320_000.0,
        blocker_power_db=-10.0,
        blocker_seed=73,
    )
    mirrored = build_composite_blocker(
        reference,
        blocker_offset_hz=-320_000.0,
        blocker_power_db=-10.0,
        blocker_seed=73,
    )
    result = analyze_modulated_capture(
        _capture(mirrored.tx_samples, noise_sigma=0.5),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=commanded.blocker_offset_hz,
        blocker_power_db=commanded.blocker_power_db,
        blocker_reference=commanded.blocker_reference,
    )
    assert result["blocker_detected"]
    assert result["measured_blocker_offset_hz"] == pytest.approx(-320_000.0)
    assert result["measured_blocker_power_db"] == pytest.approx(-10.0, abs=0.1)
    assert not result["quality_valid"]
    assert "blocker_signed_offset_mismatch" in result["quality_reasons"]


def test_wrong_blocker_power_fails_commanded_relative_power_gate(reference) -> None:
    actual = build_composite_blocker(
        reference,
        blocker_offset_hz=320_000.0,
        blocker_power_db=-20.0,
        blocker_seed=74,
    )
    result = analyze_modulated_capture(
        _capture(actual.tx_samples, noise_sigma=0.5),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=320_000.0,
        blocker_power_db=-10.0,
        blocker_reference=actual.blocker_reference,
    )
    assert result["blocker_detected"]
    assert result["measured_blocker_power_db"] == pytest.approx(-20.0, abs=0.1)
    assert not result["quality_valid"]
    assert "blocker_relative_power_mismatch" in result["quality_reasons"]


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (
            lambda: root_raised_cosine_taps(
                samples_per_symbol=1, span_symbols=10, rolloff=0.25
            ),
            "at least two",
        ),
        (
            lambda: root_raised_cosine_taps(
                samples_per_symbol=4, span_symbols=9, rolloff=0.25
            ),
            "even integer",
        ),
        (
            lambda: root_raised_cosine_taps(
                samples_per_symbol=4, span_symbols=10, rolloff=1.1
            ),
            "rolloff",
        ),
        (
            lambda: generate_cyclic_qpsk(
                sample_rate_hz=SAMPLE_RATE_HZ, symbol_count=65
            ),
            "multiple of four",
        ),
        (
            lambda: generate_cyclic_qpsk(sample_rate_hz=1_000_001, symbol_count=256),
            "divisible",
        ),
    ],
)
def test_generation_strictly_rejects_invalid_options(call, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()


def test_blocker_and_encoder_strictly_reject_unsafe_inputs(reference) -> None:
    np = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="integer number of cycles"):
        build_composite_blocker(
            reference, blocker_offset_hz=64_000.5, blocker_power_db=-3.0
        )
    with pytest.raises(ValueError, match="Nyquist"):
        build_composite_blocker(
            reference, blocker_offset_hz=448_000.0, blocker_power_db=-3.0
        )
    with pytest.raises(ValueError, match="non-finite"):
        encode_tx2_cs16(np.asarray([1.0 + 1.0j, complex(math.nan, 0.0)]))
    with pytest.raises(ValueError, match="all zero"):
        encode_tx2_cs16(np.zeros(32, dtype=np.complex128))
    with pytest.raises(ValueError, match="headroom"):
        encode_tx2_cs16(reference.samples, headroom_db=-1.0)


@pytest.mark.parametrize(
    ("payload", "message"),
    [(b"", "empty"), (b"\x00\x00", "multiple of four words")],
)
def test_dual_decoder_rejects_malformed_payload(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode_dual_rx_cs16(payload)


def test_analyzer_strictly_rejects_short_nonfinite_and_invalid_metadata(
    reference,
) -> None:
    np = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="two complete"):
        analyze_modulated_capture(
            np.zeros((2, reference.cycle_samples), dtype=np.complex128),
            reference=reference,
        )
    nonfinite = np.zeros((2, 2 * reference.cycle_samples), dtype=np.complex128)
    nonfinite[0, 0] = math.inf
    with pytest.raises(ValueError, match="non-finite"):
        analyze_modulated_capture(nonfinite, reference=reference)
    with pytest.raises(ValueError, match="supplied together"):
        analyze_modulated_capture(
            _capture(reference.samples),
            reference=reference,
            blocker_offset_hz=64_000.0,
        )
    with pytest.raises(ValueError, match="max_ser"):
        analyze_modulated_capture(
            _capture(reference.samples),
            reference=reference,
            thresholds=ModulatedQualityThresholds(max_ser=1.1),
        )


def test_degradation_rejects_mismatched_or_duplicate_evidence(reference) -> None:
    baseline = analyze_modulated_capture(
        _capture(reference.samples), reference=reference, max_cfo_hz=2_000.0
    )
    blocked_waveform = build_composite_blocker(
        reference,
        blocker_offset_hz=64_000.0,
        blocker_power_db=-10.0,
        blocker_seed=52,
    )
    blocked = analyze_modulated_capture(
        _capture(blocked_waveform.tx_samples),
        reference=reference,
        max_cfo_hz=2_000.0,
        blocker_offset_hz=64_000.0,
        blocker_power_db=-10.0,
        blocker_reference=blocked_waveform.blocker_reference,
    )
    different = generate_cyclic_qpsk(
        sample_rate_hz=SAMPLE_RATE_HZ,
        symbol_count=256,
        samples_per_symbol=4,
        seed=999,
    )
    mismatched = dict(blocked)
    mismatched["reference_id"] = different.reference_id
    with pytest.raises(ValueError, match="reference IDs differ"):
        quantify_blocker_degradation(baseline, mismatched)
    with pytest.raises(ValueError, match="duplicate"):
        summarize_blocker_sweep(baseline, [blocked, dict(blocked)])
