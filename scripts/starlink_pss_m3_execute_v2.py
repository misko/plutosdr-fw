#!/usr/bin/env python3
"""Run M3 through the deterministic receiver-context monitor entry point.

The sealed v1 M3 execution plan and receipt remain authoritative.  This
versioned operational wrapper forces every receiver dwell through monitor v3
and writes a deterministic adjacent runner receipt binding the exact executor,
monitor, base receipt, and cleanup policy used for the attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_m3_execute_v1 as execute_v1
import scripts.starlink_pss_monitor_probe_v3 as monitor_v3

RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m3-runner-receipt.v2"
CLAIM_SCOPE = "cabled_campaign_transport_and_cleanup_only"
ProbeError = execute_v1.ProbeError
RUNNER_FIELDS = {
    "schema",
    "schema_version",
    "receipt_id",
    "created_at",
    "outcome",
    "plan",
    "execution_receipt",
    "runner_source",
    "base_executor_source",
    "receiver_monitor_source",
    "receiver_context_close_contract_active",
    "receiver_context_close_implementation",
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
    return base.with_name(f"{base.stem}-runner-v2.json")


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


def _validate_runner(
    runner: dict[str, Any], *, plan_path: Path, plan: dict[str, Any]
) -> None:
    if (
        set(runner) != RUNNER_FIELDS
        or runner.get("schema") != RECEIPT_SCHEMA
        or runner.get("schema_version") != 2
        or not isinstance(runner.get("receipt_id"), str)
        or len(runner["receipt_id"]) != 32
        or any(
            character not in "0123456789abcdef" for character in runner["receipt_id"]
        )
        or runner.get("outcome") not in {"pass", "failed"}
        or runner.get("plan")
        != execute_v1._identity(plan_path, label="M3 execution plan")
        or runner.get("runner_source")
        != _source_identity(sys.modules[__name__], label="M3 v2 runner source")
        or runner.get("base_executor_source")
        != _source_identity(execute_v1, label="M3 v1 executor source")
        or runner.get("receiver_monitor_source")
        != _source_identity(monitor_v3, label="M3 v3 monitor source")
        or runner.get("receiver_context_close_contract_active") is not True
        or runner.get("receiver_context_close_implementation")
        != "attested-ppu-modern-or-legacy-deterministic"
        or not isinstance(runner.get("hardware_accessed"), bool)
        or runner.get("persistent_write") is not False
        or runner.get("do_not_merge") is not True
        or runner.get("claim_scope") != CLAIM_SCOPE
        or runner.get("pss_detected") is not False
        or runner.get("sss_detected") is not False
        or runner.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M3 v2 runner receipt violates its cleanup-only contract")
    execute_v1.campaign._parse_time(runner.get("created_at"), label="runner created_at")
    execution = runner.get("execution_receipt")
    if execution is not None:
        execute_v1.campaign._validate_identity(execution, label="execution receipt")
        if execution != execute_v1._identity(
            Path(plan["execution_receipt_path"]), label="M3 execution receipt"
        ):
            raise ProbeError("M3 v2 runner binds a changed execution receipt")
        base_receipt = execute_v1._load(
            Path(plan["execution_receipt_path"]), label="M3 execution receipt"
        )
        if (
            base_receipt.get("outcome") != runner["outcome"]
            or (base_receipt.get("hardware_accessed") is True)
            is not runner["hardware_accessed"]
        ):
            raise ProbeError("M3 v2 runner and base execution outcomes differ")
    if (
        runner["outcome"] == "pass"
        and (
            execution is None
            or runner.get("hardware_accessed") is not True
            or runner.get("error") is not None
        )
    ) or (runner["outcome"] == "failed" and not isinstance(runner.get("error"), str)):
        raise ProbeError("M3 v2 runner outcome evidence is inconsistent")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="delegate v1 offline plan sealing")
    plan.add_argument("--campaign-plan", type=Path, required=True)
    plan.add_argument("--transmitter-topology", required=True)
    plan.add_argument("--ppu-repository", type=Path, required=True)
    plan.add_argument("--ppu-commit", required=True)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute", help="run with deterministic RX cleanup")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--receiver-state-root", type=Path, required=True)
    execute.add_argument("--receiver-timeout-s", type=float, default=240.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify base and v2 runner receipts")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_plan(args: Any) -> dict[str, Any]:
    result = execute_v1.build_plan(args)
    result["required_runner_receipt"] = str(
        _runner_path(
            execute_v1._load(args.output.absolute(), label="M3 execution plan")
        )
    )
    return result


def execute_plan(
    args: Any,
    *,
    base_execute: Any | None = None,
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = execute_v1._load(plan_path, label="M3 execution plan")
    execute_v1._validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(
            f"confirmation must be exactly {plan['confirmation_phrase']!r}"
        )
    runner_path = _runner_path(plan)
    execute_v1.probe_v1._require_new_private_output(runner_path)
    failure: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        selected = base_execute or execute_v1.execute_plan
        selected_dependencies = dependencies or {}
        if "monitor_execute" in selected_dependencies:
            raise ProbeError("M3 v2 receiver monitor cannot be overridden")
        result = selected(
            args,
            monitor_execute=monitor_v3.execute_plan,
            **selected_dependencies,
        )
    except BaseException as error:  # noqa: BLE001 - seal every base outcome
        failure = error
    execution_path = Path(plan["execution_receipt_path"])
    execution: dict[str, Any] | None = None
    execution_identity: dict[str, Any] | None = None
    if execution_path.exists():
        execution_identity = execute_v1._identity(
            execution_path, label="M3 execution receipt"
        )
        execution = execute_v1._load(execution_path, label="M3 execution receipt")
    runner = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 2,
        "receipt_id": uuid.uuid4().hex,
        "created_at": _now(),
        "outcome": "pass" if failure is None else "failed",
        "plan": execute_v1._identity(plan_path, label="M3 execution plan"),
        "execution_receipt": execution_identity,
        "runner_source": _source_identity(
            sys.modules[__name__], label="M3 v2 runner source"
        ),
        "base_executor_source": _source_identity(
            execute_v1, label="M3 v1 executor source"
        ),
        "receiver_monitor_source": _source_identity(
            monitor_v3, label="M3 v3 monitor source"
        ),
        "receiver_context_close_contract_active": True,
        "receiver_context_close_implementation": (
            "attested-ppu-modern-or-legacy-deterministic"
        ),
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
            f"M3 v2 execution failed after writing {identity['path']}: {failure}"
        ) from failure
    if result is None:
        raise ProbeError("M3 v2 execution produced no result")
    return {
        **result,
        "receiver_context_close_contract_active": True,
        "runner_receipt": identity,
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    base = execute_v1.verify_receipt(args)
    plan_path = args.plan.absolute()
    plan = execute_v1._load(plan_path, label="M3 execution plan")
    runner_path = _runner_path(plan)
    runner = execute_v1._load(runner_path, label="M3 v2 runner receipt")
    _validate_runner(runner, plan_path=plan_path, plan=plan)
    if runner["outcome"] != base["outcome"]:
        raise ProbeError("base execution and v2 runner outcomes differ")
    return {
        **base,
        "receiver_context_close_contract_active": True,
        "runner_receipt_sha256": hashlib.sha256(runner_path.read_bytes()).hexdigest(),
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
