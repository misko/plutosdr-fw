"""Deterministic 15 MS/s PSS acquisition and phase-map oracle.

Contract ``starlink-pss-acquisition-oracle-v1`` separates three concerns:

* CI16/Q1.15 correlations have the same integer dot-product meaning as the
  exact tracking oracle;
* normalized match power is rounded to an unsigned fixed-point score with
  exact rational, ties-to-even arithmetic; and
* the FPGA-facing reduction takes one maximum per coarse phase bin and frame,
  then sums those maxima into bounded, ping-pong-friendly phase maps.

The overlap-save FFT in this module is only an accelerated host computation of
the integer dot products.  Its complex results are rounded back to integers and
checked against a conservative numerical residual bound.  It deliberately does
not define the internal scaling or rounding of a future RTL FFT.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .fixed import FixedCorrelationResult, fixed_correlate_ci16
from .numerology import FRAME_RATE_HZ, numerology_for_rate

ACQUISITION_ORACLE_SCHEMA = "starlink-pss-acquisition-oracle-v1"
ACQUISITION_SAMPLE_RATE_HZ = 15_000_000
DEFAULT_FFT_SAMPLES = 512
DEFAULT_PHASE_BIN_SAMPLES = 1
DEFAULT_TILE_FRAMES = 64
DEFAULT_SCORE_BITS = 8
DEFAULT_PHASE_MAP_WORD_BITS = 16
PHASE_MAP_WORD_BITS = (16, 32)


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Frozen geometry for one canonical 15 MS/s acquisition map."""

    fft_samples: int = DEFAULT_FFT_SAMPLES
    phase_bin_samples: int = DEFAULT_PHASE_BIN_SAMPLES
    tile_frames: int = DEFAULT_TILE_FRAMES
    score_bits: int = DEFAULT_SCORE_BITS
    phase_map_word_bits: int = DEFAULT_PHASE_MAP_WORD_BITS
    schema: str = ACQUISITION_ORACLE_SCHEMA

    def __post_init__(self) -> None:
        for name, value in (
            ("fft_samples", self.fft_samples),
            ("phase_bin_samples", self.phase_bin_samples),
            ("tile_frames", self.tile_frames),
            ("score_bits", self.score_bits),
            ("phase_map_word_bits", self.phase_map_word_bits),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fft_samples & (self.fft_samples - 1):
            raise ValueError("fft_samples must be a power of two")
        if self.fft_samples < self.template_samples:
            raise ValueError("fft_samples must contain one complete PSS template")
        if self.frame_samples % self.phase_bin_samples:
            raise ValueError("phase_bin_samples must divide the 15 MS/s frame exactly")
        if not 1 <= self.score_bits <= 24:
            raise ValueError("score_bits must lie in [1, 24]")
        if self.phase_map_word_bits not in PHASE_MAP_WORD_BITS:
            raise ValueError("phase_map_word_bits must be 16 or 32")
        if self.maximum_phase_map_value > (1 << self.phase_map_word_bits) - 1:
            raise ValueError("one phase-map bin does not fit its configured word")

    @property
    def template_samples(self) -> int:
        return numerology_for_rate(ACQUISITION_SAMPLE_RATE_HZ).symbol_samples

    @property
    def frame_samples(self) -> int:
        return numerology_for_rate(ACQUISITION_SAMPLE_RATE_HZ).frame_samples

    @property
    def valid_fft_outputs(self) -> int:
        return self.fft_samples - self.template_samples + 1

    @property
    def phase_bins(self) -> int:
        return self.frame_samples // self.phase_bin_samples

    @property
    def score_full_scale(self) -> int:
        return (1 << self.score_bits) - 1

    @property
    def maximum_phase_map_value(self) -> int:
        return self.tile_frames * self.score_full_scale

    @property
    def phase_map_bytes(self) -> int:
        return self.phase_bins * (self.phase_map_word_bits // 8)

    @property
    def phase_map_bytes_per_second(self) -> float:
        return self.phase_map_bytes * FRAME_RATE_HZ / self.tile_frames


@dataclass(frozen=True, slots=True)
class FixedMatchScoreStream:
    """Contiguous fixed-point scores naming their first input sample."""

    first_sample_index: int
    scores: npt.NDArray[np.uint32]
    template_samples: int
    coefficient_energy: int
    fft_samples: int
    maximum_fft_rounding_residual: float
    schema: str = ACQUISITION_ORACLE_SCHEMA


@dataclass(frozen=True, slots=True)
class PhaseMapTiles:
    """Complete phase maps; partial leading and trailing frames are omitted."""

    maps: npt.NDArray[np.uint32]
    tile_start_sample_indexes: npt.NDArray[np.int64]
    phase_bin_samples: int
    tile_frames: int
    frame_samples: int
    score_bits: int
    phase_map_word_bits: int
    discarded_leading_scores: int
    discarded_trailing_scores: int
    schema: str = ACQUISITION_ORACLE_SCHEMA


@dataclass(frozen=True, slots=True)
class PhaseMapCandidate:
    """Best phase and linear inter-tile drift under deterministic tie rules."""

    phase_bin: int
    phase_bin_start_sample: int
    phase_bin_center_sample: float
    drift_bins_per_tile: float
    estimated_frame_period_samples: float
    combined_score: int
    combined_median: float
    peak_to_median: float
    robust_z: float
    tile_count: int
    schema: str = ACQUISITION_ORACLE_SCHEMA


def quantize_normalized_match_power(
    result: FixedCorrelationResult,
    *,
    score_bits: int = DEFAULT_SCORE_BITS,
) -> int:
    """Round normalized match power to unsigned fixed point, ties to even."""

    if isinstance(score_bits, bool) or not isinstance(score_bits, int):
        raise TypeError("score_bits must be an integer")
    if not 1 <= score_bits <= 24:
        raise ValueError("score_bits must lie in [1, 24]")
    denominator = result.normalization_product
    if denominator <= 0:
        return 0
    return _round_normalized_power(
        result.correlation_power,
        denominator,
        full_scale=(1 << score_bits) - 1,
    )


def direct_fixed_match_scores(
    samples_iq: npt.ArrayLike,
    coefficients_iq: npt.ArrayLike,
    *,
    first_sample_index: int = 0,
    score_bits: int = DEFAULT_SCORE_BITS,
) -> FixedMatchScoreStream:
    """Small, direct reference used to qualify the accelerated FFT oracle."""

    samples = _ci16_matrix(samples_iq, "samples_iq")
    coefficients = _ci16_matrix(coefficients_iq, "coefficients_iq")
    _validate_first_sample_index(first_sample_index)
    if coefficients.shape[0] > samples.shape[0]:
        raise ValueError("coefficients must not be longer than samples")
    output_count = samples.shape[0] - coefficients.shape[0] + 1
    scores = np.fromiter(
        (
            quantize_normalized_match_power(
                fixed_correlate_ci16(
                    samples[start : start + coefficients.shape[0]], coefficients
                ),
                score_bits=score_bits,
            )
            for start in range(output_count)
        ),
        dtype=np.uint32,
        count=output_count,
    )
    scores.flags.writeable = False
    coefficient_energy = int(
        np.sum(
            coefficients[:, 0] * coefficients[:, 0]
            + coefficients[:, 1] * coefficients[:, 1],
            dtype=np.int64,
        )
    )
    return FixedMatchScoreStream(
        first_sample_index=first_sample_index,
        scores=scores,
        template_samples=coefficients.shape[0],
        coefficient_energy=coefficient_energy,
        fft_samples=0,
        maximum_fft_rounding_residual=0.0,
    )


def overlap_save_fixed_match_scores(
    samples_iq: npt.ArrayLike,
    coefficients_iq: npt.ArrayLike,
    *,
    first_sample_index: int = 0,
    fft_samples: int = DEFAULT_FFT_SAMPLES,
    score_bits: int = DEFAULT_SCORE_BITS,
) -> FixedMatchScoreStream:
    """Compute exact-integer correlation scores through overlap-save FFTs.

    Complex FFT results must lie within one eighth of an integer before they
    are rounded.  The bound is intentionally much larger than normal binary64
    FFT noise but much smaller than a correlation accumulator LSB.
    """

    samples = _ci16_matrix(samples_iq, "samples_iq")
    coefficients = _ci16_matrix(coefficients_iq, "coefficients_iq")
    _validate_first_sample_index(first_sample_index)
    _validate_score_bits(score_bits)
    if isinstance(fft_samples, bool) or not isinstance(fft_samples, int):
        raise TypeError("fft_samples must be an integer")
    if fft_samples <= 0 or fft_samples & (fft_samples - 1):
        raise ValueError("fft_samples must be a positive power of two")
    if coefficients.shape[0] > samples.shape[0]:
        raise ValueError("coefficients must not be longer than samples")
    if coefficients.shape[0] > fft_samples:
        raise ValueError("fft_samples must contain one complete coefficient vector")

    template_samples = coefficients.shape[0]
    output_count = samples.shape[0] - template_samples + 1
    valid_outputs = fft_samples - template_samples + 1
    sample_complex = np.asarray(
        samples[:, 0] + 1j * samples[:, 1], dtype=np.complex128
    )
    coefficient_complex = np.asarray(
        coefficients[:, 0] + 1j * coefficients[:, 1], dtype=np.complex128
    )
    convolution_kernel = np.conj(coefficient_complex[::-1])
    kernel_fft = np.fft.fft(convolution_kernel, fft_samples)

    sample_power = (
        samples[:, 0] * samples[:, 0] + samples[:, 1] * samples[:, 1]
    )
    cumulative_energy = np.empty(samples.shape[0] + 1, dtype=np.int64)
    cumulative_energy[0] = 0
    np.cumsum(sample_power, dtype=np.int64, out=cumulative_energy[1:])
    window_energy = (
        cumulative_energy[template_samples:] - cumulative_energy[:-template_samples]
    )
    coefficient_energy = int(
        np.sum(
            coefficients[:, 0] * coefficients[:, 0]
            + coefficients[:, 1] * coefficients[:, 1],
            dtype=np.int64,
        )
    )

    scores = np.empty(output_count, dtype=np.uint32)
    maximum_residual = 0.0
    full_scale = (1 << score_bits) - 1
    padded = np.zeros(fft_samples, dtype=np.complex128)
    for output_start in range(0, output_count, valid_outputs):
        count = min(valid_outputs, output_count - output_start)
        padded.fill(0)
        source = sample_complex[output_start : output_start + fft_samples]
        padded[: source.size] = source
        circular = np.fft.ifft(np.fft.fft(padded) * kernel_fft)
        selected = circular[
            template_samples - 1 : template_samples - 1 + count
        ]
        rounded_real = np.rint(selected.real)
        rounded_imag = np.rint(selected.imag)
        if selected.size:
            maximum_residual = max(
                maximum_residual,
                float(np.max(np.abs(selected.real - rounded_real))),
                float(np.max(np.abs(selected.imag - rounded_imag))),
            )
        if maximum_residual >= 0.125:
            raise ArithmeticError(
                "binary64 overlap-save result is not safely inside one integer LSB"
            )
        real = np.asarray(rounded_real, dtype=np.int64)
        imag = np.asarray(rounded_imag, dtype=np.int64)
        for local_index, (real_value, imag_value, energy_value) in enumerate(
            zip(
                real,
                imag,
                window_energy[output_start : output_start + count],
                strict=True,
            )
        ):
            correlation_power = int(real_value) ** 2 + int(imag_value) ** 2
            denominator = int(energy_value) * coefficient_energy
            scores[output_start + local_index] = _round_normalized_power(
                correlation_power,
                denominator,
                full_scale=full_scale,
            )

    scores.flags.writeable = False
    return FixedMatchScoreStream(
        first_sample_index=first_sample_index,
        scores=scores,
        template_samples=template_samples,
        coefficient_energy=coefficient_energy,
        fft_samples=fft_samples,
        maximum_fft_rounding_residual=maximum_residual,
    )


def fold_phase_map_tiles(
    stream: FixedMatchScoreStream,
    config: AcquisitionConfig,
) -> PhaseMapTiles:
    """Reduce complete nominal frames into exact 32-bit phase-map tiles.

    The first reduction is a maximum over ``phase_bin_samples`` consecutive
    scores in each frame.  This preserves a narrow correlation peak instead of
    paying the noise penalty of summing every fine lag.  The per-frame maxima
    are then summed over ``tile_frames``.
    """

    if stream.schema != ACQUISITION_ORACLE_SCHEMA:
        raise ValueError("score stream schema is not supported")
    if stream.scores.ndim != 1:
        raise ValueError("score stream must be one-dimensional")
    if stream.template_samples != config.template_samples:
        raise ValueError("score stream template geometry does not match configuration")
    if np.any(stream.scores > config.score_full_scale):
        raise ValueError("score stream exceeds the configured fixed-point width")

    frame_samples = config.frame_samples
    first_aligned = _ceil_div(stream.first_sample_index, frame_samples) * frame_samples
    leading = first_aligned - stream.first_sample_index
    if leading >= stream.scores.size:
        complete_tile_count = 0
    else:
        complete_tile_count = (
            stream.scores.size - leading
        ) // (config.tile_frames * frame_samples)
    retained_count = complete_tile_count * config.tile_frames * frame_samples
    trailing = stream.scores.size - leading - retained_count

    if complete_tile_count:
        retained = stream.scores[leading : leading + retained_count]
        framed = retained.reshape(
            complete_tile_count,
            config.tile_frames,
            config.phase_bins,
            config.phase_bin_samples,
        )
        per_frame_maximum = np.max(framed, axis=3)
        maps64 = np.sum(per_frame_maximum, axis=1, dtype=np.uint64)
        if int(np.max(maps64)) > (1 << config.phase_map_word_bits) - 1:
            raise OverflowError("phase map exceeds its configured accumulator")
        map_dtype = np.uint16 if config.phase_map_word_bits == 16 else np.uint32
        maps = np.asarray(maps64, dtype=map_dtype)
        starts = first_aligned + np.arange(complete_tile_count, dtype=np.int64) * (
            config.tile_frames * frame_samples
        )
    else:
        map_dtype = np.uint16 if config.phase_map_word_bits == 16 else np.uint32
        maps = np.empty((0, config.phase_bins), dtype=map_dtype)
        starts = np.empty(0, dtype=np.int64)
    maps.flags.writeable = False
    starts.flags.writeable = False
    return PhaseMapTiles(
        maps=maps,
        tile_start_sample_indexes=starts,
        phase_bin_samples=config.phase_bin_samples,
        tile_frames=config.tile_frames,
        frame_samples=frame_samples,
        score_bits=config.score_bits,
        phase_map_word_bits=config.phase_map_word_bits,
        discarded_leading_scores=leading,
        discarded_trailing_scores=trailing,
    )


def search_phase_map_drift(
    tiles: PhaseMapTiles,
    *,
    drift_bins_per_tile: Iterable[float] = (0.0,),
) -> PhaseMapCandidate:
    """Shift-and-sum maps over a finite linear cadence-drift bank.

    Drift hypotheses are sorted.  Exact score ties retain the numerically
    smallest drift and then the smallest phase bin.
    """

    if tiles.schema != ACQUISITION_ORACLE_SCHEMA:
        raise ValueError("phase-map schema is not supported")
    if tiles.maps.ndim != 2 or tiles.maps.shape[0] == 0:
        raise ValueError("at least one complete phase-map tile is required")
    hypotheses = tuple(sorted(float(value) for value in drift_bins_per_tile))
    if not hypotheses or not all(math.isfinite(value) for value in hypotheses):
        raise ValueError("drift hypothesis bank must be finite and nonempty")
    if len(set(hypotheses)) != len(hypotheses):
        raise ValueError("drift hypothesis bank must be unique")

    best_drift = hypotheses[0]
    best_bin = 0
    best_score = -1
    best_combined: npt.NDArray[np.uint64] | None = None
    for drift in hypotheses:
        combined = np.zeros(tiles.maps.shape[1], dtype=np.uint64)
        for tile_index, phase_map in enumerate(tiles.maps):
            shift = -round(tile_index * drift)
            combined += np.roll(phase_map, shift)
        phase_bin = int(np.argmax(combined))
        score = int(combined[phase_bin])
        if score > best_score:
            best_drift = drift
            best_bin = phase_bin
            best_score = score
            best_combined = combined

    assert best_combined is not None
    median = float(np.median(best_combined))
    robust_sigma = 1.4826 * float(np.median(np.abs(best_combined - median)))
    peak_to_median = (
        best_score / median if median > 0 else (math.inf if best_score > 0 else 1.0)
    )
    robust_z = (
        (best_score - median) / robust_sigma
        if robust_sigma > 0
        else (math.inf if best_score > median else 0.0)
    )
    phase_start = best_bin * tiles.phase_bin_samples
    period_delta = (
        best_drift * tiles.phase_bin_samples / tiles.tile_frames
    )
    return PhaseMapCandidate(
        phase_bin=best_bin,
        phase_bin_start_sample=phase_start,
        phase_bin_center_sample=phase_start + (tiles.phase_bin_samples - 1) / 2,
        drift_bins_per_tile=best_drift,
        estimated_frame_period_samples=tiles.frame_samples + period_delta,
        combined_score=best_score,
        combined_median=median,
        peak_to_median=float(peak_to_median),
        robust_z=float(robust_z),
        tile_count=tiles.maps.shape[0],
    )


def _round_normalized_power(
    numerator: int,
    denominator: int,
    *,
    full_scale: int,
) -> int:
    if numerator <= 0 or denominator <= 0:
        return 0
    if numerator >= denominator:
        return full_scale
    quotient, remainder = divmod(numerator * full_scale, denominator)
    doubled = 2 * remainder
    if doubled > denominator or (doubled == denominator and quotient & 1):
        quotient += 1
    return quotient


def _ci16_matrix(values: npt.ArrayLike, name: str) -> npt.NDArray[np.int64]:
    raw = np.asarray(values)
    if (
        raw.ndim != 2
        or raw.shape[1:] != (2,)
        or not np.issubdtype(raw.dtype, np.integer)
    ):
        raise ValueError(f"{name} must be an integer matrix with shape (N, 2)")
    converted = np.asarray(raw, dtype=np.int64)
    if np.any(converted < -(1 << 15)) or np.any(converted > (1 << 15) - 1):
        raise ValueError(f"{name} components must fit signed 16 bits")
    return converted


def _validate_first_sample_index(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("first_sample_index must be an integer")
    if value < 0 or value > (1 << 63) - 1:
        raise ValueError("first_sample_index must fit nonnegative signed 64 bits")


def _validate_score_bits(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("score_bits must be an integer")
    if not 1 <= value <= 24:
        raise ValueError("score_bits must lie in [1, 24]")


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)
