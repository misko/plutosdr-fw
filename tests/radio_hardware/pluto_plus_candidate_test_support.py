"""Test-only construction of exact pluto-plus-utils candidate lifecycle records."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .pluto_plus_candidate import (
    PLUTO_IIO_BUFFER_METADATA_ABI,
    PLUTO_PLUS_UTILS_REPOSITORY,
    PLUTO_PLUS_UTILS_SOURCE_COMMIT,
    PLUTO_PLUS_UTILS_VERSION,
)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def identity(path: Path, value: object) -> dict[str, object]:
    payload = canonical_bytes(value)
    return {
        "path": str(path.absolute()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_private(path: Path, value: object) -> bytes:
    payload = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o755)
    path.write_bytes(payload)
    path.chmod(0o600)
    return payload


def build_utility_deployment_bundle(
    *,
    root: Path,
    artifact_index_path: Path,
    artifact_index: dict[str, Any],
    artifact_index_payload: bytes,
    serial: str,
    expected_current_firmware: str,
    topology: str = "3-8",
    bus_number: int = 3,
    device_number: int = 23,
    network_interface: str = "enx001122334455",
    source_ipv4: str = "192.168.2.10",
) -> dict[str, Path]:
    """Write one exact private plan/inventory/operation/passing-receipt fixture."""

    deploy = root / "hardware" / "deploy" / serial
    deploy.mkdir(parents=True, exist_ok=True)
    os.chmod(deploy, 0o755)
    candidate_path = deploy / "release-candidate-plan.json"
    inventory_path = deploy / "usb-inventory.json"
    operation_path = deploy / "operation-plan.json"
    receipt_path = deploy / "ram-boot-receipt.json"
    dfu_path = root / artifact_index["artifact"]["dfu_path"]
    now = "2026-08-26T18:00:00Z"
    artifact_index_sha256 = hashlib.sha256(artifact_index_payload).hexdigest()
    candidate = {
        "schema": "pluto-plus-utils.release-candidate-plan.v1",
        "schema_version": 1,
        "candidate_id": hashlib.sha256(
            b"pluto-plus-utils.release-candidate-plan.v1\0"
            + artifact_index_sha256.encode()
            + PLUTO_PLUS_UTILS_SOURCE_COMMIT.encode()
        ).hexdigest()[:32],
        "created_at": now,
        "source_repository": "misko/plutosdr-fw",
        "source_commit": artifact_index["source"]["commit"],
        "device_tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
        "device_tool_version": PLUTO_PLUS_UTILS_VERSION,
        "device_tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
        "artifact_index": {
            "path": str(artifact_index_path.absolute()),
            "bytes": len(artifact_index_payload),
            "sha256": artifact_index_sha256,
        },
        "dfu": {
            "path": str(dfu_path.absolute()),
            "bytes": artifact_index["artifact"]["dfu_bytes"],
            "sha256": artifact_index["artifact"]["dfu_sha256"],
        },
        "fit": {
            "bytes": artifact_index["artifact"]["fit_bytes"],
            "sha256": artifact_index["artifact"]["fit_sha256"],
        },
        "expected_runtime": {
            "firmware_version": artifact_index["release"]["firmware_version"],
            "hardware_model": artifact_index["release"]["hardware_model"],
            "metadata_abi": PLUTO_IIO_BUFFER_METADATA_ABI,
            "capabilities": ["tandem-agc"],
        },
        "dfu_identity": {
            "vendor_id": "0456",
            "runtime_product_id": "b673",
            "dfu_product_id": "b674",
            "selector": "0456:b673,0456:b674",
            "alternate": "firmware.dfu",
        },
        "allowed_operation": "ram-only",
    }
    candidate_payload = write_private(candidate_path, candidate)
    target = {
        "serial": serial,
        "topology": topology,
        "sysfs_path": f"/sys/bus/usb/devices/{topology}",
        "vendor_id": "0456",
        "product_id": "b673",
        "bus_number": bus_number,
        "device_number": device_number,
        "network_interface": network_interface,
        "source_ipv4": source_ipv4,
    }
    inventory = {
        "schema": "pluto-plus-utils.release-usb-inventory.v1",
        "schema_version": 1,
        "created_at": now,
        "devices": [target],
    }
    inventory_payload = write_private(inventory_path, inventory)
    operation = {
        "schema": "pluto-plus-utils.release-candidate-operation-plan.v1",
        "schema_version": 1,
        "plan_id": "6" * 32,
        "created_at": now,
        "candidate_plan": {
            "path": str(candidate_path.absolute()),
            "bytes": len(candidate_payload),
            "sha256": hashlib.sha256(candidate_payload).hexdigest(),
        },
        "usb_inventory": {
            "path": str(inventory_path.absolute()),
            "bytes": len(inventory_payload),
            "sha256": hashlib.sha256(inventory_payload).hexdigest(),
        },
        "target": target,
        "expected_current_firmware": expected_current_firmware,
        "ssh_host": "192.168.2.1",
        "receipt_path": str(receipt_path.absolute()),
        "confirmation_phrase": f"RAM BOOT RELEASE CANDIDATE {serial}",
        "hardware_accessed": False,
    }
    operation_payload = write_private(operation_path, operation)

    def safe_state() -> dict[str, Any]:
        return {
            "tx_gain_db": [-80.0, -80.0],
            "dds_raw": [0] * 8,
            "dds_scale": [0.0] * 8,
            "dac_selectors": [3, 3, 3, 3],
            "tandem_state": "IDLE",
            "fifo_level": 0,
            "fault_flags": 0,
        }

    def runtime(firmware: str, boot_id: str) -> dict[str, Any]:
        value = {
            "serial": serial,
            "topology": topology,
            "usb_uri": f"usb:{bus_number}.{device_number}.5",
            "hardware_model": artifact_index["release"]["hardware_model"],
            "firmware_version": firmware,
            "metadata_abi": PLUTO_IIO_BUFFER_METADATA_ABI,
            "capabilities": ["tandem-agc"],
            "boot_id": boot_id,
            "qspi": {
                "partition": "/dev/mtdblock3",
                "mtd_name": "qspi-linux",
                "bytes": 31_457_280,
                "sha256": "7" * 64,
            },
            "safe_state": safe_state(),
        }
        if artifact_index["release"]["hardware_model"].endswith("(Z7010-AD9363A)"):
            value["canonical_hardware_setup"] = {
                "uboot_attr_name_absent": True,
                "uboot_attr_val_absent": True,
                "uboot_compatible": "ad9361",
                "uboot_mode": "2r2t",
                "phy_model": "ad9363a",
                "rx_scan_channels": [
                    "voltage0",
                    "voltage1",
                    "voltage2",
                    "voltage3",
                ],
                "tandem_device": True,
            }
        return value

    receipt = {
        "schema": "pluto-plus-utils.release-candidate-ram-receipt.v1",
        "schema_version": 1,
        "receipt_id": "8" * 32,
        "outcome": "pass",
        "started_at": now,
        "completed_at": "2026-08-26T18:02:00Z",
        "tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
        "tool_version": PLUTO_PLUS_UTILS_VERSION,
        "tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
        "operation_plan": {
            "path": str(operation_path.absolute()),
            "bytes": len(operation_payload),
            "sha256": hashlib.sha256(operation_payload).hexdigest(),
        },
        "candidate_plan": {
            "path": str(candidate_path.absolute()),
            "bytes": len(candidate_payload),
            "sha256": hashlib.sha256(candidate_payload).hexdigest(),
        },
        "candidate_dfu": {
            "bytes": artifact_index["artifact"]["dfu_bytes"],
            "sha256": artifact_index["artifact"]["dfu_sha256"],
        },
        "candidate_fit": {
            "bytes": artifact_index["artifact"]["fit_bytes"],
            "sha256": artifact_index["artifact"]["fit_sha256"],
        },
        "target": target,
        "expected_firmware": artifact_index["release"]["firmware_version"],
        "expected_hardware_model": artifact_index["release"]["hardware_model"],
        "expected_metadata_abi": PLUTO_IIO_BUFFER_METADATA_ABI,
        "required_capabilities": ["tandem-agc"],
        "pre_runtime": runtime(
            expected_current_firmware,
            "11111111-1111-4111-8111-111111111111",
        ),
        "post_runtime": runtime(
            artifact_index["release"]["firmware_version"],
            "22222222-2222-4222-8222-222222222222",
        ),
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": network_interface,
            "source": source_ipv4,
            "release_verified": True,
        },
        "transition": {
            "method": "download-then-detach-e",
            "selector": "0456:b673,0456:b674",
            "topology": topology,
            "alternate": "firmware.dfu",
            "sealed_input": True,
            "download_completed": True,
            "detach_completed": True,
            "persistent_write": False,
        },
        "cleanup": {"verified": True, "errors": []},
        "failure_phase": None,
        "error": None,
    }
    write_private(receipt_path, receipt)
    return {
        "candidate_plan": candidate_path,
        "usb_inventory": inventory_path,
        "operation_plan": operation_path,
        "receipt": receipt_path,
    }
