#!/usr/bin/env python3
"""Receipt-bound post-RAM Starlink PSS acquisition probe.

The ``plan`` command is offline.  It accepts only a passing PPU RX-only v2 RAM
receipt and creates a serial/rate-specific measurement plan.  The ``execute``
command revalidates that complete contract bundle, acquires PPU's exact radio
and route locks, configures only the RX sample-rate path, runs the fixed
``starlink_pss_acqctl`` commands, restores the RX attributes, and emits a
receipt.  It never invokes DFU or writes persistent radio storage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-hardware-probe-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-hardware-probe-receipt.v1"
ALLOCATED_SERIAL = "104000bac4950008230026001b440a003a"
PPU_SLUG = "misko/pluto-plus-utils"
EXPECTED_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9363A)"
RUNTIME_TARGET = "ad9363a-1r1t"
SUPPORTED_RATES = (15, 30, 60)
MAX_RF_BANDWIDTH_HZ = 20_000_000
ADC_GP_CONTROL_REG = 0x800000BC
MAX_JSON_BYTES = 4 * 1024 * 1024
HEX_32 = re.compile(r"^[0-9a-f]{32}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class ProbeError(RuntimeError):
    """The probe cannot prove its exact input, execution, or cleanup state."""


def _stat_identity(state: os.stat_result) -> tuple[int, ...]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_mode,
        state.st_uid,
        state.st_nlink,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProbeError(f"JSON contains duplicate key {key!r}")
        value[key] = item
    return value


def _private_file(path: Path, *, label: str) -> bytes:
    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
    except OSError as error:
        raise ProbeError(f"{label} cannot be opened safely: {error}") from error
    try:
        opened = os.fstat(descriptor)
        identity = _stat_identity(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size <= 0
            or opened.st_size > MAX_JSON_BYTES
            or identity
            != _stat_identity(before)
        ):
            raise ProbeError(f"{label} is not one stable owned mode-0600 file")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            if not chunk:
                raise ProbeError(f"{label} was truncated while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ProbeError(f"{label} grew while reading")
        if identity != _stat_identity(os.fstat(descriptor)):
            raise ProbeError(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _load_private_json(path: Path, *, label: str) -> dict[str, Any]:
    payload = _private_file(path, label=label)
    try:
        value = json.loads(payload, object_pairs_hook=_json_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise ProbeError(f"{label} is not one canonical JSON object")
    return value


def _identity(path: Path, *, label: str) -> dict[str, Any]:
    payload = _private_file(path, label=label)
    return {
        "path": str(path.absolute()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_new_private(path: Path, value: object) -> dict[str, Any]:
    selected = path.absolute()
    _require_new_private_output(selected)
    payload = _canonical(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(selected, flags, 0o600)
    except OSError as error:
        raise ProbeError(f"refusing unavailable or existing output {selected}: {error}") from error
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise ProbeError("could not write the complete private output")
            offset += written
        os.fsync(descriptor)
    except BaseException:
        with suppress(OSError):
            selected.unlink()
        raise
    finally:
        os.close(descriptor)
    return {
        "path": str(selected),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _require_new_private_output(path: Path) -> None:
    selected = path.absolute()
    parent = selected.parent
    try:
        state = parent.lstat()
    except OSError as error:
        raise ProbeError(f"output parent cannot be inspected: {error}") from error
    if (
        not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != 0o700
    ):
        raise ProbeError("output parent must be an owned mode-0700 directory")
    try:
        selected.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ProbeError(f"output path cannot be inspected: {error}") from error
    raise ProbeError(f"refusing unavailable or existing output {selected}")


def _verify_ppu_repository(repository: Path, commit: str) -> Path:
    selected = repository.absolute()
    if HEX_40.fullmatch(commit) is None:
        raise ProbeError("PPU commit must be one lowercase 40-hex identity")

    def git(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ("git", "-C", str(selected), *arguments),
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ProbeError("PPU repository cannot be attested") from error
        return result.stdout.strip()

    remote = git("remote", "get-url", "origin").removesuffix(".git").replace(":", "/")
    if (
        Path(git("rev-parse", "--show-toplevel")).absolute() != selected
        or git("rev-parse", "HEAD") != commit
        or git("status", "--porcelain=v1", "--untracked-files=all")
        or not remote.endswith(f"/{PPU_SLUG}")
    ):
        raise ProbeError("PPU repository is not the exact clean expected checkout")
    return selected


def _import_ppu(repository: Path) -> SimpleNamespace:
    source = str(repository / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    try:
        candidate = importlib.import_module("pluto_plus.release_candidate")
        rx = importlib.import_module("pluto_plus.release_candidate_rx_only")
        lifecycle = importlib.import_module(
            "pluto_plus.release_candidate_rx_only_lifecycle"
        )
        linux = importlib.import_module("pluto_plus.release_candidate_rx_only_linux")
    except (ImportError, OSError) as error:
        raise ProbeError("exact PPU source cannot be imported") from error
    expected_root = (repository / "src").resolve()
    for module in (candidate, rx, lifecycle, linux):
        module_path = Path(str(module.__file__)).resolve()
        if not module_path.is_relative_to(expected_root):
            raise ProbeError("imported PPU module is outside the attested checkout")
    return SimpleNamespace(candidate=candidate, rx=rx, lifecycle=lifecycle, linux=linux)


def _load_handoff(
    *,
    ppu_repository: Path,
    ppu_commit: str,
    candidate_path: Path,
    operation_path: Path,
    ram_receipt_path: Path,
    rate_msps: int,
) -> SimpleNamespace:
    repository = _verify_ppu_repository(ppu_repository, ppu_commit)
    ppu = _import_ppu(repository)
    try:
        candidate = ppu.candidate.load_private_contract(
            candidate_path.absolute(), ppu.rx.ReleaseCandidatePlanV2
        )
        operation = ppu.candidate.load_private_contract(
            operation_path.absolute(), ppu.rx.ReleaseCandidateOperationPlanV2
        )
        receipt = ppu.candidate.load_private_contract(
            ram_receipt_path.absolute(), ppu.rx.ReleaseCandidateRamReceiptV2
        )
        ppu.rx.validate_rx_only_contract_bundle(
            candidate,
            operation,
            receipt,
            candidate_path=candidate_path.absolute(),
            operation_path=operation_path.absolute(),
        )
    except (OSError, ValueError, ppu.candidate.ReleaseCandidateContractError) as error:
        raise ProbeError(f"PPU RAM handoff is invalid: {error}") from error
    expected_version = f"v0.50-plutoplus-starlink-pss-{rate_msps}m-rx-only-dnm-v2"
    if (
        receipt.outcome != "pass"
        or not receipt.cleanup.verified
        or not receipt.host_route.release_verified
        or receipt.transition.persistent_write
        or candidate.expected_runtime.firmware_version != expected_version
        or candidate.expected_runtime.hardware_model != EXPECTED_MODEL
        or candidate.device_tool_repository != PPU_SLUG
        or candidate.device_tool_source_commit != ppu_commit
        or operation.runtime_target != RUNTIME_TARGET
        or operation.target.serial != ALLOCATED_SERIAL
        or receipt.target != operation.target
        or receipt.runtime_target != RUNTIME_TARGET
    ):
        raise ProbeError("PPU RAM handoff is not a passing allocated-radio AD9363A trial")
    return SimpleNamespace(
        ppu=ppu,
        candidate=candidate,
        operation=operation,
        receipt=receipt,
        repository=repository,
    )


def _confirmation(serial: str, rate_msps: int) -> str:
    return f"RUN STARLINK PSS CANDIDATE {serial} {rate_msps} MSPS"


def _validate_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "plan_id",
        "created_at",
        "do_not_merge",
        "allowed_operation",
        "hardware_accessed",
        "persistent_write",
        "serial",
        "rate_msps",
        "sample_rate_hz",
        "rf_bandwidth_hz",
        "runtime_target",
        "expected_firmware",
        "ppu_repository",
        "ppu_source_commit",
        "candidate_plan",
        "operation_plan",
        "ram_receipt",
        "controller_timeout_ms",
        "confirmation_phrase",
        "receipt_path",
    }
    if set(plan) != required:
        raise ProbeError("probe plan field inventory is not exact")
    rate = plan.get("rate_msps")
    serial = plan.get("serial")
    bandwidth = plan.get("rf_bandwidth_hz")
    timeout = plan.get("controller_timeout_ms")
    created_at = plan.get("created_at")
    try:
        created = datetime.fromisoformat(str(created_at).removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ProbeError("probe plan creation time is not canonical UTC") from error
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != 1
        or HEX_32.fullmatch(str(plan.get("plan_id", ""))) is None
        or not isinstance(created_at, str)
        or not created_at.endswith("Z")
        or created.tzinfo != UTC
        or plan.get("do_not_merge") is not True
        or plan.get("allowed_operation") != "rx-only-candidate-measurement"
        or plan.get("hardware_accessed") is not False
        or plan.get("persistent_write") is not False
        or serial != ALLOCATED_SERIAL
        or rate not in SUPPORTED_RATES
        or plan.get("sample_rate_hz") != rate * 1_000_000
        or isinstance(bandwidth, bool)
        or not isinstance(bandwidth, int)
        or bandwidth <= 0
        or bandwidth > min(MAX_RF_BANDWIDTH_HZ, rate * 1_000_000)
        or plan.get("runtime_target") != RUNTIME_TARGET
        or plan.get("expected_firmware")
        != f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v2"
        or HEX_40.fullmatch(str(plan.get("ppu_source_commit", ""))) is None
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or timeout < 1000
        or timeout > 60000
        or plan.get("confirmation_phrase") != _confirmation(serial, rate)
    ):
        raise ProbeError("probe plan policy or rate identity is invalid")
    for label in ("candidate_plan", "operation_plan", "ram_receipt"):
        identity = plan.get(label)
        if (
            not isinstance(identity, dict)
            or set(identity) != {"path", "bytes", "sha256"}
            or not isinstance(identity.get("path"), str)
            or not Path(identity["path"]).is_absolute()
            or isinstance(identity.get("bytes"), bool)
            or not isinstance(identity.get("bytes"), int)
            or identity["bytes"] <= 0
            or HEX_64.fullmatch(str(identity.get("sha256", ""))) is None
        ):
            raise ProbeError(f"probe plan {label} identity is invalid")
    repository = plan.get("ppu_repository")
    receipt_path = plan.get("receipt_path")
    if (
        not isinstance(repository, str)
        or not Path(repository).is_absolute()
        or ".." in Path(repository).parts
        or not isinstance(receipt_path, str)
        or not Path(receipt_path).is_absolute()
        or ".." in Path(receipt_path).parts
    ):
        raise ProbeError("probe plan paths must be absolute")
    paths = [Path(plan[label]["path"]) for label in ("candidate_plan", "operation_plan", "ram_receipt")]
    if len(set(paths + [Path(receipt_path)])) != 4:
        raise ProbeError("probe inputs and receipt path must be distinct")


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    rate = args.rate
    if rate not in SUPPORTED_RATES:
        raise ProbeError("rate must be exactly 15, 30, or 60 MS/s")
    handoff = _load_handoff(
        ppu_repository=args.ppu_repository,
        ppu_commit=args.ppu_commit,
        candidate_path=args.candidate_plan,
        operation_path=args.operation_plan,
        ram_receipt_path=args.ram_receipt,
        rate_msps=rate,
    )
    _require_new_private_output(args.receipt)
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "do_not_merge": True,
        "allowed_operation": "rx-only-candidate-measurement",
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": ALLOCATED_SERIAL,
        "rate_msps": rate,
        "sample_rate_hz": rate * 1_000_000,
        "rf_bandwidth_hz": args.rf_bandwidth_hz,
        "runtime_target": RUNTIME_TARGET,
        "expected_firmware": handoff.candidate.expected_runtime.firmware_version,
        "ppu_repository": str(handoff.repository),
        "ppu_source_commit": args.ppu_commit,
        "candidate_plan": _identity(args.candidate_plan, label="candidate plan"),
        "operation_plan": _identity(args.operation_plan, label="operation plan"),
        "ram_receipt": _identity(args.ram_receipt, label="RAM receipt"),
        "controller_timeout_ms": args.controller_timeout_ms,
        "confirmation_phrase": _confirmation(ALLOCATED_SERIAL, rate),
        "receipt_path": str(args.receipt.absolute()),
    }
    _validate_plan(plan)
    identity = _write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE",
        "hardware_accessed": False,
        "will_write_qspi": False,
        "will_load_volatile_ram": False,
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _number(value: Any, *, label: str) -> float:
    try:
        result = float(str(value).strip().split()[0])
    except (IndexError, TypeError, ValueError) as error:
        raise ProbeError(f"{label} is not numeric") from error
    if not math.isfinite(result):
        raise ProbeError(f"{label} is not finite")
    return result


def _channel(device: Any, identifier: str, output: bool, *, label: str) -> Any:
    channel = device.find_channel(identifier, output)
    if channel is None:
        raise ProbeError(f"{label} channel {identifier!r} is absent")
    return channel


def _attribute(channel: Any, name: str, *, label: str) -> Any:
    attribute = getattr(channel, "attrs", {}).get(name)
    if attribute is None:
        raise ProbeError(f"{label} attribute {name!r} is absent")
    return attribute


def _write_numeric(
    channel: Any, name: str, requested: int, tolerance: float, *, label: str
) -> int:
    attribute = _attribute(channel, name, label=label)
    attribute.value = str(requested)
    observed = round(_number(attribute.value, label=f"{label} {name}"))
    if abs(observed - requested) > tolerance:
        raise ProbeError(
            f"{label} {name} readback {observed} differs from {requested}"
        )
    return observed


def _remote_json(
    backend: Any,
    target: Any,
    *,
    ssh_host: str,
    password_path: Path,
    command: str,
    timeout_s: float,
    ssh_builder: Callable[..., tuple[str, ...]],
) -> dict[str, Any]:
    argv = ssh_builder(
        target,
        ssh_host=ssh_host,
        password_path=password_path,
        remote_command=command,
    )
    output = backend.runner.run(argv, timeout_s=timeout_s)
    try:
        value = json.loads(output, object_pairs_hook=_json_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeError("controller did not emit one JSON document") from error
    if not isinstance(value, dict):
        raise ProbeError("controller output is not one JSON object")
    return value


def _measure(
    plan: dict[str, Any],
    handoff: SimpleNamespace,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Callable[..., tuple[str, ...]],
) -> dict[str, Any]:
    target = handoff.operation.target
    context: Any = None
    originals: list[tuple[Any, str, str, str]] = []
    restored = False
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
            or attrs.get("hw_model") != EXPECTED_MODEL
        ):
            raise ProbeError("USB-IIO serial, firmware, or model differs from the plan")
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        if phy is None or rx is None:
            raise ProbeError("RX-only runtime lacks PHY or RX capture core")
        phy_rx = _channel(phy, "voltage0", False, label="PHY RX")
        capture_rx = _channel(rx, "voltage0", False, label="capture RX")
        settings = (
            (phy_rx, "sampling_frequency", plan["sample_rate_hz"], "PHY RX"),
            (capture_rx, "sampling_frequency", plan["sample_rate_hz"], "capture RX"),
            (phy_rx, "rf_bandwidth", plan["rf_bandwidth_hz"], "PHY RX"),
        )
        before: dict[str, str] = {}
        selected: dict[str, int] = {}
        for channel, name, requested, label in settings:
            attribute = _attribute(channel, name, label=label)
            original = str(attribute.value)
            key = f"{label.lower().replace(' ', '_')}_{name}"
            before[key] = original
            originals.append((channel, name, original, label))
            tolerance = max(2.0, requested * 100e-6)
            selected[key] = _write_numeric(
                channel, name, requested, tolerance, label=label
            )

        available = tuple(
            int(value)
            for value in str(
                _attribute(
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
            adc_gp_control = int(reader(ADC_GP_CONTROL_REG)) & 0xFFFFFFFF
        except (OSError, TypeError, ValueError) as error:
            raise ProbeError("FPGA decimation readback failed") from error
        if available != (
            plan["sample_rate_hz"],
            plan["sample_rate_hz"] // 8,
        ) or adc_gp_control & 1:
            raise ProbeError("RX rate is not an exact factor-one capture path")

        serial = plan["serial"]
        binary = "/usr/sbin/starlink_pss_acqctl"
        common = f"{binary} --expect-serial {serial}"
        timeout_s = max(10.0, plan["controller_timeout_ms"] / 1000.0 + 5.0)
        info = _remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        before_snapshot = _remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} snapshot --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        candidate = _remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} candidate --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        after_snapshot = _remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} snapshot --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        final_info = _remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        try:
            initial_status = int(str(info.get("status", "")), 0)
            final_status = int(str(final_info.get("status", "")), 0)
        except ValueError as error:
            raise ProbeError("controller status is not a numeric hex word") from error
        if (
            info.get("schema") != "starlink-pss-acqctl.info.v1"
            or info.get("claim_scope") != "hardware_contract_only"
            or info.get("serial") != serial
            or info.get("input_rate_msps") != plan["rate_msps"]
            or initial_status & 0x2
            or before_snapshot.get("schema") != "starlink-pss-acqctl.snapshot.v1"
            or before_snapshot.get("serial") != serial
            or candidate.get("schema") != "starlink-pss-acqctl.candidate.v1"
            or candidate.get("claim_scope") != "candidate_measurement_only"
            or candidate.get("serial") != serial
            or candidate.get("input_rate_msps") != plan["rate_msps"]
            or candidate.get("continuity_ok") is not True
            or candidate.get("threshold_decision") is not None
            or candidate.get("frame_lock_claim") is not False
            or candidate.get("fault_free_epoch") is not True
            or after_snapshot.get("schema") != "starlink-pss-acqctl.snapshot.v1"
            or after_snapshot.get("serial") != serial
            or after_snapshot.get("fault_free_epoch") is not True
            or final_info.get("schema") != "starlink-pss-acqctl.info.v1"
            or final_info.get("serial") != serial
            or final_info.get("input_rate_msps") != plan["rate_msps"]
            or final_status & 0x2
        ):
            raise ProbeError("controller JSON does not satisfy the measurement-only contract")
        measurement = {
            "iio_uri": uri,
            "iio_before": before,
            "iio_selected": selected,
            "capture_rates_available_hz": available,
            "adc_gp_control": adc_gp_control,
            "fpga_decimation_factor": 1,
            "controller_info": info,
            "snapshot_before": before_snapshot,
            "candidate": candidate,
            "snapshot_after": after_snapshot,
            "controller_info_after": final_info,
        }
    finally:
        errors: list[str] = []
        # Restore bandwidth first, then the RFIC source rate before its FPGA
        # capture child.  This mirrors PPU's source-locked programming order.
        priorities = {
            ("PHY RX", "rf_bandwidth"): 0,
            ("PHY RX", "sampling_frequency"): 1,
            ("capture RX", "sampling_frequency"): 2,
        }
        restore_order = sorted(
            originals,
            key=lambda item: priorities.get((item[3], item[1]), 3),
        )
        for channel, name, original, label in restore_order:
            try:
                attribute = _attribute(channel, name, label=label)
                attribute.value = original
                requested = _number(original, label=f"original {label} {name}")
                observed = _number(attribute.value, label=f"restored {label} {name}")
                if abs(observed - requested) > max(2.0, abs(requested) * 100e-6):
                    raise ProbeError(
                        f"restored {label} {name} readback {observed} differs from {requested}"
                    )
                key = f"{label.lower().replace(' ', '_')}_{name}"
                restored_values[key] = round(observed)
            except Exception as error:  # noqa: BLE001 - restoration is best-effort inventory
                errors.append(f"{label} {name}: {error}")
        restored = bool(originals) and not errors
        if context is not None:
            close = getattr(context, "close", None)
            if callable(close):
                with suppress(BaseException):
                    close()
        if errors:
            raise ProbeError("RX attribute restoration failed: " + "; ".join(errors))
        if originals and not restored:
            raise ProbeError("RX attribute restoration was not verified")
    if measurement is None:
        raise ProbeError("probe measurement did not complete")
    measurement["iio_restore_verified"] = restored
    measurement["iio_restored"] = restored_values
    return measurement


def execute_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load_private_json(plan_path, label="probe plan")
    _validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    for label in ("candidate_plan", "operation_plan", "ram_receipt"):
        expected = plan[label]
        observed = _identity(Path(expected["path"]), label=label.replace("_", " "))
        if observed != expected:
            raise ProbeError(f"probe plan no longer binds the exact {label}")
    handoff = _load_handoff(
        ppu_repository=Path(plan["ppu_repository"]),
        ppu_commit=plan["ppu_source_commit"],
        candidate_path=Path(plan["candidate_plan"]["path"]),
        operation_path=Path(plan["operation_plan"]["path"]),
        ram_receipt_path=Path(plan["ram_receipt"]["path"]),
        rate_msps=plan["rate_msps"],
    )
    if Path(plan["receipt_path"]) != args.output.absolute():
        raise ProbeError("execute output differs from the sealed receipt path")
    _require_new_private_output(args.output)
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
    try:
        with backend.transaction_locks(
            handoff.operation.target, handoff.operation.ssh_host
        ):
            fresh = backend.revalidate_target(handoff.operation.target)
            if fresh != handoff.operation.target:
                raise ProbeError("live target differs from the sealed PPU operation")
            route = backend.acquire_host_route(
                handoff.operation.target, handoff.operation.ssh_host
            )
            try:
                runtime = backend.attest_rx_only_runtime_v2(
                    handoff.operation.target,
                    runtime_target=RUNTIME_TARGET,
                    expected_firmware=plan["expected_firmware"],
                    password=password,
                    route=route,
                )
                measurement = _measure(
                    plan,
                    handoff,
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
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "outcome": "pass" if failure is None else "failed",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "plan": _identity(plan_path, label="probe plan"),
        "serial": plan["serial"],
        "rate_msps": plan["rate_msps"],
        "runtime_target": RUNTIME_TARGET,
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
    identity = _write_new_private(args.output, receipt)
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


def _validate_receipt(receipt: dict[str, Any], plan: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "receipt_id",
        "outcome",
        "started_at",
        "completed_at",
        "plan",
        "serial",
        "rate_msps",
        "runtime_target",
        "expected_firmware",
        "hardware_accessed",
        "persistent_write",
        "claim_scope",
        "runtime",
        "measurement",
        "route_release_verified",
        "recovery_required",
        "error",
    }
    if set(receipt) != required:
        raise ProbeError("probe receipt field inventory is not exact")
    try:
        started = datetime.fromisoformat(
            str(receipt.get("started_at", "")).removesuffix("Z") + "+00:00"
        )
        completed = datetime.fromisoformat(
            str(receipt.get("completed_at", "")).removesuffix("Z") + "+00:00"
        )
    except ValueError as error:
        raise ProbeError("probe receipt timestamps are not canonical UTC") from error
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or HEX_32.fullmatch(str(receipt.get("receipt_id", ""))) is None
        or not str(receipt.get("started_at", "")).endswith("Z")
        or not str(receipt.get("completed_at", "")).endswith("Z")
        or started.tzinfo != UTC
        or completed.tzinfo != UTC
        or completed < started
        or receipt.get("outcome") not in {"pass", "failed"}
        or receipt.get("serial") != plan["serial"]
        or receipt.get("rate_msps") != plan["rate_msps"]
        or receipt.get("runtime_target") != plan["runtime_target"]
        or receipt.get("expected_firmware") != plan["expected_firmware"]
        or receipt.get("hardware_accessed") is not True
        or receipt.get("persistent_write") is not False
        or receipt.get("claim_scope") != "candidate_measurement_only"
        or receipt.get("recovery_required") is not True
    ):
        raise ProbeError("probe receipt identity or policy is invalid")
def verify_receipt(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    receipt_path = args.receipt.absolute()
    plan = _load_private_json(plan_path, label="probe plan")
    _validate_plan(plan)
    receipt = _load_private_json(receipt_path, label="probe receipt")
    _validate_receipt(receipt, plan)
    if receipt["plan"] != _identity(plan_path, label="probe plan"):
        raise ProbeError("probe receipt does not bind the exact plan bytes")
    if Path(plan["receipt_path"]) != receipt_path:
        raise ProbeError("probe receipt path differs from the sealed plan")
    if receipt["outcome"] == "pass":
        measurement = receipt["measurement"]
        if (
            not isinstance(receipt["runtime"], dict)
            or not isinstance(measurement, dict)
            or receipt["route_release_verified"] is not True
            or receipt["error"] is not None
            or measurement.get("iio_restore_verified") is not True
            or not isinstance(measurement.get("iio_restored"), dict)
        ):
            raise ProbeError("passing probe receipt lacks runtime, restore, or route proof")
        candidate = measurement.get("candidate")
        final_info = measurement.get("controller_info_after")
        if (
            not isinstance(candidate, dict)
            or candidate.get("schema") != "starlink-pss-acqctl.candidate.v1"
            or candidate.get("serial") != plan["serial"]
            or candidate.get("input_rate_msps") != plan["rate_msps"]
            or candidate.get("claim_scope") != "candidate_measurement_only"
            or candidate.get("continuity_ok") is not True
            or candidate.get("threshold_decision") is not None
            or candidate.get("frame_lock_claim") is not False
            or candidate.get("fault_free_epoch") is not True
            or not isinstance(final_info, dict)
            or int(str(final_info.get("status", "")), 0) & 0x2
        ):
            raise ProbeError("passing probe receipt violates the controller contract")
    elif (
        not isinstance(receipt["error"], str)
        or not receipt["error"]
        or receipt["measurement"] is not None
    ):
        raise ProbeError("failed probe receipt lacks its fail-closed error state")
    return {
        "verdict": "PASS_RECEIPT_STRUCTURE",
        "outcome": receipt["outcome"],
        "candidate_measurement_only": True,
        "frame_lock_claim": False,
        "persistent_write": False,
        "recovery_required": True,
        "receipt_sha256": hashlib.sha256(_canonical(receipt)).hexdigest(),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="build an offline receipt-bound probe plan")
    plan.add_argument("--ppu-repository", type=Path, required=True)
    plan.add_argument("--ppu-commit", required=True)
    plan.add_argument("--candidate-plan", type=Path, required=True)
    plan.add_argument("--operation-plan", type=Path, required=True)
    plan.add_argument("--ram-receipt", type=Path, required=True)
    plan.add_argument("--rate", type=int, choices=SUPPORTED_RATES, required=True)
    plan.add_argument("--rf-bandwidth-hz", type=int, required=True)
    plan.add_argument("--controller-timeout-ms", type=int, default=5000)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute", help="run one confirmed exact-radio probe")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--state-root", type=Path, required=True)
    execute.add_argument("--timeout-s", type=float, default=45.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify one probe receipt offline")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return root


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
