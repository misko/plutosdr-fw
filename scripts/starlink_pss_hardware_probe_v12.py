#!/usr/bin/env python3
"""Cleanup-aware launcher for the 30 MS/s acquisition-only v9 candidate.

Historical probe revisions remain immutable.  The controller deliberately
disables and flushes PSMA after printing its successful, pre-cleanup candidate
snapshot.  That shutdown can increment only the discarded-score and
discontinuity-abort counters.  This revision preserves the raw post-cleanup
snapshot in the receipt while admitting that bounded bookkeeping; every
in-observation and non-cleanup fault gate remains strict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe_v11 as probe_v11

ProbeError = probe_v11.ProbeError
parser = probe_v11.parser
probe_v1 = probe_v11.probe_v1
probe_v5 = probe_v11.probe_v5

_DEPENDENCY_SAFE_MEASURE = probe_v5._measure
_NON_CLEANUP_ZERO_FIELDS = (
    "map_overruns",
    "protocol_errors",
    "arithmetic_overflows",
    "map_read_errors",
    "map_release_errors",
    "ingress_dropped_samples",
    "scheduler_gaps",
    "scheduler_index_errors",
    "scheduler_overflows",
    "detector_faults",
    "phase_discontinuities",
    "zero_denominators",
)


def _numeric_word(value: Any, *, label: str) -> int:
    try:
        parsed = int(str(value), 0)
    except (TypeError, ValueError) as error:
        raise ProbeError(f"{label} is not a numeric word") from error
    if parsed < 0 or parsed > 0xFFFFFFFF:
        raise ProbeError(f"{label} is outside the 32-bit counter range")
    return parsed


def _cleanup_only_contract(
    before: dict[str, Any],
    candidate: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Prove that post-candidate faults are bounded shutdown bookkeeping."""

    if (
        before.get("schema") != "starlink-pss-acqctl.snapshot.v1"
        or before.get("fault_free_epoch") is not True
        or candidate.get("schema") != "starlink-pss-acqctl.candidate.v1"
        or candidate.get("fault_free_epoch") is not True
        or candidate.get("continuity_ok") is not True
        or candidate.get("final_health_flags") != "0x00000000"
        or after.get("schema") != "starlink-pss-acqctl.snapshot.v1"
        or after.get("ready_mask") != 0
        or _numeric_word(after.get("health_flags"), label="post-cleanup health_flags")
        != 0
    ):
        raise ProbeError("controller observation was not clean before shutdown")

    for side in ("before", "after"):
        ddc = candidate.get(f"ddc_counters_{side}")
        if not isinstance(ddc, dict):
            raise ProbeError(f"candidate DDC {side} counters are missing")
        if (
            _numeric_word(ddc.get("discontinuity"), label=f"DDC {side} discontinuity")
            != 0
            or _numeric_word(ddc.get("saturation"), label=f"DDC {side} saturation")
            != 0
        ):
            raise ProbeError("candidate DDC fault counters are nonzero")

    for field in _NON_CLEANUP_ZERO_FIELDS:
        if _numeric_word(after.get(field), label=f"post-cleanup {field}") != 0:
            raise ProbeError(f"post-cleanup snapshot has a real fault in {field}")

    deltas: dict[str, int] = {}
    for field in ("discarded_scores", "discontinuity_aborts"):
        initial = _numeric_word(before.get(field), label=f"initial {field}")
        final = _numeric_word(after.get(field), label=f"post-cleanup {field}")
        if final < initial or final - initial > 1:
            raise ProbeError(f"post-cleanup {field} is not a bounded shutdown delta")
        deltas[field] = final - initial

    raw_fault_free = after.get("fault_free_epoch")
    expected_fault_free = not any(deltas.values())
    if raw_fault_free is not expected_fault_free:
        raise ProbeError("post-cleanup fault-free flag disagrees with cleanup counters")
    return {
        "schema": "starlink-pss-probe.cleanup-verification.v1",
        "classification": "controller_disable_flush_only",
        "raw_fault_free_epoch": raw_fault_free,
        "discarded_scores_delta": deltas["discarded_scores"],
        "discontinuity_aborts_delta": deltas["discontinuity_aborts"],
        "non_cleanup_faults_zero": True,
        "candidate_observation_fault_free": True,
    }


def _measure(
    plan: dict[str, Any],
    handoff: Any,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Any,
) -> dict[str, Any]:
    """Reuse v5's rate-safe measurement while correcting its cleanup gate."""

    original_remote = probe_v1._remote_json
    before: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    raw_after: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None

    def cleanup_aware_remote(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal before, candidate, raw_after, cleanup
        value = original_remote(*args, **kwargs)
        schema = value.get("schema")
        if schema == "starlink-pss-acqctl.snapshot.v1":
            if before is None:
                before = value
            elif candidate is not None and raw_after is None:
                raw_after = value
                cleanup = _cleanup_only_contract(before, candidate, raw_after)
                admitted = dict(value)
                admitted["fault_free_epoch"] = True
                return admitted
        elif schema == "starlink-pss-acqctl.candidate.v1":
            candidate = value
        return value

    probe_v1._remote_json = cleanup_aware_remote
    try:
        measurement = _DEPENDENCY_SAFE_MEASURE(
            plan, handoff, backend, password, iio_module, ssh_builder
        )
    finally:
        probe_v1._remote_json = original_remote
    if raw_after is None or cleanup is None:
        raise ProbeError("controller cleanup snapshot was not observed")
    measurement["snapshot_after"] = raw_after
    measurement["controller_cleanup"] = cleanup
    return measurement


def build_plan(args: Any) -> dict[str, Any]:
    return probe_v11.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    original_measure = probe_v5._measure
    probe_v5._measure = _measure
    try:
        return probe_v11.execute_plan(args)
    finally:
        probe_v5._measure = original_measure


def verify_receipt(args: Any) -> dict[str, Any]:
    return probe_v11.verify_receipt(args)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            result = build_plan(arguments)
        elif arguments.command == "execute":
            result = execute_plan(arguments)
        else:
            result = verify_receipt(arguments)
    except (OSError, ValueError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
