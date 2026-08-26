"""Planted-failure oracles for candidate artifact and RAM receipt binding."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest

from .candidate_binding import (
    PLUTOPLUS_HARDWARE_MODEL,
    REQUIRED_EVIDENCE_ROLES,
    CandidateBindingError,
    validate_artifact_index,
    validate_deployment_receipt,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SERIAL = "104473222a87000abc00123456789def"
VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc20"


def _artifact_index() -> dict[str, Any]:
    return {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": "candidate-pre-hardware",
        "release": {
            "firmware_version": VERSION,
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": "1" * 40,
            "manifest_path": "source/tandem-agc-v8-rc20-source.yaml",
            "manifest_sha256": "2" * 64,
        },
        "build": {"run_id": 1234, "run_attempt": 1},
        "artifact": {
            "dfu_path": "artifact/firmware.dfu",
            "dfu_bytes": 8_388_624,
            "dfu_sha256": SHA_A,
            "fit_bytes": 8_388_608,
            "fit_sha256": SHA_B,
        },
        "harness": {
            "files": [
                {
                    "path": "scripts/run_tandem_agc_release_hardware.sh",
                    "sha256": "3" * 64,
                },
                {"path": "tests/radio_hardware/release_cli.py", "sha256": "4" * 64},
            ]
        },
        "evidence": {
            "members": [
                {
                    "role": role,
                    "path": f"evidence/{role}.txt",
                    "bytes": index + 1,
                    "sha256": f"{(index + 5) % 16:x}" * 64,
                }
                for index, role in enumerate(REQUIRED_EVIDENCE_ROLES)
            ]
        },
    }


def _receipt() -> dict[str, Any]:
    return {
        "schema": "plutosdr-fw.tandem-ram-boot-receipt",
        "schema_version": 4,
        "verdict": "pass",
        "boot_mode": "ram-only",
        "artifact_index_sha256": SHA_B,
        "radio": {"serial": SERIAL},
        "artifact": {"dfu_sha256": SHA_A},
        "runtime": {
            "firmware_version": VERSION,
            "hardware_model": PLUTOPLUS_HARDWARE_MODEL,
        },
        "boot": {"pre_id": "boot-before", "post_id": "boot-after"},
        "persistent_flash": {
            "partition": "/dev/mtdblock3",
            "mtd_name": "qspi-linux",
            "bytes": 32 * 1024 * 1024,
            "pre_sha256": "7" * 64,
            "post_sha256": "7" * 64,
            "unchanged": True,
        },
        "safety": {
            "final_tx_muted": True,
            "final_dds_disabled": True,
            "final_dac_selectors_zero": True,
            "final_tandem_state": "IDLE",
            "final_fifo_level": 0,
            "final_fault_flags": 0,
        },
        "timestamps": {"started_unix_ns": 100, "completed_unix_ns": 200},
        "topology": {
            "usb_port": "1-2.3",
            "pre_sysfs_path": "/sys/bus/usb/devices/1-2.3",
            "dfu_sysfs_path": "/sys/bus/usb/devices/1-2.3",
            "post_sysfs_path": "/sys/bus/usb/devices/1-2.3",
            "network_interface": "enx001122334455",
        },
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": "enx001122334455",
            "source": "192.168.2.10",
            "release_verified": True,
        },
        "commands": [
            {
                "phase": "request-ram-mode",
                "argv": [
                    "sshpass",
                    "-f",
                    "/private/ssh-password",
                    "ssh",
                    "-F",
                    "/dev/null",
                    "-B",
                    "enx001122334455",
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
                    "root@192.168.2.1",
                    "/usr/sbin/device_reboot ram",
                ],
            },
            {
                "phase": "download-firmware-to-ram",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "1-2.3",
                    "-a",
                    "firmware.dfu",
                    "-D",
                    "/proc/self/fd/9",
                ],
            },
            {
                "phase": "detach-into-downloaded-image",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "1-2.3",
                    "-a",
                    "firmware.dfu",
                    "-e",
                ],
            },
        ],
    }


def _validate_receipt(value: object) -> dict[str, Any]:
    return validate_deployment_receipt(
        value,
        artifact_index_sha256=SHA_B,
        serial=SERIAL,
        firmware_version=VERSION,
        hardware_model=PLUTOPLUS_HARDWARE_MODEL,
        dfu_sha256=SHA_A,
    )


def test_candidate_bindings_accept_exact_versioned_records_and_return_copies() -> None:
    index = _artifact_index()
    receipt = _receipt()

    validated_index = validate_artifact_index(index)
    validated_receipt = _validate_receipt(receipt)

    assert validated_index == index and validated_index is not index
    assert validated_receipt == receipt and validated_receipt is not receipt


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value.update(schema_version=True),
        lambda value: value.update(stage="candidate-qualified"),
        lambda value: value["source"].update(commit="A" * 40),
        lambda value: value["source"].update(manifest_path="../escape.yaml"),
        lambda value: value["build"].update(run_attempt=0),
        lambda value: value["artifact"].update(dfu_sha256="A" * 64),
        lambda value: value["artifact"].update(fit_bytes=9_000_000),
        lambda value: value["harness"]["files"].reverse(),
        lambda value: value["harness"]["files"][0].update(extra="decoy"),
        lambda value: value["evidence"]["members"].pop(),
        lambda value: value["evidence"]["members"][0].update(bytes=True),
        lambda value: value["evidence"]["members"][1].update(
            path=value["evidence"]["members"][0]["path"]
        ),
    ],
)
def test_artifact_index_rejects_identity_and_shape_mutations(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    value = copy.deepcopy(_artifact_index())
    mutation(value)

    with pytest.raises(CandidateBindingError):
        validate_artifact_index(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value.update(schema_version=3),
        lambda value: value.update(verdict="fail"),
        lambda value: value.update(boot_mode="persistent"),
        lambda value: value.update(artifact_index_sha256="0" * 64),
        lambda value: value["radio"].update(serial="another-radio"),
        lambda value: value["artifact"].update(dfu_sha256="0" * 64),
        lambda value: value["runtime"].update(firmware_version="wrong"),
        lambda value: value["runtime"].update(hardware_model="wrong"),
        lambda value: value["runtime"].pop("hardware_model"),
        lambda value: value["boot"].update(post_id="boot-before"),
        lambda value: value["persistent_flash"].update(mtd_name="bootloader"),
        lambda value: value["persistent_flash"].update(post_sha256="8" * 64),
        lambda value: value["persistent_flash"].update(unchanged=False),
        lambda value: value["safety"].update(final_tx_muted=False),
        lambda value: value["safety"].update(final_dds_disabled=1),
        lambda value: value["safety"].update(final_dac_selectors_zero=False),
        lambda value: value["safety"].update(final_tandem_state="HOLD"),
        lambda value: value["safety"].update(final_fifo_level=1),
        lambda value: value["safety"].update(final_fault_flags=1),
        lambda value: value["timestamps"].update(completed_unix_ns=99),
        lambda value: value["topology"].update(usb_port="../1-2"),
        lambda value: value["topology"].update(
            dfu_sysfs_path="/sys/bus/usb/devices/1-9"
        ),
        lambda value: value["host_route"].update(destination="192.168.2.1/24"),
        lambda value: value["host_route"].update(interface="other0"),
        lambda value: value["host_route"].update(source="not-an-ip"),
        lambda value: value["host_route"].update(release_verified=False),
        lambda value: value["commands"].reverse(),
        lambda value: value["commands"][0].update(argv=["true"]),
        lambda value: value["commands"][0]["argv"].__setitem__(-2, "root@not-an-ip"),
        lambda value: value["commands"][0]["argv"].__setitem__(
            value["commands"][0]["argv"].index("StrictHostKeyChecking=no"),
            "StrictHostKeyChecking=yes",
        ),
        lambda value: value["commands"][0]["argv"].__setitem__(
            value["commands"][0]["argv"].index("UserKnownHostsFile=/dev/null"),
            "UserKnownHostsFile=/evidence/known_hosts",
        ),
        lambda value: value["commands"][1]["argv"].__setitem__(4, "1-9"),
        lambda value: value["commands"][1]["argv"].__setitem__(2, "0456:b674"),
        lambda value: value["commands"][2]["argv"].__setitem__(2, "0456:b674"),
        lambda value: value["commands"][1]["argv"].__setitem__(
            -1, "/evidence/firmware.dfu"
        ),
        lambda value: value["commands"][2].update(argv=["dfu-util", "-e"]),
        lambda value: value["commands"][1]["argv"].append("-R"),
        lambda value: value["commands"][1]["argv"].extend(["-S", SERIAL]),
        lambda value: value["commands"][1]["argv"].append("--reset"),
        lambda value: value.update(transition_proof_sha256="5" * 64),
        lambda value: value.update(known_hosts_sha256="6" * 64),
    ],
)
def test_ram_receipt_rejects_wrong_bytes_identity_epoch_or_cleanup(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    value = copy.deepcopy(_receipt())
    mutation(value)

    with pytest.raises(CandidateBindingError):
        _validate_receipt(value)


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("artifact_index_sha256", "0" * 64),
        ("serial", "different"),
        ("firmware_version", "different"),
        ("hardware_model", "different"),
        ("dfu_sha256", "0" * 64),
    ],
)
def test_ram_receipt_rejects_mismatched_caller_expectations(
    override: str, value: str
) -> None:
    expected = {
        "artifact_index_sha256": SHA_B,
        "serial": SERIAL,
        "firmware_version": VERSION,
        "hardware_model": PLUTOPLUS_HARDWARE_MODEL,
        "dfu_sha256": SHA_A,
    }
    expected[override] = value

    with pytest.raises(CandidateBindingError):
        validate_deployment_receipt(_receipt(), **expected)
