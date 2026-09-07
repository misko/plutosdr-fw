#!/usr/bin/env python3
"""Plan, execute, and verify the guarded cabled 15 MS/s M3 sequence.

The executor owns exactly one transmitter through PPU's shared serial lock,
opens it by its freshly resolved USB bus/device address, and holds the cyclic
IIO buffer while the existing exact-receiver monitor runs.  Every exit path
attempts a final transmitter mute.  This is DNM-only and never writes radio
persistent storage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_m3_campaign_v1 as campaign
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
from scripts.starlink_pss_m3_iio_tx_v1 import (
    SingleTxCyclicIio,
    TxSafetyError,
    close_iio_context,
    load_exact_payload,
)

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-m3-execution-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m3-execution-receipt.v1"
CLAIM_SCOPE = "cabled_campaign_transport_only"
RF_BANDWIDTH_HZ = 15_000_000
ALLOCATED_TRANSMITTER_SERIAL = "1040007c4a94000211000b009186843ef2"
ALLOCATED_TRANSMITTER_TOPOLOGY = "3-11"
ALLOCATED_TRANSMITTER_NETWORK_INTERFACE = "enx00e02297811f"
HEX40 = re.compile(r"[0-9a-f]{40}")
PLAN_FIELDS = {
    "schema",
    "schema_version",
    "plan_id",
    "created_at",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "claim_scope",
    "campaign_plan",
    "receiver_serial",
    "transmitter_serial",
    "transmitter_topology",
    "transmitter_network_interface",
    "ppu_repository",
    "ppu_source_commit",
    "rf_bandwidth_hz",
    "execution_receipt_path",
    "confirmation_phrase",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
}
RECEIPT_FIELDS = {
    "schema",
    "schema_version",
    "receipt_id",
    "started_at",
    "completed_at",
    "outcome",
    "plan",
    "campaign_plan",
    "receiver_serial",
    "transmitter_serial",
    "transmitter_topology",
    "transmitter_network_interface",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "claim_scope",
    "ppu_repository",
    "ppu_source_commit",
    "transmitter_inventory",
    "iio_uri",
    "iio_identity",
    "initial_mute",
    "configuration",
    "actions",
    "stimulus_receipts",
    "receiver_monitor_receipts",
    "final_mute",
    "transmitter_cleanup_verified",
    "context_close_verified",
    "context_close_method",
    "receiver_recovery_required",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
    "error",
}

ProbeError = campaign.ProbeError
probe_v1 = campaign.probe_v1


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load(path: Path, *, label: str) -> dict[str, Any]:
    return campaign._load(path.absolute(), label=label)


def _identity(path: Path, *, label: str) -> dict[str, Any]:
    return campaign._identity(path.absolute(), label=label)


def _git_source(repository: Path) -> tuple[str, str]:
    if not repository.is_absolute() or ".." in repository.parts:
        raise ProbeError("PPU repository path must be absolute and normalized")
    try:
        commit = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain"],
            check=True,
            text=True,
            capture_output=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ProbeError(f"PPU source cannot be attested: {error}") from error
    if HEX40.fullmatch(commit) is None:
        raise ProbeError("PPU HEAD is not one full commit")
    return commit, status


def _import_ppu_hardware(repository: Path) -> SimpleNamespace:
    source_root = (repository / "src").resolve()
    source = str(source_root)
    if source not in sys.path:
        sys.path.insert(0, source)
    try:
        inventory = importlib.import_module("pluto_plus.inventory")
        radio_lock = importlib.import_module("pluto_plus.radio_lock")
    except (ImportError, OSError) as error:
        raise ProbeError(f"PPU hardware modules are unavailable: {error}") from error
    for module in (inventory, radio_lock):
        module_path = Path(str(module.__file__)).resolve()
        if not module_path.is_relative_to(source_root):
            raise ProbeError(
                "imported PPU hardware module is outside the attested checkout"
            )
    return SimpleNamespace(inventory=inventory, radio_lock=radio_lock)


def _confirmation(
    plan: dict[str, Any], fixture: dict[str, Any], base: dict[str, Any]
) -> str:
    return (
        f"EXECUTE CABLED PSS M3 TX {plan['transmitter_serial']} "
        f"AT {plan['transmitter_topology']} TO RX {plan['receiver_serial']} "
        f"WITH {fixture['effective_attenuation_db']:g} DB AT "
        f"{base['transmitter_lo_hz']} HZ"
    )


def _validate_plan(plan: dict[str, Any]) -> None:
    if set(plan) != PLAN_FIELDS:
        raise ProbeError("M3 execution plan fields differ from v1")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != 1
        or not isinstance(plan.get("plan_id"), str)
        or len(plan["plan_id"]) != 32
        or any(character not in "0123456789abcdef" for character in plan["plan_id"])
        or plan.get("hardware_accessed") is not False
        or plan.get("persistent_write") is not False
        or plan.get("do_not_merge") is not True
        or plan.get("claim_scope") != CLAIM_SCOPE
        or plan.get("receiver_serial") != campaign.RECEIVER_SERIAL
        or plan.get("transmitter_serial") != ALLOCATED_TRANSMITTER_SERIAL
        or plan.get("transmitter_topology") != ALLOCATED_TRANSMITTER_TOPOLOGY
        or plan.get("transmitter_network_interface")
        != ALLOCATED_TRANSMITTER_NETWORK_INTERFACE
        or not isinstance(plan.get("ppu_repository"), str)
        or not Path(plan["ppu_repository"]).is_absolute()
        or HEX40.fullmatch(str(plan.get("ppu_source_commit", ""))) is None
        or plan.get("rf_bandwidth_hz") != RF_BANDWIDTH_HZ
        or not isinstance(plan.get("execution_receipt_path"), str)
        or not Path(plan["execution_receipt_path"]).is_absolute()
        or not isinstance(plan.get("confirmation_phrase"), str)
        or plan.get("pss_detected") is not False
        or plan.get("sss_detected") is not False
        or plan.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M3 execution plan values violate the v1 contract")
    campaign._parse_time(plan.get("created_at"), label="execution plan created_at")
    campaign._validate_identity(plan.get("campaign_plan"), label="campaign plan")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="seal an offline exact-radio execution plan"
    )
    plan.add_argument("--campaign-plan", type=Path, required=True)
    plan.add_argument("--transmitter-topology", required=True)
    plan.add_argument("--ppu-repository", type=Path, required=True)
    plan.add_argument("--ppu-commit", required=True)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser(
        "execute", help="run one explicitly confirmed campaign"
    )
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--receiver-state-root", type=Path, required=True)
    execute.add_argument("--receiver-timeout-s", type=float, default=240.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser(
        "verify", help="verify one M3 execution receipt offline"
    )
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_plan(args: Any) -> dict[str, Any]:
    campaign_path = args.campaign_plan.absolute()
    base = _load(campaign_path, label="M3 campaign plan")
    campaign._validate_plan(base)
    campaign._ensure_inputs_unchanged(base)
    fixture = _load(
        Path(base["fixture_declaration"]["path"]), label="M3 fixture declaration"
    )
    campaign._validate_fixture(fixture)
    repository = probe_v1._verify_ppu_repository(
        args.ppu_repository.absolute(), args.ppu_commit
    )
    observed_commit, status = _git_source(repository)
    if observed_commit != args.ppu_commit or status:
        raise ProbeError("PPU repository changed during source attestation")
    if (
        base["transmitter_serial"] != ALLOCATED_TRANSMITTER_SERIAL
        or args.transmitter_topology != ALLOCATED_TRANSMITTER_TOPOLOGY
    ):
        raise ProbeError("campaign does not select the one allocated bench transmitter")
    probe_v1._require_new_private_output(args.receipt)
    probe_v1._require_new_private_output(args.output)
    if args.receipt.absolute() == args.output.absolute():
        raise ProbeError("execution plan and receipt paths must differ")
    draft = {
        "transmitter_serial": base["transmitter_serial"],
        "transmitter_topology": args.transmitter_topology,
        "transmitter_network_interface": ALLOCATED_TRANSMITTER_NETWORK_INTERFACE,
        "receiver_serial": base["receiver_serial"],
    }
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": uuid.uuid4().hex,
        "created_at": _now(),
        "hardware_accessed": False,
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": CLAIM_SCOPE,
        "campaign_plan": _identity(campaign_path, label="M3 campaign plan"),
        "receiver_serial": base["receiver_serial"],
        "transmitter_serial": base["transmitter_serial"],
        "transmitter_topology": args.transmitter_topology,
        "transmitter_network_interface": ALLOCATED_TRANSMITTER_NETWORK_INTERFACE,
        "ppu_repository": str(args.ppu_repository.absolute()),
        "ppu_source_commit": args.ppu_commit,
        "rf_bandwidth_hz": RF_BANDWIDTH_HZ,
        "execution_receipt_path": str(args.receipt.absolute()),
        "confirmation_phrase": _confirmation(draft, fixture, base),
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    _validate_plan(plan)
    identity = probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_M3_EXECUTION_PLAN_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _load_bound_campaign(plan: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    identity = plan["campaign_plan"]
    path = Path(identity["path"])
    if _identity(path, label="M3 campaign plan") != identity:
        raise ProbeError("M3 campaign plan changed after execution sealing")
    base = _load(path, label="M3 campaign plan")
    campaign._validate_plan(base)
    campaign._ensure_inputs_unchanged(base)
    if (
        base["receiver_serial"] != plan["receiver_serial"]
        or base["transmitter_serial"] != plan["transmitter_serial"]
    ):
        raise ProbeError("M3 execution and campaign radio identities differ")
    fixture = _load(
        Path(base["fixture_declaration"]["path"]), label="M3 fixture declaration"
    )
    if plan["confirmation_phrase"] != _confirmation(plan, fixture, base):
        raise ProbeError("M3 execution confirmation phrase changed")
    return path, base


def _resolve_transmitter(
    devices: Any, *, serial: str, topology: str, network_interface: str
) -> dict[str, Any]:
    matches = [
        device
        for device in devices
        if getattr(device, "serial", None) == serial
        and Path(str(getattr(device, "usb_path", ""))).name == topology
    ]
    if len(matches) != 1:
        raise ProbeError("exact transmitter serial/topology does not resolve uniquely")
    device = matches[0]
    bus = getattr(device, "bus_number", None)
    address = getattr(device, "device_number", None)
    network_interfaces = [
        str(item.name) for item in getattr(device, "host_network_interfaces", ())
    ]
    if (
        not bool(getattr(device, "confirmed_plus", False))
        or not isinstance(bus, int)
        or isinstance(bus, bool)
        or bus <= 0
        or not isinstance(address, int)
        or isinstance(address, bool)
        or address <= 0
        or network_interface not in network_interfaces
    ):
        raise ProbeError("transmitter inventory is not one usable PlutoSDR+")
    return {
        "serial": serial,
        "topology": topology,
        "usb_path": str(device.usb_path),
        "bus_number": bus,
        "device_number": address,
        "product": str(device.product),
        "network_interfaces": network_interfaces,
    }


def _usb_openers(
    bus: int, device: int, *, proc_root: Path = Path("/proc")
) -> list[int]:
    target = f"/dev/bus/usb/{bus:03d}/{device:03d}"
    owners: list[int] = []
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            descriptors = (process / "fd").iterdir()
            if any(os.readlink(descriptor) == target for descriptor in descriptors):
                owners.append(int(process.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
    return sorted(owners)


def _iio_identity(context: Any, expected_serial: str) -> dict[str, str]:
    attrs = {str(key): str(value) for key, value in context.attrs.items()}
    serial = attrs.get("hw_serial", attrs.get("usb,serial", attrs.get("serial", "")))
    if serial != expected_serial:
        raise ProbeError("transmitter IIO context resolved the wrong serial")
    return {
        "serial": serial,
        "firmware_version": attrs.get("fw_version", ""),
        "hardware_model": attrs.get("hw_model", ""),
    }


def _stimulus_receipt(
    *,
    base: dict[str, Any],
    state: str,
    started_at: str,
    completed_at: str,
    active: dict[str, Any] | None,
    mute: dict[str, Any] | None,
) -> dict[str, Any]:
    is_active = state == "active"
    receipt = {
        "schema": campaign.STIMULUS_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "started_at": started_at,
        "completed_at": completed_at,
        "outcome": "pass",
        "fixture_declaration": base["fixture_declaration"],
        "transmitter_serial": base["transmitter_serial"],
        "state": state,
        "hardware_accessed": True,
        "persistent_write": False,
        "cabled_only": True,
        "over_the_air_transmission": False,
        "waveform_evidence": base["waveform_evidence"] if is_active else None,
        "waveform_binary": base["waveform_binary"] if is_active else None,
        "requested_sample_rate_hz": (
            base["transmitter_sample_rate_hz"] if is_active else None
        ),
        "readback_sample_rate_hz": (
            active["configuration"]["sample_rate_hz"] if is_active else None
        ),
        "cyclic_buffer_active": is_active,
        "tx_lo_hz": active["configuration"]["tx_lo_hz"] if is_active else None,
        "tx_hardwaregain_db": (
            active["tx_hardwaregain_db"] if is_active else mute["tx_hardwaregain_db"]
        ),
        "tx_buffer_disabled": not is_active,
        "tx_lo_powerdown": not is_active,
        "cleanup_verified": not is_active,
        "error": None,
    }
    campaign._validate_stimulus(receipt, expected_state=state, plan=base)
    return receipt


def _write_stimulus(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    return probe_v1._write_new_private(path, receipt)


def _run_receiver_monitor(
    dwell: dict[str, Any], args: Any, *, monitor_execute: Any
) -> dict[str, Any]:
    plan_path = Path(dwell["monitor_plan"]["path"])
    monitor_plan = _load(plan_path, label=f"{dwell['role']} receiver monitor plan")
    return monitor_execute(
        SimpleNamespace(
            plan=plan_path,
            ssh_password_file=args.ssh_password_file,
            state_root=args.receiver_state_root,
            timeout_s=args.receiver_timeout_s,
            confirm=monitor_plan["confirmation_phrase"],
            output=Path(dwell["monitor_receipt_path"]),
        )
    )


def execute_plan(
    args: Any,
    *,
    scanner: Any | None = None,
    lock_factory: Any | None = None,
    iio_module: Any | None = None,
    monitor_execute: Any | None = None,
    opener_checker: Any | None = None,
) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M3 execution plan")
    _validate_plan(plan)
    _campaign_path, base = _load_bound_campaign(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(
            f"confirmation must be exactly {plan['confirmation_phrase']!r}"
        )
    if args.output.absolute() != Path(plan["execution_receipt_path"]):
        raise ProbeError("execution output differs from the sealed receipt path")
    probe_v1._require_new_private_output(args.output)
    if (
        args.receiver_timeout_s <= 0
        or not args.receiver_state_root.is_absolute()
        or ".." in args.receiver_state_root.parts
    ):
        raise ProbeError("receiver timeout or state root is invalid")
    commit, status = _git_source(Path(plan["ppu_repository"]))
    if commit != plan["ppu_source_commit"] or status:
        raise ProbeError("PPU source changed after execution-plan sealing")

    if scanner is None or lock_factory is None:
        ppu = _import_ppu_hardware(Path(plan["ppu_repository"]))
        scanner = scanner or ppu.inventory.scan_local_usb_plutos
        lock_factory = lock_factory or ppu.radio_lock.acquire_radio_lock
    if iio_module is None:
        try:
            iio_module = importlib.import_module("iio")
        except ImportError as error:
            raise ProbeError(
                f"libiio Python binding is unavailable: {error}"
            ) from error
    monitor_execute = monitor_execute or monitor_v2.execute_plan
    opener_checker = opener_checker or _usb_openers

    started = _now()
    inventory: dict[str, Any] | None = None
    uri: str | None = None
    identity: dict[str, str] | None = None
    initial_mute: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None
    final_mute: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = []
    stimulus_receipts: dict[str, Any] = {}
    receiver_receipts: dict[str, Any] = {}
    receiver_monitor_attempted = False
    driver: SingleTxCyclicIio | None = None
    context_close_verified = False
    context_close_method: str | None = None
    context: Any | None = None
    failure: BaseException | None = None
    try:
        first = _resolve_transmitter(
            scanner(),
            serial=plan["transmitter_serial"],
            topology=plan["transmitter_topology"],
            network_interface=plan["transmitter_network_interface"],
        )
        with lock_factory(plan["transmitter_serial"]):
            inventory = _resolve_transmitter(
                scanner(),
                serial=plan["transmitter_serial"],
                topology=plan["transmitter_topology"],
                network_interface=plan["transmitter_network_interface"],
            )
            if inventory != first:
                raise ProbeError(
                    "transmitter USB identity changed while acquiring its lock"
                )
            owners = opener_checker(inventory["bus_number"], inventory["device_number"])
            if owners:
                raise ProbeError(
                    f"transmitter USB device is already open by PIDs {owners}"
                )
            uri = f"usb:{inventory['bus_number']}.{inventory['device_number']}.5"
            context = iio_module.Context(uri)
            identity = _iio_identity(context, plan["transmitter_serial"])
            driver = SingleTxCyclicIio(
                iio_module, context, expected_serial=plan["transmitter_serial"]
            )
            initial_mute = driver.mute()
            configuration = driver.configure(
                sample_rate_hz=base["transmitter_sample_rate_hz"],
                rf_bandwidth_hz=plan["rf_bandwidth_hz"],
                tx_lo_hz=base["transmitter_lo_hz"],
            )
            waveform = base["waveform_binary"]
            payload = load_exact_payload(
                Path(waveform["path"]),
                expected_bytes=waveform["bytes"],
                expected_sha256=waveform["sha256"],
            )
            for dwell in base["dwells"]:
                role = dwell["role"]
                state = dwell["expected_stimulus_state"]
                action_started = _now()
                if state == "active":
                    active = driver.start(
                        payload, gain_db=base["transmitter_hardwaregain_db"]
                    )
                    mute = None
                else:
                    active = None
                    mute = driver.mute()
                action_completed = _now()
                stimulus = _stimulus_receipt(
                    base=base,
                    state=state,
                    started_at=action_started,
                    completed_at=action_completed,
                    active=active,
                    mute=mute,
                )
                stimulus_identity = _write_stimulus(
                    Path(dwell["stimulus_receipt_path"]), stimulus
                )
                stimulus_receipts[role] = stimulus_identity
                actions.append(
                    {
                        "role": role,
                        "state": state,
                        "started_at": action_started,
                        "completed_at": action_completed,
                        "stimulus_receipt": stimulus_identity,
                    }
                )
                receiver_monitor_attempted = True
                _run_receiver_monitor(dwell, args, monitor_execute=monitor_execute)
                receiver_receipts[role] = _identity(
                    Path(dwell["monitor_receipt_path"]),
                    label=f"{role} receiver monitor receipt",
                )
            final_started = _now()
            final_mute = driver.mute()
            final_completed = _now()
            final_receipt = _stimulus_receipt(
                base=base,
                state="muted",
                started_at=final_started,
                completed_at=final_completed,
                active=None,
                mute=final_mute,
            )
            final_path = Path(base["final_mute_stimulus_receipt_path"])
            final_identity = _write_stimulus(final_path, final_receipt)
            actions.append(
                {
                    "role": "final_mute",
                    "state": "muted",
                    "started_at": final_started,
                    "completed_at": final_completed,
                    "stimulus_receipt": final_identity,
                }
            )
            close_evidence = driver.close()
            context_close_method = close_evidence["context_release"]
            context_close_verified = True
    except BaseException as error:  # noqa: BLE001 - receipt every outcome
        failure = error
    finally:
        if driver is not None and not context_close_verified:
            try:
                cleanup_started = _now()
                final_mute = driver.mute()
                final_path = Path(base["final_mute_stimulus_receipt_path"])
                if not final_path.exists():
                    final_identity = _write_stimulus(
                        final_path,
                        _stimulus_receipt(
                            base=base,
                            state="muted",
                            started_at=cleanup_started,
                            completed_at=_now(),
                            active=None,
                            mute=final_mute,
                        ),
                    )
                    actions.append(
                        {
                            "role": "failure_final_mute",
                            "state": "muted",
                            "started_at": cleanup_started,
                            "completed_at": _now(),
                            "stimulus_receipt": final_identity,
                        }
                    )
                close_evidence = driver.close()
                context_close_method = close_evidence["context_release"]
                context_close_verified = True
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve cleanup
                failure = TxSafetyError(
                    f"execution failed ({failure}); final TX cleanup failed ({cleanup_error})"
                )
        elif context is not None and not context_close_verified:
            try:
                context_close_method = close_iio_context(iio_module, context)
                context_close_verified = True
            except BaseException as cleanup_error:  # noqa: BLE001 - receipt cleanup
                failure = TxSafetyError(
                    f"execution failed ({failure}); IIO context close failed ({cleanup_error})"
                )
    completed = _now()
    final_path = Path(base["final_mute_stimulus_receipt_path"])
    cleanup_verified = (
        final_mute is not None
        and final_mute.get("verified") is True
        and final_path.exists()
        and context_close_verified
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "started_at": started,
        "completed_at": completed,
        "outcome": "pass" if failure is None else "failed",
        "plan": _identity(plan_path, label="M3 execution plan"),
        "campaign_plan": plan["campaign_plan"],
        "receiver_serial": plan["receiver_serial"],
        "transmitter_serial": plan["transmitter_serial"],
        "transmitter_topology": plan["transmitter_topology"],
        "transmitter_network_interface": plan["transmitter_network_interface"],
        "hardware_accessed": inventory is not None,
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": CLAIM_SCOPE,
        "ppu_repository": plan["ppu_repository"],
        "ppu_source_commit": plan["ppu_source_commit"],
        "transmitter_inventory": inventory,
        "iio_uri": uri,
        "iio_identity": identity,
        "initial_mute": initial_mute,
        "configuration": configuration,
        "actions": actions,
        "stimulus_receipts": stimulus_receipts,
        "receiver_monitor_receipts": receiver_receipts,
        "final_mute": final_mute,
        "transmitter_cleanup_verified": cleanup_verified,
        "context_close_verified": context_close_verified,
        "context_close_method": context_close_method,
        "receiver_recovery_required": receiver_monitor_attempted,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    identity_out = probe_v1._write_new_private(args.output, receipt)
    if failure is not None:
        raise ProbeError(
            f"M3 execution failed after writing {identity_out['path']}: {failure}"
        )
    return {
        "verdict": "PASS_M3_CABLED_TRANSPORT_ONLY",
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receiver_recovery_required": True,
        "receipt": identity_out,
        "next_gate": "offline M3 qualification, then PPU receiver recovery",
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M3 execution plan")
    _validate_plan(plan)
    _campaign_path, base = _load_bound_campaign(plan)
    if args.receipt.absolute() != Path(plan["execution_receipt_path"]):
        raise ProbeError("M3 execution receipt path differs from its plan")
    receipt = _load(args.receipt.absolute(), label="M3 execution receipt")
    if (
        set(receipt) != RECEIPT_FIELDS
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("plan") != _identity(plan_path, label="M3 execution plan")
        or receipt.get("campaign_plan") != plan["campaign_plan"]
        or receipt.get("receiver_serial") != plan["receiver_serial"]
        or receipt.get("transmitter_serial") != plan["transmitter_serial"]
        or receipt.get("transmitter_topology") != plan["transmitter_topology"]
        or receipt.get("transmitter_network_interface")
        != plan["transmitter_network_interface"]
        or receipt.get("persistent_write") is not False
        or receipt.get("do_not_merge") is not True
        or receipt.get("claim_scope") != CLAIM_SCOPE
        or receipt.get("ppu_repository") != plan["ppu_repository"]
        or receipt.get("ppu_source_commit") != plan["ppu_source_commit"]
        or receipt.get("pss_detected") is not False
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("outcome") not in ("pass", "failed")
    ):
        raise ProbeError("M3 execution receipt violates its sealed plan")
    if receipt["outcome"] == "pass":
        if (
            receipt.get("hardware_accessed") is not True
            or receipt.get("transmitter_cleanup_verified") is not True
            or receipt.get("context_close_verified") is not True
            or receipt.get("context_close_method")
            not in {"explicit-close", "legacy-native-destroy"}
            or receipt.get("receiver_recovery_required") is not True
            or receipt.get("error") is not None
            or set(receipt.get("stimulus_receipts", {}))
            != {"positive_a", "negative_muted", "positive_b"}
            or set(receipt.get("receiver_monitor_receipts", {}))
            != {"positive_a", "negative_muted", "positive_b"}
        ):
            raise ProbeError(
                "passing M3 execution lacks complete cleanup or dwell proof"
            )
        for dwell in base["dwells"]:
            role = dwell["role"]
            stimulus_path = Path(dwell["stimulus_receipt_path"])
            if (
                _identity(stimulus_path, label=f"{role} stimulus receipt")
                != receipt["stimulus_receipts"][role]
            ):
                raise ProbeError(f"{role} stimulus receipt changed")
            stimulus = _load(stimulus_path, label=f"{role} stimulus receipt")
            campaign._validate_stimulus(
                stimulus,
                expected_state=dwell["expected_stimulus_state"],
                plan=base,
            )
            monitor_path = Path(dwell["monitor_receipt_path"])
            if (
                _identity(monitor_path, label=f"{role} monitor receipt")
                != receipt["receiver_monitor_receipts"][role]
            ):
                raise ProbeError(f"{role} receiver receipt changed")
            monitor_v2.verify_receipt(
                SimpleNamespace(
                    plan=Path(dwell["monitor_plan"]["path"]), receipt=monitor_path
                )
            )
        final_path = Path(base["final_mute_stimulus_receipt_path"])
        final = _load(final_path, label="final mute stimulus receipt")
        campaign._validate_stimulus(final, expected_state="muted", plan=base)
    return {
        "verdict": "PASS_M3_EXECUTION_RECEIPT_STRUCTURE",
        "outcome": receipt["outcome"],
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
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
