"""Planted oracles for the pluto-plus-utils release-candidate contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest

from .candidate_binding import REQUIRED_EVIDENCE_ROLES, CandidateBindingError
from .pluto_plus_candidate import (
    PLUTO_PLUS_UTILS_REPOSITORY,
    PLUTO_PLUS_UTILS_SOURCE_COMMIT,
    PLUTO_PLUS_UTILS_VERSION,
    PLUTOPLUS_HARDWARE_MODEL,
    validate_release_candidate_plan,
    validate_release_candidate_receipt,
    validate_release_operation_plan,
    validate_release_usb_inventory,
)

SERIAL = "winbond-db6968136727402c"
VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc15"
INDEX_SHA = "a" * 64
DFU_SHA = "b" * 64
FIT_SHA = "c" * 64
INDEX_BYTES = 9_890
NOW = "2026-08-26T17:00:00Z"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _identity(path: str, value: object) -> dict[str, object]:
    payload = _canonical(value)
    return {
        "path": path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _artifact_index() -> dict[str, Any]:
    return {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": "candidate-pre-hardware",
        "release": {
            "firmware_version": VERSION,
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": PLUTOPLUS_HARDWARE_MODEL,
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": "1" * 40,
            "manifest_path": "source/tandem-agc-v8-rc15-source.yaml",
            "manifest_sha256": "2" * 64,
        },
        "build": {"run_id": 1234, "run_attempt": 1},
        "artifact": {
            "dfu_path": "artifact/firmware.dfu",
            "dfu_bytes": 8_388_624,
            "dfu_sha256": DFU_SHA,
            "fit_bytes": 8_388_608,
            "fit_sha256": FIT_SHA,
        },
        "harness": {
            "files": [
                {"path": "scripts/tandem_release_device_plan.py", "sha256": "3" * 64},
                {
                    "path": "tests/radio_hardware/pluto_plus_candidate.py",
                    "sha256": "4" * 64,
                },
            ]
        },
        "evidence": {
            "members": [
                {
                    "role": role,
                    "path": f"evidence/{role}.txt",
                    "bytes": position + 1,
                    "sha256": f"{(position + 5) % 16:x}" * 64,
                }
                for position, role in enumerate(REQUIRED_EVIDENCE_ROLES)
            ]
        },
    }


def _candidate() -> dict[str, Any]:
    return {
        "schema": "pluto-plus-utils.release-candidate-plan.v1",
        "schema_version": 1,
        "candidate_id": hashlib.sha256(
            b"pluto-plus-utils.release-candidate-plan.v1\0"
            + INDEX_SHA.encode()
            + PLUTO_PLUS_UTILS_SOURCE_COMMIT.encode()
        ).hexdigest()[:32],
        "created_at": NOW,
        "source_repository": "misko/plutosdr-fw",
        "source_commit": "1" * 40,
        "device_tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
        "device_tool_version": PLUTO_PLUS_UTILS_VERSION,
        "device_tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
        "artifact_index": {
            "path": "/private/rc15/candidate-index.json",
            "bytes": INDEX_BYTES,
            "sha256": INDEX_SHA,
        },
        "dfu": {
            "path": "/private/rc15/artifact/firmware.dfu",
            "bytes": 8_388_624,
            "sha256": DFU_SHA,
        },
        "fit": {"bytes": 8_388_608, "sha256": FIT_SHA},
        "expected_runtime": {
            "firmware_version": VERSION,
            "hardware_model": PLUTOPLUS_HARDWARE_MODEL,
            "metadata_abi": "frame-metadata-v5",
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


def _target() -> dict[str, Any]:
    return {
        "serial": SERIAL,
        "topology": "3-7",
        "sysfs_path": "/sys/bus/usb/devices/3-7",
        "vendor_id": "0456",
        "product_id": "b673",
        "bus_number": 3,
        "device_number": 29,
        "network_interface": "enx00e02215c53b",
        "source_ipv4": "192.168.2.10",
    }


def _inventory() -> dict[str, Any]:
    return {
        "schema": "pluto-plus-utils.release-usb-inventory.v1",
        "schema_version": 1,
        "created_at": NOW,
        "devices": [_target()],
    }


def _operation(candidate: object, inventory: object) -> dict[str, Any]:
    return {
        "schema": "pluto-plus-utils.release-candidate-operation-plan.v1",
        "schema_version": 1,
        "plan_id": "6" * 32,
        "created_at": NOW,
        "candidate_plan": _identity(
            f"/private/rc15/hardware/deploy/{SERIAL}/release-candidate-plan.json",
            candidate,
        ),
        "usb_inventory": _identity(
            f"/private/rc15/hardware/deploy/{SERIAL}/usb-inventory.json", inventory
        ),
        "target": _target(),
        "expected_current_firmware": "v0.41-plutoplus-spf-tandem-agc-v8-rc12",
        "ssh_host": "192.168.2.1",
        "receipt_path": f"/private/rc15/hardware/deploy/{SERIAL}/ram-boot-receipt.json",
        "confirmation_phrase": f"RAM BOOT RELEASE CANDIDATE {SERIAL}",
        "hardware_accessed": False,
    }


def _safe() -> dict[str, Any]:
    return {
        "tx_gain_db": [-80.0, -80.0],
        "dds_raw": [0] * 8,
        "dds_scale": [0.0] * 8,
        "dac_selectors": [3, 3, 3, 3],
        "tandem_state": "IDLE",
        "fifo_level": 0,
        "fault_flags": 0,
    }


def _runtime(firmware: str, boot_id: str) -> dict[str, Any]:
    return {
        "serial": SERIAL,
        "topology": "3-7",
        "usb_uri": "usb:3.29.5",
        "hardware_model": PLUTOPLUS_HARDWARE_MODEL,
        "firmware_version": firmware,
        "metadata_abi": "frame-metadata-v5",
        "capabilities": ["tandem-agc"],
        "boot_id": boot_id,
        "qspi": {
            "partition": "/dev/mtdblock3",
            "mtd_name": "qspi-linux",
            "bytes": 31_457_280,
            "sha256": "7" * 64,
        },
        "safe_state": _safe(),
    }


def _receipt(candidate: object, operation: object) -> dict[str, Any]:
    return {
        "schema": "pluto-plus-utils.release-candidate-ram-receipt.v1",
        "schema_version": 1,
        "receipt_id": "8" * 32,
        "outcome": "pass",
        "started_at": NOW,
        "completed_at": "2026-08-26T17:02:00Z",
        "tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
        "tool_version": PLUTO_PLUS_UTILS_VERSION,
        "tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
        "operation_plan": _identity(
            f"/private/rc15/hardware/deploy/{SERIAL}/operation-plan.json", operation
        ),
        "candidate_plan": _identity(
            f"/private/rc15/hardware/deploy/{SERIAL}/release-candidate-plan.json",
            candidate,
        ),
        "candidate_dfu": {"bytes": 8_388_624, "sha256": DFU_SHA},
        "candidate_fit": {"bytes": 8_388_608, "sha256": FIT_SHA},
        "target": _target(),
        "expected_firmware": VERSION,
        "expected_hardware_model": PLUTOPLUS_HARDWARE_MODEL,
        "expected_metadata_abi": "frame-metadata-v5",
        "required_capabilities": ["tandem-agc"],
        "pre_runtime": _runtime(
            "v0.41-plutoplus-spf-tandem-agc-v8-rc12",
            "11111111-1111-4111-8111-111111111111",
        ),
        "post_runtime": _runtime(VERSION, "22222222-2222-4222-8222-222222222222"),
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": "enx00e02215c53b",
            "source": "192.168.2.10",
            "release_verified": True,
        },
        "transition": {
            "method": "download-then-detach-e",
            "selector": "0456:b673,0456:b674",
            "topology": "3-7",
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


def _validate(
    candidate: dict[str, Any],
    inventory: dict[str, Any],
    operation: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    validated_candidate = validate_release_candidate_plan(
        candidate,
        artifact_index=_artifact_index(),
        artifact_index_bytes=INDEX_BYTES,
        artifact_index_sha256=INDEX_SHA,
    )
    validated_inventory = validate_release_usb_inventory(inventory)
    candidate_identity = _identity("/retained/release-candidate-plan.json", candidate)
    inventory_identity = _identity("/retained/usb-inventory.json", inventory)
    validated_operation = validate_release_operation_plan(
        operation,
        candidate_plan=validated_candidate,
        candidate_plan_bytes=candidate_identity["bytes"],
        candidate_plan_sha256=candidate_identity["sha256"],
        usb_inventory=validated_inventory,
        usb_inventory_bytes=inventory_identity["bytes"],
        usb_inventory_sha256=inventory_identity["sha256"],
        serial=SERIAL,
    )
    operation_identity = _identity("/retained/operation-plan.json", operation)
    validate_release_candidate_receipt(
        receipt,
        candidate_plan=validated_candidate,
        candidate_plan_bytes=candidate_identity["bytes"],
        candidate_plan_sha256=candidate_identity["sha256"],
        operation_plan=validated_operation,
        operation_plan_bytes=operation_identity["bytes"],
        operation_plan_sha256=operation_identity["sha256"],
        serial=SERIAL,
    )


def test_exact_utility_contract_bundle_passes() -> None:
    candidate = _candidate()
    inventory = _inventory()
    operation = _operation(candidate, inventory)
    receipt = _receipt(candidate, operation)

    _validate(candidate, inventory, operation, receipt)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c, _i, _o, _r: c.update(device_tool_source_commit="9" * 40),
        lambda c, _i, _o, _r: c.update(allowed_operation="persistent"),
        lambda _c, i, _o, _r: i["devices"][0].update(topology="3-8"),
        lambda _c, _i, o, _r: o.update(hardware_accessed=True),
        lambda _c, _i, o, _r: o.update(ssh_host="192.168.3.1"),
        lambda _c, _i, _o, r: r.update(outcome="unknown"),
        lambda _c, _i, _o, r: r.update(tool_source_commit="9" * 40),
        lambda _c, _i, _o, r: r["post_runtime"]["qspi"].update(sha256="9" * 64),
        lambda _c, _i, _o, r: r["post_runtime"]["safe_state"].update(fifo_level=1),
        lambda _c, _i, _o, r: r["transition"].update(persistent_write=True),
        lambda _c, _i, _o, r: r["host_route"].update(release_verified=False),
        lambda _c, _i, _o, r: r.update(extra="decoy"),
    ],
)
def test_utility_contract_bundle_rejects_authority_and_semantic_mutations(
    mutation: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]], object
    ],
) -> None:
    candidate = _candidate()
    inventory = _inventory()
    operation = _operation(candidate, inventory)
    receipt = _receipt(candidate, operation)
    mutation(candidate, inventory, operation, receipt)

    with pytest.raises(CandidateBindingError):
        _validate(candidate, inventory, operation, receipt)


def test_candidate_plan_binds_exact_artifact_index_identity() -> None:
    candidate = _candidate()
    candidate["artifact_index"]["sha256"] = "9" * 64

    with pytest.raises(CandidateBindingError, match="artifact index SHA-256"):
        validate_release_candidate_plan(
            candidate,
            artifact_index=_artifact_index(),
            artifact_index_bytes=INDEX_BYTES,
            artifact_index_sha256=INDEX_SHA,
        )


@pytest.mark.parametrize("duplicate", ["serial", "topology"])
def test_usb_inventory_rejects_duplicate_physical_identity(duplicate: str) -> None:
    inventory = _inventory()
    second = dict(inventory["devices"][0])
    if duplicate == "serial":
        second["topology"] = "3-9"
        second["sysfs_path"] = "/sys/bus/usb/devices/3-9"
    else:
        second["serial"] = "zzzz-radio"
    inventory["devices"].append(second)

    with pytest.raises(CandidateBindingError, match="not unique"):
        validate_release_usb_inventory(inventory)
