#!/usr/bin/env python3
"""RAM-test and optionally persist one exact issue-107 DFU on one Pluto+.

The candidate remains explicitly hardware-unqualified for UTC timing. The
persistent step is a local USB canary and requires this image's successful,
serial-bound RAM receipt first. Use the PPU virtualenv containing pluto_plus.
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pluto_plus.bootstrap_firmware import (
    SINGLE_RX_TX_CAPABLE_LAYOUT,
    STANDALONE_FLASH_PROFILES,
    BoundSshBootstrapTransport,
    execute_usb_flash_plan,
    prepare_usb_flash_plan,
)
from pluto_plus.doctor import FEATURE_103_V1_RELEASE_RAM_POLICY
from pluto_plus.firmware import FirmwareImageError, validate_dfu
from pluto_plus.hardware.discovery import discover_network_iio
from pluto_plus.inventory import LocalUsbPluto, scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.volatile_firmware import (
    SshRamBootTransition,
    VolatileFirmwareError,
    execute_ram_boot_plan,
    prepare_ram_boot_plan,
)

CURRENT_FIRMWARE = "v0.52-plutoplus-spf-adaptive-scan-v1"
EXPECTED_SERIALS = {
    "104000b29905000e17000800065934759d",
    "1040007c4a94000211000b009186843ef2",
}
RAM_PHASES = {
    "exact_path_returned_runtime",
    "return_attested",
    "tx_safe_attested",
}
FUNCTIONAL_RATES = (10_000_000, 15_000_000, 20_000_000)


def _private_directory(path: Path) -> Path:
    selected = path.expanduser().absolute()
    selected.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = selected.lstat()
    if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
        raise ValueError("evidence root must be a real directory")
    if state.st_uid != os.getuid():
        raise ValueError("evidence root must be owned by the current user")
    os.chmod(selected, 0o700)
    return selected


def _read_private(path: Path, *, label: str, maximum: int = 16_000_000) -> bytes:
    state = path.lstat()
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_uid != os.getuid()
        or stat.S_IMODE(state.st_mode) & 0o077
        or state.st_size > maximum
    ):
        raise ValueError(f"{label} must be a private, owned regular file")
    payload = path.read_bytes()
    if len(payload) != state.st_size:
        raise ValueError(f"{label} changed while being read")
    return payload


def _password() -> str:
    password_file = os.environ.get("PLUTO_PASSWORD_FILE")
    if password_file:
        return (
            _read_private(
                Path(password_file), label="radio password file", maximum=4096
            )
            .decode("utf-8")
            .rstrip("\r\n")
        )
    config_file = os.environ.get("PLUTO_BUILDROOT_CONFIG")
    if config_file:
        content = _read_private(
            Path(config_file), label="Buildroot configuration", maximum=4_000_000
        ).decode("utf-8")
        match = re.search(
            r'^BR2_TARGET_GENERIC_ROOT_PASSWD="([^"\n]+)"$', content, re.MULTILINE
        )
        if match:
            return match.group(1)
    return getpass.getpass("Radio SSH password: ")


def _manifest(image: Path, manifest_path: Path) -> tuple[dict[str, Any], bytes, str]:
    manifest_state = manifest_path.lstat()
    if (
        stat.S_ISLNK(manifest_state.st_mode)
        or not stat.S_ISREG(manifest_state.st_mode)
        or manifest_state.st_size > 4_000_000
    ):
        raise ValueError(
            "candidate manifest must be a regular file no larger than 4 MB"
        )
    raw = manifest_path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise TypeError("candidate manifest must contain a JSON object")
    if document.get("utc_hardware_qualified", False) is not False:
        raise ValueError("issue-107 deployment must remain UTC hardware-unqualified")
    firmware = document.get("firmware")
    asset_sha = document.get("asset_sha256")
    fit_sha = document.get("fit_sha256")
    fit_size = document.get("fit_size")
    sources = document.get("sources")
    source_commit = (
        sources.get("firmware_base") if isinstance(sources, dict) else None
    ) or document.get("firmware_source_commit")
    if not isinstance(firmware, str) or not firmware.startswith("v0.52-"):
        raise ValueError("manifest must identify the candidate v0.52 firmware")
    if not isinstance(source_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", source_commit
    ):
        raise ValueError("manifest must identify the immutable firmware source commit")
    image_data = image.expanduser().resolve(strict=True).read_bytes()
    if hashlib.sha256(image_data).hexdigest() != asset_sha:
        raise ValueError("DFU SHA-256 does not match the candidate manifest")
    fit = validate_dfu(image_data)
    if hashlib.sha256(fit).hexdigest() != fit_sha or len(fit) != fit_size:
        raise ValueError("DFU FIT hash or size does not match the candidate manifest")
    return document, image_data, hashlib.sha256(raw).hexdigest()


def _candidate_profiles(
    manifest: dict[str, Any], image: Path, image_data: bytes
) -> tuple[str, str]:
    source = (
        manifest["sources"]["firmware_base"]
        if isinstance(manifest.get("sources"), dict)
        else manifest["firmware_source_commit"]
    )
    image_fit = validate_dfu(image_data)
    digest = hashlib.sha256(image_data).hexdigest()[:12]
    base_id = FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id
    base = STANDALONE_FLASH_PROFILES[base_id]
    common = {
        "release_tag": f"issue-107-counter-utc-{digest}-canary",
        "device_firmware": manifest["firmware"],
        "asset_name": image.name,
        "asset_sha256": hashlib.sha256(image_data).hexdigest(),
        "release_url": manifest.get(
            "release_url", "https://github.com/misko/plutosdr-fw/issues/107"
        ),
        "source_commit": source,
        "fit_body_sha256": hashlib.sha256(image_fit).hexdigest(),
        "fit_body_size": len(image_fit),
        "hardware_qualified": False,
        "published_at": datetime.now(UTC),
    }
    ram_id = f"issue-107-{digest}-ram"
    persistent_id = f"issue-107-{digest}-local-canary"
    ram_policy = FEATURE_103_V1_RELEASE_RAM_POLICY.model_copy(
        update={"profile_id": ram_id, **common}
    )
    persistent_policy = ram_policy.model_copy(update={"profile_id": persistent_id})
    STANDALONE_FLASH_PROFILES[ram_id] = replace(
        base,
        policy=ram_policy,
        persistent_allowed=False,
        source_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=(CURRENT_FIRMWARE,),
    )
    STANDALONE_FLASH_PROFILES[persistent_id] = replace(
        base,
        policy=persistent_policy,
        persistent_allowed=True,
        source_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=(manifest["firmware"],),
    )
    return ram_id, persistent_id


def _attest(
    serial: str, host: str, expected_firmware: str
) -> tuple[LocalUsbPluto, Any]:
    devices = [device for device in scan_local_usb_plutos() if device.serial == serial]
    if len(devices) != 1:
        raise RuntimeError("exact serial is not present as one local USB radio")
    observations = discover_network_iio([f"{host}/32"], max_hosts=1, workers=1)
    matches = [item for item in observations if item.serial == serial]
    if len(matches) != 1:
        raise RuntimeError("the requested host does not attest the same radio serial")
    if matches[0].firmware_version != expected_firmware:
        raise RuntimeError("radio firmware differs from the expected phase identity")
    return devices[0], matches[0]


def _load_matching_ram_receipt(
    path: Path, *, serial: str, image_sha: str, firmware: str, usb_path: str
) -> dict[str, Any]:
    receipt = json.loads(
        _read_private(path, label="RAM-boot receipt", maximum=1_000_000)
    )
    plan = receipt.get("plan")
    phases = set(receipt.get("phases", ()))
    if (
        receipt.get("outcome") != "success"
        or not RAM_PHASES.issubset(phases)
        or not isinstance(plan, dict)
        or plan.get("serial") != serial
        or plan.get("usb_sysfs_path") != usb_path
        or plan.get("image_sha256") != image_sha
        or plan.get("expected_firmware") != firmware
        or receipt.get("returned_serial") != serial
        or receipt.get("returned_firmware") != firmware
        or receipt.get("receipt_id") != path.stem
    ):
        raise ValueError(
            "RAM receipt does not attest this exact radio and candidate image"
        )
    return receipt


def _load_functional_report(
    path: Path, *, serial: str, firmware: str, image_sha: str
) -> tuple[dict[str, Any], str]:
    report_path = path.expanduser().absolute()
    report = json.loads(
        _read_private(report_path, label="functional capture report", maximum=2_000_000)
    )
    if not isinstance(report, dict):
        raise TypeError("functional capture report must be a JSON object")
    rates = report.get("rates_hz")
    if (
        report.get("schema") != "issue107.functional-capture/v1"
        or report.get("radio_serial") != serial
        or report.get("firmware") != firmware
        or report.get("image_sha256") != image_sha
        or not isinstance(report.get("boot_id"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", report["boot_id"])
        or report.get("all_rates_passed") is not True
        or report.get("scantime_protocol_version") != 1
        or report.get("counter_continuity_passed") is not True
        or report.get("utc_hardware_qualified") is not False
        or not isinstance(rates, list)
        or tuple(sorted(set(rates))) != FUNCTIONAL_RATES
        or not isinstance(report.get("test_evidence_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", report["test_evidence_sha256"])
    ):
        raise ValueError(
            "functional report must pass exact-radio 10/15/20 MS/s counter-time checks "
            "while leaving UTC accuracy unqualified"
        )
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return report, digest


def _new_attempt(evidence_dir: Path, phase: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    attempt = evidence_dir / phase / f"{stamp}-{uuid.uuid4().hex}"
    attempt.mkdir(mode=0o700, parents=True, exist_ok=False)
    return attempt


def _parse_marked_boot_id(transcript: str) -> str:
    marker = "ISSUE107_BOOT_ID="
    marked_lines = [
        line.strip()
        for line in transcript.splitlines()
        if line.strip().startswith(marker)
    ]
    if len(marked_lines) != 1:
        raise RuntimeError("radio boot-ID response must contain exactly one marked value")
    value = marked_lines[0][len(marker) :]
    if not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
    ):
        raise RuntimeError("radio returned a malformed marked boot UUID")
    return value.replace("-", "")


def _read_boot_id(*, host: str, known_hosts: Path) -> str:
    transport = BoundSshBootstrapTransport(
        host=host,
        interface=None,
        password=_password(),
        known_hosts_file=known_hosts,
    )
    command = (
        "printf '\\nISSUE107_BOOT_ID=%s\\n' "
        '"$(cat /proc/sys/kernel/random/boot_id)"'
    )
    transcript = transport.run(command, timeout_s=15)
    return _parse_marked_boot_id(transcript)


def _require_report_boot_id(report: dict[str, Any], live_boot_id: str) -> None:
    if report.get("boot_id") != live_boot_id:
        raise ValueError("functional report boot UUID differs from the live radio")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, choices=sorted(EXPECTED_SERIALS))
    parser.add_argument("--host", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("ram", "persist"), default="ram")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--ram-receipt", type=Path)
    parser.add_argument("--functional-report", type=Path)
    parser.add_argument("--ssh-known-hosts-file", type=Path)
    return parser


def main() -> int:
    parser = _argument_parser()
    args = parser.parse_args()

    if args.phase == "persist" and args.ram_receipt is None:
        parser.error(
            "--phase persist requires --ram-receipt from a successful RAM boot"
        )
    if args.phase == "persist" and args.functional_report is None:
        parser.error("--phase persist requires --functional-report")
    if args.phase != "persist" and args.ram_receipt is not None:
        parser.error("--ram-receipt is only valid with --phase persist")
    if args.phase != "persist" and args.functional_report is not None:
        parser.error("--functional-report is only valid with --phase persist")
    if not args.execute and args.confirm:
        parser.error("--confirm requires --execute")
    try:
        host_ip = ipaddress.ip_address(args.host)
        if host_ip.version != 4 or not host_ip.is_private:
            raise ValueError("host must be a private literal IPv4 address")
        evidence_root = _private_directory(args.evidence_root)
        evidence_dir = _private_directory(evidence_root / args.serial)
        image = args.image.expanduser().resolve(strict=True)
        manifest, image_data, manifest_sha = _manifest(
            image, args.manifest.expanduser().resolve()
        )
        ram_profile, persistent_profile = _candidate_profiles(
            manifest, image, image_data
        )
        image_sha = hashlib.sha256(image_data).hexdigest()
        if (
            args.phase == "ram"
            and args.execute
            and args.confirm != f"RAM BOOT {args.serial}"
        ):
            raise ValueError(
                f"RAM execution requires --confirm 'RAM BOOT {args.serial}'"
            )
        if (
            args.phase == "persist"
            and args.execute
            and args.confirm != f"FLASH {args.serial}"
        ):
            raise ValueError(
                f"persistent execution requires --confirm 'FLASH {args.serial}'"
            )

        with acquire_radio_lock(args.serial):
            phase_firmware = (
                CURRENT_FIRMWARE if args.phase == "ram" else manifest["firmware"]
            )
            device, radio = _attest(args.serial, str(host_ip), phase_firmware)
            known_hosts = (
                args.ssh_known_hosts_file.expanduser().absolute()
                if args.ssh_known_hosts_file
                else evidence_dir / "known_hosts"
            )
            if args.phase == "ram":
                attempt_dir = _new_attempt(evidence_dir, "ram")
                if not known_hosts.is_file():
                    raise ValueError(
                        "a pinned per-radio SSH known_hosts file is required"
                    )
                _read_private(known_hosts, label="pinned SSH known_hosts file")
                plan = prepare_ram_boot_plan(
                    image,
                    Path(device.usb_path),
                    profile_id=ram_profile,
                    transition_host=str(host_ip),
                    known_hosts_file=known_hosts,
                )
                payload = {
                    "operation": "RAM boot",
                    "radio_serial": args.serial,
                    "radio_host": str(host_ip),
                    "radio_firmware_before": radio.firmware_version,
                    "candidate_firmware": manifest["firmware"],
                    "image_sha256": image_sha,
                    "manifest_sha256": manifest_sha,
                    "profile": ram_profile,
                    "utc_hardware_qualified": False,
                    "will_write_qspi": False,
                    "plan": dataclasses.asdict(plan),
                }
                plan_path = attempt_dir / "plan.json"
                _write_json(plan_path, payload)
                print(json.dumps({"plan": str(plan_path), "will_write_qspi": False}))
                if args.execute:
                    transport = BoundSshBootstrapTransport(
                        host=str(host_ip),
                        interface=None,
                        password=_password(),
                        known_hosts_file=known_hosts,
                    )
                    result = execute_ram_boot_plan(
                        plan,
                        confirmation=args.confirm or "",
                        known_hosts_file=known_hosts,
                        transition=SshRamBootTransition(transport),
                        receipt_directory=attempt_dir / "receipts",
                    )
                    if result.outcome != "success":
                        raise RuntimeError(
                            f"RAM boot ended {result.outcome}; inspect its receipt and do not retry"
                        )
                    print(
                        json.dumps(
                            {
                                "ram_receipt": result.receipt_path,
                                "outcome": result.outcome,
                            }
                        )
                    )
                return 0

            ram_receipt = _load_matching_ram_receipt(
                args.ram_receipt.expanduser().absolute(),
                serial=args.serial,
                image_sha=image_sha,
                firmware=manifest["firmware"],
                usb_path=device.usb_path,
            )
            if radio.firmware_version != manifest["firmware"]:
                raise RuntimeError("candidate RAM firmware is not currently running")
            functional_report, functional_report_sha = _load_functional_report(
                args.functional_report,
                serial=args.serial,
                firmware=manifest["firmware"],
                image_sha=image_sha,
            )
            known_hosts = (
                args.ssh_known_hosts_file.expanduser().absolute()
                if args.ssh_known_hosts_file
                else evidence_dir / "known_hosts"
            )
            _read_private(known_hosts, label="pinned SSH known_hosts file")
            live_boot_id = _read_boot_id(host=str(host_ip), known_hosts=known_hosts)
            _require_report_boot_id(functional_report, live_boot_id)
            attempt_dir = _new_attempt(evidence_dir, "persistent")
            plan, frm = prepare_usb_flash_plan(
                image,
                Path(device.usb_path),
                mutation_profile_id=persistent_profile,
            )
            payload = {
                "operation": "local USB persistent canary",
                "radio_serial": args.serial,
                "radio_host": str(host_ip),
                "candidate_firmware": manifest["firmware"],
                "image_sha256": image_sha,
                "manifest_sha256": manifest_sha,
                "functional_report_sha256": functional_report_sha,
                "boot_id": live_boot_id,
                "profile": persistent_profile,
                "ram_receipt_id": ram_receipt["receipt_id"],
                "utc_hardware_qualified": False,
                "will_write_qspi": True,
                "plan": dataclasses.asdict(plan),
            }
            plan_path = attempt_dir / "plan.json"
            _write_json(plan_path, payload)
            print(json.dumps({"plan": str(plan_path), "will_write_qspi": True}))
            if args.execute:
                result = execute_usb_flash_plan(
                    plan,
                    frm,
                    confirmation=args.confirm or "",
                    receipt_directory=attempt_dir / "receipts",
                )
                if result.outcome != "success":
                    raise RuntimeError(
                        f"persistent update ended {result.outcome}; inspect its receipt and do not retry"
                    )
                print(
                    json.dumps(
                        {"receipt": result.receipt_path, "outcome": result.outcome}
                    )
                )
        return 0
    except (
        OSError,
        TypeError,
        ValueError,
        RuntimeError,
        FirmwareImageError,
        VolatileFirmwareError,
    ) as error:
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
