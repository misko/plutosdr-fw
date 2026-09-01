from __future__ import annotations

import numpy as np
import pytest

from tests.starlink_oracle import (
    deterministic_float_search,
    numerology_for_rate,
    projected_pss,
    projected_sss,
)


def test_direct_float_search_recovers_pss_then_next_symbol_sss() -> None:
    sample_rate_hz = 15_000_000
    edge = "lower"
    numerology = numerology_for_rate(sample_rate_hz)
    pss = np.asarray(projected_pss(sample_rate_hz, edge), dtype=np.complex128)
    sss = np.asarray(projected_sss(sample_rate_hz, edge), dtype=np.complex128)
    pss_start = 47
    sss_start = pss_start + numerology.symbol_samples
    cfo_hz = -187_500.0
    values = np.zeros(sss_start + numerology.symbol_samples + 31, dtype=np.complex128)
    local_time_s = np.arange(numerology.symbol_samples, dtype=float) / sample_rate_hz
    rotation = np.exp(2j * np.pi * cfo_hz * local_time_s)
    values[pss_start : pss_start + numerology.symbol_samples] = pss * rotation
    values[sss_start : sss_start + numerology.symbol_samples] = 0.7j * sss * rotation

    bank = (0.0, 187_500.0, cfo_hz)
    pss_result = deterministic_float_search(
        values,
        pss,
        sample_rate_hz,
        frequency_offsets_hz=bank,
    )
    sss_result = deterministic_float_search(
        values,
        sss,
        sample_rate_hz,
        frequency_offsets_hz=bank,
        start_sample=pss_result.sample_index + numerology.symbol_samples,
    )

    assert pss_result.sample_index == pss_start
    assert pss_result.frequency_offset_hz == cfo_hz
    assert pss_result.normalized_match_power == pytest.approx(1.0, abs=1e-14)
    assert sss_result.sample_index == sss_start
    assert sss_result.frequency_offset_hz == cfo_hz
    assert sss_result.normalized_match_power == pytest.approx(1.0, abs=1e-14)


def test_float_search_is_repeatable_and_has_declared_tie_breaking() -> None:
    samples = np.zeros(20, dtype=np.complex64)
    template = np.ones(4, dtype=np.complex64)
    arguments = {
        "frequency_offsets_hz": (100.0, 0.0, -100.0),
        "start_sample": 3,
        "stop_sample": 9,
    }

    first = deterministic_float_search(samples, template, 15_000_000, **arguments)
    second = deterministic_float_search(samples, template, 15_000_000, **arguments)

    assert first == second
    assert first.sample_index == 3
    assert first.frequency_offset_hz == -100.0
    assert first.normalized_match_power == 0.0
    assert first.evaluated_hypotheses == 6 * 3


def test_float_search_rejects_invalid_domains() -> None:
    with pytest.raises(ValueError, match="longer"):
        deterministic_float_search(np.ones(3), np.ones(4), 15_000_000)
    with pytest.raises(ValueError, match="unique"):
        deterministic_float_search(
            np.ones(8),
            np.ones(4),
            15_000_000,
            frequency_offsets_hz=(0.0, 0.0),
        )
    with pytest.raises(ValueError, match="Nyquist"):
        deterministic_float_search(
            np.ones(8),
            np.ones(4),
            15_000_000,
            frequency_offsets_hz=(7_500_000.0,),
        )
