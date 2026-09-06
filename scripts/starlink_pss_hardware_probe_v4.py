#!/usr/bin/env python3
"""Idempotent source-locked-rate launcher for the Starlink PSS probe.

The AD936x source rate drives the FPGA capture rate.  Some kernels reject a
redundant write to the capture selector even when its readback already equals
the requested parent rate.  This launcher skips only that exact idempotent
write; all existing readback, decimation-bypass, restoration, and receipt gates
remain in the immutable v1-v3 implementation.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe as probe_v1
import scripts.starlink_pss_hardware_probe_v3 as probe_v3

ProbeError = probe_v3.ProbeError
build_plan = probe_v3.build_plan
verify_receipt = probe_v3.verify_receipt
parser = probe_v3.parser
_attribute_v1 = probe_v1._attribute


class _IdempotentNumericAttribute:
    def __init__(self, attribute: Any) -> None:
        self._attribute = attribute

    @property
    def value(self) -> Any:
        return self._attribute.value

    @value.setter
    def value(self, requested: Any) -> None:
        try:
            current_number = float(str(self._attribute.value).strip().split()[0])
            requested_number = float(str(requested).strip().split()[0])
        except (IndexError, TypeError, ValueError):
            self._attribute.value = requested
            return
        if not (
            math.isfinite(current_number)
            and math.isfinite(requested_number)
            and current_number == requested_number
        ):
            self._attribute.value = requested


def _idempotent_source_locked_attribute(
    channel: Any, name: str, *, label: str
) -> Any:
    attribute = _attribute_v1(channel, name, label=label)
    if label == "capture RX" and name == "sampling_frequency":
        return _IdempotentNumericAttribute(attribute)
    return attribute


def execute_plan(args: Any) -> dict[str, Any]:
    original = probe_v1._attribute
    probe_v1._attribute = _idempotent_source_locked_attribute
    try:
        return probe_v3.execute_plan(args)
    finally:
        probe_v1._attribute = original


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
