"""Pure validation of pluto-plus-utils release-candidate lifecycle records."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from .candidate_binding import CandidateBindingError, validate_artifact_index

PLUTO_PLUS_UTILS_REPOSITORY = "misko/pluto-plus-utils"
PLUTO_PLUS_UTILS_VERSION = "0.1.0"
PLUTO_PLUS_UTILS_SOURCE_COMMIT = "9ef137768d59925acf21d5cd3ff71d1cb523dba7"
CANDIDATE_PLAN_SCHEMA = "pluto-plus-utils.release-candidate-plan.v1"
USB_INVENTORY_SCHEMA = "pluto-plus-utils.release-usb-inventory.v1"
OPERATION_PLAN_SCHEMA = "pluto-plus-utils.release-candidate-operation-plan.v1"
RAM_RECEIPT_SCHEMA = "pluto-plus-utils.release-candidate-ram-receipt.v1"
PLUTOPLUS_HARDWARE_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_IDENTIFIER = re.compile(r"[0-9a-f]{32}")
_SERIAL = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_TOPOLOGY = re.compile(r"[0-9]+-[0-9]+(?:[.][0-9]+)*")
_INTERFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_METADATA_ABI = re.compile(r"frame-metadata-v[1-9][0-9]*")
_BOOT_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_USB_URI = re.compile(r"usb:[1-9][0-9]*[.][1-9][0-9]*[.][1-9][0-9]*")


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


def _integer(value: object, *, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"{name} must be an integer >= {minimum}")
    return value


def _boolean(value: object, *, name: str) -> bool:
    if type(value) is not bool:
        _fail(f"{name} must be a boolean")
    return value


def _sha256(value: object, *, name: str) -> str:
    return _string(value, name=name, pattern=_SHA256, maximum=64)


def _timestamp(value: object, *, name: str) -> datetime:
    text = _string(value, name=name, maximum=64)
    if not text.endswith("Z"):
        _fail(f"{name} must be expressed canonically in UTC")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise CandidateBindingError(f"{name} is not an ISO-8601 timestamp") from error
    return parsed


def _absolute_path(value: object, *, name: str) -> str:
    text = _string(value, name=name)
    path = PurePosixPath(text)
    if not path.is_absolute() or str(path) != text or ".." in path.parts:
        _fail(f"{name} must be a canonical absolute POSIX path")
    return text


def _ipv4(value: object, *, name: str, private: bool = False) -> str:
    text = _string(value, name=name, maximum=64)
    try:
        address = ipaddress.ip_address(text)
    except ValueError as error:
        raise CandidateBindingError(f"{name} is not an IP address") from error
    if (
        address.version != 4
        or str(address) != text
        or (private and not address.is_private)
    ):
        _fail(f"{name} is not a canonical private IPv4 address")
    return text


def _sequence(value: object, *, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail(f"{name} must be an array")
    return value


def _normalized(value: Mapping[str, object]) -> dict[str, Any]:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _file_identity(
    value: object,
    *,
    name: str,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
    expected_name: str | None = None,
) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(record, {"path", "bytes", "sha256"}, name=name)
    path = _absolute_path(record["path"], name=f"{name} path")
    size = _integer(record["bytes"], name=f"{name} bytes", minimum=1)
    digest = _sha256(record["sha256"], name=f"{name} SHA-256")
    if expected_bytes is not None and size != expected_bytes:
        _fail(f"{name} byte count differs from retained bytes")
    if expected_sha256 is not None and digest != expected_sha256:
        _fail(f"{name} SHA-256 differs from retained bytes")
    if expected_name is not None and PurePosixPath(path).name != expected_name:
        _fail(f"{name} filename is not exact")
    return {"path": path, "bytes": size, "sha256": digest}


def _content_identity(
    value: object,
    *,
    name: str,
    expected_bytes: int,
    expected_sha256: str,
) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(record, {"bytes", "sha256"}, name=name)
    size = _integer(record["bytes"], name=f"{name} bytes", minimum=1)
    digest = _sha256(record["sha256"], name=f"{name} SHA-256")
    if size != expected_bytes or digest != expected_sha256:
        _fail(f"{name} differs from the release candidate")
    return {"bytes": size, "sha256": digest}


def _capabilities(value: object, *, name: str) -> tuple[str, ...]:
    raw = _sequence(value, name=name)
    parsed = tuple(
        _string(
            item,
            name=f"{name} item {position}",
            pattern=re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}"),
            maximum=64,
        )
        for position, item in enumerate(raw)
    )
    if not parsed or parsed != tuple(sorted(set(parsed))):
        _fail(f"{name} must be nonempty, unique, and sorted")
    return parsed


def _target(value: object, *, name: str) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(
        record,
        {
            "serial",
            "topology",
            "sysfs_path",
            "vendor_id",
            "product_id",
            "bus_number",
            "device_number",
            "network_interface",
            "source_ipv4",
        },
        name=name,
    )
    serial = _string(record["serial"], name=f"{name} serial", pattern=_SERIAL)
    topology = _string(record["topology"], name=f"{name} topology", pattern=_TOPOLOGY)
    sysfs_path = _absolute_path(record["sysfs_path"], name=f"{name} sysfs path")
    if sysfs_path != f"/sys/bus/usb/devices/{topology}":
        _fail(f"{name} sysfs path does not match its topology")
    if record["vendor_id"] != "0456" or record["product_id"] != "b673":
        _fail(f"{name} is not an exact Pluto runtime USB device")
    return {
        "serial": serial,
        "topology": topology,
        "sysfs_path": sysfs_path,
        "vendor_id": "0456",
        "product_id": "b673",
        "bus_number": _integer(record["bus_number"], name=f"{name} bus", minimum=1),
        "device_number": _integer(
            record["device_number"], name=f"{name} device", minimum=1
        ),
        "network_interface": _string(
            record["network_interface"], name=f"{name} interface", pattern=_INTERFACE
        ),
        "source_ipv4": _ipv4(
            record["source_ipv4"], name=f"{name} source IPv4", private=True
        ),
    }


def validate_release_candidate_plan(
    value: object,
    *,
    artifact_index: object,
    artifact_index_bytes: int,
    artifact_index_sha256: str,
) -> dict[str, Any]:
    """Validate the firmware-produced utility plan against one artifact index."""

    artifact = validate_artifact_index(artifact_index)
    index_digest = _sha256(artifact_index_sha256, name="artifact-index SHA-256")
    record = _mapping(value, name="release candidate plan")
    _exact_keys(
        record,
        {
            "schema",
            "schema_version",
            "candidate_id",
            "created_at",
            "source_repository",
            "source_commit",
            "device_tool_repository",
            "device_tool_version",
            "device_tool_source_commit",
            "artifact_index",
            "dfu",
            "fit",
            "expected_runtime",
            "dfu_identity",
            "allowed_operation",
        },
        name="release candidate plan",
    )
    if record["schema"] != CANDIDATE_PLAN_SCHEMA or record["schema_version"] != 1:
        _fail("release candidate plan schema/version is not exact")
    candidate_id = _string(
        record["candidate_id"], name="candidate ID", pattern=_IDENTIFIER
    )
    _timestamp(record["created_at"], name="candidate creation time")
    if (
        record["source_repository"] != "misko/plutosdr-fw"
        or record["source_commit"] != artifact["source"]["commit"]
    ):
        _fail("release candidate plan source identity is not exact")
    if (
        record["device_tool_repository"] != PLUTO_PLUS_UTILS_REPOSITORY
        or record["device_tool_version"] != PLUTO_PLUS_UTILS_VERSION
        or record["device_tool_source_commit"] != PLUTO_PLUS_UTILS_SOURCE_COMMIT
    ):
        _fail("release candidate plan utility identity is not exact")
    expected_index_name = {
        "candidate-pre-hardware": "candidate-index.json",
        "final-pre-confirmation": "final-artifact-index.json",
    }.get(str(artifact.get("stage", "")))
    if expected_index_name is None:
        _fail("release candidate plan artifact stage is not deployable")
    _file_identity(
        record["artifact_index"],
        name="candidate artifact index",
        expected_bytes=artifact_index_bytes,
        expected_sha256=index_digest,
        expected_name=expected_index_name,
    )
    expected_candidate_id = hashlib.sha256(
        b"pluto-plus-utils.release-candidate-plan.v1\0"
        + index_digest.encode()
        + PLUTO_PLUS_UTILS_SOURCE_COMMIT.encode()
    ).hexdigest()[:32]
    if candidate_id != expected_candidate_id:
        _fail("release candidate plan ID is not derived from its exact inputs")
    dfu_name = PurePosixPath(str(artifact["artifact"]["dfu_path"])).name
    _file_identity(
        record["dfu"],
        name="candidate DFU",
        expected_bytes=artifact["artifact"]["dfu_bytes"],
        expected_sha256=artifact["artifact"]["dfu_sha256"],
        expected_name=dfu_name,
    )
    _content_identity(
        record["fit"],
        name="candidate FIT",
        expected_bytes=artifact["artifact"]["fit_bytes"],
        expected_sha256=artifact["artifact"]["fit_sha256"],
    )
    expected_runtime = _mapping(record["expected_runtime"], name="expected runtime")
    _exact_keys(
        expected_runtime,
        {"firmware_version", "hardware_model", "metadata_abi", "capabilities"},
        name="expected runtime",
    )
    if (
        expected_runtime["firmware_version"] != artifact["release"]["firmware_version"]
        or expected_runtime["hardware_model"] != artifact["release"]["hardware_model"]
        or expected_runtime["metadata_abi"] != artifact["release"]["metadata_abi"]
        or _capabilities(expected_runtime["capabilities"], name="expected capabilities")
        != ("tandem-agc",)
    ):
        _fail("release candidate plan expected runtime differs from the artifact")
    dfu_identity = _mapping(record["dfu_identity"], name="candidate DFU identity")
    expected_dfu_identity = {
        "vendor_id": "0456",
        "runtime_product_id": "b673",
        "dfu_product_id": "b674",
        "selector": "0456:b673,0456:b674",
        "alternate": "firmware.dfu",
    }
    _exact_keys(dfu_identity, set(expected_dfu_identity), name="candidate DFU identity")
    if (
        dict(dfu_identity) != expected_dfu_identity
        or record["allowed_operation"] != "ram-only"
    ):
        _fail("release candidate plan does not authorize only the exact RAM transition")
    return _normalized(record)


def validate_release_usb_inventory(value: object) -> dict[str, Any]:
    """Validate the utility's strict read-only USB inventory."""

    record = _mapping(value, name="release USB inventory")
    _exact_keys(
        record,
        {"schema", "schema_version", "created_at", "devices"},
        name="release USB inventory",
    )
    if record["schema"] != USB_INVENTORY_SCHEMA or record["schema_version"] != 1:
        _fail("release USB inventory schema/version is not exact")
    _timestamp(record["created_at"], name="USB inventory creation time")
    devices = tuple(
        _target(item, name=f"USB inventory device {position}")
        for position, item in enumerate(
            _sequence(record["devices"], name="USB inventory devices")
        )
    )
    if not devices:
        _fail("release USB inventory is empty")
    identities = tuple((item["serial"], item["topology"]) for item in devices)
    serials = tuple(item["serial"] for item in devices)
    topologies = tuple(item["topology"] for item in devices)
    if (
        identities != tuple(sorted(identities))
        or len(serials) != len(set(serials))
        or len(topologies) != len(set(topologies))
    ):
        _fail("release USB inventory identities are not unique and sorted")
    return _normalized(record)


