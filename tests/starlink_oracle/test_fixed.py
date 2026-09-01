from __future__ import annotations

import numpy as np
import pytest

from tests.starlink_oracle import (
    ACCUMULATOR_BITS,
    ACCUMULATOR_MAX,
    COEFFICIENT_FRACTION_BITS,
    COMPONENT_BITS,
    FIXED_CORRELATOR_SCHEMA,
    fixed_correlate_ci16,
    meets_rational_power_threshold,
    projected_pss,
    quantize_q15,
)


def test_q15_quantizer_declares_ties_to_even_and_component_saturation() -> None:
    lsb = 1.0 / (1 << COEFFICIENT_FRACTION_BITS)
    values = np.asarray(
        (
            complex(2.0, -2.0),
            complex(0.5 * lsb, 1.5 * lsb),
            complex(-0.5 * lsb, -1.5 * lsb),
        )
    )

    result = quantize_q15(values)

    assert COMPONENT_BITS == 16
    assert result.dtype == np.dtype(np.int16)
    np.testing.assert_array_equal(
        result,
        np.asarray(((32767, -32768), (0, 2), (0, -2)), dtype=np.int16),
    )


def test_fixed_correlator_zero_and_full_scale_vectors_are_exact() -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, "lower"))
    zero = fixed_correlate_ci16(np.zeros_like(coefficients), coefficients)

    assert zero.schema == FIXED_CORRELATOR_SCHEMA
    assert ACCUMULATOR_BITS == 48
    assert (zero.real, zero.imag, zero.sample_energy) == (0, 0, 0)
    assert zero.coefficient_energy > 0
    assert not zero.saturated

    full_scale = fixed_correlate_ci16(
        np.asarray(((32767, -32768),), dtype=np.int16),
        np.asarray(((32767, 32767),), dtype=np.int16),
    )
    assert full_scale.real == -32_767
    assert full_scale.imag == -2_147_385_345
    assert full_scale.sample_energy == 2_147_418_113
    assert full_scale.coefficient_energy == 2_147_352_578
    assert full_scale.correlation_power.bit_length() <= 96
    assert not full_scale.saturated


def test_fixed_correlator_saturates_and_counts_48_bit_overflow() -> None:
    # Each real/energy tap is exactly 2**31. At 65,536 taps the positive
    # accumulator would become 2**47, one beyond signed 48-bit full scale.
    full_negative = np.full((65_537, 2), -32_768, dtype=np.int16)

    result = fixed_correlate_ci16(full_negative, full_negative)

    assert result.real == ACCUMULATOR_MAX
    assert result.imag == 0
    assert result.sample_energy == ACCUMULATOR_MAX
    assert result.coefficient_energy == ACCUMULATOR_MAX
    assert result.saturated
    assert result.saturation_events == 6


def test_rational_threshold_comparison_uses_exact_cross_products() -> None:
    vector = np.asarray(((1000, -2000), (3000, 4000), (-5000, 6000)), dtype=np.int16)
    result = fixed_correlate_ci16(vector, vector)

    assert result.real == result.sample_energy == result.coefficient_energy
    assert result.imag == 0
    assert meets_rational_power_threshold(
        result,
        threshold_numerator=1,
        threshold_denominator=1,
    )
    assert not meets_rational_power_threshold(
        result,
        threshold_numerator=1001,
        threshold_denominator=1000,
    )

    zero = fixed_correlate_ci16(np.zeros((1, 2), dtype=np.int16), vector[:1])
    with pytest.raises(ValueError, match="positive.*energy"):
        meets_rational_power_threshold(
            zero,
            threshold_numerator=1,
            threshold_denominator=2,
        )
