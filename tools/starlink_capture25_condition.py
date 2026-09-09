"""Bounded offline 25 -> 15 MS/s replay conditioner, not receiver firmware.

Positive downmix multiplies by exp(-j*2*pi*f*t) at the absolute source index.
The centered FIR is noncausal offline processing. Only complete-support output
centers are returned; no padded boundary samples are admitted. Its measured
passband is <=6.5 MHz, not the complete 15 MHz Nyquist interval. This changes
the captured spectrum and cannot restore analog bandwidth or missing samples.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from numbers import Real

import numpy as np

INPUT_RATE_HZ = 25_000_000
OUTPUT_RATE_HZ = 15_000_000
UPSAMPLE = 3
DOWNSAMPLE = 5
FILTER_RATE_HZ = INPUT_RATE_HZ * UPSAMPLE
FILTER_TAPS = 481
FILTER_HALF = (FILTER_TAPS - 1) // 2
FILTER_CUTOFF_HZ = 7_000_000
FILTER_BETA = 8.6
MAX_INPUT_SAMPLES = 8_100_000
RESPONSE_FFT_LENGTH = 262_144


@lru_cache(maxsize=1)
def coefficients() -> np.ndarray:
    """Declared odd Kaiser-windowed sinc; sum3 compensates zero insertion."""
    offsets = np.arange(FILTER_TAPS, dtype=np.float64) - FILTER_HALF
    normalized = 2 * FILTER_CUTOFF_HZ / FILTER_RATE_HZ
    result = normalized * np.sinc(normalized * offsets) * np.kaiser(FILTER_TAPS, FILTER_BETA)
    result *= UPSAMPLE / result.sum()
    result.flags.writeable = False
    return result


@lru_cache(maxsize=1)
def _filter_metadata() -> dict:
    values = coefficients()
    frequencies = np.fft.rfftfreq(RESPONSE_FFT_LENGTH, d=1 / FILTER_RATE_HZ)
    response = np.abs(np.fft.rfft(values, RESPONSE_FFT_LENGTH)) / UPSAMPLE
    passband = response[frequencies <= 6_500_000]
    stopband = response[frequencies >= 7_500_000]
    return {
        "taps": FILTER_TAPS, "upsampled_rate_hz": FILTER_RATE_HZ,
        "window": "kaiser", "beta": FILTER_BETA, "cutoff_hz": FILTER_CUTOFF_HZ,
        "coefficient_sha256": hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest(),
        "coefficient_encoding": "little-endian float64, ascending causal FIR tap index",
        "coefficient_dc_sum": float(values.sum()),
        "polyphase_dc_sums": [float(values[phase::3].sum()) for phase in range(3)],
        "response_fft_length": RESPONSE_FFT_LENGTH,
        "response_grid_spacing_hz": FILTER_RATE_HZ / RESPONSE_FFT_LENGTH,
        "response_normalization": "magnitude / 3 (zero-insertion gain)",
        "measured_passband_stop_hz": 6_500_000,
        "measured_passband_max_absolute_db": float(np.max(np.abs(20 * np.log10(passband)))),
        "measured_stopband_start_hz": 7_500_000,
        "measured_stopband_max_db": float(20 * np.log10(np.max(stopband))),
        "response_extrema_are_sampled_not_continuous_bounds": True,
        "centered_offline": True, "causal_group_delay_high_rate_samples": FILTER_HALF,
        "causal_group_delay_source_samples": FILTER_HALF // 3,
        "returned_center_delay_source_samples": 0,
        "boundary_policy": "discard every output lacking full original-input FIR support",
        "full_15mhz_bandwidth_preserved": False,
    }


def _downmix_fraction(value: Real) -> Fraction:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError("downmix_hz must be a finite real frequency")
    if not math.isfinite(float(value)) or abs(value) >= INPUT_RATE_HZ / 2:
        raise ValueError("downmix_hz must lie strictly inside source Nyquist")
    cycles = Fraction(str(float(value))) / INPUT_RATE_HZ
    # Remainders below2**53 convert exactly to binary64 before angle formation.
    if cycles.denominator > (1 << 53):
        raise ValueError("downmix rational phase period exceeds exact integer phase bound")
    return cycles


def _absolute_downmix(values: np.ndarray, first_index: int, cycles: Fraction) -> np.ndarray:
    numerator, denominator = cycles.numerator, cycles.denominator
    sign = -1 if numerator < 0 else 1
    numerator = abs(numerator)
    output = np.empty(len(values), dtype=np.complex128)
    # Exact modular integer phase avoids large-epoch float multiplication and
    # makes a sample's oscillator phase independent of the requested window.
    block_size = 2048  # period<=2**53 and |cycles|<1/2 keep products below2**64.
    for begin in range(0, len(values), block_size):
        end = min(begin + block_size, len(values))
        phase_start = ((first_index + begin) * numerator) % denominator
        phases = (np.arange(end - begin, dtype=np.uint64) * np.uint64(numerator)
                  + np.uint64(phase_start)) % np.uint64(denominator)
        angle = -sign * (2 * np.pi / denominator) * phases.astype(np.float64)
        output[begin:end] = values[begin:end] * np.exp(1j * angle)
    return output


@dataclass(frozen=True, slots=True)
class ConditionedCapture25:
    samples_iq: np.ndarray
    first_canonical_index: int
    clipped_components: int
    source_input_start_index: int
    source_input_stop_index: int
    source_dependency_start_index: int
    source_dependency_stop_index: int
    downmix_hz: float
    downmix_cycles_numerator: int
    downmix_cycles_denominator: int

    def metadata(self) -> dict:
        count = len(self.samples_iq)
        info = _filter_metadata()
        return {
            "schema": "starlink-capture25-condition-v1",
            "input_rate_hz": INPUT_RATE_HZ, "output_rate_hz": OUTPUT_RATE_HZ,
            "upsample": UPSAMPLE, "downsample": DOWNSAMPLE,
            "first_canonical_index": self.first_canonical_index,
            "canonical_stop_index": self.first_canonical_index + count,
            "output_sample_count": count,
            "source_input_start_index": self.source_input_start_index,
            "source_input_stop_index": self.source_input_stop_index,
            "source_dependency_start_index": self.source_dependency_start_index,
            "source_dependency_stop_index": self.source_dependency_stop_index,
            "first_source_center_numerator": 5 * self.first_canonical_index,
            "last_source_center_numerator": 5 * (self.first_canonical_index + count - 1),
            "source_center_denominator": 3,
            "downmix_hz": self.downmix_hz,
            "downmix_cycles_per_source_sample": [self.downmix_cycles_numerator,
                                                  self.downmix_cycles_denominator],
            "downmix_sign": "positive multiplies exp(-j*2*pi*f*absolute_source_index/25e6)",
            "quantization": "componentwise ties-to-even, then saturate to signed CI16",
            "clipped_components": self.clipped_components,
            "implicit_amplitude_normalization": False,
            "filter": {**info, "polyphase_dc_sums": list(info["polyphase_dc_sums"])},
            "adc_rf_continuity_clock_or_fpga_timing_qualified": False,
        }


def condition_capture25(
    samples_iq: np.ndarray, *, first_index: int, downmix_hz: Real = 5_000_000.0,
) -> ConditionedCapture25:
    """Return supported CI16 centers at the exact3/5 absolute-index lattice.

    At returned index k, source center is5*k/3 (possibly fractional). The
    source first index must be divisible by5 so the canonical origin is an
    integer. Callers must separately establish capture continuity and RF/LO
    provenance; selecting an array does not establish either.
    """
    if isinstance(first_index, bool) or not isinstance(first_index, int) or first_index < 0:
        raise ValueError("first_index must be a nonnegative integer")
    if first_index % 5:
        raise ValueError("first_index must be a multiple of5")
    raw = np.asarray(samples_iq)
    if raw.ndim != 2 or raw.shape[1] != 2 or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError("samples_iq must have integer CI16 shape (N,2)")
    if not 1 <= len(raw) <= MAX_INPUT_SAMPLES:
        raise ValueError("input sample count exceeds the bounded conditioner contract")
    if first_index + len(raw) > 1 << 64:
        raise ValueError("source interval must fit the uint64 counter")
    if np.any(raw < -32768) or np.any(raw > 32767):
        raise ValueError("samples_iq must fit signed CI16")
    cycles = _downmix_fraction(downmix_hz)
    first_local = (FILTER_HALF + 4) // 5
    last_local = (3 * (len(raw) - 1) - FILTER_HALF) // 5
    if last_local < first_local:
        raise ValueError("input has no complete-support output centers")
    source = raw[:, 0].astype(np.float64) + 1j * raw[:, 1].astype(np.float64)
    mixed = _absolute_downmix(source, first_index, cycles)
    local_indexes = np.arange(first_local, last_local + 1, dtype=np.int64)
    result = np.empty(len(local_indexes), dtype=np.complex128)
    bank = coefficients()
    for residue in range(3):
        selected = local_indexes % 3 == residue
        indexes = local_indexes[selected]
        phase = (FILTER_HALF + 5 * residue) % 3
        polyphase = bank[phase::3]
        # h[half+5*m-3*n] becomes one ordinary convolution for each m%3.
        convolution = np.convolve(mixed, polyphase, mode="valid")
        positions = 5 * ((indexes - residue) // 3) + (FILTER_HALF + 5 * residue) // 3
        positions -= len(polyphase) - 1
        if len(positions) and (positions[0] < 0 or positions[-1] >= len(convolution)):
            raise RuntimeError("internal complete-support polyphase mapping failed")
        result[selected] = convolution[positions]
    rounded = np.rint(np.column_stack((result.real, result.imag)))
    clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    quantized = np.clip(rounded, -32768, 32767).astype(np.int16)
    quantized.flags.writeable = False
    return ConditionedCapture25(
        samples_iq=quantized, first_canonical_index=3 * first_index // 5 + first_local,
        clipped_components=clipped, source_input_start_index=first_index,
        source_input_stop_index=first_index + len(raw),
        source_dependency_start_index=first_index + (5 * first_local - FILTER_HALF + 2) // 3,
        source_dependency_stop_index=first_index + (5 * last_local + FILTER_HALF) // 3 + 1,
        downmix_hz=float(downmix_hz), downmix_cycles_numerator=cycles.numerator,
        downmix_cycles_denominator=cycles.denominator,
    )
