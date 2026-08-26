"""Offline planted-failure oracles for exact-serial RAM-only deployment."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from . import tandem_ram_deploy as deploy
from .candidate_binding import (
    REQUIRED_EVIDENCE_ROLES,
    CandidateBindingError,
    validate_deployment_receipt,
)

SERIAL = "104473222a87000abc00123456789def"
CURRENT_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc4"
CANDIDATE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc6"
TOPOLOGY = "3-8"
INTERFACE = "enx001122334455"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stub_live_repository_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most oracles isolate deployment logic from this intentionally dirty tree."""

    def verified(*, index_path: Path, index: dict[str, Any]) -> dict[str, Any]:
        indexed = {item["path"]: item["sha256"] for item in index["harness"]["files"]}
        missing = set(deploy.DEPLOYER_HARNESS_PATHS) - set(indexed)
        if missing:
            raise deploy.DeploymentError(
                f"artifact index omits deployer harness paths: {sorted(missing)}"
            )
        return {
            "repository": str(ROOT),
            "commit": index["source"]["commit"],
            "clean": True,
            "files": [
                {"path": path, "sha256": indexed[path]}
                for path in deploy.DEPLOYER_HARNESS_PATHS
            ],
            "index_path": str(index_path),
        }

    monkeypatch.setattr(deploy, "_verify_runner_provenance", verified)

    def semantic(index_path: Path, *, expected_stage: str) -> dict[str, Any]:
        value = json.loads(index_path.read_text())
        normalized = deploy.validate_artifact_index(value)
        assert normalized["stage"] == expected_stage
        return normalized

    monkeypatch.setattr(deploy, "verify_artifact_index_semantics", semantic)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


@dataclass
class Fixture:
    options: deploy.DeploymentOptions
    index: dict[str, Any]
    index_path: Path
    artifact_path: Path
    manifest_path: Path
    proof_path: Path
    known_hosts_path: Path

    def rewrite_index(self) -> None:
        payload = (json.dumps(self.index, sort_keys=True) + "\n").encode()
        self.index_path.write_bytes(payload)
        self.options = replace(
            self.options,
            artifact_index_sha256=_sha(payload),
        )


def _fixture(tmp_path: Path, *, artifact_name: str = "firmware.dfu") -> Fixture:
    archive = tmp_path / "candidate"
    manifest_path = archive / "source" / "manifest.yaml"
    manifest_payload = b"schema: test-source-lock\n"
    _write(manifest_path, manifest_payload)

    fit_payload = b"\xd0\x0d\xfe\xed" + b"candidate-fit-body" * 8
    suffix = b"\x00" * 8 + b"UFD" + b"\x10" + b"\x00" * 4
    assert len(suffix) == 16
    dfu_payload = fit_payload + suffix
    artifact_path = archive / "artifact" / artifact_name
    _write(artifact_path, dfu_payload)

    harness_records: list[dict[str, str]] = []
    for position, relative in enumerate(deploy.DEPLOYER_HARNESS_PATHS):
        payload = f"synthetic-deployer-harness-{position}\n".encode()
        path = archive / relative
        _write(path, payload)
        harness_records.append({"path": relative, "sha256": _sha(payload)})

    evidence_records: list[dict[str, Any]] = []
    for position, role in enumerate(REQUIRED_EVIDENCE_ROLES):
        relative = f"evidence/{position:02d}-{role}.json"
        payload = bytes([(position % 251) + 1]) * (position + 1)
        _write(archive / relative, payload)
        evidence_records.append(
            {
                "role": role,
                "path": relative,
                "bytes": len(payload),
                "sha256": _sha(payload),
            }
        )

    index: dict[str, Any] = {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": "candidate-pre-hardware",
        "release": {
            "firmware_version": CANDIDATE_VERSION,
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": "1" * 40,
            "manifest_path": "source/manifest.yaml",
            "manifest_sha256": _sha(manifest_payload),
        },
        "build": {"run_id": 12345, "run_attempt": 1},
        "artifact": {
            "dfu_path": f"artifact/{artifact_name}",
            "dfu_bytes": len(dfu_payload),
            "dfu_sha256": _sha(dfu_payload),
            "fit_bytes": len(fit_payload),
            "fit_sha256": _sha(fit_payload),
        },
        "harness": {"files": harness_records},
        "evidence": {"members": evidence_records},
    }
    index_path = archive / "candidate-index.json"
    index_payload = (json.dumps(index, sort_keys=True) + "\n").encode()
    _write(index_path, index_payload)

    proof = {
        "schema": "plutosdr-fw.tandem-ram-transition-proof",
        "schema_version": 1,
        "verdict": "pass",
        "method": "download-then-detach-e",
        "reviewed": True,
        "tested_serial": SERIAL,
        "evidence_sha256": "a" * 64,
        "observations": {
            "usb_reset_R": "persistent-image",
            "dfu_detach_e": "ram-image",
            "qspi_written": False,
        },
    }
    proof_path = tmp_path / "transition-proof.json"
    proof_payload = (json.dumps(proof, sort_keys=True) + "\n").encode()
    _write(proof_path, proof_payload, mode=0o600)

    known_hosts_path = tmp_path / "known_hosts"
    known_hosts_payload = b"192.168.2.1 ssh-ed25519 AAAAtestkey\n"
    _write(known_hosts_path, known_hosts_payload, mode=0o600)

    receipt_parent = archive / SERIAL
    receipt_parent.mkdir()
    options = deploy.DeploymentOptions(
        serial=SERIAL,
        artifact_path=artifact_path,
        artifact_sha256=_sha(dfu_payload),
        artifact_index_path=index_path,
        artifact_index_sha256=_sha(index_payload),
        expected_current_firmware=CURRENT_VERSION,
        receipt_path=receipt_parent / "ram-receipt.json",
        known_hosts_path=known_hosts_path,
        known_hosts_sha256=_sha(known_hosts_payload),
        ssh_host="192.168.2.1",
        ssh_user="root",
        ssh_identity_file=None,
        usb_interface=None,
        transition_proof_path=proof_path,
        transition_proof_sha256=_sha(proof_payload),
        operator_confirmation=f"RAM BOOT {SERIAL}",
        timeout_seconds=1.0,
    )
    return Fixture(
        options=options,
        index=index,
        index_path=index_path,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        proof_path=proof_path,
        known_hosts_path=known_hosts_path,
    )


