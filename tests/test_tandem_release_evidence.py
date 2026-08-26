"""Offline planted-failure tests for staged tandem release evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.radio_hardware.pluto_plus_candidate_test_support import (
    build_utility_deployment_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tandem_release_evidence.py"
COMMIT = "1" * 40
FINAL_COMMIT = "2" * 40
VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc16"
FINAL_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8"
RUN_ID = 123456
RUN_ATTEMPT = 1
LIBIIO_COMMIT = "d" * 40
PACKAGE_STEM = "plutoplus-spf-tandem-agc-v8-rc16-111111111111"
SOURCE_MANIFEST_PAYLOAD = b"""schema: plutosdr-fw.source-manifest
schema_version: 1
release_state: candidate
libiio_0_25_source: dddddddddddddddddddddddddddddddddddddddd
libiio_0_25_ref: refs/tags/tandem-agc-v8-test-source/libiio-v1
versions_hdl: tandem-agc-v2-source/hdl-v2
versions_buildroot: tandem-agc-v8-rc3-source/buildroot-v1
versions_linux: tandem-agc-v2-source/linux-v11
versions_u_boot_xlnx: gain-series-v4-rc2-source/u-boot-xlnx
gadget_source: 8888888888888888888888888888888888888888
submodule_buildroot: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
submodule_linux: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
submodule_u_boot_xlnx: cccccccccccccccccccccccccccccccccccccccc
"""


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tandem_release_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVIDENCE = _load_module()

_STAGE_INEXACT_SOURCE_LOCK_CASES = (
    pytest.param(
        "candidate-pre-hardware",
        EVIDENCE.FINAL_SOURCE_LOCK_REF,
        id="candidate-uses-final-cross-stage-lock",
    ),
    pytest.param(
        "final-pre-confirmation",
        EVIDENCE.CANDIDATE_SOURCE_LOCK_REF,
        id="final-uses-candidate-cross-stage-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc99-source/firmware-v1",
        id="candidate-uses-rc99-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc15-source/firmware-v1",
        id="candidate-uses-burned-rc15-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc13-source/firmware-v1",
        id="candidate-uses-burned-rc13-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc11-source/firmware-v1",
        id="candidate-uses-burned-rc11-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc10-source/firmware-v1",
        id="candidate-uses-burned-rc10-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc9-source/firmware-v1",
        id="candidate-uses-burned-rc9-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc8-source/firmware-v1",
        id="candidate-uses-burned-rc8-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc7-source/firmware-v1",
        id="candidate-uses-burned-rc7-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc6-source/firmware-v1",
        id="candidate-uses-burned-rc6-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc5-source/firmware-v1",
        id="candidate-uses-burned-rc5-lock",
    ),
    pytest.param(
        "candidate-pre-hardware",
        "refs/tags/tandem-agc-v8-rc4-source/firmware-v1",
        id="candidate-uses-wrong-rc-lock",
    ),
)


@pytest.fixture(autouse=True)
def _git_evidence_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    def committed_file_sha256(_commit: str, relative: str) -> str:
        if relative == EVIDENCE.SEMANTIC_VERIFIER_HARNESS_PATH:
            return _digest(SCRIPT.read_bytes())
        if relative == EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH:
            return _digest((ROOT / relative).read_bytes())
        return _digest(SOURCE_MANIFEST_PAYLOAD)

    monkeypatch.setattr(
        EVIDENCE,
        "_resolve_local_source_lock",
        lambda ref: (
            "commit",
            FINAL_COMMIT
            if ref == "refs/tags/tandem-agc-v8-source/firmware-v1"
            else COMMIT,
        ),
    )
    monkeypatch.setattr(
        EVIDENCE,
        "_resolve_local_annotated_tag",
        lambda _tag: ("tag", "7" * 40, FINAL_COMMIT),
    )
    monkeypatch.setattr(
        EVIDENCE,
        "_committed_file_sha256",
        committed_file_sha256,
    )


def _write(path: Path, payload: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        payload = payload.encode()
    path.write_bytes(payload)
    path.chmod(0o644)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _checksum_bytes(members: dict[str, bytes], names: set[str]) -> bytes:
    return "".join(
        f"{_digest(members[name])}  {name}\n" for name in sorted(names)
    ).encode()


def _write_bundle(path: Path, members: dict[str, bytes]) -> None:
    _write_bundle_entries(path, sorted(members.items()))


def _write_bundle_entries(path: Path, entries: list[tuple[str, bytes]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    path.chmod(0o644)


def _xsa_bytes(bitstream: bytes) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, mode="w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("system_top.bit", date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        archive.writestr(info, bitstream)
    return result.getvalue()


def _bundle_details(input_path: Path) -> tuple[Path, Path]:
    descriptor = json.loads(input_path.read_text())
    paths = {
        member["role"]: input_path.parent / member["path"]
        for member in descriptor["evidence"]["members"]
    }
    return paths["bundle"], paths["attestation-verification"]


def _bundle_members(bundle_path: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with tarfile.open(bundle_path, "r:gz") as archive:
        for member in archive:
            stream = archive.extractfile(member)
            assert stream is not None
            result[member.name] = stream.read()
    return result


def _rebind_bundle(bundle_path: Path, attestation_path: Path) -> None:
    digest = _sha(bundle_path)
    _write(Path(str(bundle_path) + ".sha256"), f"{digest}  {bundle_path.name}\n")
    attestation = json.loads(attestation_path.read_text())
    attestation["bundle_sha256"] = digest
    attestation["subject"]["sha256"] = digest
    if "tool_output" in attestation:
        attestation["tool_output"]["subject"]["sha256"] = digest
    _write(attestation_path, _json_bytes(attestation))


def _rewrite_coherent_bundle(
    input_path: Path,
    members: dict[str, bytes],
    *,
    rewritten_roles: dict[str, str] | None = None,
) -> None:
    bundle, attestation = _bundle_details(input_path)
    payload_names = set(
        EVIDENCE._parse_checksum_inventory(
            members["PAYLOAD_SHA256SUMS"], name="test payload sums"
        )
    )
    members["PAYLOAD_SHA256SUMS"] = _checksum_bytes(members, payload_names)
    members["SHA256SUMS"] = _checksum_bytes(members, set(members) - {"SHA256SUMS"})
    descriptor = json.loads(input_path.read_text())
    role_paths = {
        member["role"]: input_path.parent / member["path"]
        for member in descriptor["evidence"]["members"]
    }
    _write(role_paths["payload-checksums"], members["PAYLOAD_SHA256SUMS"])
    _write(role_paths["bundle-inner-checksums"], members["SHA256SUMS"])
    for role, member_name in (rewritten_roles or {}).items():
        _write(role_paths[role], members[member_name])
    _write_bundle(bundle, members)
    _rebind_bundle(bundle, attestation)


def _fixture(
    root: Path,
    *,
    commit: str = COMMIT,
    version: str = VERSION,
    stage: str = "candidate-pre-hardware",
    package_stem: str = PACKAGE_STEM,
    captured_attestation: bool = False,
    source_lock_ref: str | None = None,
) -> tuple[Path, Path]:
    is_candidate = stage == "candidate-pre-hardware"
    manifest_name = (
        "tandem-agc-v8-rc16-source.yaml"
        if is_candidate
        else "tandem-agc-v8-source.yaml"
    )
    if source_lock_ref is None:
        source_lock_ref = (
            EVIDENCE.CANDIDATE_SOURCE_LOCK_REF
            if is_candidate
            else EVIDENCE.FINAL_SOURCE_LOCK_REF
        )
    build_ref = (
        "refs/heads/codex/firmware-tandem-agc-v8-rc16"
        if is_candidate
        else "refs/heads/main"
    )
    manifest = root / "source" / manifest_name
    manifest_payload = SOURCE_MANIFEST_PAYLOAD
    _write(manifest, manifest_payload)
    dfu_payload = b"F" * 64 + b"S" * 16
    dfu_name = f"{package_stem}-pluto.dfu"
    dfu = root / "artifact" / dfu_name
    _write(dfu, dfu_payload)

    harness_paths = EVIDENCE.ARTIFACT_HARNESS_PATHS
    for index, relative in enumerate(harness_paths):
        if relative == EVIDENCE.SEMANTIC_VERIFIER_HARNESS_PATH:
            payload = SCRIPT.read_bytes()
        elif relative == EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH:
            payload = (ROOT / relative).read_bytes()
        else:
            payload = f"harness-{index}\n"
        _write(root / relative, payload)

    role_names = {
        **EVIDENCE._BUNDLE_FIXED_ROLE_NAMES,
        "actions-run": "actions-run.json",
        "attestation-verification": "attestation-verification.json",
        "bundle": f"{package_stem}.tar.gz",
        "ooc-evidence-manifest": "evidence-sha256.txt",
        "ooc-status": "ooc-status.txt",
        "provenance": f"{package_stem}-provenance.txt",
        "rootfs": f"{package_stem}-rootfs.cpio.gz",
        "source-lock": "source-lock.txt",
        "source-tool-hashes": "source-and-tool-hashes.txt",
        "waiver-inventory": "tandem-agc-v8-integrated-waivers.json",
        "xsa": f"{package_stem}-system_top.xsa",
    }
    external_roles = {
        "actions-run",
        "attestation-verification",
        "bundle",
        "ooc-evidence-manifest",
        "ooc-status",
        "source-lock",
        "source-tool-hashes",
    }
    role_paths = {
        role: (
            f"artifact/{role_names[role]}"
            if role in {"actions-run", "attestation-verification", "bundle"}
            else f"evidence/{role_names[role]}"
        )
        for role in EVIDENCE.REQUIRED_EVIDENCE_ROLES
    }

    bitstream_payload = b"synthetic-qualified-fpga-bitstream\n"
    bundle_members: dict[str, bytes] = {
        manifest.name: manifest_payload,
        dfu_name: dfu_payload,
        f"{package_stem}-pluto.frm": (
            dfu_payload[:64]
            + hashlib.md5(dfu_payload[:64], usedforsecurity=False).hexdigest().encode()
            + b"\n"
        ),
        f"{package_stem}-system_top.xsa": _xsa_bytes(bitstream_payload),
        f"{package_stem}-rootfs.cpio.gz": b"synthetic-rootfs\n",
        f"{package_stem}-provenance.txt": b"synthetic-provenance\n",
        "dfu-suffix-check.txt": b"Vendor ID: 0x0456\nProduct ID: 0xB673\nLength: 16\n",
        "fit-layout.txt": b"synthetic-fit-layout\n",
        "frm-layout.txt": b"fit_bytes=64\ndfu_fit_matches_frm=true\n",
        "system_top.bit": bitstream_payload,
        "packed-fpga.bit": bitstream_payload,
        "system-top-bit.sha256": (
            f"{_digest(bitstream_payload)}  system_top.bit\n".encode()
        ),
        "integrated-release-verdict.json": b"placeholder\n",
        "offline-validation-summary.txt": b"PASS OFFLINE / HARDWARE UNTESTED\n",
        "packed-VERSIONS.txt": (
            f"""device-fw {version}
