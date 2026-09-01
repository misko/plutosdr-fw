"""Declared bit-exact CI16/Q1.15 complex correlator model.

Contract ``starlink-fixed-correlator-v1``:

* input samples are raw signed CI16 components;
* coefficients are signed 16-bit values with 15 fractional bits (Q1.15);
* float coefficient conversion is ``clip(rint(x * 32768), -32768, 32767)``;
* ``rint`` is IEEE round-to-nearest, ties-to-even;
* each complex tap is formed exactly, with no product rounding;
* correlation is ``sum(x * conj(h))`` in ascending tap order;
* correlation and both energy accumulators saturate after each complete tap to
  signed 48-bit range; and
* correlation power, energy product, and rational-threshold cross products are
  evaluated as unsigned 96-bit and unsigned 128-bit quantities respectively.

No NCO is part of v1.  Callers must supply zero-CFO or separately pre-corrected
CI16 samples.  Python integers implement the declared wide arithmetic without
host-language overflow.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FIXED_CORRELATOR_SCHEMA = "starlink-fixed-correlator-v1"
COMPONENT_BITS = 16
COEFFICIENT_FRACTION_BITS = 15
ACCUMULATOR_BITS = 48
POWER_BITS = 96
THRESHOLD_CROSS_PRODUCT_BITS = 128
COMPONENT_MIN = -(1 << (COMPONENT_BITS - 1))
COMPONENT_MAX = (1 << (COMPONENT_BITS - 1)) - 1
ACCUMULATOR_MIN = -(1 << (ACCUMULATOR_BITS - 1))
ACCUMULATOR_MAX = (1 << (ACCUMULATOR_BITS - 1)) - 1
THRESHOLD_FACTOR_MAX = (1 << 32) - 1


@dataclass(frozen=True, slots=True)
class FixedCorrelationResult:
    """Bit-exact raw accumulators and saturation accounting."""

    real: int
    imag: int
    sample_energy: int
    coefficient_energy: int
    tap_count: int
    saturation_events: int
    schema: str = FIXED_CORRELATOR_SCHEMA

    @property
    def correlation_power(self) -> int:
        return self.real * self.real + self.imag * self.imag

    @property
    def normalization_product(self) -> int:
        return self.sample_energy * self.coefficient_energy

    @property
    def saturated(self) -> bool:
        return self.saturation_events > 0


def quantize_q15(values: npt.ArrayLike) -> npt.NDArray[np.int16]:
    """Quantize complex floats to an ``(N, 2)`` CI16/Q1.15 matrix."""

    samples = np.asarray(values, dtype=np.complex128)
    if samples.ndim != 1 or not np.all(np.isfinite(samples)):
        raise ValueError("Q1.15 input must be one-dimensional and finite")
    scaled = np.column_stack((samples.real, samples.imag)) * (
        1 << COEFFICIENT_FRACTION_BITS
    )
    rounded = np.rint(scaled)
    clipped = np.clip(rounded, COMPONENT_MIN, COMPONENT_MAX)
    return np.asarray(clipped, dtype=np.int16)


def fixed_correlate_ci16(
    samples_iq: npt.ArrayLike,
    coefficients_iq: npt.ArrayLike,
) -> FixedCorrelationResult:
    """Return the v1 saturating direct correlation and energy accumulators."""

    samples = _ci16_matrix(samples_iq, "samples_iq")
    coefficients = _ci16_matrix(coefficients_iq, "coefficients_iq")
    if samples.shape != coefficients.shape:
        raise ValueError("sample and coefficient matrices must have identical shape")
    if not samples.shape[0]:
        raise ValueError("fixed correlation requires at least one tap")

    real = imag = sample_energy = coefficient_energy = 0
    saturation_events = 0
    for sample, coefficient in zip(samples, coefficients, strict=True):
        sample_i, sample_q = int(sample[0]), int(sample[1])
        coefficient_i, coefficient_q = int(coefficient[0]), int(coefficient[1])
        real_tap = sample_i * coefficient_i + sample_q * coefficient_q
        imag_tap = sample_q * coefficient_i - sample_i * coefficient_q
        sample_energy_tap = sample_i * sample_i + sample_q * sample_q
        coefficient_energy_tap = (
            coefficient_i * coefficient_i + coefficient_q * coefficient_q
        )
        real, event = _saturating_accumulate(real, real_tap)
        saturation_events += event
        imag, event = _saturating_accumulate(imag, imag_tap)
        saturation_events += event
        sample_energy, event = _saturating_accumulate(sample_energy, sample_energy_tap)
        saturation_events += event
        coefficient_energy, event = _saturating_accumulate(
            coefficient_energy, coefficient_energy_tap
        )
        saturation_events += event
    return FixedCorrelationResult(
        real=real,
        imag=imag,
        sample_energy=sample_energy,
        coefficient_energy=coefficient_energy,
        tap_count=samples.shape[0],
        saturation_events=saturation_events,
    )


def meets_rational_power_threshold(
    result: FixedCorrelationResult,
    *,
    threshold_numerator: int,
    threshold_denominator: int,
) -> bool:
    """Compare a normalized-power threshold without division or float math."""

    for name, value in (
        ("threshold_numerator", threshold_numerator),
        ("threshold_denominator", threshold_denominator),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0 or value > THRESHOLD_FACTOR_MAX:
            raise ValueError(f"{name} must fit unsigned 32 bits")
    if threshold_denominator == 0:
        raise ValueError("threshold_denominator must be positive")
    if result.normalization_product == 0:
        raise ValueError(
            "normalized threshold requires positive sample and coefficient energy"
        )
    left = threshold_denominator * result.correlation_power
    right = threshold_numerator * result.normalization_product
    if left.bit_length() > THRESHOLD_CROSS_PRODUCT_BITS:
        raise OverflowError("correlation threshold cross product exceeds 128 bits")
    if right.bit_length() > THRESHOLD_CROSS_PRODUCT_BITS:
        raise OverflowError("energy threshold cross product exceeds 128 bits")
    return left >= right


def _ci16_matrix(values: npt.ArrayLike, name: str) -> npt.NDArray[np.int64]:
    raw = np.asarray(values)
    if (
        raw.ndim != 2
        or raw.shape[1:] != (2,)
        or not np.issubdtype(raw.dtype, np.integer)
    ):
        raise ValueError(f"{name} must be an integer matrix with shape (N, 2)")
    converted = np.asarray(raw, dtype=np.int64)
    if np.any(converted < COMPONENT_MIN) or np.any(converted > COMPONENT_MAX):
        raise ValueError(f"{name} components must fit signed 16 bits")
    return converted


def _saturating_accumulate(accumulator: int, addend: int) -> tuple[int, int]:
    total = accumulator + addend
    if total > ACCUMULATOR_MAX:
        return ACCUMULATOR_MAX, 1
    if total < ACCUMULATOR_MIN:
        return ACCUMULATOR_MIN, 1
    return total, 0
