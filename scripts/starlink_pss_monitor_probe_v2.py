#!/usr/bin/env python3
"""V7-bound continuous phase-map monitor for the 15 MS/s M3 campaign.

The transport and cleanup implementation remains the reviewed v1 monitor.
This wrapper scopes its identity to the acquisition-injection v7 RAM image for
one call and restores every inherited module constant afterwards.  It never
writes persistent storage and never claims PSS, SSS, or frame lock.
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

import scripts.starlink_pss_hardware_probe_v9 as probe_v9
import scripts.starlink_pss_monitor_probe_v1 as monitor_v1

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-monitor-probe-plan.v2"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-monitor-probe-receipt.v2"
EXPECTED_FIRMWARE = probe_v9.EXPECTED_FIRMWARE
ProbeError = monitor_v1.ProbeError
parser = monitor_v1.parser


@contextmanager
def _v7_monitor_contract() -> Iterator[None]:
    """Temporarily bind inherited plan/execute/verify logic to candidate v7."""

    names = (
        "PLAN_SCHEMA",
        "RECEIPT_SCHEMA",
        "EXPECTED_FIRMWARE",
        "_ad9361_v6_contract",
    )
    previous = {name: getattr(monitor_v1, name) for name in names}
    monitor_v1.PLAN_SCHEMA = PLAN_SCHEMA
    monitor_v1.RECEIPT_SCHEMA = RECEIPT_SCHEMA
    monitor_v1.EXPECTED_FIRMWARE = EXPECTED_FIRMWARE
    monitor_v1._ad9361_v6_contract = (
        probe_v9._ad9361_v7_acquisition_injection_contract
    )
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(monitor_v1, name, value)


def _validate_plan(plan: dict[str, Any]) -> None:
    with _v7_monitor_contract():
        monitor_v1._validate_plan(plan)


def _validate_monitor_records(
    records: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    with _v7_monitor_contract():
        return monitor_v1._validate_monitor_records(records, plan)


def build_plan(args: Any) -> dict[str, Any]:
    with _v7_monitor_contract():
        return monitor_v1.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    with _v7_monitor_contract():
        return monitor_v1.execute_plan(args)


def verify_receipt(args: Any) -> dict[str, Any]:
    with _v7_monitor_contract():
        return monitor_v1.verify_receipt(args)


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
