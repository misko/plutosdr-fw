#!/usr/bin/env python3
"""V6-only launcher for the immutable Starlink PSS progress diagnostic.

The v1 diagnostic remains unchanged and reproducible for the v4 candidate.
This wrapper admits only the acquisition-only v6 firmware identity while
reusing v1's sealed plan, temporary /tmp upload, counter measurement, cleanup,
RX restoration, route release, and receipt implementation.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe_v2 as hardware_probe_v2
import scripts.starlink_pss_progress_probe_v1 as probe_v1

ProbeError = probe_v1.ProbeError
parser = probe_v1.parser
_validate_plan_v1 = probe_v1._validate_plan


def _validate_plan(plan: dict[str, Any]) -> None:
    rate = plan.get("rate_msps")
    expected = plan.get("expected_firmware")
    if (
        not isinstance(rate, int)
        or expected
        != f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v6"
    ):
        raise ProbeError("progress plan is not an acquisition-only v6 candidate")
    compatible = dict(plan)
    compatible["expected_firmware"] = (
        f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v4"
    )
    _validate_plan_v1(compatible)


@contextmanager
def _identity_passthrough() -> Iterator[None]:
    yield


@contextmanager
def _v6_candidate_identity() -> Iterator[None]:
    """Temporarily admit only the v6 extension at v1's identity boundaries."""

    original_revisions = hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS
    original_identity = probe_v1.probe_v6._v4_candidate_identity
    original_validate = probe_v1._validate_plan
    hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS = (
        "v2",
        "v3",
        "v4",
        "v5",
        "v6",
    )
    probe_v1.probe_v6._v4_candidate_identity = _identity_passthrough
    probe_v1._validate_plan = _validate_plan
    try:
        yield
    finally:
        probe_v1._validate_plan = original_validate
        probe_v1.probe_v6._v4_candidate_identity = original_identity
        hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS = original_revisions


def build_plan(args: Any) -> dict[str, Any]:
    with _v6_candidate_identity():
        return probe_v1.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    with _v6_candidate_identity():
        return probe_v1.execute_plan(args)


def verify_receipt(args: Any) -> dict[str, Any]:
    with _v6_candidate_identity():
        return probe_v1.verify_receipt(args)


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