def _device(
    product: str, *, serial: str = SERIAL, topology: str = TOPOLOGY
) -> deploy.UsbDevice:
    return deploy.UsbDevice(
        topology=topology,
        sysfs_path=f"/sys/bus/usb/devices/{topology}",
        serial=serial,
        vendor_id=deploy.USB_VENDOR,
        product_id=product,
        busnum=3,
        devnum=8,
        network_interfaces=(INTERFACE,) if product == deploy.RUNTIME_PRODUCT else (),
    )


def _attestation(
    *,
    firmware: str,
    boot_id: str,
    serial: str = SERIAL,
    safe: bool = True,
    qspi_sha256: str = "7" * 64,
) -> deploy.RuntimeAttestation:
    return deploy.RuntimeAttestation(
        serial=serial,
        boot_id=boot_id,
        firmware_version=firmware,
        qspi_partition="/dev/mtdblock3",
        qspi_mtd_name="qspi-linux",
        qspi_bytes=32 * 1024 * 1024,
        qspi_sha256=qspi_sha256,
        tx_muted=safe,
        dds_disabled=safe,
        dac_selectors_zero=safe,
        tandem_state="IDLE" if safe else "RUNNING",
        fifo_level=0 if safe else 1,
        fault_flags=0 if safe else 1,
        raw={},
    )


class FakeBackend:
    def __init__(
        self,
        *,
        inventory: Sequence[deploy.UsbDevice] | None = None,
        attestations: Sequence[deploy.RuntimeAttestation] | None = None,
    ) -> None:
        self.devices = tuple(inventory or (_device(deploy.RUNTIME_PRODUCT),))
        self.attestations = list(
            attestations
            or (
                _attestation(firmware=CURRENT_VERSION, boot_id="boot-before"),
                _attestation(firmware=CANDIDATE_VERSION, boot_id="boot-after"),
            )
        )
        self.inventory_calls = 0
        self.attestation_calls: list[tuple[str, str, bool]] = []
        self.ram_requests: list[list[str]] = []
        self.dfu_commands: list[list[str]] = []

    def inventory(self) -> tuple[deploy.UsbDevice, ...]:
        self.inventory_calls += 1
        return self.devices

    def attest_runtime(
        self,
        device: deploy.UsbDevice,
        *,
        interface: str,
        expected_firmware: str,
        force_safe: bool,
    ) -> deploy.RuntimeAttestation:
        self.attestation_calls.append(
            (device.product_id, expected_firmware, force_safe)
        )
        index = min(len(self.attestation_calls) - 1, len(self.attestations) - 1)
        return self.attestations[index]

    def request_ram_mode(self, argv: Sequence[str]) -> None:
        self.ram_requests.append(list(argv))

    def wait_for_mode(
        self,
        *,
        serial: str,
        topology: str,
        product_id: str,
        timeout_seconds: float,
    ) -> deploy.UsbDevice:
        del timeout_seconds
        return _device(product_id, serial=serial, topology=topology)

    def run_dfu(self, argv: Sequence[str]) -> None:
        self.dfu_commands.append(list(argv))


