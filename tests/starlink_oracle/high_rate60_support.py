"""Pre-evaluation sample support for the future paired 60 MS/s fixture.

This admits no runtime profile and generates no replacement 30 MS/s golden.
The acquisition cascade has 21 raw samples of delay/support on either side
of a canonical center. Native capture bypasses both acquisition filters.
Intervals returned here are half-open and must fit the raw uint64 timeline.
"""

from __future__ import annotations

LIMIT = 1 << 64
COARSE_FIRST = (1 << 33) - 16
CANONICAL_FIRST = COARSE_FIRST - 768
CANONICAL_COUNT = 4096
NATIVE_CENTER = 4 * (COARSE_FIRST + 520)


def _integer(value: int, name: str) -> None:
    if type(value) is not int:
        raise ValueError(f"{name} must be a literal integer")


def _interval(first: int, stop: int) -> tuple[int, int]:
    if not 0 <= first < stop <= LIMIT:
        raise ValueError("raw support must fit uint64 without wrap")
    return first, stop


def raw_support(first: int, count: int) -> tuple[int, int]:
    """Full support of count consecutive 15 MS/s outputs at source 60."""
    _integer(first, "canonical first")
    _integer(count, "canonical count")
    if count <= 0:
        raise ValueError("canonical count must be positive")
    return _interval(4 * first - 21, 4 * (first + count - 1) + 22)


def native_support(center: int) -> tuple[int, int]:
    """264 taps at raw lags -128..128 require 520 original samples."""
    _integer(center, "native center")
    return _interval(center - 128, center + 128 + 264)


def native_lead(center: int, accepted_index: int) -> int:
    """Signed lead from the scheduler's NEXT sample, not current sample."""
    first, _ = native_support(center)
    _integer(accepted_index, "accepted raw index")
    if not 0 <= accepted_index < LIMIT - 1:
        raise ValueError("next accepted sample must fit uint64")
    lead = first - (accepted_index + 1)
    if not -(1 << 63) <= lead < (1 << 63):
        raise ValueError("lead does not fit signed hardware subtraction")
    return lead


def pilot_support(newest: int) -> tuple[int, int]:
    """One supported /6 pilot output, including both upstream x2 filters."""
    _integer(newest, "pilot newest canonical index")
    if newest % 6:
        raise ValueError("pilot output must use absolute canonical phase zero")
    return raw_support(newest - 538, 539)


def recipe() -> dict:
    """Fixed geometry only; no service-cost or real-time qualification claim."""
    source_first, source_stop = raw_support(CANONICAL_FIRST, CANONICAL_COUNT)
    capture_first, capture_stop = native_support(NATIVE_CENTER)
    first_pilot = ((CANONICAL_FIRST + 538 + 5) // 6) * 6
    last_pilot = first_pilot + 511 * 6
    return {
        "scope": "offline60_support_only_NOT_runtime_or_timing_qualification",
        "source_rate_hz": 60_000_000,
        "canonical_rate_hz": 15_000_000,
        "pilot_rate_hz": 2_500_000,
        "raw_half_open": [source_first, source_stop],
        "raw_count": source_stop - source_first,
        "canonical_first": CANONICAL_FIRST,
        "canonical_count": CANONICAL_COUNT,
        "coarse_first": COARSE_FIRST,
        "native_center": NATIVE_CENTER,
        "native_capture_half_open": [capture_first, capture_stop],
        "native_capture_count": 520,
        "native_taps": 264,
        "native_raw_lags": [-128, 128],
        "native_qualified_lags": [-120, 120],
        "native_raw_tuple_count": 257,
        "native_qualified_tuple_count": 241,
        "native_default_minimum_lead": 256,
        "native_tap_lag_products": 257 * 264,
        "raw_after_capture": source_stop - capture_stop,
        "pilot_newest_canonical": [first_pilot, last_pilot],
        "pilot_selected_count": 512,
        "pilot_raw_centers": [4 * (first_pilot - 269), 4 * (last_pilot - 269)],
        "pilot_raw_support_half_open": [pilot_support(first_pilot)[0], pilot_support(last_pilot)[1]],
        "pilot_raw_step": 24,
        "pilot_bytes": 2048,
        "pilot_stream_bytes_per_second": 10_000_000,
    }
