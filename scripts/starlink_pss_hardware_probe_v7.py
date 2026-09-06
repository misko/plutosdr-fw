#!/usr/bin/env python3
"""V6-candidate launcher for the dependency-safe Starlink PSS probe.

The immutable v1-v6 probe revisions remain unchanged. This launcher admits
the acquisition-only v6 candidate while reusing the v5 measurement,
restoration, exact-radio locking, and receipt implementation.
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

import scripts.starlink_pss_hardware_probe_v2 as probe_v2
import scripts.starlink_pss_hardware_probe_v5 as probe_v5

ProbeError = probe_v5.ProbeError
parser = probe_v5.parser


@contextmanager
def _v6_candidate_identity() -> Iterator[None]:
    """Admit source revisions through v6 only for one v7 operation."""

    original = probe_v2.SUPPORTED_SOURCE_REVISIONS
    probe_v2.SUPPORTED_SOURCE_REVISIONS = ("v2", "v3", "v4", "v5", "v6")
    try:
        yield
    finally:
        probe_v2.SUPPORTED_SOURCE_REVISIONS = original


def build_plan(args: Any) -> dict[str, Any]:
    with _v6_candidate_identity():
        return probe_v5.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    """Run the dependency-safe v5 measurement with v6 identity enabled."""

    with _v6_candidate_identity():
        return probe_v5.execute_plan(args)


def verify_receipt(args: Any) -> dict[str, Any]:
    with _v6_candidate_identity():
        return probe_v5.verify_receipt(args)


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
