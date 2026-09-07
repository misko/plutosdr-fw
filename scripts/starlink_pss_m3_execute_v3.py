#!/usr/bin/env python3
"""Run M3 with deterministic RX cleanup and stable legacy TX attestation.

The v1 executor and v2 cleanup runner remain frozen.  This wrapper scopes the
v2 transmitter guard into the inherited executor for one call, restores the
module binding afterwards, and writes an adjacent receipt which binds the
actual transmitter guard source used by the attempt.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_m3_execute_v1 as execute_v1
import scripts.starlink_pss_m3_execute_v2 as execute_v2
import scripts.starlink_pss_m3_iio_tx_v2 as tx_v2
import scripts.starlink_pss_monitor_probe_v3 as monitor_v3

RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m3-runner-receipt.v3"
CLAIM_SCOPE = "cabled_campaign_transport_cleanup_and_stable_tx_identity_only"
ProbeError = execute_v1.ProbeError
parser = execute_v2.parser
RUNNER_FIELDS = {
    "schema",
    "schema_version",
    "receipt_id",
    "created_at",
    "outcome",
    "plan",
    "execution_receipt",
    "inherited_runner_receipt",
    "runner_source",
    "inherited_runner_source",
    "base_executor_source",
    "transmitter_driver_source",
    "receiver_monitor_source",
    "stable_channel_identity_policy",
    "module_binding_restored",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "claim_scope",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
    "error",
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _runner_path(plan: dict[str, Any]) -> Path:
    base = Path(plan["execution_receipt_path"])
    return base.with_name(f"{base.stem}-runner-v3.json")


def _source_identity(module: Any, *, label: str) -> dict[str, Any]:
    path = Path(module.__file__).absolute()
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ProbeError(f"{label} cannot be read: {error}") from error
    if not payload:
        raise ProbeError(f"{label} is empty")
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


@contextmanager
def _stable_tx_driver_contract() -> Iterator[None]:
    original = execute_v1.SingleTxCyclicIio
    execute_v1.SingleTxCyclicIio = tx_v2.SingleTxCyclicIio
    try:
        yield
    finally:
        execute_v1.SingleTxCyclicIio = original


def _validate_runner(
    runner: dict[str, Any], *, plan_path: Path, plan: dict[str, Any]
) -> None:
    if (
        set(runner) != RUNNER_FIELDS
        or runner.get("schema") != RECEIPT_SCHEMA
        or runner.get("schema_version") != 3
        or not isinstance(runner.get("receipt_id"), str)
        or len(runner["receipt_id"]) != 32
        or any(
            character not in "0123456789abcdef" for character in runner["receipt_id"]
        )
        or runner.get("outcome") not in {"pass", "failed"}
        or runner.get("plan")
        != execute_v1._identity(plan_path, label="M3 execution plan")
        or runner.get("runner_source")
        != _source_identity(sys.modules[__name__], label="M3 v3 runner source")
        or runner.get("inherited_runner_source")
        != _source_identity(execute_v2, label="M3 v2 runner source")
        or runner.get("base_executor_source")
        != _source_identity(execute_v1, label="M3 v1 executor source")
        or runner.get("transmitter_driver_source")
        != _source_identity(tx_v2, label="M3 v2 transmitter driver source")
        or runner.get("receiver_monitor_source")
        != _source_identity(monitor_v3, label="M3 v3 monitor source")
        or runner.get("stable_channel_identity_policy")
        != "id-direction-and-complete-gain-inventory"
        or runner.get("module_binding_restored") is not True
        or not isinstance(runner.get("hardware_accessed"), bool)
        or runner.get("persistent_write") is not False
        or runner.get("do_not_merge") is not True
        or runner.get("claim_scope") != CLAIM_SCOPE
        or runner.get("pss_detected") is not False
        or runner.get("sss_detected") is not False
        or runner.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M3 v3 runner receipt violates its guarded contract")
    execute_v1.campaign._parse_time(runner.get("created_at"), label="runner created_at")

    execution = runner.get("execution_receipt")
    inherited = runner.get("inherited_runner_receipt")
    if execution is not None:
        execute_v1.campaign._validate_identity(execution, label="execution receipt")
        if execution != execute_v1._identity(
            Path(plan["execution_receipt_path"]), label="M3 execution receipt"
        ):
            raise ProbeError("M3 v3 runner binds a changed execution receipt")
    if inherited is not None:
        execute_v1.campaign._validate_identity(
            inherited, label="inherited runner receipt"
        )
        inherited_path = execute_v2._runner_path(plan)
        if inherited != execute_v1._identity(
            inherited_path, label="M3 v2 runner receipt"
        ):
            raise ProbeError("M3 v3 runner binds a changed inherited runner receipt")
    if runner["outcome"] == "pass":
        if (
            execution is None
            or inherited is None
            or runner["hardware_accessed"] is not True
            or runner.get("error") is not None
        ):
            raise ProbeError("M3 v3 pass receipt is incomplete")
    elif not isinstance(runner.get("error"), str):
        raise ProbeError("M3 v3 failure receipt lacks an error")


def build_plan(args: Any) -> dict[str, Any]:
    result = execute_v2.build_plan(args)
    plan = execute_v1._load(args.output.absolute(), label="M3 execution plan")
    result["required_stable_tx_runner_receipt"] = str(_runner_path(plan))
    return result


def execute_plan(args: Any, *, base_execute: Any | None = None) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = execute_v1._load(plan_path, label="M3 execution plan")
    execute_v1._validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(
            f"confirmation must be exactly {plan['confirmation_phrase']!r}"
        )
    runner_path = _runner_path(plan)
    execute_v1.probe_v1._require_new_private_output(runner_path)

    selected = base_execute or execute_v1.execute_plan

    def corrected_base(arguments: Any, **dependencies: Any) -> dict[str, Any]:
        with _stable_tx_driver_contract():
            return selected(arguments, **dependencies)

    failure: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        result = execute_v2.execute_plan(args, base_execute=corrected_base)
    except BaseException as error:  # noqa: BLE001 - seal every inherited outcome
        failure = error

    execution_path = Path(plan["execution_receipt_path"])
    inherited_path = execute_v2._runner_path(plan)
    execution_identity = (
        execute_v1._identity(execution_path, label="M3 execution receipt")
        if execution_path.exists()
        else None
    )
    inherited_identity = (
        execute_v1._identity(inherited_path, label="M3 v2 runner receipt")
        if inherited_path.exists()
        else None
    )
    execution = (
        execute_v1._load(execution_path, label="M3 execution receipt")
        if execution_path.exists()
        else None
    )
    runner = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 3,
        "receipt_id": uuid.uuid4().hex,
        "created_at": _now(),
        "outcome": "pass" if failure is None else "failed",
        "plan": execute_v1._identity(plan_path, label="M3 execution plan"),
        "execution_receipt": execution_identity,
        "inherited_runner_receipt": inherited_identity,
        "runner_source": _source_identity(
            sys.modules[__name__], label="M3 v3 runner source"
        ),
        "inherited_runner_source": _source_identity(
            execute_v2, label="M3 v2 runner source"
        ),
        "base_executor_source": _source_identity(
            execute_v1, label="M3 v1 executor source"
        ),
        "transmitter_driver_source": _source_identity(
            tx_v2, label="M3 v2 transmitter driver source"
        ),
        "receiver_monitor_source": _source_identity(
            monitor_v3, label="M3 v3 monitor source"
        ),
        "stable_channel_identity_policy": "id-direction-and-complete-gain-inventory",
        "module_binding_restored": execute_v1.SingleTxCyclicIio
        is not tx_v2.SingleTxCyclicIio,
        "hardware_accessed": (
            execution.get("hardware_accessed") is True
            if execution is not None
            else False
        ),
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": CLAIM_SCOPE,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    _validate_runner(runner, plan_path=plan_path, plan=plan)
    identity = execute_v1.probe_v1._write_new_private(runner_path, runner)
    if failure is not None:
        raise ProbeError(
            f"M3 v3 execution failed after writing {identity['path']}: {failure}"
        ) from failure
    if result is None:
        raise ProbeError("M3 v3 execution produced no result")
    return {
        **result,
        "stable_tx_channel_identity_contract_active": True,
        "stable_tx_runner_receipt": identity,
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    base = execute_v2.verify_receipt(args)
    plan_path = args.plan.absolute()
    plan = execute_v1._load(plan_path, label="M3 execution plan")
    runner_path = _runner_path(plan)
    runner = execute_v1._load(runner_path, label="M3 v3 runner receipt")
    _validate_runner(runner, plan_path=plan_path, plan=plan)
    if runner["outcome"] != base["outcome"]:
        raise ProbeError("inherited and v3 runner outcomes differ")
    return {
        **base,
        "stable_tx_channel_identity_contract_active": True,
        "stable_tx_runner_receipt_sha256": hashlib.sha256(
            runner_path.read_bytes()
        ).hexdigest(),
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
