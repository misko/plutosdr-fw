#!/usr/bin/env python3
"""Deterministic-context runner for the v7-bound 15 MS/s map monitor.

The v2 monitor contract and receipt schema remain unchanged.  This operational
entry point adds one cleanup invariant: every IIO context is wrapped with a
public ``close`` method backed by the deterministic modern/legacy closer from
the exact attested PPU checkout.  The inherited monitor therefore cannot fall
back to implicit Python garbage collection on the installed legacy pylibiio.
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

import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2

PLAN_SCHEMA = monitor_v2.PLAN_SCHEMA
RECEIPT_SCHEMA = monitor_v2.RECEIPT_SCHEMA
EXPECTED_FIRMWARE = monitor_v2.EXPECTED_FIRMWARE
ProbeError = monitor_v2.ProbeError
parser = monitor_v2.parser
build_plan = monitor_v2.build_plan
verify_receipt = monitor_v2.verify_receipt
_validate_plan = monitor_v2._validate_plan
_validate_monitor_records = monitor_v2._validate_monitor_records


class _ClosingContext:
    """Expose deterministic close while otherwise preserving pylibiio behavior."""

    def __init__(self, context: Any, iio_module: Any, closer: Any) -> None:
        self._wrapped_context = context
        self._iio_module = iio_module
        self._closer = closer
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        if self._closed:
            raise ProbeError("receiver IIO context was already closed")
        return getattr(self._wrapped_context, name)

    def close(self) -> None:
        if self._closed:
            raise ProbeError("receiver IIO context was already closed")
        self._closer(self._iio_module, self._wrapped_context)
        self._closed = True


class _ClosingIio:
    def __init__(self, iio_module: Any, closer: Any) -> None:
        self._wrapped_iio = iio_module
        self._closer = closer
        self.contexts: list[_ClosingContext] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped_iio, name)

    def Context(self, uri: str) -> _ClosingContext:
        context = self._wrapped_iio.Context(uri)
        wrapped = _ClosingContext(context, self._wrapped_iio, self._closer)
        self.contexts.append(wrapped)
        return wrapped


@contextmanager
def _deterministic_context_contract() -> Iterator[None]:
    """Scope inherited v1 measurement to PPU's deterministic IIO closer."""

    previous = monitor_v1._execute_measurement

    def execute_measurement(
        plan: dict[str, Any],
        base: dict[str, Any],
        handoff: Any,
        backend: Any,
        password: Any,
        iio_module: Any,
        ssh_builder: Any,
        payload: bytes,
    ) -> dict[str, Any]:
        closer = getattr(handoff.ppu.linux, "_close_iio_context", None)
        if not callable(closer):
            raise ProbeError("attested PPU source lacks deterministic IIO close")
        wrapped_iio = _ClosingIio(iio_module, closer)
        result = previous(
            plan,
            base,
            handoff,
            backend,
            password,
            wrapped_iio,
            ssh_builder,
            payload,
        )
        if (
            len(wrapped_iio.contexts) != 1
            or wrapped_iio.contexts[0]._closed is not True
        ):
            raise ProbeError(
                "receiver IIO context close was not deterministically verified"
            )
        return result

    monitor_v1._execute_measurement = execute_measurement
    try:
        yield
    finally:
        monitor_v1._execute_measurement = previous


def execute_plan(args: Any) -> dict[str, Any]:
    with _deterministic_context_contract():
        return monitor_v2.execute_plan(args)


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
