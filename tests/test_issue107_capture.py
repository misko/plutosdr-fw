"""Pure continuity checks for the issue-107 receive-only capture harness."""

from scripts.issue107.capture import counter_continuity_passed


def _visit(first: int, end: int, *, missing: int = 0) -> dict[str, int]:
    return {
        "first_sample": first,
        "end_sample_exclusive": end,
        "valid_sample_count": end - first,
        "missing_samples_before": missing,
    }


def test_scheduled_gap_between_visits_is_allowed() -> None:
    assert counter_continuity_passed([_visit(100, 200), _visit(250, 350)])


def test_dma_reported_missing_samples_fail_continuity() -> None:
    assert not counter_continuity_passed(
        [_visit(100, 200), _visit(250, 350, missing=8)]
    )


def test_overlapping_visit_ranges_fail_continuity() -> None:
    assert not counter_continuity_passed([_visit(100, 220), _visit(200, 300)])


def test_empty_or_zero_sample_capture_fails_continuity() -> None:
    assert not counter_continuity_passed([])
    assert not counter_continuity_passed([_visit(100, 100)])
