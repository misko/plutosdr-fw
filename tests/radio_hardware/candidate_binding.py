"""Strict, hardware-free validation of release artifact and RAM-boot bindings.

The validators in this module deliberately operate on already-decoded JSON.
Callers remain responsible for race-safe file opening, ownership/mode checks,
bounded reads, and hashing the exact bytes that were decoded.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

ARTIFACT_INDEX_SCHEMA = "plutosdr-fw.tandem-release-evidence"
RAM_BOOT_RECEIPT_SCHEMA = "plutosdr-fw.tandem-ram-boot-receipt"
ARTIFACT_INDEX_SCHEMA_VERSION = 1
RAM_BOOT_RECEIPT_SCHEMA_VERSION = 4
PLUTOPLUS_HARDWARE_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
# Backward-compatible public name used by release-evidence code for the
# artifact-index schema. Receipt validation has its own version above.
SCHEMA_VERSION = ARTIFACT_INDEX_SCHEMA_VERSION
ARTIFACT_INDEX_STAGES = frozenset(
    {
        "candidate-pre-hardware",
        "final-pre-confirmation",
    }
)
REQUIRED_EVIDENCE_ROLES = (
    "actions-run",
    "attestation-verification",
    "bundle",
    "bundle-inner-checksums",
    "dfu-suffix-check",
    "fit-layout",
    "fpga-bitstream",
    "integrated-verdict",
    "offline-validation-summary",
    "ooc-evidence-manifest",
    "ooc-status",
    "packed-versions",
    "payload-checksums",
    "provenance",
    "rootfs",
    "routed-bus-skew",
    "routed-cdc",
    "routed-dcp",
    "routed-drc",
    "routed-methodology",
    "routed-route-status",
    "routed-timing",
    "routed-utilization",
    "source-lock",
    "source-tool-hashes",
    "waiver-inventory",
    "xsa",
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]+")
_SAFE_SSH_USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


class CandidateBindingError(ValueError):
    """An artifact index or RAM-boot receipt is not authorizing evidence."""


def _fail(message: str) -> None:
    raise CandidateBindingError(message)


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail(f"{name} must be a string-keyed object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], *, name: str) -> None:
    observed = set(value)
    if observed != expected:
        _fail(
            f"{name} keys are not exact: missing={sorted(expected - observed)} "
            f"extra={sorted(observed - expected)}"
        )


def _exact_int(value: object, *, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"{name} must be an integer >= {minimum}")
    return value


def _exact_bool(value: object, *, name: str) -> bool:
    if type(value) is not bool:
        _fail(f"{name} must be a boolean")
    return value


def _string(
    value: object,
    *,
    name: str,
    pattern: re.Pattern[str] | None = None,
    maximum: int = 4096,
) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{name} must be a bounded nonempty string")
    if value.strip() != value or "\x00" in value or "\n" in value or "\r" in value:
        _fail(f"{name} is not one canonical line")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(f"{name} has an invalid format")
    return value


def _sha256(value: object, *, name: str) -> str:
    return _string(value, name=name, pattern=_SHA256, maximum=64)


def _absolute_path(value: object, *, name: str) -> str:
    text = _string(value, name=name)
    path = PurePosixPath(text)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{name} must be a canonical absolute POSIX path")
    if str(path) != text:
        _fail(f"{name} must be a canonical absolute POSIX path")
    return text


def _relative_path(value: object, *, name: str) -> str:
    text = _string(value, name=name, maximum=512)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != text
    ):
        _fail(f"{name} must be a canonical relative POSIX path")
    return text


def _normalized(value: Mapping[str, object]) -> dict[str, Any]:
    # The domain above contains only ordinary JSON scalars/containers.  A
    # canonical round trip returns an unaliased plain-dict projection to callers.
    return json.loads(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def validate_artifact_index(value: object) -> dict[str, Any]:
    """Validate the exact v1 artifact binding consumed before hardware access."""

    record = _mapping(value, name="artifact index")
    _exact_keys(
        record,
        {
            "schema",
            "schema_version",
            "stage",
            "release",
            "source",
            "build",
            "artifact",
            "harness",
            "evidence",
        },
        name="artifact index",
    )
    if record["schema"] != ARTIFACT_INDEX_SCHEMA:
        _fail("artifact index schema is not exact")
    if (
        record["schema_version"] != ARTIFACT_INDEX_SCHEMA_VERSION
        or type(record["schema_version"]) is not int
    ):
        _fail("artifact index schema_version is not exact")
    if record["stage"] not in ARTIFACT_INDEX_STAGES:
        _fail("artifact index stage is not authorizing for hardware")

    release = _mapping(record["release"], name="artifact index release")
    _exact_keys(
        release,
        {
            "firmware_version",
            "kernel_version",
            "hardware_model",
            "metadata_abi",
            "tandem_agc",
        },
        name="artifact index release",
    )
    _string(release["firmware_version"], name="artifact firmware version", maximum=256)
    _string(release["kernel_version"], name="artifact kernel version", maximum=256)
    _string(release["hardware_model"], name="artifact hardware model", maximum=256)
    _string(release["metadata_abi"], name="artifact metadata ABI", maximum=128)
    _string(release["tandem_agc"], name="artifact tandem AGC identity", maximum=128)

    source = _mapping(record["source"], name="artifact index source")
    _exact_keys(
        source,
        {"commit", "manifest_path", "manifest_sha256"},
        name="artifact index source",
    )
    _string(
        source["commit"], name="artifact source commit", pattern=_COMMIT, maximum=40
    )
    _relative_path(source["manifest_path"], name="artifact source manifest path")
    _sha256(source["manifest_sha256"], name="artifact source manifest SHA-256")

    build = _mapping(record["build"], name="artifact index build")
    _exact_keys(build, {"run_id", "run_attempt"}, name="artifact index build")
    _exact_int(build["run_id"], name="artifact build run_id", minimum=1)
    _exact_int(build["run_attempt"], name="artifact build run_attempt", minimum=1)

    artifact = _mapping(record["artifact"], name="artifact index payload")
    _exact_keys(
        artifact,
        {"dfu_path", "dfu_bytes", "dfu_sha256", "fit_bytes", "fit_sha256"},
        name="artifact index payload",
    )
    _relative_path(artifact["dfu_path"], name="artifact DFU path")
    dfu_bytes = _exact_int(artifact["dfu_bytes"], name="artifact DFU bytes", minimum=1)
    _sha256(artifact["dfu_sha256"], name="artifact DFU SHA-256")
    fit_bytes = _exact_int(artifact["fit_bytes"], name="artifact FIT bytes", minimum=1)
    _sha256(artifact["fit_sha256"], name="artifact FIT SHA-256")
    if fit_bytes > dfu_bytes:
        _fail("artifact FIT bytes exceed DFU bytes")

    harness = _mapping(record["harness"], name="artifact index harness")
    _exact_keys(harness, {"files"}, name="artifact index harness")
    files = harness["files"]
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)) or not files:
        _fail("artifact harness files must be a nonempty array")
    paths: list[str] = []
    for index, raw_entry in enumerate(files):
        entry = _mapping(raw_entry, name=f"artifact harness file {index}")
        _exact_keys(entry, {"path", "sha256"}, name=f"artifact harness file {index}")
        paths.append(
            _relative_path(entry["path"], name=f"artifact harness path {index}")
        )
        _sha256(entry["sha256"], name=f"artifact harness SHA-256 {index}")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        _fail("artifact harness paths must be unique and sorted")

    evidence = _mapping(record["evidence"], name="artifact index evidence")
    _exact_keys(evidence, {"members"}, name="artifact index evidence")
    members = evidence["members"]
    if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
        _fail("artifact evidence members must be an array")
    roles: list[str] = []
    member_paths: list[str] = []
    for index, raw_member in enumerate(members):
        member = _mapping(raw_member, name=f"artifact evidence member {index}")
        _exact_keys(
            member,
            {"role", "path", "bytes", "sha256"},
            name=f"artifact evidence member {index}",
        )
        roles.append(
            _string(
                member["role"],
                name=f"artifact evidence role {index}",
                pattern=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*"),
                maximum=128,
            )
        )
        member_paths.append(
            _relative_path(member["path"], name=f"artifact evidence path {index}")
        )
        _exact_int(member["bytes"], name=f"artifact evidence bytes {index}", minimum=1)
        _sha256(member["sha256"], name=f"artifact evidence SHA-256 {index}")
    if tuple(roles) != REQUIRED_EVIDENCE_ROLES:
        _fail("artifact evidence role inventory/order is not exact")
    if len(member_paths) != len(set(member_paths)):
        _fail("artifact evidence member paths are not unique")

    return _normalized(record)


def validate_deployment_receipt(
    value: object,
    *,
    artifact_index_sha256: str,
    serial: str,
    firmware_version: str,
    hardware_model: str,
    dfu_sha256: str,
) -> dict[str, Any]:
    """Validate a passing RAM-only receipt against exact expected identities."""

    expected_index_sha = _sha256(
        artifact_index_sha256, name="expected artifact-index SHA-256"
    )
    expected_serial = _string(serial, name="expected radio serial", pattern=_SAFE_ID)
    expected_version = _string(
        firmware_version, name="expected firmware version", maximum=256
    )
    expected_hardware_model = _string(
        hardware_model, name="expected hardware model", maximum=256
    )
    if expected_hardware_model != PLUTOPLUS_HARDWARE_MODEL:
        _fail("expected hardware model is not the exact Pluto+ model")
    expected_dfu_sha = _sha256(dfu_sha256, name="expected DFU SHA-256")

    record = _mapping(value, name="RAM-boot receipt")
    _exact_keys(
        record,
        {
            "schema",
            "schema_version",
            "verdict",
            "boot_mode",
            "artifact_index_sha256",
            "radio",
            "artifact",
            "runtime",
            "boot",
            "persistent_flash",
            "safety",
            "timestamps",
            "topology",
            "host_route",
            "commands",
        },
        name="RAM-boot receipt",
    )
    if record["schema"] != RAM_BOOT_RECEIPT_SCHEMA:
        _fail("RAM-boot receipt schema is not exact")
    if (
        record["schema_version"] != RAM_BOOT_RECEIPT_SCHEMA_VERSION
        or type(record["schema_version"]) is not int
    ):
        _fail("RAM-boot receipt schema_version is not exact")
    if record["verdict"] != "pass" or record["boot_mode"] != "ram-only":
        _fail("RAM-boot receipt is not a passing RAM-only deployment")
    if (
        _sha256(record["artifact_index_sha256"], name="receipt artifact-index SHA-256")
        != expected_index_sha
    ):
        _fail("RAM-boot receipt binds a different artifact index")

    radio = _mapping(record["radio"], name="RAM-boot receipt radio")
    _exact_keys(radio, {"serial"}, name="RAM-boot receipt radio")
    if (
        _string(radio["serial"], name="receipt radio serial", pattern=_SAFE_ID)
        != expected_serial
    ):
        _fail("RAM-boot receipt binds a different radio serial")

    artifact = _mapping(record["artifact"], name="RAM-boot receipt artifact")
    _exact_keys(artifact, {"dfu_sha256"}, name="RAM-boot receipt artifact")
    if _sha256(artifact["dfu_sha256"], name="receipt DFU SHA-256") != expected_dfu_sha:
        _fail("RAM-boot receipt binds different DFU bytes")

    runtime = _mapping(record["runtime"], name="RAM-boot receipt runtime")
    _exact_keys(
        runtime,
        {"firmware_version", "hardware_model"},
        name="RAM-boot receipt runtime",
    )
    if (
        _string(
            runtime["firmware_version"], name="receipt firmware version", maximum=256
        )
        != expected_version
    ):
        _fail("RAM-boot receipt binds a different firmware version")
    if (
        _string(runtime["hardware_model"], name="receipt hardware model", maximum=256)
        != expected_hardware_model
    ):
        _fail("RAM-boot receipt binds a different hardware model")

    boot = _mapping(record["boot"], name="RAM-boot receipt boot")
    _exact_keys(boot, {"pre_id", "post_id"}, name="RAM-boot receipt boot")
    pre_id = _string(boot["pre_id"], name="receipt pre-boot ID", pattern=_SAFE_ID)
    post_id = _string(boot["post_id"], name="receipt post-boot ID", pattern=_SAFE_ID)
    if pre_id == post_id:
        _fail("RAM-boot receipt does not prove a new boot epoch")

    persistent_flash = _mapping(
        record["persistent_flash"], name="RAM-boot receipt persistent flash"
    )
    _exact_keys(
        persistent_flash,
        {
            "partition",
            "mtd_name",
            "bytes",
            "pre_sha256",
            "post_sha256",
            "unchanged",
        },
        name="RAM-boot receipt persistent flash",
    )
    if persistent_flash["partition"] != "/dev/mtdblock3":
        _fail("RAM-boot receipt did not read the firmware MTD block partition")
    if persistent_flash["mtd_name"] != "qspi-linux":
        _fail("RAM-boot receipt did not identify the qspi-linux partition")
    _exact_int(
        persistent_flash["bytes"],
        name="receipt persistent flash bytes",
        minimum=1,
    )
    pre_flash_sha = _sha256(
        persistent_flash["pre_sha256"], name="receipt pre-boot flash SHA-256"
    )
    post_flash_sha = _sha256(
        persistent_flash["post_sha256"], name="receipt post-boot flash SHA-256"
    )
    if (
        not _exact_bool(
            persistent_flash["unchanged"], name="receipt persistent flash unchanged"
        )
        or pre_flash_sha != post_flash_sha
    ):
        _fail("RAM-boot receipt does not prove unchanged persistent firmware")

    safety = _mapping(record["safety"], name="RAM-boot receipt safety")
    _exact_keys(
        safety,
        {
            "final_tx_muted",
            "final_dds_disabled",
            "final_dac_selectors_zero",
            "final_tandem_state",
            "final_fifo_level",
            "final_fault_flags",
        },
        name="RAM-boot receipt safety",
    )
    if not _exact_bool(safety["final_tx_muted"], name="receipt final TX mute"):
        _fail("RAM-boot receipt final TX state is not muted")
    if not _exact_bool(safety["final_dds_disabled"], name="receipt final DDS state"):
        _fail("RAM-boot receipt final DDS state is not disabled")
    if not _exact_bool(
        safety["final_dac_selectors_zero"], name="receipt final DAC selectors"
    ):
        _fail("RAM-boot receipt final DAC selectors are not zero")
    if (
        _string(safety["final_tandem_state"], name="receipt final tandem state")
        != "IDLE"
    ):
        _fail("RAM-boot receipt final tandem state is not IDLE")
    if _exact_int(safety["final_fifo_level"], name="receipt final FIFO level") != 0:
        _fail("RAM-boot receipt final FIFO is not empty")
    if _exact_int(safety["final_fault_flags"], name="receipt final fault flags") != 0:
        _fail("RAM-boot receipt final fault flags are not clear")

    timestamps = _mapping(record["timestamps"], name="RAM-boot receipt timestamps")
    _exact_keys(
        timestamps,
        {"started_unix_ns", "completed_unix_ns"},
        name="RAM-boot receipt timestamps",
    )
    started = _exact_int(
        timestamps["started_unix_ns"], name="receipt start timestamp", minimum=1
    )
    completed = _exact_int(
        timestamps["completed_unix_ns"], name="receipt completion timestamp", minimum=1
    )
    if completed < started:
        _fail("RAM-boot receipt timestamps run backwards")

    topology = _mapping(record["topology"], name="RAM-boot receipt topology")
    _exact_keys(
        topology,
        {
            "usb_port",
            "pre_sysfs_path",
            "dfu_sysfs_path",
            "post_sysfs_path",
            "network_interface",
        },
        name="RAM-boot receipt topology",
    )
    usb_port = _string(
        topology["usb_port"],
        name="receipt USB port",
        pattern=re.compile(r"[0-9]+-[0-9]+(?:[.][0-9]+)*"),
        maximum=128,
    )
    for key in ("pre_sysfs_path", "dfu_sysfs_path", "post_sysfs_path"):
        sysfs_path = _absolute_path(topology[key], name=f"receipt {key}")
        parsed_sysfs = PurePosixPath(sysfs_path)
        if (
            parsed_sysfs.parent != PurePosixPath("/sys/bus/usb/devices")
            or parsed_sysfs.name != usb_port
        ):
            _fail(f"receipt {key} does not identify the exact USB port")
    _string(
        topology["network_interface"],
        name="receipt network interface",
        pattern=_SAFE_ID,
        maximum=128,
    )
    network_interface = str(topology["network_interface"])

    host_route = _mapping(record["host_route"], name="RAM-boot receipt host route")
    _exact_keys(
        host_route,
        {"destination", "interface", "source", "release_verified"},
        name="RAM-boot receipt host route",
    )
    destination_text = _string(
        host_route["destination"], name="receipt host-route destination"
    )
    try:
        destination = ipaddress.ip_network(destination_text, strict=True)
    except ValueError as error:
        raise CandidateBindingError(
            "RAM-boot receipt host-route destination is malformed"
        ) from error
    if destination.version != 4 or destination.prefixlen != 32:
        _fail("RAM-boot receipt host-route destination is not one IPv4 /32")
    if (
        _string(
            host_route["interface"],
            name="receipt host-route interface",
            pattern=_SAFE_ID,
            maximum=128,
        )
        != network_interface
    ):
        _fail("RAM-boot receipt host-route interface differs from USB topology")
    try:
        route_source = ipaddress.ip_address(
            _string(host_route["source"], name="receipt host-route source")
        )
    except ValueError as error:
        raise CandidateBindingError(
            "RAM-boot receipt host-route source is malformed"
        ) from error
    if route_source.version != 4:
        _fail("RAM-boot receipt host-route source is not IPv4")
    if not _exact_bool(
        host_route["release_verified"],
        name="receipt host-route release verification",
    ):
        _fail("RAM-boot receipt did not verify host-route cleanup")

    commands = record["commands"]
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        _fail("RAM-boot receipt commands must be an array")
    expected_phases = (
        "request-ram-mode",
        "download-firmware-to-ram",
        "detach-into-downloaded-image",
    )
    if len(commands) != len(expected_phases):
        _fail("RAM-boot receipt command inventory is not exact")
    normalized_commands: list[list[str]] = []
    for index, (raw_command, expected_phase) in enumerate(
        zip(commands, expected_phases, strict=True)
    ):
        command = _mapping(raw_command, name=f"RAM-boot receipt command {index}")
        _exact_keys(
            command,
            {"phase", "argv"},
            name=f"RAM-boot receipt command {index}",
        )
        if command["phase"] != expected_phase:
            _fail("RAM-boot receipt command phase order is not exact")
        argv = command["argv"]
        if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)) or not argv:
            _fail(f"RAM-boot receipt command {index} argv is not a nonempty array")
        normalized_argv = [
            _string(argument, name=f"receipt command {index} argument {position}")
            for position, argument in enumerate(argv)
        ]
        normalized_commands.append(normalized_argv)
        if any(
            argument in {"-R", "--reset"}
            or argument.lower().endswith((".frm", ".zip"))
            or argument.lower()
            in {"qspi", "flash", "bootloader", "boot.dfu", "uboot-env.dfu"}
            or argument.lower().startswith(("/dev/mtd", "/dev/mtdblock"))
            for argument in normalized_argv
        ):
            _fail("RAM-boot receipt contains a forbidden persistent/reset command")

    request, download, detach = normalized_commands
    request_prefix = [
        "sshpass",
        "-f",
    ]
    if request[: len(request_prefix)] != request_prefix:
        _fail("RAM-boot receipt SSH command lacks transparent password transport")
    if len(request) < 3:
        _fail("RAM-boot receipt SSH password-file option is incomplete")
    _absolute_path(request[2], name="receipt SSH password-file path")
    request_prefix = [
        *request_prefix,
        request[2],
        "ssh",
        "-F",
        "/dev/null",
        "-B",
        network_interface,
        "-o",
        "BatchMode=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PasswordAuthentication=yes",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "CheckHostIP=no",
        "-o",
        "UpdateHostKeys=no",
    ]
    if request[: len(request_prefix)] != request_prefix:
        _fail("RAM-boot receipt SSH command is not the guarded request sequence")
    cursor = len(request_prefix)
    if len(request) - cursor != 2:
        _fail("RAM-boot receipt SSH target/command inventory is not exact")
    target, remote_command = request[cursor:]
    if target.count("@") != 1:
        _fail("RAM-boot receipt SSH target is malformed")
    user, host = target.split("@", 1)
    if _SAFE_SSH_USER.fullmatch(user) is None:
        _fail("RAM-boot receipt SSH user is malformed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise CandidateBindingError(
            "RAM-boot receipt SSH host is not an IP address"
        ) from error
    if (
        address.version != 4
        or address != destination.network_address
        or remote_command != "/usr/sbin/device_reboot ram"
    ):
        _fail("RAM-boot receipt SSH target/remote command is not exact")

    dfu_prefix = [
        "dfu-util",
        "-d",
        "0456:b673,0456:b674",
        "-p",
        usb_port,
        "-a",
        "firmware.dfu",
    ]
    if (
        len(download) != len(dfu_prefix) + 2
        or download[: len(dfu_prefix)] != dfu_prefix
    ):
        _fail("RAM-boot receipt DFU download command is not exact")
    if download[-2] != "-D":
        _fail("RAM-boot receipt DFU download operation is not exact")
    downloaded_path = _absolute_path(download[-1], name="receipt downloaded DFU path")
    parsed_download = PurePosixPath(downloaded_path)
    sealed_descriptor = (
        parsed_download.parts[:4] == ("/", "proc", "self", "fd")
        and len(parsed_download.parts) == 5
        and parsed_download.name.isdigit()
        and int(parsed_download.name) > 2
    )
    if not sealed_descriptor:
        _fail("RAM-boot receipt did not download from a sealed descriptor")
    if detach != [*dfu_prefix, "-e"]:
        _fail("RAM-boot receipt DFU detach command is not exact")

    return _normalized(record)