def test_semantic_evidence_failure_precedes_usb_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend()

    def reject(_path: Path, *, expected_stage: str) -> dict[str, Any]:
        assert expected_stage == "candidate-pre-hardware"
        raise deploy.EvidenceError("planted incoherent bundle")

    monkeypatch.setattr(deploy, "verify_artifact_index_semantics", reject)
    with pytest.raises(deploy.DeploymentError, match="not authorizing"):
        deploy.execute_deployment(fixture.options, backend)
    assert backend.inventory_calls == 0
    assert not fixture.options.receipt_path.exists()


def test_candidate_load_binds_index_manifest_dfu_fit_and_evidence_contract(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    artifact = deploy.load_candidate_artifact(fixture.options)

    assert artifact.dfu_path == fixture.artifact_path
    assert artifact.dfu_sha256 == fixture.options.artifact_sha256
    assert artifact.source_manifest_path == fixture.manifest_path
    assert artifact.evidence_roles == REQUIRED_EVIDENCE_ROLES


def test_runner_provenance_requires_clean_head_blob_and_index_agreement(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    payloads: dict[str, bytes] = {}
    for position, relative in enumerate(deploy.DEPLOYER_HARNESS_PATHS):
        payload = f"committed-runner-{position}\n".encode()
        payloads[relative] = payload
        _write(repository / relative, payload)

    def git(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            text=True,
            capture_output=True,
            timeout=10,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Offline Test")
    git("config", "user.email", "offline@example.invalid")
    git("add", "--", *deploy.DEPLOYER_HARNESS_PATHS)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "runner")
    commit = git("rev-parse", "HEAD")

    archive = tmp_path / "archive"
    archive.mkdir()
    index_path = archive / "candidate-index.json"
    _write(index_path, b"{}\n")
    files: list[dict[str, str]] = []
    for relative in deploy.DEPLOYER_HARNESS_PATHS:
        _write(archive / relative, payloads[relative])
        files.append({"path": relative, "sha256": _sha(payloads[relative])})
    index = {"source": {"commit": commit}, "harness": {"files": files}}

    result = deploy._verify_runner_provenance_at(
        repository, index_path=index_path, index=index
    )
    assert result["clean"] is True
    assert result["commit"] == commit

    live = repository / deploy.DEPLOYER_HARNESS_PATHS[0]
    live.write_bytes(b"dirty-runner\n")
    with pytest.raises(deploy.DeploymentError, match="completely clean"):
        deploy._verify_runner_provenance_at(
            repository, index_path=index_path, index=index
        )
    live.write_bytes(payloads[deploy.DEPLOYER_HARNESS_PATHS[0]])

    untracked = repository / "untracked.txt"
    untracked.write_text("untracked\n")
    with pytest.raises(deploy.DeploymentError, match="completely clean"):
        deploy._verify_runner_provenance_at(
            repository, index_path=index_path, index=index
        )
    untracked.unlink()

    archived = archive / deploy.DEPLOYER_HARNESS_PATHS[1]
    archived.write_bytes(b"substituted-archive-runner\n")
    with pytest.raises(deploy.DeploymentError, match="differs"):
        deploy._verify_runner_provenance_at(
            repository, index_path=index_path, index=index
        )

    wrong_commit = copy.deepcopy(index)
    wrong_commit["source"]["commit"] = "0" * 40
    with pytest.raises(deploy.DeploymentError, match="HEAD differs"):
        deploy._verify_runner_provenance_at(
            repository, index_path=index_path, index=wrong_commit
        )


@pytest.mark.parametrize("which", ["artifact", "index", "known-hosts", "proof"])
def test_exact_hash_mutations_fail_before_inventory(tmp_path: Path, which: str) -> None:
    fixture = _fixture(tmp_path)
    options = fixture.options
    if which == "artifact":
        options = replace(options, artifact_sha256="0" * 64)
    elif which == "index":
        options = replace(options, artifact_index_sha256="0" * 64)
    elif which == "known-hosts":
        options = replace(options, known_hosts_sha256="0" * 64)
    else:
        options = replace(options, transition_proof_sha256="0" * 64)
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError):
        deploy.execute_deployment(options, backend)

    assert backend.inventory_calls == 0
    assert not backend.ram_requests and not backend.dfu_commands


def test_requested_artifact_path_must_equal_index_member(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    decoy = tmp_path / "candidate" / "artifact" / "decoy.dfu"
    decoy.write_bytes(fixture.artifact_path.read_bytes())
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="path differs"):
        deploy.execute_deployment(
            replace(fixture.options, artifact_path=decoy), backend
        )

    assert backend.inventory_calls == 0


def test_semantically_wrong_index_fails_even_with_matching_file_hash(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.index["evidence"]["members"].pop()
    fixture.rewrite_index()
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="semantics"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 0


@pytest.mark.parametrize("member_kind", ["harness", "evidence"])
def test_substituted_indexed_member_fails_before_inventory(
    tmp_path: Path, member_kind: str
) -> None:
    fixture = _fixture(tmp_path)
    if member_kind == "harness":
        relative = fixture.index["harness"]["files"][0]["path"]
    else:
        relative = fixture.index["evidence"]["members"][0]["path"]
    member = fixture.index_path.parent / relative
    payload = bytearray(member.read_bytes())
    payload[0] ^= 0xFF
    member.write_bytes(payload)
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="changed|differs"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 0


def test_candidate_index_must_bind_all_live_deployer_sources(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.index["harness"]["files"].pop(0)
    fixture.rewrite_index()
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="omits deployer harness"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 0


@pytest.mark.parametrize("artifact_name", ["boot.dfu", "uboot-env.dfu", "image.zip"])
def test_non_firmware_targets_are_rejected_offline(
    tmp_path: Path, artifact_name: str
) -> None:
    fixture = _fixture(tmp_path, artifact_name=artifact_name)
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="only a firmware"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 0


def test_transition_proof_is_exact_serial_private_and_reviewed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    proof = json.loads(fixture.proof_path.read_text())
    proof["tested_serial"] = "another-radio"
    payload = (json.dumps(proof, sort_keys=True) + "\n").encode()
    fixture.proof_path.write_bytes(payload)
    options = replace(fixture.options, transition_proof_sha256=_sha(payload))

    with pytest.raises(deploy.DeploymentError, match="exact radio"):
        deploy.load_transition_proof(options)

    fixture.proof_path.chmod(0o644)
    with pytest.raises(deploy.DeploymentError, match="mode"):
        deploy.load_transition_proof(options)


def test_missing_transition_proof_blocks_without_hardware(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend()
    options = replace(
        fixture.options,
        transition_proof_path=None,
        transition_proof_sha256=None,
    )

    with pytest.raises(deploy.DeploymentError, match="execution is blocked"):
        deploy.execute_deployment(options, backend)

    assert backend.inventory_calls == 0


def test_exact_serial_ambiguity_stops_before_any_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend(
        inventory=(
            _device(deploy.RUNTIME_PRODUCT, topology="3-8"),
            _device(deploy.RUNTIME_PRODUCT, topology="4-2"),
        )
    )

    with pytest.raises(deploy.DeploymentError, match="exactly one"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 1
    assert not backend.attestation_calls
    assert not backend.ram_requests and not backend.dfu_commands


def test_artifact_change_after_safe_preflight_stops_before_transition(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    class MutatingBackend(FakeBackend):
        def attest_runtime(
            self,
            device: deploy.UsbDevice,
            *,
            interface: str,
            expected_firmware: str,
            force_safe: bool,
        ) -> deploy.RuntimeAttestation:
            result = super().attest_runtime(
                device,
                interface=interface,
                expected_firmware=expected_firmware,
                force_safe=force_safe,
            )
            payload = bytearray(fixture.artifact_path.read_bytes())
            payload[0] ^= 0xFF
            fixture.artifact_path.write_bytes(payload)
            return result

    backend = MutatingBackend()
    with pytest.raises(
        deploy.DeploymentError, match="changed after initial validation"
    ):
        deploy.execute_deployment(fixture.options, backend)

    assert not backend.ram_requests and not backend.dfu_commands


def test_wrong_serial_stops_before_any_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend(
        inventory=(_device(deploy.RUNTIME_PRODUCT, serial="different-radio"),)
    )

    with pytest.raises(deploy.DeploymentError, match="exactly one"):
        deploy.execute_deployment(fixture.options, backend)

    assert not backend.attestation_calls
    assert not backend.ram_requests and not backend.dfu_commands


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value[2]["argv"].append("-R"),
        lambda value: value[2]["argv"].append("--reset"),
        lambda value: value[0]["argv"].__setitem__(-1, "/usr/sbin/device_reboot sf"),
        lambda value: value[1]["argv"].__setitem__(-1, "/tmp/boot.dfu"),
        lambda value: value[1]["argv"].append("/dev/mtd0"),
        lambda value: value[1]["argv"].append("qspi-write"),
        lambda value: value[1]["argv"].append("bootloader"),
        lambda value: value[1]["argv"].append("candidate.zip"),
        lambda value: value[1]["argv"].append("candidate.frm"),
        lambda value: value[1].update(phase="persistent-write"),
    ],
)
def test_command_plan_rejects_unsafe_or_ambiguous_mutations(
    tmp_path: Path, mutation: Any
) -> None:
    fixture = _fixture(tmp_path)
    plan = [
        copy.deepcopy(item)
        for item in deploy.build_command_plan(
            fixture.options, _device(deploy.RUNTIME_PRODUCT), INTERFACE
        )
    ]
    mutation(plan)

    with pytest.raises(deploy.DeploymentError):
        deploy.validate_command_plan(
            plan,
            options=fixture.options,
            artifact=fixture.artifact_path,
            topology=TOPOLOGY,
            interface=INTERFACE,
        )


def test_success_publishes_absent_only_private_bound_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend()

    receipt, digest = deploy.execute_deployment(fixture.options, backend)

    payload = fixture.options.receipt_path.read_bytes()
    assert digest == _sha(payload)
    assert stat.S_IMODE(fixture.options.receipt_path.stat().st_mode) == 0o600
    assert receipt == json.loads(payload)
    validated = validate_deployment_receipt(
        receipt,
        artifact_index_sha256=fixture.options.artifact_index_sha256,
        serial=SERIAL,
        firmware_version=CANDIDATE_VERSION,
        dfu_sha256=fixture.options.artifact_sha256,
    )
    assert validated == receipt
    assert len(backend.ram_requests) == 1
    assert backend.ram_requests[0][-1] == "/usr/sbin/device_reboot ram"
    assert backend.ram_requests[0][:5] == ["ssh", "-F", "/dev/null", "-B", INTERFACE]
    assert len(backend.dfu_commands) == 2
    assert backend.dfu_commands[0][-2] == "-D"
    assert backend.dfu_commands[0][-1].startswith("/proc/self/fd/")
    assert backend.dfu_commands[1][-1] == "-e"
    assert all("-R" not in command for command in backend.dfu_commands)
    assert receipt["persistent_flash"]["pre_sha256"] == "7" * 64
    assert receipt["persistent_flash"]["post_sha256"] == "7" * 64
    assert receipt["persistent_flash"]["unchanged"] is True


def test_qspi_change_blocks_receipt_after_ram_boot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend(
        attestations=(
            _attestation(firmware=CURRENT_VERSION, boot_id="boot-before"),
            _attestation(
                firmware=CANDIDATE_VERSION,
                boot_id="boot-after",
                qspi_sha256="8" * 64,
            ),
            _attestation(
                firmware=CANDIDATE_VERSION,
                boot_id="boot-cleanup",
                qspi_sha256="8" * 64,
            ),
        )
    )
    with pytest.raises(deploy.DeploymentError, match="unchanged qspi-linux"):
        deploy.execute_deployment(fixture.options, backend)
    assert not fixture.options.receipt_path.exists()


def test_system_backend_downloads_only_from_inherited_sealed_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    payload = fixture.artifact_path.read_bytes()
    descriptor = os.memfd_create(
        "test-candidate", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
    )
    try:
        os.write(descriptor, payload)
        fcntl.fcntl(descriptor, deploy.F_ADD_SEALS, deploy.REQUIRED_DFU_SEALS)
        observed: list[dict[str, Any]] = []

        def fake_run(
            argv: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            observed.append({"argv": argv, **kwargs})
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(deploy.subprocess, "run", fake_run)
        deploy.SystemBackend(fixture.options).run_dfu(
            ["dfu-util", "-D", f"/proc/self/fd/{descriptor}"]
        )
        assert observed[0]["pass_fds"] == (descriptor,)
        assert observed[0]["argv"][-1] == f"/proc/self/fd/{descriptor}"
    finally:
        os.close(descriptor)


def test_candidate_inputs_are_attested_at_all_three_authorization_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    observed: list[str] = []
    original = deploy.attest_candidate_inputs

    def record(
        options: deploy.DeploymentOptions, artifact: deploy.CandidateArtifact
    ) -> dict[str, Any]:
        observed.append(artifact.index_sha256)
        return original(options, artifact)

    monkeypatch.setattr(deploy, "attest_candidate_inputs", record)
    deploy.execute_deployment(fixture.options, FakeBackend())

    assert observed == [fixture.options.artifact_index_sha256] * 3


def test_receipt_binding_mutations_are_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt, _digest = deploy.execute_deployment(fixture.options, FakeBackend())

    for changed in (
        {"artifact_index_sha256": "0" * 64},
        {"serial": "another-radio"},
        {"firmware_version": "wrong-version"},
        {"dfu_sha256": "f" * 64},
    ):
        arguments = {
            "artifact_index_sha256": fixture.options.artifact_index_sha256,
            "serial": SERIAL,
            "firmware_version": CANDIDATE_VERSION,
            "dfu_sha256": fixture.options.artifact_sha256,
            **changed,
        }
        with pytest.raises(CandidateBindingError):
            validate_deployment_receipt(receipt, **arguments)


def test_existing_receipt_refuses_before_inventory(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.options.receipt_path.write_text("reserved\n")
    backend = FakeBackend()

    with pytest.raises(deploy.DeploymentError, match="receipt path"):
        deploy.execute_deployment(fixture.options, backend)

    assert backend.inventory_calls == 0


def test_receipt_path_must_be_scoped_to_exact_serial_before_inventory(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend()
    unscoped = fixture.index_path.parent / "unscoped"
    unscoped.mkdir()

    with pytest.raises(deploy.DeploymentError, match="scoped to the exact serial"):
        deploy.execute_deployment(
            replace(fixture.options, receipt_path=unscoped / "receipt.json"), backend
        )

    assert backend.inventory_calls == 0


def test_receipt_path_must_remain_inside_candidate_archive(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    backend = FakeBackend()
    outside = tmp_path / "outside" / SERIAL
    outside.mkdir(parents=True)

    with pytest.raises(deploy.DeploymentError, match="artifact-index archive"):
        deploy.execute_deployment(
            replace(fixture.options, receipt_path=outside / "receipt.json"), backend
        )

    assert backend.inventory_calls == 0


def test_new_boot_epoch_and_final_safe_state_are_mandatory(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    same_boot_backend = FakeBackend(
        attestations=(
            _attestation(firmware=CURRENT_VERSION, boot_id="same-boot"),
            _attestation(firmware=CANDIDATE_VERSION, boot_id="same-boot"),
        )
    )
    with pytest.raises(deploy.DeploymentError, match="new boot ID"):
        deploy.execute_deployment(fixture.options, same_boot_backend)
    assert not fixture.options.receipt_path.exists()

    unsafe_backend = FakeBackend(
        attestations=(
            _attestation(firmware=CURRENT_VERSION, boot_id="boot-before"),
            _attestation(firmware=CANDIDATE_VERSION, boot_id="boot-after", safe=False),
            _attestation(firmware=CANDIDATE_VERSION, boot_id="boot-after", safe=False),
        )
    )
    with pytest.raises(deploy.DeploymentError, match="safe cleanup also failed"):
        deploy.execute_deployment(fixture.options, unsafe_backend)
    assert not fixture.options.receipt_path.exists()


def _cli_arguments(fixture: Fixture) -> list[str]:
    options = fixture.options
    return [
        "--radio-serial",
        options.serial,
        "--artifact",
        str(options.artifact_path),
        "--artifact-sha256",
        options.artifact_sha256,
        "--artifact-index",
        str(options.artifact_index_path),
        "--artifact-index-sha256",
        options.artifact_index_sha256,
        "--expected-current-firmware",
        options.expected_current_firmware,
        "--receipt",
        str(options.receipt_path),
        "--known-hosts",
        str(options.known_hosts_path),
        "--known-hosts-sha256",
        options.known_hosts_sha256,
    ]


def test_default_cli_is_offline_and_never_constructs_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)

    def forbidden_backend(_options: deploy.DeploymentOptions) -> None:
        raise AssertionError("default planning touched the hardware backend")

    monkeypatch.setattr(deploy, "SystemBackend", forbidden_backend)
    assert deploy.main(_cli_arguments(fixture)) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["hardware_accessed"] is False
    assert document["executable"] is False
    assert document["verdict"] == "blocked"
    assert "commands" not in document


def test_captured_inventory_plan_is_exact_and_still_hardware_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)
    inventory_path = tmp_path / "usb-inventory.json"
    inventory = {
        "schema": "plutosdr-fw.usb-inventory",
        "schema_version": 1,
        "devices": [
            {
                "topology": TOPOLOGY,
                "sysfs_path": f"/sys/bus/usb/devices/{TOPOLOGY}",
                "serial": SERIAL,
                "vendor_id": deploy.USB_VENDOR,
                "product_id": deploy.RUNTIME_PRODUCT,
                "busnum": 3,
                "devnum": 8,
                "network_interfaces": [INTERFACE],
            }
        ],
    }
    inventory_path.write_text(json.dumps(inventory))
    inventory_path.chmod(0o644)

    def forbidden_backend(_options: deploy.DeploymentOptions) -> None:
        raise AssertionError("captured-inventory planning touched hardware")

    monkeypatch.setattr(deploy, "SystemBackend", forbidden_backend)
    assert (
        deploy.main([*_cli_arguments(fixture), "--usb-inventory", str(inventory_path)])
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert document["hardware_accessed"] is False
    assert document["executable"] is False
    assert document["verdict"] == "ready-for-review"
    assert [item["phase"] for item in document["commands"]] == [
        "request-ram-mode",
        "download-firmware-to-ram",
        "detach-into-downloaded-image",
    ]
    assert document["commands"][1]["argv"][-2:] == [
        "-D",
        str(fixture.artifact_path),
    ]
    assert document["commands"][2]["argv"][-1] == "-e"
    assert "-R" not in json.dumps(document["commands"])


def test_sequence_experiment_is_non_executable_and_omits_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)

    assert deploy.main([*_cli_arguments(fixture), "--sequence-experiment-plan"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["executable"] is False
    assert document["verdict"].startswith("blocked")
    assert "argv" not in json.dumps(document)
    assert "dfu-util" not in json.dumps(document)
    assert all(
        item["execution_command_intentionally_omitted"]
        for item in document["comparisons"]
    )


def test_legacy_downloader_is_quarantined_without_hardware_access() -> None:
    script = ROOT / "download_and_test.sh"
    text = script.read_text()

    assert "dfu-util" not in text
    assert "device_reboot" not in text
    assert "deploy_tandem_agc_ram_hardware.sh" in text
    completed = subprocess.run(
        [str(script)],
        check=False,
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert completed.returncode == 2
    assert "quarantined" in completed.stderr


def test_flashing_guide_has_no_executable_reset_ram_recipe() -> None:
    text = (ROOT / "flashing.md").read_text()
    ram_section = text.split("## Method 3: volatile RAM boot for testing", 1)[1].split(
        "## Verify a persistent installation", 1
    )[0]

    assert "sudo dfu-util -R" not in ram_section
    assert "scripts/deploy_tandem_agc_ram_hardware.sh" in ram_section
    assert "--sequence-experiment-plan" in ram_section
    assert "deliberately non-executable" in ram_section


def test_flashing_guide_distinguishes_v8_frm_and_persistent_dfu_detach() -> None:
    text = (ROOT / "flashing.md").read_text()
    persistent_section = text.split(
        "## Method 2: persistent firmware-only DFU update", 1
    )[1].split("## Method 3: volatile RAM boot for testing", 1)[0]

    assert "Tandem AGC v8 releases publish" in text
    assert "Older DFU-only release assets" in text
    assert "downloaded RAM image" not in persistent_section
    assert "exits DFU mode" in persistent_section
    assert "persistent firmware partition" in persistent_section
    assert "post_boot_id" in persistent_section
    assert 'test "$post_boot_id" != "$pre_boot_id"' in persistent_section
    assert "installed_firmware_version" in persistent_section
