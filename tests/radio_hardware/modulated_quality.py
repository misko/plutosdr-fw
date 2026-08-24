"""Deterministic modulated-signal generation and dual-RX quality analysis.

The hardware integration can cyclically transmit :class:`QpskReference.samples`
through TX2 after encoding it with :func:`encode_tx2_cs16`.  Captures are
synchronized against the complete known waveform, so the oracle does not need
an external trigger or an SPF dependency.  NumPy is the only numerical
dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("modulated-quality analysis requires numpy") from exc
    return numpy


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number")
    return converted


def _positive_integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class QpskReference:
    """One complete periodic QPSK reference cycle."""

    samples: Any
    symbols: Any
    bits: Any
    rrc_taps: Any
    sample_rate_hz: int
    samples_per_symbol: int
    rolloff: float
    span_symbols: int
    seed: int
    reference_id: str

    @property
    def symbol_count(self) -> int:
        return int(self.symbols.size)

    @property
    def cycle_samples(self) -> int:
        return int(self.samples.size)

    @property
    def symbol_rate_hz(self) -> float:
        return self.sample_rate_hz / self.samples_per_symbol


@dataclass(frozen=True)
class CompositeQpsk:
    """Desired QPSK plus an optional independently seeded QPSK blocker."""

    tx_samples: Any
    desired_samples: Any
    blocker_samples: Any | None
    desired_reference: QpskReference
    blocker_reference: QpskReference | None
    blocker_offset_hz: float | None
    blocker_power_db: float | None
    applied_scale: float
    peak_fraction: float


@dataclass(frozen=True)
class EncodedCS16:
    """A safely scaled little-endian, interleaved I/Q transmit payload."""

    payload: bytes
    sample_count: int
    applied_scale: float
    peak_code: int
    headroom_db: float


@dataclass(frozen=True)
class ModulatedQualityThresholds:
    """Absolute limits applied after known-reference synchronization."""

    max_evm_percent: float = 18.0
    min_mer_db: float = 14.9
    max_ser: float = 0.01
    max_ber: float = 0.005
    max_clipping_fraction: float = 0.0
    min_cross_channel_coherence: float = 0.98
    max_timing_disagreement_samples: int = 0
    max_abs_cfo_hz: float = 5_000.0
    min_blocker_correlation: float = 0.50
    max_blocker_offset_error_hz: float = 1.0
    max_blocker_power_error_db: float = 2.0


DEFAULT_MODULATED_THRESHOLDS = ModulatedQualityThresholds()


def root_raised_cosine_taps(
    *, samples_per_symbol: int, span_symbols: int, rolloff: float
) -> Any:
    """Return a unit-energy, odd-length root-raised-cosine FIR."""

    np = _numpy()
    samples_per_symbol = _positive_integer("samples_per_symbol", samples_per_symbol)
    span_symbols = _positive_integer("span_symbols", span_symbols)
    rolloff = _finite_number("rolloff", rolloff)
    if samples_per_symbol < 2:
        raise ValueError("samples_per_symbol must be at least two")
    if span_symbols < 2 or span_symbols % 2:
        raise ValueError("span_symbols must be an even integer of at least two")
    if not 0.0 <= rolloff <= 1.0:
        raise ValueError("rolloff must be in [0, 1]")

    sample_offsets = np.arange(
        -(span_symbols * samples_per_symbol) // 2,
        (span_symbols * samples_per_symbol) // 2 + 1,
        dtype=np.float64,
    )
    time_symbols = sample_offsets / samples_per_symbol
    taps = np.empty(time_symbols.size, dtype=np.float64)
    if rolloff == 0.0:
        taps[:] = np.sinc(time_symbols)
    else:
        singular = 1.0 / (4.0 * rolloff)
        for index, time_value in enumerate(time_symbols):
            if abs(float(time_value)) < 1e-14:
                taps[index] = 1.0 - rolloff + 4.0 * rolloff / math.pi
            elif abs(abs(float(time_value)) - singular) < 1e-12:
                taps[index] = (rolloff / math.sqrt(2.0)) * (
                    (1.0 + 2.0 / math.pi) * math.sin(math.pi / (4.0 * rolloff))
                    + (1.0 - 2.0 / math.pi) * math.cos(math.pi / (4.0 * rolloff))
                )
            else:
                numerator = math.sin(math.pi * time_value * (1.0 - rolloff))
                numerator += (
                    4.0
                    * rolloff
                    * time_value
                    * math.cos(math.pi * time_value * (1.0 + rolloff))
                )
                denominator = (
                    math.pi * time_value * (1.0 - (4.0 * rolloff * time_value) ** 2)
                )
                taps[index] = numerator / denominator
    energy = float(np.sum(taps**2))
    if not math.isfinite(energy) or energy <= 0.0:
        raise ValueError("RRC design produced invalid energy")
    taps /= math.sqrt(energy)
    return taps


def _circular_filter(samples: Any, taps: Any) -> Any:
    """Apply a zero-delay FIR with circular boundary conditions."""

    np = _numpy()
    vector = np.asarray(samples, dtype=np.complex128)
    coefficients = np.asarray(taps, dtype=np.float64)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("circular-filter input must be a nonempty vector")
    if (
        coefficients.ndim != 1
        or coefficients.size < 3
        or coefficients.size > vector.size
    ):
        raise ValueError("circular-filter taps must fit inside the input cycle")
    padded = np.zeros(vector.size, dtype=np.complex128)
    center = coefficients.size // 2
    for index, coefficient in enumerate(coefficients):
        padded[(index - center) % vector.size] += coefficient
    return np.fft.ifft(np.fft.fft(vector) * np.fft.fft(padded))


def _reference_digest(
    *,
    bits: Any,
    sample_rate_hz: int,
    samples_per_symbol: int,
    rolloff: float,
    span_symbols: int,
    seed: int,
) -> str:
    config = json.dumps(
        {
            "sample_rate_hz": sample_rate_hz,
            "samples_per_symbol": samples_per_symbol,
            "rolloff": rolloff,
            "span_symbols": span_symbols,
            "seed": seed,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256(config)
    digest.update(bits.tobytes())
    return digest.hexdigest()


def generate_cyclic_qpsk(
    *,
    sample_rate_hz: int,
    symbol_count: int = 512,
    samples_per_symbol: int = 4,
    rolloff: float = 0.25,
    span_symbols: int = 10,
    seed: int = 46,
) -> QpskReference:
    """Generate a deterministic, balanced, circularly RRC-shaped QPSK cycle."""

    np = _numpy()
    sample_rate_hz = _positive_integer("sample_rate_hz", sample_rate_hz)
    symbol_count = _positive_integer("symbol_count", symbol_count)
    samples_per_symbol = _positive_integer("samples_per_symbol", samples_per_symbol)
    if symbol_count < 64 or symbol_count % 4:
        raise ValueError("symbol_count must be a multiple of four and at least 64")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if sample_rate_hz % samples_per_symbol:
        raise ValueError("sample_rate_hz must be divisible by samples_per_symbol")

    taps = root_raised_cosine_taps(
        samples_per_symbol=samples_per_symbol,
        span_symbols=span_symbols,
        rolloff=rolloff,
    )
    if taps.size > symbol_count * samples_per_symbol:
        raise ValueError("RRC span does not fit inside one waveform cycle")

    # Equal populations make the finite cyclic reference exactly zero mean.
    quadrants = np.tile(np.arange(4, dtype=np.uint8), symbol_count // 4)
    rng = np.random.default_rng(seed)
    rng.shuffle(quadrants)
    bit0 = (quadrants >> 1) & 1
    bit1 = quadrants & 1
    bits = np.column_stack((bit0, bit1)).astype(np.uint8)
    symbols = (
        (1.0 - 2.0 * bits[:, 0].astype(np.float64))
        + 1j * (1.0 - 2.0 * bits[:, 1].astype(np.float64))
    ) / math.sqrt(2.0)

    upsampled = np.zeros(symbol_count * samples_per_symbol, dtype=np.complex128)
    upsampled[::samples_per_symbol] = symbols
    shaped = _circular_filter(upsampled, taps)
    rms = math.sqrt(float(np.mean(np.abs(shaped) ** 2)))
    if not math.isfinite(rms) or rms <= 0.0:
        raise ValueError("QPSK shaping produced invalid power")
    shaped /= rms
    reference_id = _reference_digest(
        bits=bits,
        sample_rate_hz=sample_rate_hz,
        samples_per_symbol=samples_per_symbol,
        rolloff=float(rolloff),
        span_symbols=span_symbols,
        seed=seed,
    )
    return QpskReference(
        samples=shaped,
        symbols=symbols,
        bits=bits,
        rrc_taps=taps,
        sample_rate_hz=sample_rate_hz,
        samples_per_symbol=samples_per_symbol,
        rolloff=float(rolloff),
        span_symbols=span_symbols,
        seed=seed,
        reference_id=reference_id,
    )


def build_composite_blocker(
    desired: QpskReference,
    *,
    blocker_offset_hz: float,
    blocker_power_db: float,
    blocker_seed: int = 47,
    peak_fraction: float = 0.80,
) -> CompositeQpsk:
    """Build a cyclic desired-plus-blocker waveform with deterministic headroom."""

    np = _numpy()
    if not isinstance(desired, QpskReference):
        raise TypeError("desired must be a QpskReference")
    offset_hz = _finite_number("blocker_offset_hz", blocker_offset_hz)
    power_db = _finite_number("blocker_power_db", blocker_power_db)
    peak_fraction = _finite_number("peak_fraction", peak_fraction)
    if not 0.0 < peak_fraction <= 1.0:
        raise ValueError("peak_fraction must be in (0, 1]")
    if offset_hz == 0.0:
        raise ValueError("blocker_offset_hz must be nonzero")

    cycle_rotations = offset_hz * desired.cycle_samples / desired.sample_rate_hz
    if abs(cycle_rotations - round(cycle_rotations)) > 1e-9:
        raise ValueError("blocker offset must contain an integer number of cycles")
    occupied_half_bandwidth = 0.5 * desired.symbol_rate_hz * (1.0 + desired.rolloff)
    if abs(offset_hz) + occupied_half_bandwidth >= desired.sample_rate_hz / 2.0:
        raise ValueError("blocker occupied bandwidth must fit strictly inside Nyquist")

    blocker = generate_cyclic_qpsk(
        sample_rate_hz=desired.sample_rate_hz,
        symbol_count=desired.symbol_count,
        samples_per_symbol=desired.samples_per_symbol,
        rolloff=desired.rolloff,
        span_symbols=desired.span_symbols,
        seed=blocker_seed,
    )
    indexes = np.arange(desired.cycle_samples, dtype=np.float64)
    frequency_shift = np.exp(2j * np.pi * offset_hz * indexes / desired.sample_rate_hz)
    blocker_scale = 10.0 ** (power_db / 20.0)
    shifted_blocker = blocker_scale * blocker.samples * frequency_shift
    composite = desired.samples + shifted_blocker
    maximum_component = float(
        max(np.max(np.abs(composite.real)), np.max(np.abs(composite.imag)))
    )
    if not math.isfinite(maximum_component) or maximum_component <= 0.0:
        raise ValueError("composite waveform has invalid peak amplitude")
    applied_scale = peak_fraction / maximum_component
    return CompositeQpsk(
        tx_samples=composite * applied_scale,
        desired_samples=desired.samples * applied_scale,
        blocker_samples=shifted_blocker * applied_scale,
        desired_reference=desired,
        blocker_reference=blocker,
        blocker_offset_hz=offset_hz,
        blocker_power_db=power_db,
        applied_scale=applied_scale,
        peak_fraction=peak_fraction,
    )


def scale_reference_for_tx(
    desired: QpskReference, *, peak_fraction: float = 0.80
) -> CompositeQpsk:
    """Scale a desired-only reference using the same policy as blocker variants."""

    np = _numpy()
    if not isinstance(desired, QpskReference):
        raise TypeError("desired must be a QpskReference")
    peak_fraction = _finite_number("peak_fraction", peak_fraction)
    if not 0.0 < peak_fraction <= 1.0:
        raise ValueError("peak_fraction must be in (0, 1]")
    maximum_component = float(
        max(np.max(np.abs(desired.samples.real)), np.max(np.abs(desired.samples.imag)))
    )
    applied_scale = peak_fraction / maximum_component
    scaled = desired.samples * applied_scale
    return CompositeQpsk(
        tx_samples=scaled,
        desired_samples=scaled,
        blocker_samples=None,
        desired_reference=desired,
        blocker_reference=None,
        blocker_offset_hz=None,
        blocker_power_db=None,
        applied_scale=applied_scale,
        peak_fraction=peak_fraction,
    )


def encode_tx2_cs16(
    samples: Any, *, headroom_db: float = 1.0, full_scale_code: int = 32_767
) -> EncodedCS16:
    """Normalize finite complex samples into safe little-endian TX2 CS16."""

    np = _numpy()
    vector = np.asarray(samples, dtype=np.complex128)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("TX2 samples must be a nonempty one-dimensional vector")
    if not np.isfinite(vector).all():
        raise ValueError("TX2 samples contain non-finite values")
    headroom_db = _finite_number("headroom_db", headroom_db)
    if headroom_db < 0.0 or headroom_db > 60.0:
        raise ValueError("headroom_db must be in [0, 60]")
    if (
        isinstance(full_scale_code, bool)
        or not isinstance(full_scale_code, int)
        or not 1 <= full_scale_code <= 32_767
    ):
        raise ValueError("full_scale_code must be an integer in [1, 32767]")
    maximum_component = float(
        max(np.max(np.abs(vector.real)), np.max(np.abs(vector.imag)))
    )
    if maximum_component <= 0.0:
        raise ValueError("TX2 samples cannot be all zero")
    target_peak = full_scale_code * 10.0 ** (-headroom_db / 20.0)
    applied_scale = target_peak / maximum_component
    words = np.empty((vector.size, 2), dtype="<i2")
    real_codes = np.rint(vector.real * applied_scale)
    imag_codes = np.rint(vector.imag * applied_scale)
    if (
        np.max(np.abs(real_codes)) > full_scale_code
        or np.max(np.abs(imag_codes)) > full_scale_code
    ):
        raise ValueError("TX2 scaling exceeded the requested full-scale code")
    words[:, 0] = real_codes.astype("<i2")
    words[:, 1] = imag_codes.astype("<i2")
    peak_code = int(max(np.max(np.abs(words[:, 0])), np.max(np.abs(words[:, 1]))))
    return EncodedCS16(
        payload=words.tobytes(),
        sample_count=int(vector.size),
        applied_scale=float(applied_scale),
        peak_code=peak_code,
        headroom_db=headroom_db,
    )


def decode_tx2_cs16(payload: bytes | bytearray | memoryview) -> Any:
    """Decode one interleaved little-endian I/Q transmit payload."""

    np = _numpy()
    words = np.frombuffer(payload, dtype="<i2")
    if not words.size:
        raise ValueError("TX2 CS16 payload is empty")
    if words.size % 2:
        raise ValueError("TX2 CS16 payload is not a multiple of two words")
    matrix = words.reshape((-1, 2))
    return matrix[:, 0].astype(np.float64) + 1j * matrix[:, 1].astype(np.float64)


def decode_dual_rx_cs16(payload: bytes | bytearray | memoryview) -> Any:
    """Decode interleaved ``RX0 I/Q, RX1 I/Q`` little-endian CS16."""

    np = _numpy()
    words = np.frombuffer(payload, dtype="<i2")
    if not words.size:
        raise ValueError("dual-RX CS16 payload is empty")
    if words.size % 4:
        raise ValueError("dual-RX CS16 payload is not a multiple of four words")
    matrix = words.reshape((-1, 4))
    return np.stack(
        (
            matrix[:, 0].astype(np.float64) + 1j * matrix[:, 1].astype(np.float64),
            matrix[:, 2].astype(np.float64) + 1j * matrix[:, 3].astype(np.float64),
        )
    )


def _dual_signal(value: Any) -> Any:
    np = _numpy()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return decode_dual_rx_cs16(value)
    matrix = np.asarray(value, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != 2:
        raise ValueError(
            f"dual-RX signal must have shape (2, samples), got {matrix.shape}"
        )
    if matrix.shape[1] == 0:
        raise ValueError("dual-RX signal contains no samples")
    return matrix


def _circular_distance(first: int, second: int, period: int) -> int:
    difference = abs(first - second) % period
    return int(min(difference, period - difference))


def _correlations(matrix: Any, reference_fft_conjugate: Any) -> Any:
    np = _numpy()
    return np.fft.ifft(
        np.fft.fft(matrix, axis=1) * reference_fft_conjugate[None, :], axis=1
    )


def _estimate_cfo_and_timing(
    matrix: Any,
    reference: QpskReference,
    *,
    max_cfo_hz: float,
    cfo_grid_oversample: int,
) -> tuple[float, int, list[int], float]:
    np = _numpy()
    cycle = reference.cycle_samples
    sample_rate = reference.sample_rate_hz
    first_cycle = matrix[:, :cycle]
    reference_fft_conjugate = np.conj(np.fft.fft(reference.samples))
    grid_step = sample_rate / (cycle * cfo_grid_oversample)
    grid_count = math.ceil(max_cfo_hz / grid_step)
    candidates = np.arange(-grid_count, grid_count + 1, dtype=np.float64) * grid_step
    indexes = np.arange(cycle, dtype=np.float64)
    best_score = -1.0
    coarse_cfo = 0.0
    coarse_timing = 0
    for candidate in candidates:
        corrected = (
            first_cycle
            * np.exp(-2j * np.pi * candidate * indexes / sample_rate)[None, :]
        )
        correlations = _correlations(corrected, reference_fft_conjugate)
        joint = np.sum(np.abs(correlations) ** 2, axis=0)
        correlation_lag = int(np.argmax(joint))
        timing = (-correlation_lag) % cycle
        score = float(joint[correlation_lag])
        if score > best_score:
            best_score = score
            coarse_cfo = float(candidate)
            coarse_timing = timing

    used_samples = (matrix.shape[1] // cycle) * cycle
    indexes = np.arange(used_samples, dtype=np.float64)
    expected = reference.samples[(indexes.astype(np.int64) + coarse_timing) % cycle]
    coarse_corrected = (
        matrix[:, :used_samples]
        * np.exp(-2j * np.pi * coarse_cfo * indexes / sample_rate)[None, :]
    )
    centers = []
    channel_phases: list[list[float]] = [[], []]
    for cycle_index in range(used_samples // cycle):
        start = cycle_index * cycle
        end = start + cycle
        expected_segment = expected[start:end]
        centers.append(start + 0.5 * (cycle - 1))
        for channel in range(2):
            coefficient = np.vdot(
                expected_segment, coarse_corrected[channel, start:end]
            )
            channel_phases[channel].append(float(np.angle(coefficient)))
    residuals = []
    for phases in channel_phases:
        slope = np.polyfit(np.asarray(centers, dtype=np.float64), np.unwrap(phases), 1)[
            0
        ]
        residuals.append(float(slope * sample_rate / (2.0 * np.pi)))
    estimated_cfo = coarse_cfo + float(np.median(residuals))

    final_first = (
        first_cycle
        * np.exp(-2j * np.pi * estimated_cfo * np.arange(cycle) / sample_rate)[None, :]
    )
    correlations = _correlations(final_first, reference_fft_conjugate)
    individual_lags = [
        int(np.argmax(np.abs(correlations[channel]) ** 2)) for channel in range(2)
    ]
    individual = [(-lag) % cycle for lag in individual_lags]
    joint = np.sum(np.abs(correlations) ** 2, axis=0)
    correlation_lag = int(np.argmax(joint))
    timing = (-correlation_lag) % cycle
    reference_power = float(np.sum(np.abs(reference.samples) ** 2))
    normalized_peak = float(
        np.clip(
            np.mean(
                [
                    abs(correlations[channel, correlation_lag]) ** 2
                    / (
                        reference_power
                        * float(np.sum(np.abs(final_first[channel]) ** 2))
                    )
                    for channel in range(2)
                ]
            ),
            0.0,
            1.0,
        )
    )
    return estimated_cfo, timing, individual, normalized_peak


def _canonicalize_iq_convention(
    matrix: Any,
    reference: QpskReference,
    *,
    max_cfo_hz: float,
    cfo_grid_oversample: int,
) -> tuple[str, Any, float, int, list[int], float, dict[str, float]]:
    """Choose the decoded-RX spectral orientation that matches the TX reference.

    A Pluto TX-to-RX RF loopback can invert the complex spectrum even though the
    DMA and IIO scan lanes are both ordered I, Q.  In that transport convention
    the decoded receive vector is a complex conjugate of the transmitted
    baseband, up to ordinary timing, carrier, and complex-gain terms.  A random
    QPSK sequence is intentionally not conjugate symmetric, so correlating only
    the direct orientation makes a clean capture look like roughly 50% BER.

    Synchronize both physically valid global orientations and retain the one
    with the stronger normalized known-reference correlation.  Conjugating both
    receive channels preserves clipping and cross-channel coherence while
    returning timing, CFO, blocker offset, EVM, and decisions to the commanded
    TX-reference convention.
    """

    np = _numpy()
    candidates: list[tuple[str, Any, float, int, list[int], float]] = []
    for convention, canonical in (
        ("direct", matrix),
        ("conjugated", np.conj(matrix)),
    ):
        cfo_hz, timing, individual_timing, correlation_peak = _estimate_cfo_and_timing(
            canonical,
            reference,
            max_cfo_hz=max_cfo_hz,
            cfo_grid_oversample=cfo_grid_oversample,
        )
        candidates.append(
            (
                convention,
                canonical,
                cfo_hz,
                timing,
                individual_timing,
                correlation_peak,
            )
        )
    # The stable ordering deliberately resolves an exact tie as direct.  A
    # low-SNR ambiguous choice still fails the independent absolute quality
    # gates; it is never promoted merely because one orientation won.
    selected = max(candidates, key=lambda item: item[5])
    peaks = {item[0]: float(item[5]) for item in candidates}
    return (*selected, peaks)


def _validate_thresholds(thresholds: ModulatedQualityThresholds) -> None:
    if not isinstance(thresholds, ModulatedQualityThresholds):
        raise TypeError("thresholds must be ModulatedQualityThresholds")
    for name in (
        "max_evm_percent",
        "min_mer_db",
        "max_ser",
        "max_ber",
        "max_clipping_fraction",
        "min_cross_channel_coherence",
        "max_abs_cfo_hz",
        "min_blocker_correlation",
        "max_blocker_offset_error_hz",
        "max_blocker_power_error_db",
    ):
        value = _finite_number(name, getattr(thresholds, name))
        if value < 0.0:
            raise ValueError(f"{name} cannot be negative")
    if thresholds.max_evm_percent <= 0.0:
        raise ValueError("max_evm_percent must be positive")
    for name in ("max_ser", "max_ber", "max_clipping_fraction"):
        if getattr(thresholds, name) > 1.0:
            raise ValueError(f"{name} must be at most one")
    if not 0.0 <= thresholds.min_cross_channel_coherence <= 1.0:
        raise ValueError("min_cross_channel_coherence must be in [0, 1]")
    if not 0.0 <= thresholds.min_blocker_correlation <= 1.0:
        raise ValueError("min_blocker_correlation must be in [0, 1]")
    if thresholds.max_blocker_offset_error_hz < 0.0:
        raise ValueError("max_blocker_offset_error_hz must be nonnegative")
    if thresholds.max_blocker_power_error_db < 0.0:
        raise ValueError("max_blocker_power_error_db must be nonnegative")
    if (
        isinstance(thresholds.max_timing_disagreement_samples, bool)
        or not isinstance(thresholds.max_timing_disagreement_samples, int)
        or thresholds.max_timing_disagreement_samples < 0
    ):
        raise ValueError("max_timing_disagreement_samples must be nonnegative")


def _measure_known_blocker(
    corrected: Any,
    *,
    desired_reference: QpskReference,
    blocker_reference: QpskReference,
    timing: int,
    commanded_offset_hz: float,
    commanded_power_db: float,
) -> dict[str, Any]:
    """Measure signed blocker offset and relative power from the IQ itself."""

    np = _numpy()
    cycle = desired_reference.cycle_samples
    used_samples = int(corrected.shape[1])
    if used_samples % cycle:
        raise AssertionError("blocker measurement requires whole reference cycles")
    cycle_indexes = np.arange(cycle, dtype=np.int64)
    aligned_indexes = (cycle_indexes + timing) % cycle
    desired_cycle = desired_reference.samples[aligned_indexes]
    blocker_cycle = blocker_reference.samples[aligned_indexes]
    folded = corrected.reshape((2, used_samples // cycle, cycle)).mean(axis=1)
    desired_power = float(np.vdot(desired_cycle, desired_cycle).real)
    desired_coefficients = np.asarray(
        [
            np.vdot(desired_cycle, folded[channel]) / desired_power
            for channel in range(2)
        ]
    )
    residual = folded - desired_coefficients[:, None] * desired_cycle[None, :]
    spectra = np.stack(
        [np.fft.fft(residual[channel] * np.conj(blocker_cycle)) for channel in range(2)]
    )
    frequencies = np.fft.fftfreq(cycle, d=1.0 / desired_reference.sample_rate_hz)
    occupied_half_bandwidth = (
        0.5 * blocker_reference.symbol_rate_hz * (1.0 + blocker_reference.rolloff)
    )
    valid = (frequencies != 0.0) & (
        np.abs(frequencies) + occupied_half_bandwidth
        < desired_reference.sample_rate_hz / 2.0
    )
    if not bool(np.any(valid)):
        raise ValueError("no valid signed blocker-offset bins remain")
    score = np.sum(np.abs(spectra) ** 2, axis=0)
    score[~valid] = -1.0
    peak_index = int(np.argmax(score))
    measured_offset_hz = float(frequencies[peak_index])

    indexes = np.arange(used_samples, dtype=np.float64)
    desired_template = desired_reference.samples[
        (indexes.astype(np.int64) + timing) % cycle
    ]
    blocker_template = blocker_reference.samples[
        (indexes.astype(np.int64) + timing) % cycle
    ] * np.exp(
        2j
        * np.pi
        * measured_offset_hz
        * (indexes + float(timing))
        / desired_reference.sample_rate_hz
    )
    design = np.column_stack((desired_template, blocker_template))
    relative_power_db: list[float] = []
    correlations: list[float] = []
    for channel in range(2):
        coefficients, _residuals, rank, _singular = np.linalg.lstsq(
            design, corrected[channel], rcond=None
        )
        if int(rank) != 2 or abs(coefficients[0]) < 1e-12:
            raise ValueError("desired/blocker joint fit is singular")
        relative_power_db.append(
            float(
                20.0 * math.log10(max(abs(coefficients[1] / coefficients[0]), 1e-300))
            )
        )
        blocker_residual = corrected[channel] - coefficients[0] * desired_template
        numerator = abs(np.vdot(blocker_template, blocker_residual)) ** 2
        denominator = float(
            np.vdot(blocker_template, blocker_template).real
            * np.vdot(blocker_residual, blocker_residual).real
        )
        correlations.append(
            float(np.clip(numerator / denominator, 0.0, 1.0))
            if denominator > 0.0
            else 0.0
        )
    measured_power_db = float(np.median(np.asarray(relative_power_db)))
    frequency_resolution_hz = desired_reference.sample_rate_hz / cycle
    return {
        "measured_signed_offset_hz": measured_offset_hz,
        "commanded_signed_offset_hz": commanded_offset_hz,
        "offset_error_hz": measured_offset_hz - commanded_offset_hz,
        "frequency_resolution_hz": float(frequency_resolution_hz),
        "measured_relative_power_db": measured_power_db,
        "measured_relative_power_db_per_rx": relative_power_db,
        "commanded_relative_power_db": commanded_power_db,
        "relative_power_error_db": measured_power_db - commanded_power_db,
        "correlation_per_rx": correlations,
        "minimum_correlation": min(correlations),
    }


def analyze_modulated_capture(
    signal_or_raw: Any,
    *,
    reference: QpskReference,
    max_cfo_hz: float = 5_000.0,
    cfo_grid_oversample: int = 4,
    adc_full_scale: float = 2_048.0,
    thresholds: ModulatedQualityThresholds = DEFAULT_MODULATED_THRESHOLDS,
    blocker_offset_hz: float | None = None,
    blocker_power_db: float | None = None,
    blocker_reference: QpskReference | None = None,
) -> dict[str, Any]:
    """Synchronize and measure a dual-RX capture against known QPSK samples."""

    np = _numpy()
    if not isinstance(reference, QpskReference):
        raise TypeError("reference must be a QpskReference")
    matrix = _dual_signal(signal_or_raw)
    if not np.isfinite(matrix).all():
        raise ValueError("dual-RX signal contains non-finite values")
    max_cfo_hz = _finite_number("max_cfo_hz", max_cfo_hz)
    adc_full_scale = _finite_number("adc_full_scale", adc_full_scale)
    if max_cfo_hz <= 0.0 or max_cfo_hz >= reference.sample_rate_hz / 4.0:
        raise ValueError("max_cfo_hz must be positive and below Fs/4")
    cfo_grid_oversample = _positive_integer("cfo_grid_oversample", cfo_grid_oversample)
    if cfo_grid_oversample < 2 or cfo_grid_oversample > 32:
        raise ValueError("cfo_grid_oversample must be in [2, 32]")
    if adc_full_scale <= 1.0:
        raise ValueError("adc_full_scale must be greater than one")
    _validate_thresholds(thresholds)
    blocker_values = (
        blocker_offset_hz is not None,
        blocker_power_db is not None,
        blocker_reference is not None,
    )
    if len(set(blocker_values)) != 1:
        raise ValueError(
            "blocker offset, power, and known reference must be supplied together"
        )
    if blocker_offset_hz is not None:
        blocker_offset_hz = _finite_number("blocker_offset_hz", blocker_offset_hz)
        blocker_power_db = _finite_number("blocker_power_db", blocker_power_db)
        if not isinstance(blocker_reference, QpskReference):
            raise ValueError("blocker_reference must be a QpskReference")
        if (
            blocker_reference.sample_rate_hz != reference.sample_rate_hz
            or blocker_reference.cycle_samples != reference.cycle_samples
            or blocker_reference.samples_per_symbol != reference.samples_per_symbol
        ):
            raise ValueError("blocker reference is incompatible with desired reference")

    cycle = reference.cycle_samples
    if matrix.shape[1] < 2 * cycle:
        raise ValueError("capture must contain at least two complete reference cycles")
    used_samples = (matrix.shape[1] // cycle) * cycle
    matrix = matrix[:, :used_samples]
    clipping_fraction = np.mean(
        (matrix.real <= -adc_full_scale)
        | (matrix.real >= adc_full_scale - 1.0)
        | (matrix.imag <= -adc_full_scale)
        | (matrix.imag >= adc_full_scale - 1.0),
        axis=1,
    )

    (
        iq_convention,
        matrix,
        cfo_hz,
        timing,
        individual_timing,
        correlation_peak,
        convention_peaks,
    ) = _canonicalize_iq_convention(
        matrix,
        reference,
        max_cfo_hz=max_cfo_hz,
        cfo_grid_oversample=cfo_grid_oversample,
    )
    timing_disagreement = _circular_distance(
        individual_timing[0], individual_timing[1], cycle
    )
    indexes = np.arange(used_samples, dtype=np.float64)
    corrected = (
        matrix
        * np.exp(-2j * np.pi * cfo_hz * indexes / reference.sample_rate_hz)[None, :]
    )
    expected = reference.samples[(indexes.astype(np.int64) + timing) % cycle]
    blocker_measurement = (
        _measure_known_blocker(
            corrected,
            desired_reference=reference,
            blocker_reference=blocker_reference,
            timing=timing,
            commanded_offset_hz=blocker_offset_hz,
            commanded_power_db=blocker_power_db,
        )
        if blocker_reference is not None
        and blocker_offset_hz is not None
        and blocker_power_db is not None
        else None
    )
    reference_power = float(np.vdot(expected, expected).real)
    gains = np.asarray(
        [
            np.vdot(expected, corrected[channel]) / reference_power
            for channel in range(2)
        ]
    )
    if not np.isfinite(gains).all() or np.any(np.abs(gains) < 1e-12):
        raise ValueError("desired-reference gain estimate is singular")
    equalized = corrected / gains[:, None]
    sample_errors = equalized - expected[None, :]
    sample_evm = np.sqrt(
        np.mean(np.abs(sample_errors) ** 2, axis=1) / np.mean(np.abs(expected) ** 2)
    )

    matched_expected = _circular_filter(expected, reference.rrc_taps)
    matched_channels = np.stack(
        [
            _circular_filter(equalized[channel], reference.rrc_taps)
            for channel in range(2)
        ]
    )
    symbol_phase = (-timing) % reference.samples_per_symbol
    symbol_positions = np.arange(
        symbol_phase, used_samples, reference.samples_per_symbol, dtype=np.int64
    )
    symbol_indices = (
        (symbol_positions + timing) // reference.samples_per_symbol
    ) % reference.symbol_count
    target_symbols = reference.symbols[symbol_indices]
    ideal_symbols = matched_expected[symbol_positions]
    calibration = np.vdot(target_symbols, ideal_symbols) / np.vdot(
        target_symbols, target_symbols
    )
    if abs(calibration) < 1e-12:
        raise ValueError("matched reference produced singular symbol calibration")

    evm_values = []
    mer_values = []
    ser_values = []
    ber_values = []
    symbol_errors = []
    bit_errors = []
    expected_bits = reference.bits[symbol_indices]
    numerical_floor = np.finfo(np.float64).tiny
    for channel in range(2):
        observed_symbols = matched_channels[channel, symbol_positions]
        error = observed_symbols - ideal_symbols
        evm = math.sqrt(
            float(np.mean(np.abs(error) ** 2) / np.mean(np.abs(ideal_symbols) ** 2))
        )
        decisions_input = observed_symbols / calibration
        decided_bits = np.column_stack(
            ((decisions_input.real < 0.0), (decisions_input.imag < 0.0))
        ).astype(np.uint8)
        bit_error_count = int(np.count_nonzero(decided_bits != expected_bits))
        symbol_error_count = int(
            np.count_nonzero(np.any(decided_bits != expected_bits, axis=1))
        )
        evm_values.append(100.0 * evm)
        mer_values.append(-20.0 * math.log10(max(evm, numerical_floor)))
        ser_values.append(symbol_error_count / symbol_positions.size)
        ber_values.append(bit_error_count / (2 * symbol_positions.size))
        symbol_errors.append(symbol_error_count)
        bit_errors.append(bit_error_count)

    cross = np.vdot(corrected[1], corrected[0])
    cross_denominator = float(
        np.vdot(corrected[0], corrected[0]).real
        * np.vdot(corrected[1], corrected[1]).real
    )
    coherence = (
        float(np.clip(abs(cross) ** 2 / cross_denominator, 0.0, 1.0))
        if cross_denominator > 0.0
        else 0.0
    )
    gain_imbalance_db = 20.0 * math.log10(abs(gains[0]) / abs(gains[1]))
    phase_difference_rad = float(np.angle(gains[0] * np.conj(gains[1])))

    reasons: list[str] = []
    for channel in range(2):
        if evm_values[channel] > thresholds.max_evm_percent:
            reasons.append(f"rx{channel}_evm_high")
        if mer_values[channel] < thresholds.min_mer_db:
            reasons.append(f"rx{channel}_mer_low")
        if ser_values[channel] > thresholds.max_ser:
            reasons.append(f"rx{channel}_ser_high")
        if ber_values[channel] > thresholds.max_ber:
            reasons.append(f"rx{channel}_ber_high")
        if clipping_fraction[channel] > thresholds.max_clipping_fraction:
            reasons.append(f"rx{channel}_clipping")
    if coherence < thresholds.min_cross_channel_coherence:
        reasons.append("cross_channel_coherence_low")
    if timing_disagreement > thresholds.max_timing_disagreement_samples:
        reasons.append("rx_timing_disagreement")
    if abs(cfo_hz) > thresholds.max_abs_cfo_hz:
        reasons.append("cfo_out_of_bounds")
    cfo_grid_step_hz = reference.sample_rate_hz / (
        reference.cycle_samples * cfo_grid_oversample
    )
    if abs(cfo_hz) >= max_cfo_hz - cfo_grid_step_hz:
        reasons.append("cfo_at_search_edge")
    if blocker_measurement is not None:
        blocker_detected = bool(
            blocker_measurement["minimum_correlation"]
            >= thresholds.min_blocker_correlation
        )
        offset_valid = bool(
            abs(blocker_measurement["offset_error_hz"])
            <= thresholds.max_blocker_offset_error_hz
        )
        power_valid = bool(
            abs(blocker_measurement["relative_power_error_db"])
            <= thresholds.max_blocker_power_error_db
        )
        blocker_measurement.update(
            {
                "detected": blocker_detected,
                "offset_valid": offset_valid,
                "relative_power_valid": power_valid,
                "valid": blocker_detected and offset_valid and power_valid,
            }
        )
        if not blocker_detected:
            reasons.append("blocker_not_detected")
        if not offset_valid:
            reasons.append("blocker_signed_offset_mismatch")
        if not power_valid:
            reasons.append("blocker_relative_power_mismatch")

    return {
        "schema": "plutosdr-fw.modulated-quality.v1",
        "reference_id": reference.reference_id,
        "channel_order": ["rx0", "rx1"],
        "sample_count": int(used_samples),
        "cycle_count": int(used_samples // cycle),
        "symbol_count_per_rx": int(symbol_positions.size),
        "sample_rate_hz": reference.sample_rate_hz,
        "symbol_rate_hz": reference.symbol_rate_hz,
        "samples_per_symbol": reference.samples_per_symbol,
        "iq_convention": iq_convention,
        "iq_canonicalization": (
            "identity" if iq_convention == "direct" else "complex_conjugate"
        ),
        "iq_convention_correlation_peaks": convention_peaks,
        "estimated_cfo_hz": float(cfo_hz),
        "timing_offset_samples": int(timing),
        "rx_timing_offsets_samples": individual_timing,
        "timing_disagreement_samples": timing_disagreement,
        "normalized_correlation_peak": float(correlation_peak),
        "desired_gain_linear": [float(abs(value)) for value in gains],
        "desired_gain_phase_rad": [float(np.angle(value)) for value in gains],
        "amplitude_imbalance_db_rx0_over_rx1": float(gain_imbalance_db),
        "phase_difference_rad_rx0_minus_rx1": phase_difference_rad,
        "phase_difference_deg_rx0_minus_rx1": math.degrees(phase_difference_rad),
        "sample_evm_percent": [float(100.0 * value) for value in sample_evm],
        "evm_percent": [float(value) for value in evm_values],
        "mer_db": [float(value) for value in mer_values],
        "symbol_error_count": symbol_errors,
        "bit_error_count": bit_errors,
        "ser": [float(value) for value in ser_values],
        "ber": [float(value) for value in ber_values],
        "clipping_fraction": [float(value) for value in clipping_fraction],
        "cross_channel_coherence": coherence,
        "blocker_offset_hz": blocker_offset_hz,
        "blocker_power_db": blocker_power_db,
        "blocker_measurement": blocker_measurement,
        "blocker_detected": (
            None if blocker_measurement is None else blocker_measurement["detected"]
        ),
        "measured_blocker_offset_hz": (
            None
            if blocker_measurement is None
            else blocker_measurement["measured_signed_offset_hz"]
        ),
        "measured_blocker_power_db": (
            None
            if blocker_measurement is None
            else blocker_measurement["measured_relative_power_db"]
        ),
        "blocker_offset_error_hz": (
            None
            if blocker_measurement is None
            else blocker_measurement["offset_error_hz"]
        ),
        "blocker_power_error_db": (
            None
            if blocker_measurement is None
            else blocker_measurement["relative_power_error_db"]
        ),
        "blocker_correlation": (
            None
            if blocker_measurement is None
            else blocker_measurement["correlation_per_rx"]
        ),
        "quality_valid": not reasons,
        "quality_reasons": reasons,
    }


def quantify_blocker_degradation(
    baseline: dict[str, Any], blocked: dict[str, Any]
) -> dict[str, Any]:
    """Compare one blocker capture with its desired-only baseline."""

    if not isinstance(baseline, dict) or not isinstance(blocked, dict):
        raise TypeError("baseline and blocked results must be dictionaries")
    required = (
        "schema",
        "reference_id",
        "evm_percent",
        "mer_db",
        "ser",
        "ber",
        "desired_gain_linear",
        "blocker_offset_hz",
        "blocker_power_db",
    )
    for label, result in (("baseline", baseline), ("blocked", blocked)):
        missing = [name for name in required if name not in result]
        if missing:
            raise ValueError(f"{label} result lacks {missing}")
        if result["schema"] != "plutosdr-fw.modulated-quality.v1":
            raise ValueError(f"{label} result has an unsupported schema")
        for name in ("evm_percent", "mer_db", "ser", "ber", "desired_gain_linear"):
            values = result[name]
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError(f"{label} {name} must contain RX0 and RX1")
            if not all(math.isfinite(float(value)) for value in values):
                raise ValueError(f"{label} {name} contains non-finite values")
    if baseline["reference_id"] != blocked["reference_id"]:
        raise ValueError("baseline and blocked reference IDs differ")
    if (
        baseline["blocker_offset_hz"] is not None
        or baseline["blocker_power_db"] is not None
    ):
        raise ValueError("baseline result must not identify a blocker")
    if blocked["blocker_offset_hz"] is None or blocked["blocker_power_db"] is None:
        raise ValueError("blocked result must identify blocker offset and power")

    offset = _finite_number("blocked blocker_offset_hz", blocked["blocker_offset_hz"])
    power = _finite_number("blocked blocker_power_db", blocked["blocker_power_db"])
    rows = []
    for channel in range(2):
        baseline_gain = float(baseline["desired_gain_linear"][channel])
        blocked_gain = float(blocked["desired_gain_linear"][channel])
        if baseline_gain <= 0.0 or blocked_gain <= 0.0:
            raise ValueError("desired gains must be positive")
        rows.append(
            {
                "channel": f"rx{channel}",
                "evm_increase_percentage_points": float(
                    blocked["evm_percent"][channel] - baseline["evm_percent"][channel]
                ),
                "mer_loss_db": float(
                    baseline["mer_db"][channel] - blocked["mer_db"][channel]
                ),
                "ser_increase": float(
                    blocked["ser"][channel] - baseline["ser"][channel]
                ),
                "ber_increase": float(
                    blocked["ber"][channel] - baseline["ber"][channel]
                ),
                "desired_gain_change_db": float(
                    20.0 * math.log10(blocked_gain / baseline_gain)
                ),
            }
        )
    return {
        "schema": "plutosdr-fw.modulated-blocker-degradation.v1",
        "reference_id": baseline["reference_id"],
        "blocker_offset_hz": offset,
        "blocker_power_db": power,
        "channels": rows,
        "worst_evm_increase_percentage_points": max(
            row["evm_increase_percentage_points"] for row in rows
        ),
        "worst_mer_loss_db": max(row["mer_loss_db"] for row in rows),
        "blocked_quality_valid": bool(blocked.get("quality_valid", False)),
    }


def summarize_blocker_sweep(
    baseline: dict[str, Any], blocked_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return blocker degradation rows ordered by offset magnitude and power."""

    if not isinstance(blocked_results, list) or not blocked_results:
        raise ValueError("blocked_results must be a nonempty list")
    rows = [quantify_blocker_degradation(baseline, item) for item in blocked_results]
    keys = [
        (float(row["blocker_offset_hz"]), float(row["blocker_power_db"]))
        for row in rows
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("blocker sweep contains duplicate offset/power points")
    rows.sort(
        key=lambda row: (
            abs(float(row["blocker_offset_hz"])),
            float(row["blocker_offset_hz"]),
            float(row["blocker_power_db"]),
        )
    )
    return {
        "schema": "plutosdr-fw.modulated-blocker-sweep.v1",
        "reference_id": baseline["reference_id"],
        "point_count": len(rows),
        "points": rows,
    }
