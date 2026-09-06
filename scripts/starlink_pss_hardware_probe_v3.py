#!/usr/bin/env python3
"""RAM-reenumeration-aware launcher for the Starlink PSS hardware probe.

The immutable v1 probe and revision-aware v2 launcher remain unchanged.  This
launcher additionally permits the USB address to change during the sealed PPU
RAM boot, while still requiring a unique match for every persistent target
identity field and an exact full-identity revalidation before IIO access.
"""

from __future__ import annotations

import importlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe as probe_v1
import scripts.starlink_pss_hardware_probe_v2 as probe_v2

ProbeError = probe_v1.ProbeError
build_plan = probe_v2.build_plan
verify_receipt = probe_v2.verify_receipt
parser = probe_v2.parser


def _resolve_live_target(backend: Any, planned: Any) -> Any:
    """Resolve one post-RAM-boot target without trusting its transient address."""

    stable_fields = (
        "serial",
        "topology",
        "sysfs_path",
        "vendor_id",
        "product_id",
        "bus_number",
        "network_interface",
        "source_ipv4",
    )
    matches = tuple(
        target
        for target in backend._runtime_targets()
        if all(getattr(target, field) == getattr(planned, field) for field in stable_fields)
    )
    if len(matches) != 1:
        raise ProbeError(
            "post-RAM target is not one unique match for the sealed "
            "serial/topology/interface identity"
        )
    return matches[0]


def execute_plan(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = probe_v1._load_private_json(plan_path, label="probe plan")
    probe_v2._validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    for label in ("candidate_plan", "operation_plan", "ram_receipt"):
        expected = plan[label]
        observed = probe_v1._identity(Path(expected["path"]), label=label.replace("_", " "))
        if observed != expected:
            raise ProbeError(f"probe plan no longer binds the exact {label}")
    handoff = probe_v2._load_handoff(
        ppu_repository=Path(plan["ppu_repository"]),
        ppu_commit=plan["ppu_source_commit"],
        candidate_path=Path(plan["candidate_plan"]["path"]),
        operation_path=Path(plan["operation_plan"]["path"]),
        ram_receipt_path=Path(plan["ram_receipt"]["path"]),
        rate_msps=plan["rate_msps"],
    )
    if Path(plan["receipt_path"]) != args.output.absolute():
        raise ProbeError("execute output differs from the sealed receipt path")
    probe_v1._require_new_private_output(args.output)
    if args.timeout_s <= 0 or not args.state_root.is_absolute() or ".." in args.state_root.parts:
        raise ProbeError("execution timeout and state root are invalid")
    try:
        password = handoff.ppu.lifecycle.validate_password_file(args.ssh_password_file)
        iio_module = importlib.import_module("iio")
    except (ImportError, OSError, ValueError) as error:
        raise ProbeError(f"probe dependency cannot be attested: {error}") from error
    try:
        password.path.relative_to(handoff.candidate.artifact_index.path.parent)
    except ValueError:
        pass
    else:
        raise ProbeError("SSH password file must be outside the candidate directory")
    backend = handoff.ppu.linux.LinuxRxOnlyReleaseCandidateBackend(
        state_root=args.state_root.absolute(), timeout_s=args.timeout_s
    )
    started = datetime.now(UTC)
    route = None
    route_released = False
    measurement: dict[str, Any] | None = None
    runtime: Any = None
    failure: BaseException | None = None
    live_target: Any = None
    try:
        live_target = _resolve_live_target(backend, handoff.operation.target)
        with backend.transaction_locks(live_target, handoff.operation.ssh_host):
            fresh = backend.revalidate_target(live_target)
            if fresh != live_target:
                raise ProbeError("live target changed during exact revalidation")
            live_operation = handoff.operation.model_copy(update={"target": live_target})
            live_handoff = SimpleNamespace(
                ppu=handoff.ppu,
                candidate=handoff.candidate,
                operation=live_operation,
                receipt=handoff.receipt,
                repository=handoff.repository,
            )
            route = backend.acquire_host_route(live_target, live_operation.ssh_host)
            try:
                runtime = backend.attest_rx_only_runtime_v2(
                    live_target,
                    runtime_target=probe_v1.RUNTIME_TARGET,
                    expected_firmware=plan["expected_firmware"],
                    password=password,
                    route=route,
                )
                measurement = probe_v1._measure(
                    plan,
                    live_handoff,
                    backend,
                    password,
                    iio_module,
                    handoff.ppu.lifecycle.ssh_fixed_argv,
                )
            finally:
                if route is not None:
                    backend.release_host_route(route)
                    route_released = True
    except Exception as error:  # noqa: BLE001 - every execution failure gets a receipt
        failure = error
    completed = datetime.now(UTC)
    receipt = {
        "schema": probe_v1.RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "outcome": "pass" if failure is None else "failed",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "plan": probe_v1._identity(plan_path, label="probe plan"),
        "serial": plan["serial"],
        "rate_msps": plan["rate_msps"],
        "runtime_target": probe_v1.RUNTIME_TARGET,
        "expected_firmware": plan["expected_firmware"],
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": "candidate_measurement_only",
        "runtime": None if runtime is None else runtime.model_dump(mode="json"),
        "measurement": measurement,
        "route_release_verified": route_released,
        "recovery_required": True,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    identity = probe_v1._write_new_private(args.output, receipt)
    if failure is not None:
        raise ProbeError(f"probe failed after writing {identity['path']}: {failure}")
    return {
        "verdict": "PASS_CANDIDATE_MEASUREMENT_ONLY",
        "hardware_accessed": True,
        "persistent_write": False,
        "frame_lock_claim": False,
        "receipt": identity,
        "next_gate": "PPU candidate-ram recover to the sealed persistent 1R1T baseline",
    }


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