hdl tandem-agc-v2-source/hdl-v2
buildroot tandem-agc-v8-rc3-source/buildroot-v1
linux tandem-agc-v2-source/linux-v11
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
""".encode()
        ),
        "system_top_routed.dcp": b"synthetic-routed-dcp\n",
        "system_top_timing_summary_routed.rpt": b"synthetic-timing\n",
        "system_top_route_status.rpt": b"synthetic-route-status\n",
        "system_top_drc_routed.rpt": b"synthetic-drc\n",
        "system_top_methodology_drc_routed.rpt": b"synthetic-methodology\n",
        "system_top_utilization_routed.rpt": b"synthetic-utilization\n",
        "system_top_cdc_routed.rpt": b"synthetic-cdc\n",
        "system_top_bus_skew_routed.rpt": b"synthetic-bus-skew\n",
        "vivado-logs.tar.gz": b"synthetic-vivado-logs\n",
        "tandem-agc-v8-integrated-waivers.json": b"synthetic-waivers\n",
    }
    bundle_members["integrated-release-verdict.json"] = _json_bytes(
        {
            "schema": EVIDENCE.INTEGRATED_VERDICT_SCHEMA,
            "verdict": "PASS",
            "source_commit": commit,
            "source_manifest_sha256": _digest(manifest_payload),
            "routed_dcp_sha256": _digest(bundle_members["system_top_routed.dcp"]),
            "waiver_inventory_sha256": _digest(
                bundle_members["tandem-agc-v8-integrated-waivers.json"]
            ),
            "validated_inputs": [
                {
                    "role": role,
                    "path": manifest.name
                    if role == "source-manifest"
                    else role_names[role],
                    "bytes": len(
                        manifest_payload
                        if role == "source-manifest"
                        else bundle_members[role_names[role]]
                    ),
                    "sha256": _digest(
                        manifest_payload
                        if role == "source-manifest"
                        else bundle_members[role_names[role]]
                    ),
                }
                for role in EVIDENCE.INTEGRATED_VALIDATED_ROLES
            ],
            "firmware_release_eligible": True,
        }
    )
    payload_names = {
        dfu_name,
        f"{package_stem}-pluto.frm",
        f"{package_stem}-system_top.xsa",
        f"{package_stem}-rootfs.cpio.gz",
        "system_top_routed.dcp",
        "system_top.bit",
        "packed-fpga.bit",
        "system-top-bit.sha256",
        "frm-layout.txt",
        "system_top_timing_summary_routed.rpt",
        "system_top_route_status.rpt",
        "system_top_drc_routed.rpt",
        "system_top_methodology_drc_routed.rpt",
        "system_top_utilization_routed.rpt",
        "system_top_cdc_routed.rpt",
        "system_top_bus_skew_routed.rpt",
        "vivado-logs.tar.gz",
        "integrated-release-verdict.json",
        "tandem-agc-v8-integrated-waivers.json",
    }
    bundle_members["PAYLOAD_SHA256SUMS"] = _checksum_bytes(
        bundle_members, payload_names
    )
    bundle_members["SHA256SUMS"] = _checksum_bytes(bundle_members, set(bundle_members))

    for role in EVIDENCE.REQUIRED_EVIDENCE_ROLES:
        if role not in external_roles:
            _write(root / role_paths[role], bundle_members[role_names[role]])
    for role in ("ooc-evidence-manifest", "source-tool-hashes"):
        _write(root / role_paths[role], f"{role}\n")

    _write(
        root / role_paths["source-lock"],
        "\n".join(
            (
                f"schema={EVIDENCE.SOURCE_LOCK_SCHEMA}",
                f"ref={source_lock_ref}",
                f"commit={commit}",
                "",
            )
        ),
    )
    _write(
        root / role_paths["actions-run"],
        _json_bytes(
            {
                "schema": EVIDENCE.ACTIONS_RUN_SCHEMA,
                "repository": "misko/plutosdr-fw",
                "workflow_path": ".github/workflows/firmware-main.yml",
                "ref": build_ref,
                "event": "workflow_dispatch",
                "id": RUN_ID,
                "run_attempt": RUN_ATTEMPT,
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
                "url": f"https://github.com/misko/plutosdr-fw/actions/runs/{RUN_ID}",
            }
        ),
    )
    ooc_manifest = root / role_paths["ooc-evidence-manifest"]
    _write(
        root / role_paths["ooc-status"],
        "\n".join(
            (
                "verdict=PASS",
                "scope=tandem_agc_axi_routed_ooc",
                "firmware_release_eligible=false",
                "integrated_route_required=true",
                f"commit={commit}",
                f"evidence_manifest_sha256={_sha(ooc_manifest)}",
                "",
            )
        ),
    )
    bundle = root / role_paths["bundle"]
    _write_bundle(bundle, bundle_members)
    _write(Path(str(bundle) + ".sha256"), f"{_sha(bundle)}  {bundle.name}\n")
    if captured_attestation:
        attestation_record: dict[str, object] = {
            "schema": EVIDENCE.ATTESTATION_SCHEMA,
            "repository": "misko/plutosdr-fw",
            "head_sha": commit,
            "run_id": RUN_ID,
            "run_attempt": RUN_ATTEMPT,
            "bundle_sha256": _sha(bundle),
            "command": [
                "gh",
                "attestation",
                "verify",
                bundle.name,
                "--repo",
                "misko/plutosdr-fw",
                "--format",
                "json",
            ],
            "subject": {"name": bundle.name, "sha256": _sha(bundle)},
            "provenance": {
                "repository": "misko/plutosdr-fw",
                "workflow_path": ".github/workflows/firmware-main.yml",
                "workflow_ref": f".github/workflows/firmware-main.yml@{build_ref}",
                "source_commit": commit,
                "run_id": RUN_ID,
                "run_attempt": RUN_ATTEMPT,
            },
            "tool_output": {
                "subject": {"sha256": _sha(bundle)},
                "predicate": {
                    "repository": "misko/plutosdr-fw",
                    "source_commit": commit,
                    "run_id": RUN_ID,
                    "run_attempt": RUN_ATTEMPT,
                },
            },
            "verified": True,
            "exit_code": 0,
        }
    else:
        attestation_record = {
            "schema": EVIDENCE.ATTESTATION_NOT_PERFORMED_SCHEMA,
            "repository": "misko/plutosdr-fw",
            "head_sha": commit,
            "run_id": RUN_ID,
            "run_attempt": RUN_ATTEMPT,
            "bundle_sha256": _sha(bundle),
            "subject": {"name": bundle.name, "sha256": _sha(bundle)},
            "verification_performed": False,
            "reason": "single-owner-operator-trust-model",
        }
    _write(
        root / role_paths["attestation-verification"],
        _json_bytes(attestation_record),
    )

    descriptor: dict[str, Any] = {
        "schema": EVIDENCE.INPUT_SCHEMA,
        "schema_version": 1,
        "stage": stage,
        "release": {
            "firmware_version": version,
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": commit,
            "manifest_path": str(manifest.relative_to(root)),
        },
        "build": {"run_id": RUN_ID, "run_attempt": RUN_ATTEMPT},
        "artifact": {"dfu_path": str(dfu.relative_to(root)), "fit_bytes": 64},
        "harness": {"paths": list(harness_paths)},
        "evidence": {
            "members": [
                {"role": role, "path": role_paths[role]}
                for role in EVIDENCE.REQUIRED_EVIDENCE_ROLES
            ]
        },
    }
    input_path = root / ("candidate-input.json" if is_candidate else "final-input.json")
    _write(input_path, _json_bytes(descriptor))
    output_name = (
        "candidate-index.json" if is_candidate else "final-artifact-index.json"
    )
    return input_path, root / output_name


def _assemble(root: Path) -> Path:
    input_path, output = _fixture(root)
    EVIDENCE.assemble(
        input_path=input_path,
        archive_root=root,
        output_path=output,
        stage="candidate-pre-hardware",
    )
    return output


def _rewrite_indexed_source_lock(index_path: Path, source_lock_ref: str) -> None:
    index = json.loads(index_path.read_text())
    member = next(
        item for item in index["evidence"]["members"] if item["role"] == "source-lock"
    )
    source_lock_path = index_path.parent / member["path"]
    payload = "\n".join(
        (
            f"schema={EVIDENCE.SOURCE_LOCK_SCHEMA}",
            f"ref={source_lock_ref}",
            f"commit={index['source']['commit']}",
            "",
        )
    )
    _write(source_lock_path, payload)
    member["bytes"] = source_lock_path.stat().st_size
    member["sha256"] = _sha(source_lock_path)
    _write(index_path, _json_bytes(index))
    _write(
        index_path.with_suffix(index_path.suffix + ".sha256"),
        f"{_sha(index_path)}  {index_path.name}\n",
    )


def _receipt_payload(
    artifact_index: Path, *, serial: str, receipt_path: Path
) -> dict[str, Any]:
    index = json.loads(artifact_index.read_text())
    index_sha = _sha(artifact_index)
    usb_port = f"3-{int(serial[-1])}"
    sysfs_path = f"/sys/bus/usb/devices/{usb_port}"
    dfu_path = "/proc/self/fd/7"
    dfu_prefix = [
        "dfu-util",
        "-d",
        "0456:b673,0456:b674",
        "-p",
        usb_port,
        "-a",
        "firmware.dfu",
    ]
    return {
        "schema": "plutosdr-fw.tandem-ram-boot-receipt",
        "schema_version": 4,
        "verdict": "pass",
        "boot_mode": "ram-only",
        "artifact_index_sha256": index_sha,
        "radio": {"serial": serial},
        "artifact": {"dfu_sha256": index["artifact"]["dfu_sha256"]},
        "runtime": {
            "firmware_version": index["release"]["firmware_version"],
            "hardware_model": index["release"]["hardware_model"],
        },
        "boot": {"pre_id": f"pre-{serial}", "post_id": f"post-{serial}"},
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
        "timestamps": {"started_unix_ns": 1, "completed_unix_ns": 2},
        "topology": {
            "usb_port": usb_port,
            "pre_sysfs_path": sysfs_path,
            "dfu_sysfs_path": sysfs_path,
            "post_sysfs_path": sysfs_path,
            "network_interface": f"usb{serial[-1]}",
        },
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": f"usb{serial[-1]}",
            "source": "192.168.2.10",
            "release_verified": True,
        },
        "commands": [
            {
                "phase": "request-ram-mode",
                "argv": [
                    "sshpass",
                    "-f",
                    f"/private/ssh-password-{serial}",
                    "ssh",
                    "-F",
                    "/dev/null",
                    "-B",
                    f"usb{serial[-1]}",
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
                "argv": [*dfu_prefix, "-D", dfu_path],
            },
            {
                "phase": "detach-into-downloaded-image",
                "argv": [*dfu_prefix, "-e"],
            },
        ],
    }


def _lineage(
    artifact_index: Path, receipt_path: Path, *, serial: str
) -> dict[str, str]:
    index = json.loads(artifact_index.read_text())
    return {
        "serial": serial,
        "firmware_version": index["release"]["firmware_version"],
        "source_commit": index["source"]["commit"],
        "artifact_index_sha256": _sha(artifact_index),
        "dfu_sha256": index["artifact"]["dfu_sha256"],
        "deployment_receipt_sha256": _sha(receipt_path),
    }


def _release_binding(
    artifact_index_path: Path, receipt_path: Path, *, serial: str
) -> dict[str, object]:
    index = json.loads(artifact_index_path.read_text())
    lineage = _lineage(artifact_index_path, receipt_path, serial=serial)
    indexed_harness = {
        item["path"]: item["sha256"] for item in index["harness"]["files"]
    }
    harness_files = [
        {
            "relative_path": relative,
            "sha256": digest,
            "required_for_release_hardware": (
                relative in EVIDENCE.RELEASE_HARDWARE_HARNESS_PATHS
            ),
            **(
                {"committed_sha256": digest}
                if relative in EVIDENCE.RELEASE_HARDWARE_HARNESS_PATHS
                else {}
            ),
        }
        for relative, digest in indexed_harness.items()
    ]
    runner_sources = [
        {
            "path": relative,
            "sha256": indexed_harness[relative],
            "committed_sha256": indexed_harness[relative],
        }
        for relative in EVIDENCE.RELEASE_RUNNER_PROVENANCE_PATHS
    ]
    normalized_index_sha = hashlib.sha256(
        json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": EVIDENCE.RELEASE_BINDING_SCHEMA,
        **lineage,
        "build_run_id": index["build"]["run_id"],
        "build_run_attempt": index["build"]["run_attempt"],
        "fit_sha256": index["artifact"]["fit_sha256"],
        "artifact_index": index,
        "initial_semantic_verification": {
            "stage": index["stage"],
            "normalized_index_sha256": normalized_index_sha,
        },
        "source_manifest_values": {"libiio_0_25_source": LIBIIO_COMMIT},
        "harness_files": harness_files,
        "runner_provenance": {
            "schema": EVIDENCE.RELEASE_RUNNER_SCHEMA,
            "commit": index["source"]["commit"],
            "clean": True,
            "sources": runner_sources,
        },
    }


def _release_host_libiio() -> dict[str, object]:
    return {
        "schema": EVIDENCE.RELEASE_HOST_LIBIIO_SCHEMA,
        "source_commit": LIBIIO_COMMIT,
        "resume_identity": {
            "binding_sha256": "a" * 64,
            "library_sha256": "b" * 64,
        },
    }


def _release_report(
    artifact_index: Path,
    receipt: Path,
    *,
    aggregate_path: Path,
    serial: str,
    policy: str,
    requested_phases: list[str],
) -> dict[str, object]:
    binding = _release_binding(artifact_index, receipt, serial=serial)
    host = _release_host_libiio()
    harness_sources = {
        item["path"]: item["sha256"]
        for item in binding["artifact_index"]["harness"]["files"]
        if item["path"] in EVIDENCE.RELEASE_HARDWARE_HARNESS_PATHS
    }
    plan: list[dict[str, object]] = []
    for phase in requested_phases:
        if phase == "steady":
            plan.append(
                {
                    "key": (
                        "steady_characterization" if policy == "full" else "steady_soak"
                    ),
                    "kind": phase,
                    "band": None,
                }
            )
        else:
            plan.extend(
                {
                    "key": f"{phase}_{band['name']}",
                    "kind": phase,
                    "band": dict(band),
                }
                for band in EVIDENCE.RELEASE_BANDS
            )
    phase_records: dict[str, dict[str, object]] = {}
    for item in plan:
        key = str(item["key"])
        raw_report = (
            aggregate_path.parent
            / "artifacts"
            / key
            / "attempt-0001"
            / "phase-report.json"
        ).absolute()
        _write(raw_report, _json_bytes({"verdict": "pass", "phase": key}))
        phase_records[key] = {
            "status": "complete",
            "phase_verdict": "pass",
            "cleanup_verified": True,
            "host_libiio_before_phase": host,
            "host_libiio_after_cleanup": host,
            "report_path": str(raw_report),
            "report_sha256": _sha(raw_report),
            "summary": {"verdict": "pass"},
        }
    is_full = policy == "full"
    return {
        "schema": "plutosdr-fw.tandem-agc-release-hardware.v1",
        "verdict": "pass",
        "all_requested_phases_complete": True,
        "all_cleanup_verified": True,
        "all_host_libiio_verified": True,
        "configuration": {
            "serial": serial,
            "firmware_version": binding["firmware_version"],
            "libiio_source_commit": LIBIIO_COMMIT,
            "harness_sources": harness_sources,
            "host_libiio": host,
            "policy_set": policy,
            "requested_phases": requested_phases,
            "bands": [dict(band) for band in EVIDENCE.RELEASE_BANDS],
            "steady_campaign_kind": (
                "one_factor_characterization"
                if is_full
                else "baseline_repeatability_soak"
            ),
            "repeat_cycles": 1 if is_full else 4,
            "cycle_interval_seconds": 0.0 if is_full else 1_200.0,
            "soak_deadline_seconds": 14_400.0 if is_full else 5_400.0,
            "sample_rate_hz": 2_500_000,
            "samples_per_channel": 65_536,
            "phase_max_seconds": 600.0,
            "candidate_binding": binding,
        },
        "host_libiio_invocations": [{"started_unix_ns": 1, "provenance": host}],
        "plan": plan,
        "counts": {
            "pending": 0,
            "running": 0,
            "complete": len(plan),
            "failed": 0,
        },
        "phases": phase_records,
    }


def _lifecycle_report(
    artifact_index_path: Path,
    receipt_path: Path,
    *,
    report_path: Path,
    serial: str,
) -> dict[str, object]:
    index_payload = artifact_index_path.read_bytes()
    index = json.loads(index_payload)
    receipt_payload = receipt_path.read_bytes()
    receipt = json.loads(receipt_payload)
    root = artifact_index_path.parent
    indexed_harness = {
        item["path"]: item["sha256"] for item in index["harness"]["files"]
    }
    runner = {
        "host_runner_repository_commit": index["source"]["commit"],
        "host_runner_repository": str(ROOT),
        "python_module_path": str(
            ROOT / "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
        ),
        "python_module_sha256": indexed_harness[
            "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
        ],
        "python_module_head_blob_sha256": indexed_harness[
            "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
        ],
        "shell_runner_path": str(
            ROOT / "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
        ),
        "shell_runner_sha256": indexed_harness[
            "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
        ],
        "shell_runner_head_blob_sha256": indexed_harness[
            "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
        ],
        "metadata_abi_path": str(ROOT / "tests/radio_hardware/metadata_abi.py"),
        "metadata_abi_sha256": indexed_harness["tests/radio_hardware/metadata_abi.py"],
        "metadata_abi_head_blob_sha256": indexed_harness[
            "tests/radio_hardware/metadata_abi.py"
        ],
        "candidate_binding_path": str(
            ROOT / "tests/radio_hardware/candidate_binding.py"
        ),
        "candidate_binding_sha256": indexed_harness[
            "tests/radio_hardware/candidate_binding.py"
        ],
        "candidate_binding_head_blob_sha256": indexed_harness[
            "tests/radio_hardware/candidate_binding.py"
        ],
    }
    source_values = {
        "libiio_0_25_source": LIBIIO_COMMIT,
        "libiio_0_25_ref": "refs/tags/tandem-agc-v8-test-source/libiio-v1",
    }
    lineage = {
        "attestation": "exact operator-owned lifecycle fixture",
        "source_commit": index["source"]["commit"],
        "source_manifest": {
            "path": str(root / index["source"]["manifest_path"]),
            "values": source_values,
        },
        "build_run_id": index["build"]["run_id"],
        "build_run_attempt": index["build"]["run_attempt"],
        "artifact_index_path": str(artifact_index_path.absolute()),
        "artifact_index_bytes": len(index_payload),
        "artifact_index_sha256": hashlib.sha256(index_payload).hexdigest(),
        "artifact_index": index,
        "evidence_member_count": len(EVIDENCE.REQUIRED_EVIDENCE_ROLES),
        "evidence_members_verified": True,
        "dfu_path": str(root / index["artifact"]["dfu_path"]),
        "dfu_bytes": index["artifact"]["dfu_bytes"],
        "dfu_sha256": index["artifact"]["dfu_sha256"],
        "fit_bytes": index["artifact"]["fit_bytes"],
        "fit_sha256": index["artifact"]["fit_sha256"],
        "deployment_receipt_path": str(receipt_path.absolute()),
        "deployment_receipt_bytes": len(receipt_payload),
        "deployment_receipt_sha256": hashlib.sha256(receipt_payload).hexdigest(),
        "deployment_receipt": receipt,
        "serial": serial,
        "firmware_version": index["release"]["firmware_version"],
        "firmware_pattern": rf"\A{re.escape(index['release']['firmware_version'])}\Z",
        "kernel_version": index["release"]["kernel_version"],
        "hardware_model": index["release"]["hardware_model"],
    }
    from tests.radio_hardware.lifecycle_test_support import (
        build_lifecycle_v5_archive,
    )

    report, raw_metadata = build_lifecycle_v5_archive(
        report_path=report_path,
        lineage=lineage,
        runner_provenance=runner,
        serial=serial,
        runtime={
            "uri": "usb:3.17.5",
            "firmware_version": index["release"]["firmware_version"],
            "kernel_version": index["release"]["kernel_version"],
            "hardware_model": index["release"]["hardware_model"],
            "libiio_source_commit": source_values["libiio_0_25_source"],
            "libiio_source_ref": source_values["libiio_0_25_ref"],
            "libiio_sha256": "e" * 64,
        },
    )
    for relative, payload in raw_metadata.items():
        raw_path = report_path.parent / relative
        _write(raw_path, payload)
        raw_path.chmod(0o600)
    return report


def _write_campaign_hardware(root: Path, artifact_index: Path) -> None:
    index_payload = artifact_index.read_bytes()
    index = json.loads(index_payload)
    for position in range(1, 5):
        serial = f"RADIO{position}"
        receipt = build_utility_deployment_bundle(
            root=root,
            artifact_index_path=artifact_index,
            artifact_index=index,
            artifact_index_payload=index_payload,
            serial=serial,
            expected_current_firmware="v0.41-plutoplus-spf-tandem-agc-v8-rc12",
        )["receipt"]
        for phase, policy, phases in (
            ("full", "full", ["steady", "transient", "modulated"]),
            ("soak", "baseline", ["steady"]),
        ):
            aggregate_path = (
                root / f"hardware/{phase}/{serial}/release-hardware-report.json"
            )
            _write(
                aggregate_path,
                _json_bytes(
                    _release_report(
                        artifact_index,
                        receipt,
                        aggregate_path=aggregate_path,
                        serial=serial,
                        policy=policy,
                        requested_phases=phases,
                    )
                ),
            )
        lifecycle_path = (
            root / f"hardware/lifecycle/{serial}/muted-metadata-batch-lifecycle-v5.json"
        )
        _write(
            lifecycle_path,
            _json_bytes(
                _lifecycle_report(
                    artifact_index,
                    receipt,
                    report_path=lifecycle_path,
                    serial=serial,
                )
            ),
        )
        _write(
            root / f"hardware/stale-latch/{serial}/stale-latch-report.json",
            _json_bytes(
                {
                    "schema": "plutosdr-fw.stale-small-adc-hardware.v1",
                    "verdict": "BLOCKED",
                    "release_pass_eligible": False,
                    "diagnostic_only": True,
                }
            ),
        )
        for phase in EVIDENCE._CAMPAIGN_PHASES:
            _write(
                root / f"hardware/{phase}/{serial}/raw-{phase}.log",
                f"raw {phase} {serial}\n",
            )
    for directory in (root / "hardware").rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    (root / "hardware").chmod(0o755)


def _assemble_campaign(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, artifact_index: Path
) -> Path:
    monkeypatch.setattr(
        EVIDENCE,
        "_validate_campaign_archive_for_promotion",
        lambda *_args, **_kwargs: None,
    )
    _write_campaign_hardware(root, artifact_index)
    output = root / "campaign-index.json"
    EVIDENCE.assemble(
        archive_root=root,
        output_path=output,
        stage="candidate-qualified",
        parent_index_path=artifact_index,
    )
    return output


def _lineage_fixture(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    identity_only: bool = True,
) -> tuple[Path, Path, Path]:
    candidate_staging = root / "candidate-staging"
    candidate_staging.mkdir(mode=0o755)
    candidate_input, candidate = _fixture(candidate_staging)
    EVIDENCE.assemble(
        archive_root=candidate_staging,
        input_path=candidate_input,
        output_path=candidate,
        stage="candidate-pre-hardware",
    )
    _assemble_campaign(candidate_staging, monkeypatch, artifact_index=candidate)
    candidate_root = root / "lineage" / "rc16"
    candidate_root.parent.mkdir(mode=0o755)
    candidate_staging.rename(candidate_root)
    candidate = candidate_root / "candidate-index.json"
    campaign = candidate_root / "campaign-index.json"

    final_input, final_artifact = _fixture(
        root,
        commit=FINAL_COMMIT,
        version=FINAL_VERSION,
        stage="final-pre-confirmation",
        package_stem="plutoplus-spf-tandem-agc-v8-222222222222",
    )
    EVIDENCE.assemble(
        archive_root=root,
        input_path=final_input,
        output_path=final_artifact,
        stage="final-pre-confirmation",
    )
    changed_files: list[dict[str, object]] = []
    final_tree = "3" * 40
    if not identity_only:
        final_tree = "4" * 40
        changed_files = [
            {
                "path": "hdl/projects/pluto/system_top.v",
                "status": "modified",
                "candidate_blob": "5" * 40,
                "final_blob": "6" * 40,
            }
        ]
    reproduced_diff = {
        "candidate": {"commit": COMMIT, "tree": "3" * 40},
        "final": {"commit": FINAL_COMMIT, "tree": final_tree},
        "changed_files": changed_files,
        "trees_identical": identity_only,
    }
    monkeypatch.setattr(
        EVIDENCE,
        "_reproduce_source_diff",
        lambda candidate, final: (
            reproduced_diff if (candidate, final) == (COMMIT, FINAL_COMMIT) else None
        ),
    )
    diff = root / "candidate-to-final-diff.json"
    _write(
        diff,
        _json_bytes(
            {
                "schema": EVIDENCE.CANDIDATE_TO_FINAL_DIFF_SCHEMA,
                "schema_version": 1,
                "candidate": {"commit": COMMIT, "tree": "3" * 40},
                "final": {"commit": FINAL_COMMIT, "tree": final_tree},
                "changed_files": changed_files,
            }
        ),
    )
    policy = root / "final-qualification-policy.json"
    EVIDENCE.assemble(
        archive_root=root,
        output_path=policy,
        stage="final-qualification-policy",
        parent_index_path=final_artifact,
        candidate_qualified_index_path=campaign,
        diff_path=diff,
    )
    return campaign, final_artifact, policy


def _descriptor(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _write_reduced_hardware(root: Path, final_artifact: Path, policy: Path) -> None:
    index_payload = final_artifact.read_bytes()
    index = json.loads(index_payload)
    radios: list[dict[str, object]] = []
    for position in range(1, 5):
        serial = f"RADIO{position}"
        receipt = build_utility_deployment_bundle(
            root=root,
            artifact_index_path=final_artifact,
            artifact_index=index,
            artifact_index_payload=index_payload,
            serial=serial,
            expected_current_firmware="v0.41-plutoplus-spf-tandem-agc-v8-rc13",
        )["receipt"]
        report = (
            root
            / f"hardware/final-confirmation/{serial}/final-confirmation-report.json"
        )
        _write(
            report,
            _json_bytes(
                {
                    "schema": EVIDENCE.FINAL_CONFIRMATION_SCHEMA,
                    "schema_version": 1,
                    "verdict": "pass",
                    "serial": serial,
                    "artifact_index_sha256": _sha(final_artifact),
                    "qualification_policy_sha256": _sha(policy),
                    "deployment_receipt_sha256": _sha(receipt),
                    "dfu_sha256": index["artifact"]["dfu_sha256"],
                    "firmware_version": index["release"]["firmware_version"],
                    "source_commit": index["source"]["commit"],
                    "checks": {
                        "live_identity": "pass",
                        "tx2_loopback": "pass",
                        "protocol_v3": "pass",
                        "cleanup": "pass",
                    },
                }
            ),
        )
        _write(report.parent / "protocol-v3.raw", f"protocol {serial}\n")
        _write(receipt.parent / "deployment.raw", f"deploy {serial}\n")
        radios.append(
            {
                "serial": serial,
                "deploy": _descriptor(root, receipt),
                "confirmation": _descriptor(root, report),
            }
        )
    aggregate = root / "hardware/final-confirmation/final-confirmation-index.json"
    _write(
        aggregate,
        _json_bytes(
            {
                "schema": EVIDENCE.FINAL_CONFIRMATION_INDEX_SCHEMA,
                "schema_version": 1,
                "verdict": "pass",
                "artifact_index_sha256": _sha(final_artifact),
                "qualification_policy_sha256": _sha(policy),
                "required_test": "reduced-confirmation",
                "serials": [str(radio["serial"]) for radio in radios],
                "reports": [
                    {"serial": radio["serial"], **dict(radio["confirmation"])}
                    for radio in radios
                ],
            }
        ),
    )
    for directory in (root / "hardware").rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    (root / "hardware").chmod(0o755)


def _assemble_final_qualification(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    _campaign, final_artifact, policy = _lineage_fixture(root, monkeypatch)
    _write_campaign_hardware(root, final_artifact)
    output = root / "final-qualification-index.json"
    EVIDENCE.assemble(
        archive_root=root,
        output_path=output,
        stage="final-qualified",
        parent_index_path=final_artifact,
        policy_index_path=policy,
    )
    return final_artifact, policy, output


def _published_fixture(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    final_artifact_path, _policy, qualification = _assemble_final_qualification(
        root, monkeypatch
    )
    final_artifact = json.loads(final_artifact_path.read_text())
    final_roles = {
        member["role"]: member for member in final_artifact["evidence"]["members"]
    }
    release_url = (
        "https://github.com/misko/plutosdr-fw/releases/download/" + FINAL_VERSION
    )
    published_root = root / "published"
    dfu_source = root / final_artifact["artifact"]["dfu_path"]
    dfu = published_root / dfu_source.name
    _write(dfu, dfu_source.read_bytes())
    verification_image = root / "remote-verification-cache" / dfu.name
    _write(verification_image, dfu_source.read_bytes())
    frm = published_root / (dfu.name.removesuffix(".dfu") + ".frm")
    fit = dfu.read_bytes()[: final_artifact["artifact"]["fit_bytes"]]
    _write(
        frm,
        fit + hashlib.md5(fit, usedforsecurity=False).hexdigest().encode() + b"\n",
    )
    bundle_source = root / final_roles["bundle"]["path"]
    bundle = published_root / bundle_source.name
    _write(bundle, bundle_source.read_bytes())
    tag_record = root / "annotated-tag-record.json"
    _write(
        tag_record,
        _json_bytes(
            {
                "schema": EVIDENCE.TAG_RECORD_SCHEMA,
                "name": FINAL_VERSION,
                "object_type": "tag",
                "object_id": "7" * 40,
                "target_type": "commit",
                "target_commit": FINAL_COMMIT,
                "signature_verification": "not-performed-or-claimed",
            }
        ),
    )
    remote_tag_record = root / "github-remote-tag-record.json"
    tag_ref = f"refs/tags/{FINAL_VERSION}"
    peeled_ref = f"{tag_ref}^{{}}"
    _write(
        remote_tag_record,
        _json_bytes(
            {
                "schema": EVIDENCE.REMOTE_TAG_RECORD_SCHEMA,
                "command": [
                    "git",
                    "ls-remote",
                    "--tags",
                    EVIDENCE.RELEASE_GIT_REMOTE_URL,
                    tag_ref,
                    peeled_ref,
                ],
                "exit_code": 0,
                "refs": [
                    {"object_id": "7" * 40, "ref": tag_ref},
                    {"object_id": FINAL_COMMIT, "ref": peeled_ref},
                ],
            }
        ),
    )
    manifest = root / "tandem-agc-v8.yaml"
    dfu_relative = dfu.relative_to(root).as_posix()
    frm_relative = frm.relative_to(root).as_posix()
    bundle_relative = bundle.relative_to(root).as_posix()
    _write(
        manifest,
        f"""schema: plutosdr-fw.build-manifest
