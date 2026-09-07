from __future__ import annotations

import pytest

from scripts.starlink_pss_iio_cabled_v1 import (
    RATE_PROFILES,
    _analyze,
    _future_center,
)


@pytest.mark.parametrize("rate_msps", [30, 60])
def test_rate_profile_scales_every_source_sample_quantity(rate_msps: int) -> None:
    profile = RATE_PROFILES[rate_msps]

    assert profile.rate_hz == rate_msps * 1_000_000
    assert profile.period_samples == profile.rate_hz // 750
    assert profile.aperture_samples == rate_msps * 2
    assert profile.host_lead_samples == profile.rate_hz // 5
    assert profile.bandwidth_hz == 20_000_000
    assert f"pss{rate_msps}" in profile.coefficient_path.name
    assert f"pss{rate_msps}" in profile.waveform_path.name
    assert profile.waveform_bytes == profile.period_samples * 4
    assert profile.request_prefix & 0x80000000


def test_future_center_honors_rate_specific_host_lead() -> None:
    profile = RATE_PROFILES[30]
    anchor = 8_192
    current = 1_000_000

    center = _future_center(
        anchor,
        current,
        profile.period_samples,
        host_lead_samples=profile.host_lead_samples,
    )

    assert center >= current + profile.host_lead_samples
    assert (center - anchor) % profile.period_samples == 0
    assert center - profile.period_samples < current + profile.host_lead_samples


def test_fine_analysis_uses_selected_rate_period_and_aperture() -> None:
    profile = RATE_PROFILES[30]
    results = [
        {
            "ordinal": ordinal,
            "winner_timestamp": 5_000_000 + ordinal * profile.period_samples,
            "winner_lag": ordinal % 3 - 1,
            "correlation_real": 2,
            "correlation_imag": 0,
            "sample_energy": 2,
            "coefficient_energy": 2,
        }
        for ordinal in range(16)
    ]

    analysis = _analyze(
        results,
        period_samples=profile.period_samples,
        aperture_samples=profile.aperture_samples,
    )

    assert analysis["fitted_period_source_samples"] == profile.period_samples
    assert analysis["relative_clock_error_ppm"] == 0
    assert analysis["residual_max_abs_source_samples"] == 0
    assert analysis["aperture_edge_hits"] == 0
    assert analysis["normalized_score_median"] == 1
