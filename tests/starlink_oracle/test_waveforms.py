from __future__ import annotations

import numpy as np
import pytest

from tests.starlink_oracle import (
    NUMEROLOGIES,
    PROJECTED_PSS_SHA256,
    PROJECTED_SSS_SHA256,
    PSS_NATIVE_SHA256,
    SSS_FREQUENCY_SHA256,
    SSS_NATIVE_SHA256,
    complex64_sha256,
    numerology_for_rate,
    projected_pss,
    projected_sss,
    pss_native_time_samples,
    sss_frequency_symbols,
    sss_native_time_samples,
)


def test_declared_15_30_60_numerology_closes_exactly() -> None:
    expected = {
        15_000_000: (64, 2, 66, 20_000, 112_382_812.5),
        30_000_000: (128, 4, 132, 40_000, 104_882_812.5),
        60_000_000: (256, 8, 264, 80_000, 89_882_812.5),
    }

    assert set(NUMEROLOGIES) == set(expected)
    for rate, values in expected.items():
        item = numerology_for_rate(rate)
        assert (
            item.useful_samples,
            item.cyclic_prefix_samples,
            item.symbol_samples,
            item.frame_samples,
            item.edge_center_magnitude_hz,
        ) == values
        assert item.useful_samples + item.cyclic_prefix_samples == item.symbol_samples
        assert item.useful_samples * 240_000_000 == rate * 1024
        assert item.cyclic_prefix_samples * 240_000_000 == rate * 32
        assert item.frame_samples * 750 == rate
        assert item.edge_center_offset_hz("lower") == -values[-1]
        assert item.edge_center_offset_hz("upper") == values[-1]


def test_native_pss_and_sss_constructions_are_frozen_and_immutable() -> None:
    pss = pss_native_time_samples()
    sss_bins = sss_frequency_symbols()
    sss = sss_native_time_samples()

    assert pss.shape == sss.shape == (1056,)
    assert pss.dtype == sss.dtype == np.dtype(np.complex64)
    assert not pss.flags.writeable and not sss.flags.writeable
    assert complex64_sha256(pss) == PSS_NATIVE_SHA256
    assert complex64_sha256(sss) == SSS_NATIVE_SHA256
    np.testing.assert_allclose(np.abs(pss), 1.0, atol=1e-7)
    np.testing.assert_array_equal(pss[:32], -pss[-32:])
    np.testing.assert_array_equal(sss[:32], sss[-32:])

    assert sss_bins.shape == (1024,)
    assert sss_bins.dtype == np.dtype(np.complex128)
    assert not sss_bins.flags.writeable
    assert complex64_sha256(sss_bins) == SSS_FREQUENCY_SHA256
    assert np.count_nonzero(sss_bins) == 1020
    np.testing.assert_array_equal(sss_bins[[0, 1, 1022, 1023]], 0j)
    assert set(sss_bins) == {0j, -1 + 0j, -1j, 1j, 1 + 0j}


@pytest.mark.parametrize("sample_rate_hz", (15_000_000, 30_000_000, 60_000_000))
@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_edge_pss_and_sss_projections_have_frozen_complex64_identity(
    sample_rate_hz: int,
    edge: str,
) -> None:
    numerology = numerology_for_rate(sample_rate_hz)
    pss = projected_pss(sample_rate_hz, edge)
    sss = projected_sss(sample_rate_hz, edge)

    assert pss.shape == sss.shape == (numerology.symbol_samples,)
    assert pss.dtype == sss.dtype == np.dtype(np.complex64)
    assert not pss.flags.writeable and not sss.flags.writeable
    assert np.linalg.norm(pss) == pytest.approx(1.0, abs=1e-7)
    assert np.linalg.norm(sss) == pytest.approx(1.0, abs=1e-7)
    assert complex64_sha256(pss) == PROJECTED_PSS_SHA256[(sample_rate_hz, edge)]
    assert complex64_sha256(sss) == PROJECTED_SSS_SHA256[(sample_rate_hz, edge)]


def test_oracle_rejects_undeclared_rates_and_edges() -> None:
    with pytest.raises(ValueError, match="15, 30, or 60"):
        numerology_for_rate(20_000_000)
    with pytest.raises(TypeError, match="integer"):
        numerology_for_rate(15_000_000.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="lower.*upper"):
        projected_pss(15_000_000, "center")
