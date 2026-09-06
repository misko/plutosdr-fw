#!/usr/bin/env python3
"""Full-snapshot launcher for the v6 Starlink PSS progress diagnostic.

The immutable v1/v2 diagnostic launchers remain unchanged. This wrapper runs
the v2 progress observation and appends the packaged controller's complete
post-diagnostic snapshot while the same exact-radio lock and host route remain
held. It therefore exposes every counter used by ``fault_free_epoch`` without
changing the FPGA, firmware image, or temporary diagnostic binary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_progress_probe_v2 as probe_v2

ProbeError = probe_v2.ProbeError
parser = probe_v2.parser
_execute_measurement_v2 = probe_v2.probe_v1._execute_measurement


def _execute_measurement(
    plan: dict[str, Any],
    base: dict[str, Any],
    handoff: Any,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Any,
    payload: bytes,
) -> dict[str, Any]:
    measurement = _execute_measurement_v2(
        plan,
        base,
        handoff,
        backend,
        password,
        iio_module,
        ssh_builder,
        payload,
    )
    common = f"/usr/sbin/starlink_pss_acqctl --expect-serial {plan['serial']}"
    measurement["controller_snapshot_after_diagnostic"] = (
        probe_v2.probe_v1.probe_v1._remote_json(
            backend,
            handoff.operation.target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=(
                f"{common} snapshot --timeout-ms {base['controller_timeout_ms']}"
            ),
            timeout_s=max(10.0, base["controller_timeout_ms"] / 1000.0 + 5.0),
            ssh_builder=ssh_builder,
        )
    )
    return measurement


build_plan = probe_v2.build_plan
verify_receipt = probe_v2.verify_receipt


def execute_plan(args: Any) -> dict[str, Any]:
    original = probe_v2.probe_v1._execute_measurement
    probe_v2.probe_v1._execute_measurement = _execute_measurement
    try:
        return probe_v2.execute_plan(args)
    finally:
        probe_v2.probe_v1._execute_measurement = original


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
