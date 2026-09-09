"""Qualification must count distinct complete frames and fail the invoking job."""
import argparse
import json
import sys

import pytest

from tools.starlink_glrt_profile import CANDIDATE, FPGA_GATES, add_arguments, profile
from tools import starlink_glrt_synthetic_qualification as qualification


def test_capture_and_replay_share_the_named_profile_and_cannot_mislabel_overrides():
    for exact_option, attribute in (("--threshold-q16", "threshold_q16"), ("--exact-q16", "exact_q16")):
        parser = argparse.ArgumentParser()
        add_arguments(parser, exact_option=exact_option)
        args = parser.parse_args(["--profile", CANDIDATE])
        gates = (args.acquisition_q16, getattr(args, attribute), args.margin_q16)
        assert gates == FPGA_GATES
        assert profile(gates, requested=args.profile)["name"] == CANDIDATE
        with pytest.raises(ValueError, match="does not allow"):
            profile((15729, *gates[1:]), requested=args.profile)
        assert profile((15729, *gates[1:]))["name"] == "custom-development"


def event(epoch, cfo=0):
    return {"detected": True, "epoch": epoch, "cfo_hz": cfo}


@pytest.mark.parametrize("events,unmatched_host,expected", [
    ([event(100), event(3433)], 0, "pass"),
    ([event(100)], 0, "failed_frame_recovery_or_agreement"),
    ([event(100), event(100)], 0, "failed_frame_recovery_or_agreement"),
    ([event(100), event(3433), event(3433)], 0, "failed_frame_recovery_or_agreement"),
    ([event(100), event(3433, 2001)], 0, "failed_frame_recovery_or_agreement"),
    ([event(100), event(3433)], 1, "failed_frame_recovery_or_agreement"),
])
def test_every_complete_frame_requires_a_unique_truth_and_host_match(events, unmatched_host, expected):
    case = {"kind": "strong", "rate": 2_500_000, "count": 4500, "cfo_hz": 0}
    result = qualification.assess(case, [100, 3433, 4400], events, unmatched_host_positives=unmatched_host)
    assert result["criterion"] == expected
    assert result["complete_truth_epochs"] == [100, 3433]
    assert result["truth_matches"] <= 2
    assert len({row["positive_index"] for row in result["truth_assignments"]}) == result["truth_matches"]


@pytest.mark.parametrize("kind", ["noise", "tone", "scrambled"])
def test_control_crossing_is_a_failure_even_with_no_truth_frames(kind):
    result = qualification.assess({"kind": kind, "rate": 2_500_000, "count": 5000, "cfo_hz": 0}, [], [event(100)])
    assert result["criterion"] == "false_positive"


@pytest.mark.parametrize("criterion,exit_code", [("pass", 0), ("failed_frame_recovery_or_agreement", 1), ("false_positive", 1)])
def test_cli_completion_does_not_hide_failed_qualification_and_subset_is_explicit(tmp_path, monkeypatch, criterion, exit_code):
    class CompletedPool:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def map(self, run, cases):
            return [{**case, "status": "complete", "criterion": criterion} for case in cases]
    monkeypatch.setattr(qualification, "ThreadPoolExecutor", CompletedPool)
    monkeypatch.setattr(sys, "argv", ["qualification", "--leo-source", str(tmp_path), "--case", "0",
                                    "--source-rate", "2500000", "--output", str(tmp_path/"result")])
    with pytest.raises(SystemExit) as stopped:
        qualification.main()
    assert stopped.value.code == exit_code
    summary = json.loads((tmp_path/"result/summary.json").read_text())
    assert summary["status"] == "complete"
    assert summary["selected_case_ids"] == [0] and not summary["full_five_rate_matrix"]
    assert summary["qualification_passed"] == (exit_code == 0)
    protocol = json.loads((tmp_path/"result/protocol.json").read_text())
    assert protocol["schema"].endswith("/v2")
    assert protocol["detector_profile"]["name"] == CANDIDATE


def test_only_exploratory_cases_cannot_claim_strong_or_control_qualification():
    summary = qualification.summarize([{"case": 3, "kind": "weak", "status": "complete", "criterion": "reported_limit"}], True, [3])
    assert summary["qualification_passed"] is None and summary["gated_cases"] == 0
