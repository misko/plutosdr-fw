#!/usr/bin/env python3
"""Receipt-bound, ephemeral datapath-progress diagnostic for the v4 candidate.

The command never loads firmware or writes persistent radio storage. It binds
one locally built static ARM diagnostic binary into an offline plan, uploads
that exact binary only to the candidate runtime's /tmp, observes bounded FPGA
progress, removes the binary, restores RX attributes, and writes a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe as probe_v1
import scripts.starlink_pss_hardware_probe_v3 as probe_v3
import scripts.starlink_pss_hardware_probe_v5 as probe_v5
import scripts.starlink_pss_hardware_probe_v6 as probe_v6

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-progress-probe-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-progress-probe-receipt.v1"
REMOTE_PREFIX = "/tmp/starlink_pss_progress_diag"
MAXIMUM_BINARY_BYTES = 4 * 1024 * 1024
ProbeError = probe_v1.ProbeError


def _binary_identity(path: Path) -> tuple[dict[str, Any], bytes]:
    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
    except OSError as error:
        raise ProbeError(f"diagnostic binary cannot be opened safely: {error}") from error
    try:
        opened = os.fstat(descriptor)
        fingerprint = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o755
            or opened.st_size <= 0
            or opened.st_size > MAXIMUM_BINARY_BYTES
            or fingerprint
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            raise ProbeError("diagnostic binary is not one stable owned mode-0755 file")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            payload = stream.read(opened.st_size + 1)
        after = os.fstat(descriptor)
        if len(payload) != opened.st_size or fingerprint != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ProbeError("diagnostic binary changed during read")
    finally:
        os.close(descriptor)
    if (
        len(payload) < 20
        or payload[:4] != b"\x7fELF"
        or payload[4:6] != b"\x01\x01"
        or int.from_bytes(payload[18:20], "little") != 40
    ):
        raise ProbeError("diagnostic binary is not a 32-bit little-endian ARM ELF")
    try:
        program_headers = subprocess.run(
            ("readelf", "-lW", str(selected)),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ProbeError("diagnostic ELF program headers cannot be attested") from error
    if "INTERP" in program_headers:
        raise ProbeError("diagnostic binary must be statically linked")
    return {
        "path": str(selected),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }, payload


def _validate_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "plan_id",
        "created_at",
        "hardware_accessed",
        "persistent_write",
        "serial",
        "rate_msps",
        "runtime_target",
        "expected_firmware",
        "duration_ms",
        "ppu_repository",
        "ppu_source_commit",
        "probe_plan",
        "diagnostic_binary",
        "receipt_path",
        "confirmation_phrase",
    }
    if set(plan) != required:
        raise ProbeError("progress plan fields differ from the v1 schema")
    if (
        plan["schema"] != PLAN_SCHEMA
        or plan["schema_version"] != 1
        or plan["hardware_accessed"] is not False
        or plan["persistent_write"] is not False
        or plan["serial"] != probe_v1.ALLOCATED_SERIAL
        or plan["rate_msps"] not in (15, 30, 60)
        or plan["runtime_target"] != probe_v1.RUNTIME_TARGET
        or plan["expected_firmware"]
        != f"v0.50-plutoplus-starlink-pss-{plan['rate_msps']}m-rx-only-dnm-v4"
        or not isinstance(plan["duration_ms"], int)
        or not 100 <= plan["duration_ms"] <= 10_000
        or plan["confirmation_phrase"]
        != (
            f"DIAGNOSE STARLINK PSS DATAPATH {plan['serial']} "
            f"{plan['rate_msps']} MSPS"
        )
        or not Path(plan["receipt_path"]).is_absolute()
    ):
        raise ProbeError("progress plan values violate the v1 diagnostic contract")
    for label in ("probe_plan", "diagnostic_binary"):
        identity = plan[label]
        if (
            not isinstance(identity, dict)
            or set(identity) != {"path", "bytes", "sha256"}
            or not Path(identity["path"]).is_absolute()
            or not isinstance(identity["bytes"], int)
            or identity["bytes"] <= 0
            or not probe_v1.HEX_64.fullmatch(identity["sha256"])
        ):
            raise ProbeError(f"progress plan {label} identity is invalid")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="seal one offline progress diagnostic")
    plan.add_argument("--probe-plan", type=Path, required=True)
    plan.add_argument("--diagnostic-binary", type=Path, required=True)
    plan.add_argument("--duration-ms", type=int, default=1000)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute", help="run one confirmed diagnostic")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--state-root", type=Path, required=True)
    execute.add_argument("--timeout-s", type=float, default=90.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify a diagnostic receipt offline")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_plan(args: Any) -> dict[str, Any]:
    base_path = args.probe_plan.absolute()
    base = probe_v1._load_private_json(base_path, label="PSS probe plan")
    with probe_v6._v4_candidate_identity():
        probe_v6.probe_v2._validate_plan(base)
    binary, _payload = _binary_identity(args.diagnostic_binary)
    if not 100 <= args.duration_ms <= 10_000:
        raise ProbeError("diagnostic duration must lie in [100, 10000] ms")
    probe_v1._require_new_private_output(args.output)
    probe_v1._require_new_private_output(args.receipt)
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": base["serial"],
        "rate_msps": base["rate_msps"],
        "runtime_target": probe_v1.RUNTIME_TARGET,
        "expected_firmware": base["expected_firmware"],
        "duration_ms": args.duration_ms,
        "ppu_repository": base["ppu_repository"],
        "ppu_source_commit": base["ppu_source_commit"],
        "probe_plan": probe_v1._identity(base_path, label="PSS probe plan"),
        "diagnostic_binary": binary,
        "receipt_path": str(args.receipt.absolute()),
        "confirmation_phrase": (
            f"DIAGNOSE STARLINK PSS DATAPATH {base['serial']} "
            f"{base['rate_msps']} MSPS"
        ),
    }
    _validate_plan(plan)
    identity = probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_DIAGNOSTIC_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _upload_binary(
    *,
    backend: Any,
    target: Any,
    ssh_host: str,
    password_path: Path,
    ssh_builder: Any,
    payload: bytes,
    digest: str,
    remote: str,
    timeout_s: float,
) -> str:
    command = (
        f"umask 077 && test ! -e {remote} && cat > {remote} && "
        f"chmod 700 {remote} && sha256sum {remote}"
    )
    argv = ssh_builder(
        target,
        ssh_host=ssh_host,
        password_path=password_path,
        remote_command=command,
    )
    try:
        completed = subprocess.run(
            argv,
            input=payload,
            check=False,
            capture_output=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"ephemeral diagnostic upload failed: {error}") from error
    output = completed.stdout.decode(errors="replace").strip()
    if completed.returncode or output != f"{digest}  {remote}":
        detail = (completed.stdout + completed.stderr).decode(errors="replace")[-1000:]
        raise ProbeError(f"ephemeral diagnostic upload was not attested: {detail}")
    return remote


def _remove_binary(
    *,
    backend: Any,
    target: Any,
    ssh_host: str,
    password_path: Path,
    ssh_builder: Any,
    remote: str,
    timeout_s: float,
) -> None:
    argv = ssh_builder(
        target,
        ssh_host=ssh_host,
        password_path=password_path,
        remote_command=f"rm -f {remote} && test ! -e {remote}",
    )
    backend.runner.run(argv, timeout_s=timeout_s)


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
    target = handoff.operation.target
    context: Any = None
    originals: list[tuple[Any, str, str, str]] = []
    remote: str | None = None
    removed = False
    restored_values: dict[str, int] = {}
    measurement: dict[str, Any] | None = None
    try:
        uri = f"usb:{target.bus_number}.{target.device_number}.5"
        context = iio_module.Context(uri)
        setter = getattr(context, "set_timeout", None)
        if not callable(setter):
            raise ProbeError("exact USB-IIO context cannot set a timeout")
        setter(5000)
        attrs = {str(key): str(value) for key, value in context.attrs.items()}
        serial = attrs.get("hw_serial", attrs.get("usb,serial", attrs.get("serial", "")))
        if (
            serial != plan["serial"]
            or attrs.get("fw_version") != plan["expected_firmware"]
            or attrs.get("hw_model") != probe_v1.EXPECTED_MODEL
        ):
            raise ProbeError("USB-IIO serial, firmware, or model differs from the plan")
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        if phy is None or rx is None:
            raise ProbeError("RX-only runtime lacks PHY or RX capture core")
        phy_rx = probe_v1._channel(phy, "voltage0", False, label="PHY RX")
        capture_rx = probe_v1._channel(rx, "voltage0", False, label="capture RX")
        settings = (
            (phy_rx, "sampling_frequency", base["sample_rate_hz"], "PHY RX"),
            (capture_rx, "sampling_frequency", base["sample_rate_hz"], "capture RX"),
            (phy_rx, "rf_bandwidth", base["rf_bandwidth_hz"], "PHY RX"),
        )
        before, originals, selected = probe_v5._snapshot_and_apply(settings)
        available = tuple(
            int(value)
            for value in str(
                probe_v1._attribute(
                    capture_rx,
                    "sampling_frequency_available",
                    label="capture RX",
                ).value
            )
            .strip()
            .replace("[", "")
            .replace("]", "")
            .split()
        )
        reader = getattr(rx, "reg_read", None)
        if not callable(reader):
            raise ProbeError("capture RX does not expose FPGA decimation readback")
        try:
            adc_gp_control = int(reader(probe_v1.ADC_GP_CONTROL_REG)) & 0xFFFFFFFF
        except (OSError, TypeError, ValueError) as error:
            raise ProbeError("FPGA decimation readback failed") from error
        if available != (
            base["sample_rate_hz"],
            base["sample_rate_hz"] // 8,
        ) or adc_gp_control & 1:
            raise ProbeError("RX rate is not an exact factor-one capture path")
        remote = f"{REMOTE_PREFIX}-{plan['diagnostic_binary']['sha256'][:16]}"
        remote = _upload_binary(
            backend=backend,
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            payload=payload,
            digest=plan["diagnostic_binary"]["sha256"],
            remote=remote,
            timeout_s=max(30.0, plan["duration_ms"] / 1000.0 + 10.0),
        )
        diagnostic = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=(
                f"{remote} --expect-serial {plan['serial']} progress "
                f"--timeout-ms {plan['duration_ms']}"
            ),
            timeout_s=max(15.0, plan["duration_ms"] / 1000.0 + 10.0),
            ssh_builder=ssh_builder,
        )
        if (
            diagnostic.get("schema") != "starlink-pss-acqctl.progress.v1"
            or diagnostic.get("claim_scope") != "datapath_progress_diagnostic_only"
            or diagnostic.get("serial") != plan["serial"]
            or diagnostic.get("input_rate_msps") != plan["rate_msps"]
            or diagnostic.get("duration_ms") != plan["duration_ms"]
            or diagnostic.get("pss_detected") is not False
            or diagnostic.get("frame_lock_claim") is not False
        ):
            raise ProbeError("progress JSON violates the diagnostic-only contract")
        _remove_binary(
            backend=backend,
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            remote=remote,
            timeout_s=15.0,
        )
        removed = True
        measurement = {
            "iio_uri": uri,
            "iio_before": before,
            "iio_selected": selected,
            "capture_rates_available_hz": available,
            "adc_gp_control": adc_gp_control,
            "fpga_decimation_factor": 1,
            "diagnostic_binary_upload_verified": True,
            "diagnostic_binary_removed": True,
            "diagnostic": diagnostic,
        }
    finally:
        cleanup_errors: list[str] = []
        if remote is not None and not removed:
            try:
                _remove_binary(
                    backend=backend,
                    target=target,
                    ssh_host=handoff.operation.ssh_host,
                    password_path=password.path,
                    ssh_builder=ssh_builder,
                    remote=remote,
                    timeout_s=15.0,
                )
                removed = True
            except Exception as error:  # noqa: BLE001 - preserve all cleanup evidence
                cleanup_errors.append(f"remote binary: {error}")
        priorities = {
            ("PHY RX", "rf_bandwidth"): 0,
            ("PHY RX", "sampling_frequency"): 1,
            ("capture RX", "sampling_frequency"): 2,
        }
        for channel, name, original, label in sorted(
            originals, key=lambda item: priorities.get((item[3], item[1]), 3)
        ):
            try:
                attribute = probe_v1._attribute(channel, name, label=label)
                attribute.value = original
                requested = probe_v1._number(original, label=f"original {label} {name}")
                observed = probe_v1._number(
                    attribute.value, label=f"restored {label} {name}"
                )
                if abs(observed - requested) > max(2.0, abs(requested) * 100e-6):
                    raise ProbeError(f"restored {label} {name} differs from original")
                restored_values[
                    f"{label.lower().replace(' ', '_')}_{name}"
                ] = round(observed)
            except Exception as error:  # noqa: BLE001 - preserve all cleanup evidence
                cleanup_errors.append(f"{label} {name}: {error}")
        if context is not None:
            close = getattr(context, "close", None)
            if callable(close):
                with suppress(BaseException):
                    close()
        if cleanup_errors:
            raise ProbeError("progress cleanup failed: " + "; ".join(cleanup_errors))
        if measurement is not None:
            measurement["iio_restore_verified"] = bool(originals)
            measurement["iio_restored"] = restored_values
    if measurement is None:
        raise ProbeError("progress measurement did not complete")
    return measurement


def execute_plan(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = probe_v1._load_private_json(plan_path, label="progress plan")
    _validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    if Path(plan["receipt_path"]) != args.output.absolute():
        raise ProbeError("execute output differs from the sealed receipt path")
    probe_v1._require_new_private_output(args.output)
    observed_probe = probe_v1._identity(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    if observed_probe != plan["probe_plan"]:
        raise ProbeError("bound PSS probe plan changed")
    binary, payload = _binary_identity(Path(plan["diagnostic_binary"]["path"]))
    if binary != plan["diagnostic_binary"]:
        raise ProbeError("bound diagnostic binary changed")
    base = probe_v1._load_private_json(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    with probe_v6._v4_candidate_identity():
        probe_v6.probe_v2._validate_plan(base)
        handoff = probe_v6.probe_v2._load_handoff(
            ppu_repository=Path(base["ppu_repository"]),
            ppu_commit=base["ppu_source_commit"],
            candidate_path=Path(base["candidate_plan"]["path"]),
            operation_path=Path(base["operation_plan"]["path"]),
            ram_receipt_path=Path(base["ram_receipt"]["path"]),
            rate_msps=base["rate_msps"],
        )
    if args.timeout_s <= 0 or not args.state_root.is_absolute() or ".." in args.state_root.parts:
        raise ProbeError("execution timeout and state root are invalid")
    try:
        password = handoff.ppu.lifecycle.validate_password_file(args.ssh_password_file)
        iio_module = importlib.import_module("iio")
    except (ImportError, OSError, ValueError) as error:
        raise ProbeError(f"progress dependency cannot be attested: {error}") from error
    backend = handoff.ppu.linux.LinuxRxOnlyReleaseCandidateBackend(
        state_root=args.state_root.absolute(), timeout_s=args.timeout_s
    )
    started = datetime.now(UTC)
    route = None
    route_released = False
    runtime: Any = None
    measurement: dict[str, Any] | None = None
    failure: BaseException | None = None
    try:
        live_target = probe_v3._resolve_live_target(backend, handoff.operation.target)
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
                measurement = _execute_measurement(
                    plan,
                    base,
                    live_handoff,
                    backend,
                    password,
                    iio_module,
                    handoff.ppu.lifecycle.ssh_fixed_argv,
                    payload,
                )
            finally:
                if route is not None:
                    backend.release_host_route(route)
                    route_released = True
    except Exception as error:  # noqa: BLE001 - every hardware outcome gets a receipt
        failure = error
    completed = datetime.now(UTC)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "outcome": "pass" if failure is None else "failed",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "plan": probe_v1._identity(plan_path, label="progress plan"),
        "serial": plan["serial"],
        "rate_msps": plan["rate_msps"],
        "runtime_target": probe_v1.RUNTIME_TARGET,
        "expected_firmware": plan["expected_firmware"],
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": "datapath_progress_diagnostic_only",
        "pss_detected": False,
        "frame_lock_claim": False,
        "runtime": None if runtime is None else runtime.model_dump(mode="json"),
        "measurement": measurement,
        "route_release_verified": route_released,
        "recovery_required": True,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    identity = probe_v1._write_new_private(args.output, receipt)
    if failure is not None:
        raise ProbeError(f"progress probe failed after writing {identity['path']}: {failure}")
    return {
        "verdict": "PASS_DATAPATH_PROGRESS_DIAGNOSTIC_ONLY",
        "hardware_accessed": True,
        "persistent_write": False,
        "pss_detected": False,
        "frame_lock_claim": False,
        "receipt": identity,
        "next_gate": "PPU candidate-ram recover before interpreting progress counters",
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    plan = probe_v1._load_private_json(args.plan.absolute(), label="progress plan")
    _validate_plan(plan)
    receipt = probe_v1._load_private_json(args.receipt.absolute(), label="progress receipt")
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("plan")
        != probe_v1._identity(args.plan.absolute(), label="progress plan")
        or receipt.get("serial") != plan["serial"]
        or receipt.get("rate_msps") != plan["rate_msps"]
        or receipt.get("persistent_write") is not False
        or receipt.get("claim_scope") != "datapath_progress_diagnostic_only"
        or receipt.get("pss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("recovery_required") is not True
        or receipt.get("outcome") not in ("pass", "failed")
    ):
        raise ProbeError("progress receipt violates its diagnostic-only plan")
    return {
        "verdict": "PASS_RECEIPT_STRUCTURE",
        "outcome": receipt["outcome"],
        "persistent_write": False,
        "pss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": True,
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = build_plan(args)
        elif args.command == "execute":
            result = execute_plan(args)
        else:
            result = verify_receipt(args)
    except (OSError, ValueError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
