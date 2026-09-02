from __future__ import annotations

import math

import numpy as np
import pytest

from tests.starlink_oracle import (
    ACQUISITION_ORACLE_SCHEMA,
    AcquisitionConfig,
    FixedCorrelationResult,
    FixedMatchScoreStream,
    direct_fixed_match_scores,
    fold_phase_map_tiles,
    overlap_save_fixed_match_scores,
    projected_pss,
    quantize_normalized_match_power,
    quantize_q15,
    search_phase_map_drift,
)


def _score_stream(scores: np.ndarray, *, first_sample_index: int = 0) -> FixedMatchScoreStream:
    values = np.asarray(scores, dtype=np.uint32)
    values.flags.writeable = False
    return FixedMatchScoreStream(
        first_sample_index=first_sample_index,
        scores=values,
        template_samples=66,
        coefficient_energy=1,
        fft_samples=512,
        maximum_fft_rounding_residual=0.0,
    )


def test_default_acquisition_geometry_preserves_single_sample_sensitivity() -> None:
    config = AcquisitionConfig()

    assert config.schema == ACQUISITION_ORACLE_SCHEMA
    assert config.template_samples == 66
    assert config.frame_samples == 20_000
    assert config.valid_fft_outputs == 447
    assert config.phase_bins == 20_000
    assert config.score_bits == 8
    assert config.phase_map_word_bits == 16
    assert config.phase_map_bytes == 40_000
    assert config.phase_map_bytes_per_second == pytest.approx(468_750.0)
    assert config.maximum_phase_map_value == 64 * 255


def test_normalized_score_rounding_is_exact_and_ties_to_even() -> None:
    below_half = FixedCorrelationResult(1, 0, 3, 1, 1, 0)
    exact_half_to_even = FixedCorrelationResult(1, 0, 2, 1, 1, 0)
    unity = FixedCorrelationResult(7, 0, 7, 7, 1, 0)
    zero = FixedCorrelationResult(0, 0, 0, 7, 1, 0)

    assert quantize_normalized_match_power(below_half, score_bits=1) == 0
    assert quantize_normalized_match_power(exact_half_to_even, score_bits=1) == 0
    assert quantize_normalized_match_power(unity, score_bits=16) == 65_535
    assert quantize_normalized_match_power(zero, score_bits=16) == 0


def test_overlap_save_scores_are_exactly_equal_to_direct_integer_oracle() -> None:
    rng = np.random.default_rng(0xA15C)
    samples = rng.integers(-20_000, 20_001, size=(1_237, 2), dtype=np.int16)
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))

    direct = direct_fixed_match_scores(samples, coefficients, first_sample_index=91)
    accelerated = overlap_save_fixed_match_scores(
        samples,
        coefficients,
        first_sample_index=91,
        fft_samples=512,
    )

    np.testing.assert_array_equal(accelerated.scores, direct.scores)
    assert accelerated.first_sample_index == direct.first_sample_index == 91
    assert accelerated.template_samples == direct.template_samples == 66
    assert accelerated.coefficient_energy == direct.coefficient_energy
    assert accelerated.maximum_fft_rounding_residual < 0.125
    assert not accelerated.scores.flags.writeable


@pytest.mark.parametrize("start", (0, 446, 447, 448, 893))
def test_overlap_save_preserves_peaks_across_every_block_boundary(start: int) -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, "lower"))
    samples = np.zeros((start + coefficients.shape[0] + 100, 2), dtype=np.int16)
    samples[start : start + coefficients.shape[0]] = coefficients

    result = overlap_save_fixed_match_scores(samples, coefficients)

    assert int(np.argmax(result.scores)) == start
    assert int(result.scores[start]) == 255


