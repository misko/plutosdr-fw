"""Cohort evidence cannot manufacture diversity, hide extras or duplicate IQ."""
from copy import deepcopy

import pytest

from tools.starlink_glrt_local_cohort import POLICY, combine


def report(identity, episodes, positives=20, recovered=None, extras=()):
    return {"schema": "gla1-same-window-comparison/v1", "status": "complete", "policy": POLICY,
            "capture_sha256": {"iq.ci16": identity}, "host_supported_windows": positives,
            "recovered_windows": positives if recovered is None else recovered,
            "host_positive_episodes": episodes, "comparable_windows": 2000,
            "fpga_additional_or_mismatched": list(extras), "host_windows_without_fpga_completion": []}


def test_unknown_capture_gap_cannot_supply_a_third_episode():
    result = combine([report("a", 2), report("b", 1)])
    assert result["positive_episode_lower_bound"] == 2
    assert result["detection_gate"] == "inconclusive"
    assert not result["inter_capture_gaps_assumed"]


def test_two_two_episode_runs_have_three_even_if_boundary_groups_merge():
    result = combine([report("a", 2), report("b", 2)])
    assert result["positive_episode_lower_bound"] == 3 and result["detection_gate"] == "pass"
    assert not result["live_detector_qualified"]


def test_no_signal_run_does_not_change_positive_episode_bound():
    result = combine([report("a", 2), report("b", 0, 0), report("c", 2)])
    assert result["positive_episode_lower_bound"] == 3
    assert result["host_supported_windows"] == result["recovered_windows"] == 40


def test_reviewed_elsewhere_extras_are_still_visible_and_need_explicit_review():
    extra = {"sample_offset": 250000, "fpga_supported": True, "host_supported": False}
    result = combine([report("a", 3, extras=[extra])])
    assert result["detection_gate"] == "review_required"
    assert result["additional_detections"] == [{"capture_iq_sha256": "a", **extra}]


def test_recovery_failure_dominates_extra_review():
    result = combine([report("a", 3, 100, 94, [{"sample_offset": 0}])])
    assert result["detection_gate"] == "fail" and result["recovery"] == .94


def test_duplicate_or_changed_policy_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        combine([report("a", 2), report("a", 2)])
    altered = deepcopy(report("b", 3))
    altered["policy"]["minimum_positive_episodes"] = 2
    with pytest.raises(ValueError, match="policy"):
        combine([altered])
