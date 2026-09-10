"""Independent arithmetic and capacity checks for the isolated alternative."""

import numpy as np

from tests.starlink_oracle.acquisition import direct_fixed_match_scores
from tests.starlink_oracle.fixed import fixed_correlate_ci16
from tools.starlink_direct_coarse_study import GATES, compare, direct_scores, schedule


def test_integer_products_match_existing_saturating_oracle():
    rng = np.random.default_rng(66)
    for endpoint in (False, True):
        x = rng.integers(-32768, 32768, (131, 2), dtype=np.int16)
        h = rng.integers(-32768, 32768, (66, 2), dtype=np.int16)
        if endpoint:
            x[:] = [-32768, 32767]
            h[:] = [32767, -32768]
        scores, sums = direct_scores(x, h)
        assert np.array_equal(scores, direct_fixed_match_scores(x, h).scores)
        for start in (0, 32, 65):
            golden = fixed_correlate_ci16(x[start : start + 66], h)
            assert tuple(sums[start]) == (golden.real, golden.imag)
            assert golden.saturation_events == 0


def test_five_lanes_and_excessive_stalls_expire_not_silently_pass():
    assert schedule(200_000_000, 5, count=20_000)["expired_jobs"] > 0
    assert schedule(200_000_000, 6, count=20_000)["expired_jobs"] == 0
    adequate = schedule(200_000_000, 6, count=20_000, stall_every=100, stall_length=200)
    overload = schedule(200_000_000, 6, count=20_000, stall_every=100, stall_length=400)
    assert adequate["bounded_for_test"] and adequate["max_backlog_samples"] == 15
    assert not overload["bounded_for_test"] and overload["expired_jobs"] > 0


def test_frozen_comparison_gate_retains_every_outlier_and_peak_change():
    assert GATES == {"max_score_delta": 1, "peak_index_delta": 0}
    result = compare(np.array([9, 8, 0, 0]), np.array([8, 10, 3, 0]))
    assert not result["comparison_pass"]
    assert result["peak_index_delta"] == 1
    assert result["beyond_tolerance"] == [
        {"index": 1, "reference": 8, "candidate": 10},
        {"index": 2, "reference": 0, "candidate": 3},
    ]