schema_version: 1
release_tag: {FINAL_VERSION}
asset_name: {dfu.name}
image_url: {release_url}/{dfu.name}
image_sha256: {_sha(dfu)}
device_fw: {FINAL_VERSION}
firmware_source: {FINAL_COMMIT}
gadget_source: {"8" * 40}
submodule_buildroot: {"a" * 40}
submodule_linux: {"b" * 40}
submodule_u_boot_xlnx: {"c" * 40}
versions_hdl: tandem-agc-v2-source/hdl-v2
versions_buildroot: tandem-agc-v8-rc3-source/buildroot-v1
versions_linux: tandem-agc-v2-source/linux-v11
versions_u_boot_xlnx: gain-series-v4-rc2-source/u-boot-xlnx
fpga_bitstream_md5: {"9" * 32}
ramdisk_md5: {"a" * 32}
fit_description: Configuration to load fpga before Kernel
frm_asset_name: {frm.name}
frm_sha256: {_sha(frm)}
bundle_asset_name: {bundle.name}
bundle_sha256: {_sha(bundle)}
hardware_qualified: true
""",
    )
    verification = root / "release-verification.json"
    manifest_relative = manifest.relative_to(root).as_posix()
    inventory = root / "github-release-inventory.json"
    _write(
        inventory,
        _json_bytes(
            {
                "schema": EVIDENCE.RELEASE_INVENTORY_SCHEMA,
                "command": [
                    "gh",
                    "api",
                    f"repos/misko/plutosdr-fw/releases/tags/{FINAL_VERSION}",
                    "--jq",
                    EVIDENCE.RELEASE_INVENTORY_JQ,
                ],
                "exit_code": 0,
                "result": {
                    "tagName": FINAL_VERSION,
                    "isDraft": False,
                    "isPrerelease": False,
                    "url": "https://github.com/misko/plutosdr-fw/releases/tag/"
                    + FINAL_VERSION,
                    "assets": [
                        {
                            "name": path.name,
                            "size": path.stat().st_size,
                            "state": "uploaded",
                            "url": f"{release_url}/{path.name}",
                            "digest": f"sha256:{_sha(path)}",
                        }
                        for path in (dfu, frm, bundle)
                    ],
                },
            }
        ),
    )
    _write(
        verification,
        _json_bytes(
            {
                "schema": EVIDENCE.RELEASE_VERIFICATION_SCHEMA,
                "command": [
                    "env",
                    "VERIFY_RELEASE_CACHE=remote-verification-cache",
                    "scripts/verify_release.sh",
                    manifest_relative,
                    "--json",
                ],
                "exit_code": 0,
                "verifier_sha256": _sha(root / EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH),
                "manifest_sha256": _sha(manifest),
                "result": {
                    "release_verified": True,
                    "release_tag": FINAL_VERSION,
                    "image": verification_image.relative_to(root).as_posix(),
                    "image_sha256": _sha(dfu),
                    "device_fw": FINAL_VERSION,
                    "firmware_source": FINAL_COMMIT,
                    "gadget_source": "8" * 40,
                    "fpga_bitstream_md5": "9" * 32,
                    "checks_passed": 14,
                },
            }
        ),
    )
    descriptor = root / "published-input.json"
    _write(
        descriptor,
        _json_bytes(
            {
                "schema": EVIDENCE.PUBLISHED_INPUT_SCHEMA,
                "schema_version": 1,
                "stage": "published-release",
                "release_url": release_url,
                "tag_record_path": tag_record.relative_to(root).as_posix(),
                "remote_tag_record_path": remote_tag_record.relative_to(
                    root
                ).as_posix(),
                "dfu_path": dfu_relative,
                "frm_path": frm_relative,
                "bundle_path": bundle_relative,
                "release_inventory_path": inventory.relative_to(root).as_posix(),
                "release_manifest_path": manifest_relative,
                "verification_image_path": verification_image.relative_to(
                    root
                ).as_posix(),
                "verification_result_path": verification.relative_to(root).as_posix(),
            }
        ),
    )
    return qualification, descriptor


def test_assemble_and_verify_candidate_index(tmp_path: Path) -> None:
    output = _assemble(tmp_path)

    index = EVIDENCE.verify_index(output, expected_stage="candidate-pre-hardware")

    assert index["source"]["commit"] == COMMIT
    assert index["release"]["firmware_version"] == VERSION
    assert index["artifact"]["dfu_bytes"] == 80
    assert index["artifact"]["fit_bytes"] == 64
    fpga_role = next(
        member
        for member in index["evidence"]["members"]
        if member["role"] == "fpga-bitstream"
    )
    assert Path(fpga_role["path"]).name == "system_top.bit"
    assert output.stat().st_mode & 0o777 == 0o644
    assert output.with_suffix(".json.sha256").stat().st_mode & 0o777 == 0o644


def test_cli_assemble_and_verify_are_hardware_free(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)

    assert (
        EVIDENCE.main(
            [
                "assemble",
                "--stage",
                "candidate-pre-hardware",
                "--archive-root",
                str(tmp_path),
                "--input",
                str(input_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        EVIDENCE.main(
            [
                "verify",
                "--stage",
                "candidate-pre-hardware",
                "--index",
                str(output),
            ]
        )
        == 0
    )


def test_consumer_semantic_api_authorizes_exact_local_operator_evidence(
    tmp_path: Path,
) -> None:
    output = _assemble(tmp_path)

    normalized = EVIDENCE.verify_artifact_index_semantics(
        output, expected_stage="candidate-pre-hardware"
    )
    assert normalized == json.loads(output.read_text())


def test_consumer_semantic_api_accepts_coherent_captured_attestation(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path, captured_attestation=True)
    EVIDENCE.assemble(
        archive_root=tmp_path,
        input_path=input_path,
        output_path=output,
        stage="candidate-pre-hardware",
    )

    normalized = EVIDENCE.verify_artifact_index_semantics(
        output, expected_stage="candidate-pre-hardware"
    )

    assert normalized == json.loads(output.read_text())


def test_consumer_semantic_api_rejects_tampered_supporting_attestation(
    tmp_path: Path,
) -> None:
    output = _assemble(tmp_path)
    index = json.loads(output.read_text())
    member = next(
        item
        for item in index["evidence"]["members"]
        if item["role"] == "attestation-verification"
    )
    record_path = tmp_path / member["path"]
    record = json.loads(record_path.read_text())
    record["run_attempt"] += 1
    _write(record_path, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="attestation-verification"):
        EVIDENCE.verify_artifact_index_semantics(
            output, expected_stage="candidate-pre-hardware"
        )


def test_assemble_rejects_external_same_basename_source_manifest(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    canonical = tmp_path / descriptor["source"]["manifest_path"]
    external = tmp_path / "external" / canonical.name
    _write(external, canonical.read_bytes())
    descriptor["source"]["manifest_path"] = external.relative_to(tmp_path).as_posix()
    _write(input_path, _json_bytes(descriptor))

    with pytest.raises(EVIDENCE.EvidenceError, match="protected canonical path"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=input_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "version",
    [
        "v0.41-plutoplus-spf-tandem-agc-v8-rc013",
        "v0.41-plutoplus-spf-tandem-agc-v8-rc16-1-g1111111",
    ],
)
def test_assemble_rejects_typo_or_git_describe_candidate_identity(
    tmp_path: Path, version: str
) -> None:
    input_path, output = _fixture(tmp_path, version=version)

    with pytest.raises(EVIDENCE.EvidenceError, match="identity is not exact RC16"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=input_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()


@pytest.mark.parametrize(("stage", "source_lock_ref"), _STAGE_INEXACT_SOURCE_LOCK_CASES)
def test_assemble_rejects_stage_inexact_source_lock_before_publish(
    tmp_path: Path, stage: str, source_lock_ref: str
) -> None:
    identity = (
        {}
        if stage == "candidate-pre-hardware"
        else {
            "commit": FINAL_COMMIT,
            "version": FINAL_VERSION,
            "package_stem": "plutoplus-spf-tandem-agc-v8-222222222222",
        }
    )
    input_path, output = _fixture(
        tmp_path,
        stage=stage,
        source_lock_ref=source_lock_ref,
        **identity,
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="source lock ref is not exact"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=input_path,
            output_path=output,
            stage=stage,
        )

    assert not output.exists()


@pytest.mark.parametrize(("stage", "source_lock_ref"), _STAGE_INEXACT_SOURCE_LOCK_CASES)
def test_semantic_verify_rejects_stage_inexact_indexed_source_lock(
    tmp_path: Path, stage: str, source_lock_ref: str
) -> None:
    identity = (
        {}
        if stage == "candidate-pre-hardware"
        else {
            "commit": FINAL_COMMIT,
            "version": FINAL_VERSION,
            "package_stem": "plutoplus-spf-tandem-agc-v8-222222222222",
        }
    )
    input_path, output = _fixture(tmp_path, stage=stage, **identity)
    EVIDENCE.assemble(
        archive_root=tmp_path,
        input_path=input_path,
        output_path=output,
        stage=stage,
    )
    _rewrite_indexed_source_lock(output, source_lock_ref)

    with pytest.raises(EVIDENCE.EvidenceError, match="source lock ref is not exact"):
        EVIDENCE.verify_artifact_index_semantics(output, expected_stage=stage)


@pytest.mark.parametrize(
    "role",
    [
        "actions-run",
        "attestation-verification",
        "integrated-verdict",
        "ooc-status",
        "packed-versions",
        "routed-dcp",
        "waiver-inventory",
    ],
)
def test_verify_rejects_mutated_indexed_evidence(tmp_path: Path, role: str) -> None:
    output = _assemble(tmp_path)
    index = json.loads(output.read_text())
    member = next(item for item in index["evidence"]["members"] if item["role"] == role)
    with (tmp_path / member["path"]).open("ab") as stream:
        stream.write(b"mutated\n")

    with pytest.raises(EVIDENCE.EvidenceError, match=role):
        EVIDENCE.verify_index(output, expected_stage="candidate-pre-hardware")


def test_verify_rejects_sidecar_or_index_stage_mismatch(tmp_path: Path) -> None:
    output = _assemble(tmp_path)
    output.with_suffix(".json.sha256").write_text("0" * 64 + "  candidate-index.json\n")

    with pytest.raises(EVIDENCE.EvidenceError, match="sidecar"):
        EVIDENCE.verify_index(output, expected_stage="candidate-pre-hardware")
    with pytest.raises(EVIDENCE.EvidenceError, match="stage"):
        EVIDENCE.verify_index(output, expected_stage="final-pre-confirmation")


def test_assemble_rejects_missing_role_without_publishing(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    descriptor["evidence"]["members"].pop()
    input_path.write_bytes(_json_bytes(descriptor))

    with pytest.raises(EVIDENCE.EvidenceError, match="inventory"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()


def test_assemble_rejects_missing_or_substituted_semantic_verifier_before_publish(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    descriptor["harness"]["paths"].remove(EVIDENCE.SEMANTIC_VERIFIER_HARNESS_PATH)
    _write(input_path, _json_bytes(descriptor))
    with pytest.raises(EVIDENCE.EvidenceError, match="omits the semantic"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()

    input_path, output = _fixture(tmp_path)
    _write(
        tmp_path / EVIDENCE.SEMANTIC_VERIFIER_HARNESS_PATH,
        "substituted verifier\n",
    )
    with pytest.raises(EVIDENCE.EvidenceError, match="exact live committed"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()


def test_assemble_rejects_missing_or_substituted_binary_verifier_before_publish(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    descriptor["harness"]["paths"].remove(EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH)
    _write(input_path, _json_bytes(descriptor))
    with pytest.raises(EVIDENCE.EvidenceError, match="omits the binary release"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()

    input_path, output = _fixture(tmp_path)
    _write(
        tmp_path / EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH,
        "substituted binary verifier\n",
    )
    with pytest.raises(EVIDENCE.EvidenceError, match="exact live committed"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "missing",
    [
        "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
        "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
    ],
)
def test_assemble_requires_the_shared_release_and_lifecycle_harness(
    tmp_path: Path, missing: str
) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    descriptor["harness"]["paths"].remove(missing)
    _write(input_path, _json_bytes(descriptor))

    with pytest.raises(EVIDENCE.EvidenceError, match="release/lifecycle superset"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_assemble_rejects_duplicate_json_keys_and_path_escape(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    input_path.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
    with pytest.raises(EVIDENCE.EvidenceError, match="duplicate"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )

    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    descriptor["artifact"]["dfu_path"] = "../firmware.dfu"
    input_path.write_bytes(_json_bytes(descriptor))
    with pytest.raises(EVIDENCE.EvidenceError, match="canonical relative"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_assemble_rejects_symlinked_member_and_existing_output(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    descriptor = json.loads(input_path.read_text())
    bundle_member = next(
        member
        for member in descriptor["evidence"]["members"]
        if member["role"] == "bundle"
    )
    evidence = tmp_path / bundle_member["path"]
    original = evidence.read_bytes()
    target = tmp_path / "real-bundle"
    target.write_text("bundle\n")
    evidence.unlink()
    evidence.symlink_to(target)

    with pytest.raises(EVIDENCE.EvidenceError, match="symlink"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )

    evidence.unlink()
    _write(evidence, original)
    output.write_text("do not replace\n")
    with pytest.raises(EVIDENCE.EvidenceError, match="replace"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_assemble_rejects_world_writable_input(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    input_path.chmod(0o666)

    with pytest.raises(EVIDENCE.EvidenceError, match="unsafe ownership"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_substituted_dfu_even_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    dfu_name = next(name for name in members if name.endswith("-pluto.dfu"))
    members[dfu_name] = b"X" * len(members[dfu_name])
    payload = EVIDENCE._parse_checksum_inventory(
        members["PAYLOAD_SHA256SUMS"], name="test payload sums"
    )
    members["PAYLOAD_SHA256SUMS"] = _checksum_bytes(members, set(payload))
    members["SHA256SUMS"] = _checksum_bytes(members, set(members) - {"SHA256SUMS"})
    descriptor = json.loads(input_path.read_text())
    role_paths = {
        member["role"]: tmp_path / member["path"]
        for member in descriptor["evidence"]["members"]
    }
    _write(role_paths["payload-checksums"], members["PAYLOAD_SHA256SUMS"])
    _write(role_paths["bundle-inner-checksums"], members["SHA256SUMS"])
    _write_bundle(bundle, members)
    _rebind_bundle(bundle, attestation)

    with pytest.raises(EVIDENCE.EvidenceError, match="DFU/FIT"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_stale_packed_dfu_fpga_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, _attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    members["packed-fpga.bit"] = b"stale-dfu-fpga-bitstream\n"
    _rewrite_coherent_bundle(input_path, members)

    with pytest.raises(EVIDENCE.EvidenceError, match="packed DFU FPGA"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_xsa_bitstream_mismatch_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, _attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    xsa_name = next(name for name in members if name.endswith("-system_top.xsa"))
    stale_bitstream = bytearray(members["system_top.bit"])
    stale_bitstream[0] ^= 0xFF
    members[xsa_name] = _xsa_bytes(bytes(stale_bitstream))
    _rewrite_coherent_bundle(
        input_path,
        members,
        rewritten_roles={"xsa": xsa_name},
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="XSA system_top.bit differs"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_stale_fpga_bitstream_sidecar_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, _attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    members["system-top-bit.sha256"] = b"0" * 64 + b"  system_top.bit\n"
    _rewrite_coherent_bundle(input_path, members)

    with pytest.raises(EVIDENCE.EvidenceError, match="exact raw-bitstream sidecar"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_integrated_verdict_rejects_substituted_report_with_coherent_bundle(
    tmp_path: Path,
) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    report_name = "system_top_timing_summary_routed.rpt"
    members[report_name] = b"substituted-timing\n"
    payload = EVIDENCE._parse_checksum_inventory(
        members["PAYLOAD_SHA256SUMS"], name="test payload sums"
    )
    members["PAYLOAD_SHA256SUMS"] = _checksum_bytes(members, set(payload))
    members["SHA256SUMS"] = _checksum_bytes(members, set(members) - {"SHA256SUMS"})
    descriptor = json.loads(input_path.read_text())
    role_paths = {
        member["role"]: tmp_path / member["path"]
        for member in descriptor["evidence"]["members"]
    }
    _write(role_paths["routed-timing"], members[report_name])
    _write(role_paths["payload-checksums"], members["PAYLOAD_SHA256SUMS"])
    _write(role_paths["bundle-inner-checksums"], members["SHA256SUMS"])
    _write_bundle(bundle, members)
    _rebind_bundle(bundle, attestation)

    with pytest.raises(EVIDENCE.EvidenceError, match="integrated verdict"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_duplicate_member(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    entries = sorted(members.items())
    entries.insert(1, entries[0])
    _write_bundle_entries(bundle, entries)
    _rebind_bundle(bundle, attestation)

    with pytest.raises(EVIDENCE.EvidenceError, match="duplicates member"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_path_traversal_member(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    entries = [("../escape", b"escape\n"), *sorted(members.items())]
    _write_bundle_entries(bundle, entries)
    _rebind_bundle(bundle, attestation)

    with pytest.raises(EVIDENCE.EvidenceError, match="canonical relative"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_bundle_rejects_incomplete_sha256sums_coverage(tmp_path: Path) -> None:
    input_path, output = _fixture(tmp_path)
    bundle, attestation = _bundle_details(input_path)
    members = _bundle_members(bundle)
    covered = set(members) - {"SHA256SUMS"}
    covered.remove(next(name for name in covered if name.endswith("-rootfs.cpio.gz")))
    members["SHA256SUMS"] = _checksum_bytes(members, covered)
    descriptor = json.loads(input_path.read_text())
    checksum_path = next(
        tmp_path / member["path"]
        for member in descriptor["evidence"]["members"]
        if member["role"] == "bundle-inner-checksums"
    )
    _write(checksum_path, members["SHA256SUMS"])
    _write_bundle(bundle, members)
    _rebind_bundle(bundle, attestation)

    with pytest.raises(EVIDENCE.EvidenceError, match="does not cover"):
        EVIDENCE.assemble(
            input_path=input_path,
            archive_root=tmp_path,
            output_path=output,
            stage="candidate-pre-hardware",
        )


def test_candidate_qualification_accepts_exact_operator_owned_campaign(
    tmp_path: Path,
) -> None:
    candidate = _assemble(tmp_path)
    _write_campaign_hardware(tmp_path, candidate)
    campaign = tmp_path / "campaign-index.json"

    EVIDENCE.assemble(
        archive_root=tmp_path,
        output_path=campaign,
        stage="candidate-qualified",
        parent_index_path=candidate,
    )

    record = EVIDENCE.verify_index(campaign, expected_stage="candidate-qualified")
    assert len(record["radios"]) == 4


def test_candidate_qualification_rejects_missing_utility_companion(
    tmp_path: Path,
) -> None:
    candidate = _assemble(tmp_path)
    _write_campaign_hardware(tmp_path, candidate)
    (tmp_path / "hardware/deploy/RADIO1/operation-plan.json").unlink()

    with pytest.raises(
        EVIDENCE.EvidenceError, match="operation plan cannot be inspected"
    ):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            output_path=tmp_path / "campaign-index.json",
            stage="candidate-qualified",
            parent_index_path=candidate,
        )


@pytest.mark.parametrize(
    "mutation",
    ["old-summary", "host-libiio", "harness", "one-band", "one-soak-cycle"],
)
def test_candidate_qualification_rejects_stale_or_unbound_release_report(
    tmp_path: Path, mutation: str
) -> None:
    candidate = _assemble(tmp_path)
    _write_campaign_hardware(tmp_path, candidate)
    report_path = tmp_path / (
        "hardware/soak/RADIO1/release-hardware-report.json"
        if mutation == "one-soak-cycle"
        else "hardware/full/RADIO1/release-hardware-report.json"
    )
    report = json.loads(report_path.read_text())
    if mutation == "old-summary":
        for key in (
            "all_host_libiio_verified",
            "host_libiio_invocations",
            "plan",
            "counts",
            "phases",
        ):
            report.pop(key)
    elif mutation == "host-libiio":
        report["all_host_libiio_verified"] = False
    elif mutation == "harness":
        report["configuration"]["harness_sources"][
            "tests/radio_hardware/release_cli.py"
        ] = "0" * 64
    elif mutation == "one-band":
        report["configuration"]["bands"] = report["configuration"]["bands"][:1]
    else:
        report["configuration"]["repeat_cycles"] = 1
    _write(report_path, _json_bytes(report))

    with pytest.raises(
        EVIDENCE.EvidenceError, match="host|harness|aggregate|configuration"
    ):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            output_path=tmp_path / "campaign-index.json",
            stage="candidate-qualified",
            parent_index_path=candidate,
        )


@pytest.mark.parametrize("mutation", ["empty-preflight", "synchronized-raw"])
def test_candidate_qualification_reuses_the_lifecycle_producer_oracle(
    tmp_path: Path, mutation: str
) -> None:
    candidate = _assemble(tmp_path)
    _write_campaign_hardware(tmp_path, candidate)
    report_path = (
        tmp_path / "hardware/lifecycle/RADIO1/muted-metadata-batch-lifecycle-v5.json"
    )
    report = json.loads(report_path.read_text())
    if mutation == "empty-preflight":
        report["preflight"] = {}
    else:
        entry = report["metadata_artifacts"]["entries"][0]
        raw_path = report_path.parent / entry["relative_path"]
        payload = bytearray(raw_path.read_bytes())
        payload[0] ^= 0xFF
        _write(raw_path, bytes(payload))
        raw_path.chmod(0o600)
        entry["sha256"] = _sha(raw_path)
        digest = hashlib.sha256()
        for observed in report["metadata_artifacts"]["entries"]:
            digest.update(observed["relative_path"].encode())
            digest.update(b"\0")
            digest.update(str(observed["bytes"]).encode())
            digest.update(b"\0")
            digest.update(observed["sha256"].encode())
            digest.update(b"\n")
        report["metadata_artifacts"]["manifest_sha256"] = digest.hexdigest()
    _write(report_path, _json_bytes(report))

    with pytest.raises(EVIDENCE.EvidenceError, match="current producer oracle"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            output_path=tmp_path / "campaign-index.json",
            stage="candidate-qualified",
            parent_index_path=candidate,
        )


def test_candidate_qualified_binds_four_serials_and_every_raw_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _assemble(tmp_path)
    campaign = _assemble_campaign(tmp_path, monkeypatch, artifact_index=candidate)

    index = EVIDENCE.verify_index(campaign, expected_stage="candidate-qualified")

    assert [radio["serial"] for radio in index["radios"]] == [
        "RADIO1",
        "RADIO2",
        "RADIO3",
        "RADIO4",
    ]
    assert set(index["radios"][0]) == {"serial", "deploy", "full", "soak", "lifecycle"}
    # Per radio: the three utility plan/inventory records preceding the receipt,
    # five phase logs, eight full/soak phase reports, and the lifecycle runner's
    # 65 retained metadata records.
    assert len(index["raw_members"]) == 4 * (3 + 5 + 8 + 65)
    assert any(
        member["path"].endswith("stale-latch-report.json")
        for member in index["raw_members"]
    )
    assert index["parent"]["sha256"] == _sha(candidate)


def test_candidate_qualified_rejects_unindexed_extra_raw_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _assemble(tmp_path)
    campaign = _assemble_campaign(tmp_path, monkeypatch, artifact_index=candidate)
    _write(tmp_path / "hardware/full/RADIO1/late-unindexed.log", "late\n")

    with pytest.raises(EVIDENCE.EvidenceError, match="every raw"):
        EVIDENCE.verify_index(campaign, expected_stage="candidate-qualified")


def test_candidate_qualified_rejects_report_receipt_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _assemble(tmp_path)
    campaign = _assemble_campaign(tmp_path, monkeypatch, artifact_index=candidate)
    report = tmp_path / "hardware/full/RADIO1/release-hardware-report.json"
    value = json.loads(report.read_text())
    value["configuration"]["candidate_binding"]["deployment_receipt_sha256"] = "0" * 64
    _write(report, _json_bytes(value))

    with pytest.raises(EVIDENCE.EvidenceError, match="immutable descriptor"):
        EVIDENCE.verify_index(campaign, expected_stage="candidate-qualified")


def test_final_policy_binds_candidate_final_diff_and_requires_real_full_campaign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign, final_artifact, policy = _lineage_fixture(tmp_path, monkeypatch)

    record = EVIDENCE.verify_index(policy, expected_stage="final-qualification-policy")

    assert record["required_test"] == "full-campaign"
    assert record["comparison"]["verdict"] == "identity-packaging-only"
    assert record["comparison"]["source_diff_reproduced"] is True
    assert record["candidate_qualification"]["sha256"] == _sha(campaign)
    assert record["final_artifact"]["sha256"] == _sha(final_artifact)


def test_final_policy_requires_full_campaign_for_source_tree_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _campaign, _final_artifact, policy = _lineage_fixture(
        tmp_path, monkeypatch, identity_only=False
    )

    record = EVIDENCE.verify_index(policy, expected_stage="final-qualification-policy")

    assert record["required_test"] == "full-campaign"
    assert record["comparison"]["verdict"] == "functional-or-unproven"


@pytest.mark.parametrize(
    "mutation",
    ["fake-tree", "omitted", "extra", "wrong-blob", "rename"],
)
def test_source_diff_must_exactly_match_local_no_renames_git_inventory(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    changes = [
        {
            "path": "deleted.txt",
            "status": "deleted",
            "candidate_blob": "5" * 40,
            "final_blob": None,
        },
        {
            "path": "new.txt",
            "status": "added",
            "candidate_blob": None,
            "final_blob": "6" * 40,
        },
    ]
    reproduced = {
        "candidate": {"commit": COMMIT, "tree": "3" * 40},
        "final": {"commit": FINAL_COMMIT, "tree": "4" * 40},
        "changed_files": changes,
        "trees_identical": False,
    }
    supplied = json.loads(json.dumps(reproduced))
    supplied.update(
        {
            "schema": EVIDENCE.CANDIDATE_TO_FINAL_DIFF_SCHEMA,
            "schema_version": 1,
        }
    )
    supplied.pop("trees_identical")
    if mutation == "fake-tree":
        supplied["final"]["tree"] = "9" * 40
    elif mutation == "omitted":
        supplied["changed_files"].pop()
    elif mutation == "extra":
        supplied["changed_files"].append(
            {
                "path": "zzz.txt",
                "status": "added",
                "candidate_blob": None,
                "final_blob": "7" * 40,
            }
        )
    elif mutation == "wrong-blob":
        supplied["changed_files"][0]["candidate_blob"] = "8" * 40
    else:
        supplied["changed_files"][0]["status"] = "renamed"
    monkeypatch.setattr(EVIDENCE, "_reproduce_source_diff", lambda _c, _f: reproduced)

    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE._decode_source_diff(
            _json_bytes(supplied),
            candidate_commit=COMMIT,
            final_commit=FINAL_COMMIT,
        )


def test_source_diff_unavailable_locally_forces_full_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(EVIDENCE, "_reproduce_source_diff", lambda _c, _f: None)
    supplied = {
        "schema": EVIDENCE.CANDIDATE_TO_FINAL_DIFF_SCHEMA,
        "schema_version": 1,
        "candidate": {"commit": COMMIT, "tree": "3" * 40},
        "final": {"commit": FINAL_COMMIT, "tree": "3" * 40},
        "changed_files": [],
    }

    decoded = EVIDENCE._decode_source_diff(
        _json_bytes(supplied),
        candidate_commit=COMMIT,
        final_commit=FINAL_COMMIT,
    )

    assert decoded["source_diff_reproduced"] is False
    assert decoded["trees_identical"] is False


def test_final_policy_rejects_tampered_required_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _campaign, _final_artifact, policy = _lineage_fixture(tmp_path, monkeypatch)
    record = json.loads(policy.read_text())
    record["required_test"] = "reduced-confirmation"
    _write(policy, _json_bytes(record))
    _write(
        policy.with_suffix(".json.sha256"),
        f"{_sha(policy)}  {policy.name}\n",
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="required-test"):
        EVIDENCE.verify_index(policy, expected_stage="final-qualification-policy")


def test_final_qualified_binds_exact_full_campaign_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final_artifact, policy, qualification = _assemble_final_qualification(
        tmp_path, monkeypatch
    )

    record = EVIDENCE.verify_index(qualification, expected_stage="final-qualified")

    assert record["required_test"] == "full-campaign"
    assert record["selected_evidence"]["mode"] == "full-campaign"
    assert record["final_artifact"]["sha256"] == _sha(final_artifact)
    assert record["policy"]["sha256"] == _sha(policy)
    assert len(record["radios"]) == 4


def test_final_qualified_rejects_mutated_full_campaign_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _final_artifact, _policy, qualification = _assemble_final_qualification(
        tmp_path, monkeypatch
    )
    report = tmp_path / "hardware/full/RADIO1/release-hardware-report.json"
    value = json.loads(report.read_text())
    value["all_host_libiio_verified"] = False
    _write(report, _json_bytes(value))

    with pytest.raises(EVIDENCE.EvidenceError, match="immutable descriptor"):
        EVIDENCE.verify_index(qualification, expected_stage="final-qualified")


def test_published_release_binds_tag_final_qualification_and_exact_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    output = tmp_path / "published-release-index.json"

    EVIDENCE.assemble(
        archive_root=tmp_path,
        input_path=descriptor,
        output_path=output,
        stage="published-release",
        parent_index_path=qualification,
    )
    record = EVIDENCE.verify_index(output, expected_stage="published-release")

    assert record["parent"]["sha256"] == _sha(qualification)
    assert record["source_commit"] == FINAL_COMMIT
    assert set(record["assets"]) == {"dfu", "frm", "bundle"}
    assert record["tag_record"]["sha256"] == _sha(
        tmp_path / "annotated-tag-record.json"
    )
    assert record["remote_tag_record"]["sha256"] == _sha(
        tmp_path / "github-remote-tag-record.json"
    )


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        pytest.param("absent", "remote annotated tag record is absent", id="absent"),
        pytest.param(
            "wrong-object", "differs from the exact local tag object", id="wrong-object"
        ),
        pytest.param(
            "wrong-target", "differs from the qualified commit", id="wrong-target"
        ),
    ],
)
def test_published_release_rejects_absent_or_mismatched_remote_tag_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    failure: str,
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    remote_tag = tmp_path / "github-remote-tag-record.json"
    if mutation == "absent":
        remote_tag.unlink()
    else:
        record = json.loads(remote_tag.read_text())
        position = 0 if mutation == "wrong-object" else 1
        record["refs"][position]["object_id"] = "6" * 40
        _write(remote_tag, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match=failure):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_frm_with_different_fit_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    raw = json.loads(descriptor.read_text())
    frm = tmp_path / raw["frm_path"]
    payload = bytearray(frm.read_bytes())
    payload[0] ^= 0xFF
    _write(frm, bytes(payload))

    with pytest.raises(EVIDENCE.EvidenceError, match="exact qualified FIT"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_wrong_repository_or_missing_remote_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong_root = tmp_path / "wrong-repository"
    wrong_root.mkdir(mode=0o755)
    qualification, descriptor = _published_fixture(wrong_root, monkeypatch)
    value = json.loads(descriptor.read_text())
    value["release_url"] = (
        "https://github.com/example/plutosdr-fw/releases/download/" + FINAL_VERSION
    )
    _write(descriptor, _json_bytes(value))
    with pytest.raises(EVIDENCE.EvidenceError, match="canonical repository/tag"):
        EVIDENCE.assemble(
            archive_root=wrong_root,
            input_path=descriptor,
            output_path=wrong_root / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )

    missing_root = tmp_path / "missing-asset"
    missing_root.mkdir(mode=0o755)
    qualification, descriptor = _published_fixture(missing_root, monkeypatch)
    inventory = missing_root / "github-release-inventory.json"
    value = json.loads(inventory.read_text())
    value["result"]["assets"] = value["result"]["assets"][:-1]
    _write(inventory, _json_bytes(value))
    with pytest.raises(EVIDENCE.EvidenceError, match="exact three-asset set"):
        EVIDENCE.assemble(
            archive_root=missing_root,
            input_path=descriptor,
            output_path=missing_root / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_local_only_binary_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    verification = tmp_path / "release-verification.json"
    record = json.loads(verification.read_text())
    record["command"] = [
        "scripts/verify_release.sh",
        "tandem-agc-v8.yaml",
        "--image",
        "published/local-only.dfu",
        "--json",
    ]
    _write(verification, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="command is not exact"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_changed_indexed_binary_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    _write(
        tmp_path / EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH,
        "changed after qualification\n",
    )

    with pytest.raises(EVIDENCE.EvidenceError, match="harness file changed"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_modified_live_binary_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    live_root = tmp_path / "live-checkout"
    _write(
        live_root / EVIDENCE.SEMANTIC_VERIFIER_HARNESS_PATH,
        SCRIPT.read_bytes(),
    )
    _write(
        live_root / EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH,
        "modified live binary verifier\n",
    )
    monkeypatch.setattr(EVIDENCE, "ROOT", live_root)

    with pytest.raises(
        EVIDENCE.EvidenceError,
        match="binary release verifier is not exact live committed indexed",
    ):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_binary_verifier_not_at_qualified_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    committed_file_sha256 = EVIDENCE._committed_file_sha256
    monkeypatch.setattr(
        EVIDENCE,
        "_committed_file_sha256",
        lambda commit, relative: (
            "6" * 64
            if relative == EVIDENCE.RELEASE_VERIFIER_HARNESS_PATH
            else committed_file_sha256(commit, relative)
        ),
    )

    with pytest.raises(
        EVIDENCE.EvidenceError,
        match="binary release verifier is not exact live committed indexed",
    ):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


@pytest.mark.parametrize("mutation", ["extra-asset", "wrong-digest"])
def test_published_release_rejects_ambiguous_or_wrong_remote_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    inventory = tmp_path / "github-release-inventory.json"
    record = json.loads(inventory.read_text())
    if mutation == "extra-asset":
        record["result"]["assets"].append(
            {
                "name": "alternate-debug-pluto.dfu",
                "size": 80,
                "state": "uploaded",
                "url": "https://github.com/misko/plutosdr-fw/releases/download/"
                f"{FINAL_VERSION}/alternate-debug-pluto.dfu",
                "digest": "sha256:" + "0" * 64,
            }
        )
    else:
        record["result"]["assets"][0]["digest"] = "sha256:" + "0" * 64
    _write(inventory, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="three-asset|not exact"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_lightweight_or_retargeted_tag_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    tag = tmp_path / "annotated-tag-record.json"
    record = json.loads(tag.read_text())
    record["target_commit"] = COMMIT
    _write(tag, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="target"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_failed_or_unbound_verifier_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    verification = tmp_path / "release-verification.json"
    record = json.loads(verification.read_text())
    record["result"]["release_verified"] = False
    _write(verification, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="not exact and successful"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_verifier_result_with_wrong_verifier_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    verification = tmp_path / "release-verification.json"
    record = json.loads(verification.read_text())
    record["verifier_sha256"] = "0" * 64
    _write(verification, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="not exact and successful"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


def test_published_release_rejects_manifest_missing_verifier_required_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    descriptor_record = json.loads(descriptor.read_text())
    manifest = tmp_path / descriptor_record["release_manifest_path"]
    filtered = "\n".join(
        line
        for line in manifest.read_text().splitlines()
        if not line.startswith("gadget_source:")
    )
    _write(manifest, filtered + "\n")

    with pytest.raises(EVIDENCE.EvidenceError, match="omits verify_release.sh"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )


@pytest.mark.parametrize("field", ["gadget_source", "fpga_bitstream_md5"])
def test_published_release_rejects_verifier_result_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    qualification, descriptor = _published_fixture(tmp_path, monkeypatch)
    verification = tmp_path / "release-verification.json"
    record = json.loads(verification.read_text())
    record["result"][field] = "d" * len(record["result"][field])
    _write(verification, _json_bytes(record))

    with pytest.raises(EVIDENCE.EvidenceError, match="not exact and successful"):
        EVIDENCE.assemble(
            archive_root=tmp_path,
            input_path=descriptor,
            output_path=tmp_path / "published-release-index.json",
            stage="published-release",
            parent_index_path=qualification,
        )
