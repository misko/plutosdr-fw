"""RED on invisible refill loss; GREEN on adjacency or explicit segmentation."""

import pytest

from .experiment import Issue46Radio, run_experiment

pytestmark = [pytest.mark.radio_hardware, pytest.mark.issue46]


def test_issue_46_delayed_refill_is_never_an_invisible_gap(
    pnxx_issue46_radio: Issue46Radio,
) -> None:
    report, report_path = run_experiment(pnxx_issue46_radio)
    expected = pnxx_issue46_radio.options.expected
    if expected == "either":
        assert report["verdict"] in {"red", "green"}
    elif expected == "red":
        classifications = {
            boundary["verdict"]["classification"]
            for cell in report["cells"]
            for boundary in cell["boundaries"]
            if boundary["verdict"]["verdict"] == "red"
        }
        reproduction_classes = {
            "gap_inside_safe_bound",
            "ordinary_unrepresented_gap",
            "metadata_unflagged_gap",
        }
        assert report["verdict"] == "red" and (
            classifications & reproduction_classes
        ), (
            "RED was expected, but no returned-IQ discontinuity reproduced; "
            f"classifications={sorted(classifications)}; evidence: {report_path}"
        )
    else:
        assert report["verdict"] == expected, (
            f"issue-46 verdict is {report['verdict']}, expected {expected}; "
            f"evidence: {report_path}"
        )
