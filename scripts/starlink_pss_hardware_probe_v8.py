#!/usr/bin/env python3
"""AD9361-personality launcher for the acquisition-only v6 PSS probe.

Historical probe revisions remain immutable.  This DNM-only launcher narrows
one operation to the explicit ``ad9361-1r1t`` runtime target and its exact live
model while reusing v7's v6-candidate admission and v5's dependency-safe
measurement, restoration, radio locking, route locking, and receipt path.
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

import scripts.starlink_pss_hardware_probe_v7 as probe_v7

ProbeError = probe_v7.ProbeError
parser = probe_v7.parser

RUNTIME_TARGET = "ad9361-1r1t"
EXPECTED_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"


@contextmanager
def _ad9361_1r1t_identity() -> Iterator[None]:
    """Scope the inherited exact-runtime checks to AD9361/1R1T."""

    probe_v1 = probe_v7.probe_v5.probe_v1
    original = (probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL)
    probe_v1.RUNTIME_TARGET = RUNTIME_TARGET
    probe_v1.EXPECTED_MODEL = EXPECTED_MODEL
    try:
        yield
    finally:
        probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL = original


def build_plan(args: Any) -> dict[str, Any]:
    with _ad9361_1r1t_identity():
        return probe_v7.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    with _ad9361_1r1t_identity():
        return probe_v7.execute_plan(args)


def verify_receipt(args: Any) -> dict[str, Any]:
    with _ad9361_1r1t_identity():
        return probe_v7.verify_receipt(args)


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