def validate_release_operation_plan(
    value: object,
    *,
    candidate_plan: Mapping[str, Any],
    candidate_plan_bytes: int,
    candidate_plan_sha256: str,
    usb_inventory: Mapping[str, Any],
    usb_inventory_bytes: int,
    usb_inventory_sha256: str,
    serial: str,
) -> dict[str, Any]:
    """Validate one file-only per-radio utility operation plan."""

    expected_serial = _string(serial, name="expected serial", pattern=_SERIAL)
    record = _mapping(value, name="release operation plan")
    _exact_keys(
        record,
        {
            "schema",
            "schema_version",
            "plan_id",
            "created_at",
            "candidate_plan",
            "usb_inventory",
            "target",
            "expected_current_firmware",
            "ssh_host",
            "receipt_path",
            "confirmation_phrase",
            "hardware_accessed",
        },
        name="release operation plan",
    )
    if record["schema"] != OPERATION_PLAN_SCHEMA or record["schema_version"] != 1:
        _fail("release operation plan schema/version is not exact")
    _string(record["plan_id"], name="operation plan ID", pattern=_IDENTIFIER)
    _timestamp(record["created_at"], name="operation plan creation time")
    _file_identity(
        record["candidate_plan"],
        name="operation candidate plan",
        expected_bytes=candidate_plan_bytes,
        expected_sha256=_sha256(candidate_plan_sha256, name="candidate plan SHA-256"),
        expected_name="release-candidate-plan.json",
    )
    _file_identity(
        record["usb_inventory"],
        name="operation USB inventory",
        expected_bytes=usb_inventory_bytes,
        expected_sha256=_sha256(usb_inventory_sha256, name="USB inventory SHA-256"),
        expected_name="usb-inventory.json",
    )
    target = _target(record["target"], name="operation target")
    if target["serial"] != expected_serial:
        _fail("release operation plan binds a different serial")
    inventory_devices = tuple(usb_inventory["devices"])
    if tuple(
        item for item in inventory_devices if item["serial"] == expected_serial
    ) != (target,):
        _fail("release operation target is not exact in its USB inventory")
    _string(
        record["expected_current_firmware"],
        name="expected current firmware",
        maximum=256,
    )
    if (
        _ipv4(record["ssh_host"], name="operation SSH host", private=True)
        != "192.168.2.1"
    ):
        _fail("release operation SSH host is not the exact gadget endpoint")
    receipt_path = _absolute_path(record["receipt_path"], name="operation receipt path")
    if PurePosixPath(receipt_path).name != "ram-boot-receipt.json":
        _fail("release operation receipt filename is not exact")
    if record["confirmation_phrase"] != f"RAM BOOT RELEASE CANDIDATE {expected_serial}":
        _fail("release operation confirmation phrase is not exact")
    if _boolean(record["hardware_accessed"], name="operation hardware access"):
        _fail("release operation plan falsely claims hardware access")
    del candidate_plan
    return _normalized(record)