def test_phase_map_uses_one_maximum_per_coarse_bin_and_frame() -> None:
    config = AcquisitionConfig(
        phase_bin_samples=4,
        tile_frames=4,
        score_bits=16,
        phase_map_word_bits=32,
    )
    score_count = 8 * config.frame_samples
    scores = np.ones(score_count, dtype=np.uint32)
    epoch = 1_234
    for frame in range(8):
        scores[frame * config.frame_samples + epoch] = 60_000
        scores[frame * config.frame_samples + epoch + 1] = 50_000

    tiles = fold_phase_map_tiles(_score_stream(scores), config)
    candidate = search_phase_map_drift(tiles)

    assert tiles.maps.shape == (2, 5_000)
    assert candidate.phase_bin_start_sample == 1_232
    assert candidate.phase_bin_center_sample == 1_233.5
    assert candidate.combined_score == 8 * 60_000
    assert candidate.peak_to_median == pytest.approx(60_000.0)
    assert math.isinf(candidate.robust_z)


def test_phase_map_omits_partial_frames_without_crossing_a_gap() -> None:
    config = AcquisitionConfig(
        phase_bin_samples=4,
        tile_frames=2,
        score_bits=16,
        phase_map_word_bits=32,
    )
    first_sample = 19_990
    complete_scores = 2 * config.frame_samples
    scores = np.full(10 + complete_scores + 37, 3, dtype=np.uint32)

    tiles = fold_phase_map_tiles(
        _score_stream(scores, first_sample_index=first_sample), config
    )

    assert tiles.maps.shape == (1, 5_000)
    assert tiles.tile_start_sample_indexes.tolist() == [20_000]
    assert tiles.discarded_leading_scores == 10
    assert tiles.discarded_trailing_scores == 37
    np.testing.assert_array_equal(tiles.maps, 6)


def test_shift_and_sum_recovers_fractional_frame_period_from_short_tiles() -> None:
    config = AcquisitionConfig(
        phase_bin_samples=4,
        tile_frames=4,
        score_bits=16,
        phase_map_word_bits=32,
    )
    frame_count = 32
    scores = np.ones(frame_count * config.frame_samples, dtype=np.uint32)
    epoch = 1_000.0
    true_period = 20_000.5
    for frame in range(frame_count):
        start = round(epoch + frame * true_period)
        if start < scores.size:
            scores[start] = 50_000

    tiles = fold_phase_map_tiles(_score_stream(scores), config)
    candidate = search_phase_map_drift(
        tiles,
        drift_bins_per_tile=np.arange(-1.0, 1.01, 0.25),
    )

    assert candidate.phase_bin_start_sample <= epoch < (
        candidate.phase_bin_start_sample + config.phase_bin_samples
    )
    assert candidate.drift_bins_per_tile == pytest.approx(0.5)
    assert candidate.estimated_frame_period_samples == pytest.approx(true_period)
    assert candidate.robust_z > 6.0


def test_noise_only_phase_map_does_not_meet_the_existing_robust_z_gate() -> None:
    config = AcquisitionConfig(
        phase_bin_samples=4,
        tile_frames=8,
        score_bits=16,
        phase_map_word_bits=32,
    )
    rng = np.random.default_rng(0xBAD5EED)
    scores = rng.integers(
        1_000,
        2_001,
        size=8 * config.frame_samples,
        dtype=np.uint32,
    )

    tiles = fold_phase_map_tiles(_score_stream(scores), config)
    candidate = search_phase_map_drift(tiles)

    assert candidate.peak_to_median < 1.15
    assert candidate.robust_z < 6.0


def test_acquisition_contract_rejects_ambiguous_or_unsafe_geometry() -> None:
    with pytest.raises(ValueError, match="power of two"):
        AcquisitionConfig(fft_samples=500)
    with pytest.raises(ValueError, match="divide"):
        AcquisitionConfig(phase_bin_samples=3)
    with pytest.raises(ValueError, match="configured word"):
        AcquisitionConfig(tile_frames=100_000)
    with pytest.raises(ValueError, match="at least one"):
        search_phase_map_drift(
            fold_phase_map_tiles(
                _score_stream(np.ones(100, dtype=np.uint32)), AcquisitionConfig()
            )
        )
