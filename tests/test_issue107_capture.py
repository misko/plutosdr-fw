"""Pure continuity checks for the issue-107 receive-only capture harness."""

from scripts.issue107.capture import (
    counter_continuity_passed,
    timing_anchor_coverage_passed,
)


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


def _anchor(counter: int, send_ns: int, receive_ns: int) -> dict[str, object]:
    return {
        "send_monotonic_ns": send_ns,
        "receive_monotonic_ns": receive_ns,
        "observation": {
            "counter": counter,
            "boot_id": "1" * 32,
            "session": 101,
            "generation": 7,
            "sample_rate_hz": 15_000_000,
            "epoch": 1234,
        },
    }


def _covered_capture(anchors: list[dict[str, object]]) -> bool:
    return timing_anchor_coverage_passed(
        anchors,
        first_valid_sample=1_000_000,
        last_valid_sample=76_000_000,
        sample_rate_hz=15_000_000,
    )


def test_short_queries_do_not_hide_fifteen_second_anchor_hole() -> None:
    anchors = [
        _anchor(1_000_000, 0, 1_000_000),
        _anchor(226_000_000, 15_000_000_000, 15_001_000_000),
    ]
    assert all(a["receive_monotonic_ns"] - a["send_monotonic_ns"] <= 50_000_000 for a in anchors)
    assert not _covered_capture(anchors)


def test_unobserved_capture_endpoint_fails_anchor_coverage() -> None:
    anchors = [
        _anchor(151_000_001, 0, 1_000_000),
        _anchor(226_000_000, 5_000_000_000, 5_001_000_000),
    ]
    assert not _covered_capture(anchors)


def test_five_second_anchor_cadence_covers_both_endpoints() -> None:
    anchors = [
        _anchor(1_000_000, 0, 1_000_000),
        _anchor(76_000_000, 5_000_000_000, 5_001_000_000),
    ]
    assert _covered_capture(anchors)