def _qspi(value: object, *, name: str) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(record, {"partition", "mtd_name", "bytes", "sha256"}, name=name)
    if record["partition"] != "/dev/mtdblock3" or record["mtd_name"] != "qspi-linux":
        _fail(f"{name} is not the exact qspi-linux partition")
    return {
        "partition": "/dev/mtdblock3",
        "mtd_name": "qspi-linux",
        "bytes": _integer(record["bytes"], name=f"{name} bytes", minimum=1),
        "sha256": _sha256(record["sha256"], name=f"{name} SHA-256"),
    }


def _safe_state(value: object, *, name: str) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(
        record,
        {
            "tx_gain_db",
            "dds_raw",
            "dds_scale",
            "dac_selectors",
            "tandem_state",
            "fifo_level",
            "fault_flags",
        },
        name=name,
    )
    gains = tuple(_sequence(record["tx_gain_db"], name=f"{name} TX gains"))
    raw = tuple(_sequence(record["dds_raw"], name=f"{name} DDS raw"))
    scales = tuple(_sequence(record["dds_scale"], name=f"{name} DDS scales"))
    selectors = tuple(_sequence(record["dac_selectors"], name=f"{name} DAC selectors"))
    if (
        len(gains) != 2
        or any(
            type(item) not in {int, float} or not (-120 <= item <= -80)
            for item in gains
        )
        or len(raw) != 8
        or any(type(item) is not int or item != 0 for item in raw)
        or len(scales) != 8
        or any(type(item) not in {int, float} or item != 0 for item in scales)
        or selectors != (3, 3, 3, 3)
        or record["tandem_state"] != "IDLE"
        or _integer(record["fifo_level"], name=f"{name} FIFO") != 0
        or _integer(record["fault_flags"], name=f"{name} faults") != 0
    ):
        _fail(f"{name} is not the exact muted/idle safe state")
    return _normalized(record)


