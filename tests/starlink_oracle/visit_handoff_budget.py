"""Offline nominal-period visit budget, not a detector or command scheduler.

The caller supplies an upper bound on map availability and command transport
delay in ORIGINAL source samples. These assumptions are not attested here.
No RF uncertainty, capture processing cost or host throughput is inferred.
This model cannot authorize a command or extend PPU's admitted15-only profile.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VisitBudget:
    rate_hz: int
    visit_start: int
    visit_stop: int
    assumed_latest_admission: int
    minimum_center: int
    maximum_center: int
    first_center: int | None
    last_center: int | None
    count: int
    period_samples: int
    host_lead_samples: int
    capture_before: int
    capture_after: int


def nominal_visit_budget(
    *, rate_hz: int, visit_start: int, coarse_phase: int,
    map_available: int, command_delay_bound: int,
) -> VisitBudget:
    """Fit nominal750Hz full captures after an assumed map/control bound.

    coarse_phase is an epoch-relative canonical15MHz phase in[0,20000).
    visit_start is its corresponding original-rate epoch, not a host timestamp.
    All centers are R*phase + n*(20000*R) from that epoch. Fractional period,
    clock drift and coarse timing error are deliberately NOT modeled.

    Host center lead65536*R matches starlink_pss_hw.h. Hardware's distinct
    capture-start lead is64*R relative to admission_index+1. Both must hold.
    Every entire130*R-sample native capture must remain inside the120ms visit.
    Count is only geometrically possible slots, not accepted/measured results.
    """
    for name, value in locals().copy().items():
        if type(value) is not int or not 0 <= value < 1 << 64:
            raise ValueError(f"{name} must be an unsigned64 integer")
    if rate_hz not in (15_000_000, 30_000_000, 60_000_000):
        raise ValueError("unsupported source rate")
    if coarse_phase >= 20_000:
        raise ValueError("coarse_phase must be canonical modulo20000")
    ratio = rate_hz // 15_000_000
    stop = visit_start + rate_hz * 120 // 1000
    if stop > 1 << 64:
        raise ValueError("visit would wrap the original source counter")
    if not visit_start <= map_available < stop:
        raise ValueError("map availability must be inside this visit")
    admission = map_available + command_delay_bound
    if admission >= 1 << 64:
        raise ValueError("assumed admission would wrap")
    before, after = 32 * ratio, 98 * ratio
    host_lead = 65536 * ratio
    lower = max(visit_start + before, admission + host_lead,
                admission + 1 + 64 * ratio + before)
    upper = stop - after
    period = 20_000 * ratio
    origin = visit_start + coarse_phase * ratio
    first_ordinal = max(0, -((origin - lower) // period))
    last_ordinal = (upper - origin) // period
    count = max(0, last_ordinal - first_ordinal + 1)
    return VisitBudget(
        rate_hz, visit_start, stop, admission, lower, upper,
        origin + first_ordinal * period if count else None,
        origin + last_ordinal * period if count else None,
        count, period, host_lead, before, after,
    )