def _runtime(value: object, *, name: str) -> dict[str, object]:
    record = _mapping(value, name=name)
    _exact_keys(
        record,
        {
            "serial",
            "topology",
            "usb_uri",
            "hardware_model",
            "firmware_version",
            "metadata_abi",
            "capabilities",
            "boot_id",
            "qspi",
            "safe_state",
        },
        name=name,
    )
    return {
        "serial": _string(record["serial"], name=f"{name} serial", pattern=_SERIAL),
        "topology": _string(
            record["topology"], name=f"{name} topology", pattern=_TOPOLOGY
        ),
        "usb_uri": _string(record["usb_uri"], name=f"{name} USB URI", pattern=_USB_URI),
        "hardware_model": _string(record["hardware_model"], name=f"{name} model"),
        "firmware_version": _string(
            record["firmware_version"], name=f"{name} firmware"
        ),
        "metadata_abi": _string(
            record["metadata_abi"], name=f"{name} ABI", pattern=_METADATA_ABI
        ),
        "capabilities": list(
            _capabilities(record["capabilities"], name=f"{name} capabilities")
        ),
        "boot_id": _string(record["boot_id"], name=f"{name} boot ID", pattern=_BOOT_ID),
        "qspi": _qspi(record["qspi"], name=f"{name} QSPI"),
        "safe_state": _safe_state(record["safe_state"], name=f"{name} safe state"),
    }


def validate_release_candidate_receipt(
    value: object,
    *,
    candidate_plan: Mapping[str, Any],
    candidate_plan_bytes: int,
    candidate_plan_sha256: str,
    operation_plan: Mapping[str, Any],
    operation_plan_bytes: int,
    operation_plan_sha256: str,
    serial: str,
) -> dict[str, Any]:
    """Validate one passing utility receipt against its retained plan files."""

    expected_serial = _string(serial, name="expected serial", pattern=_SERIAL)
    record = _mapping(value, name="release candidate RAM receipt")
    _exact_keys(
        record,
        {
            "schema",
            "schema_version",
            "receipt_id",
            "outcome",
            "started_at",
            "completed_at",
            "tool_repository",
            "tool_version",
            "tool_source_commit",
            "operation_plan",
            "candidate_plan",
            "candidate_dfu",
            "candidate_fit",
            "target",
            "expected_firmware",
            "expected_hardware_model",
            "expected_metadata_abi",
            "required_capabilities",
            "pre_runtime",
            "post_runtime",
            "host_route",
            "transition",
            "cleanup",
            "failure_phase",
            "error",
        },
        name="release candidate RAM receipt",
    )
    if record["schema"] != RAM_RECEIPT_SCHEMA or record["schema_version"] != 1:
        _fail("release candidate RAM receipt schema/version is not exact")
    _string(record["receipt_id"], name="receipt ID", pattern=_IDENTIFIER)
    if (
        record["outcome"] != "pass"
        or record["failure_phase"] is not None
        or record["error"] is not None
    ):
        _fail("release candidate RAM receipt is not a clean passing outcome")
    started = _timestamp(record["started_at"], name="receipt start time")
    completed = _timestamp(record["completed_at"], name="receipt completion time")
    if completed < started:
        _fail("release candidate RAM receipt timestamps run backwards")
    if (
        record["tool_repository"] != candidate_plan["device_tool_repository"]
        or record["tool_version"] != candidate_plan["device_tool_version"]
        or record["tool_source_commit"] != candidate_plan["device_tool_source_commit"]
    ):
        _fail("release candidate RAM receipt utility identity differs from its plan")
    _file_identity(
        record["candidate_plan"],
        name="receipt candidate plan",
        expected_bytes=candidate_plan_bytes,
        expected_sha256=_sha256(candidate_plan_sha256, name="candidate plan SHA-256"),
        expected_name="release-candidate-plan.json",
    )
    _file_identity(
        record["operation_plan"],
        name="receipt operation plan",
        expected_bytes=operation_plan_bytes,
        expected_sha256=_sha256(operation_plan_sha256, name="operation plan SHA-256"),
        expected_name="operation-plan.json",
    )
    _content_identity(
        record["candidate_dfu"],
        name="receipt DFU",
        expected_bytes=candidate_plan["dfu"]["bytes"],
        expected_sha256=candidate_plan["dfu"]["sha256"],
    )
    _content_identity(
        record["candidate_fit"],
        name="receipt FIT",
        expected_bytes=candidate_plan["fit"]["bytes"],
        expected_sha256=candidate_plan["fit"]["sha256"],
    )
    target = _target(record["target"], name="receipt target")
    if target != operation_plan["target"] or target["serial"] != expected_serial:
        _fail("release candidate RAM receipt target differs from its operation plan")
    expected_runtime = candidate_plan["expected_runtime"]
    if (
        record["expected_firmware"] != expected_runtime["firmware_version"]
        or record["expected_hardware_model"] != expected_runtime["hardware_model"]
        or record["expected_metadata_abi"] != expected_runtime["metadata_abi"]
        or _capabilities(
            record["required_capabilities"], name="receipt required capabilities"
        )
        != tuple(expected_runtime["capabilities"])
    ):
        _fail("release candidate RAM receipt expected runtime differs from its plan")
    pre = _runtime(record["pre_runtime"], name="receipt preboot runtime")
    post = _runtime(record["post_runtime"], name="receipt postboot runtime")
    if (
        pre["serial"] != expected_serial
        or post["serial"] != expected_serial
        or pre["topology"] != target["topology"]
        or post["topology"] != target["topology"]
        or pre["firmware_version"] != operation_plan["expected_current_firmware"]
        or post["firmware_version"] != expected_runtime["firmware_version"]
        or pre["hardware_model"] != expected_runtime["hardware_model"]
        or post["hardware_model"] != expected_runtime["hardware_model"]
        or post["metadata_abi"] != expected_runtime["metadata_abi"]
        or tuple(post["capabilities"]) != tuple(expected_runtime["capabilities"])
        or pre["boot_id"] == post["boot_id"]
        or pre["qspi"] != post["qspi"]
    ):
        _fail(
            "release candidate RAM receipt does not prove the exact RAM-only runtime transition"
        )
    host_route = _mapping(record["host_route"], name="receipt host route")
    _exact_keys(
        host_route,
        {"destination", "interface", "source", "release_verified"},
        name="receipt host route",
    )
    if (
        host_route["destination"] != f"{operation_plan['ssh_host']}/32"
        or host_route["interface"] != target["network_interface"]
        or host_route["source"] != target["source_ipv4"]
        or host_route["release_verified"] is not True
    ):
        _fail("release candidate RAM receipt host route is not exact and released")
    transition = _mapping(record["transition"], name="receipt transition")
    expected_transition = {
        "method": "download-then-detach-e",
        "selector": "0456:b673,0456:b674",
        "topology": target["topology"],
        "alternate": "firmware.dfu",
        "sealed_input": True,
        "download_completed": True,
        "detach_completed": True,
        "persistent_write": False,
    }
    _exact_keys(transition, set(expected_transition), name="receipt transition")
    if dict(transition) != expected_transition:
        _fail("release candidate RAM receipt transition is not exact")
    cleanup = _mapping(record["cleanup"], name="receipt cleanup")
    _exact_keys(cleanup, {"verified", "errors"}, name="receipt cleanup")
    if cleanup["verified"] is not True or tuple(
        _sequence(cleanup["errors"], name="cleanup errors")
    ):
        _fail("release candidate RAM receipt cleanup is not verified")
    return _normalized(record)
