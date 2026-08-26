"""Fail-closed, exact-serial RAM-only firmware deployment.

The default CLI path is an offline planner. Hardware access requires both
``--execute`` and an exact operator confirmation. The executable command plan
permits only a firmware.dfu download followed by DFU detach.
"""

from __future__ import annotations

import argparse
import fcntl
import gc
import hashlib
import importlib
import ipaddress
import json
import math
import os
import re
import shutil
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from scripts.tandem_release_evidence import (
    EvidenceError,
    verify_artifact_index_semantics,
)

from .candidate_binding import (
    PLUTOPLUS_HARDWARE_MODEL,
    RAM_BOOT_RECEIPT_SCHEMA_VERSION,
    REQUIRED_EVIDENCE_ROLES,
    CandidateBindingError,
    validate_artifact_index,
    validate_deployment_receipt,
)

RECEIPT_SCHEMA = "plutosdr-fw.tandem-ram-boot-receipt"
USB_INVENTORY_SCHEMA = "plutosdr-fw.usb-inventory"
USB_VENDOR = "0456"
RUNTIME_PRODUCT = "b673"
DFU_PRODUCT = "b674"
DFU_DEVICE_SELECTOR = f"{USB_VENDOR}:{RUNTIME_PRODUCT},{USB_VENDOR}:{DFU_PRODUCT}"
DFU_ALT = "firmware.dfu"
TRANSITION_METHOD = "download-then-detach-e"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_PASSWORD_BYTES = 4096
MAX_DFU_BYTES = 256 * 1024 * 1024
MAX_HARNESS_BYTES = 32 * 1024 * 1024
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024 * 1024
# Linux fcntl seal constants are absent from some supported Python 3.11 builds.
# The executor is Linux-only (USB sysfs and memfd); retain the kernel UAPI
# values locally while still requiring memfd_create/MFD_ALLOW_SEALING.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)
REQUIRED_DFU_SEALS = F_SEAL_SEAL | F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_WRITE
DEPLOYER_HARNESS_PATHS = (
    "scripts/deploy_tandem_agc_ram_hardware.sh",
    "scripts/tandem_release_evidence.py",
    "tests/radio_hardware/candidate_binding.py",
    "tests/radio_hardware/tandem_ram_deploy.py",
)
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_SERIAL = re.compile(r"[A-Za-z0-9_.-]+\Z")
SAFE_USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
SAFE_INTERFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
TOPOLOGY = re.compile(r"[0-9]+-[0-9]+(?:[.][0-9]+)*\Z")


class DeploymentError(RuntimeError):
    """A deployment input, device binding, or safety invariant failed."""


@dataclass(frozen=True)
class UsbDevice:
    topology: str
    sysfs_path: str
    serial: str
    vendor_id: str
    product_id: str
    busnum: int
    devnum: int
    network_interfaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateArtifact:
    index: Mapping[str, Any]
    index_path: Path
    index_sha256: str
    firmware_version: str
    hardware_model: str
    source_commit: str
    source_manifest_path: Path
    source_manifest_sha256: str
    build_run_id: int
    build_run_attempt: int
    dfu_path: Path
    dfu_bytes: int
    dfu_sha256: str
    fit_bytes: int
    fit_sha256: str
    evidence_roles: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeAttestation:
    serial: str
    hardware_model: str
    boot_id: str
    firmware_version: str
    qspi_partition: str
    qspi_mtd_name: str
    qspi_bytes: int
    qspi_sha256: str
    tx_muted: bool
    dds_disabled: bool
    dac_selectors_zero: bool
    tandem_state: str
    fifo_level: int
    fault_flags: int
    raw: Mapping[str, str]


@dataclass(frozen=True)
class HostRoute:
    destination: str
    interface: str
    source: str


@dataclass(frozen=True)
class DeploymentOptions:
    serial: str
    artifact_path: Path
    artifact_sha256: str
    artifact_index_path: Path
    artifact_index_sha256: str
    expected_current_firmware: str
    receipt_path: Path
    ssh_host: str
    ssh_user: str
    ssh_password_file: Path | None
    usb_interface: str | None
    operator_confirmation: str | None
    timeout_seconds: float


class HardwareBackend(Protocol):
    def inventory(self) -> tuple[UsbDevice, ...]: ...

    def acquire_host_route(self, *, interface: str, host: str) -> HostRoute: ...

    def ensure_host_route(self, route: HostRoute, *, interface: str) -> None: ...

    def release_host_route(self, route: HostRoute) -> None: ...

    def attest_runtime(
        self,
        device: UsbDevice,
        *,
        interface: str,
        expected_firmware: str,
        force_safe: bool,
    ) -> RuntimeAttestation: ...

    def request_ram_mode(self, argv: Sequence[str]) -> None: ...

    def wait_for_mode(
        self, *, serial: str, topology: str, product_id: str, timeout_seconds: float
    ) -> UsbDevice: ...

    def run_dfu(self, argv: Sequence[str]) -> None: ...


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeploymentError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _parse_json(payload: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_json_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                DeploymentError(f"{label} contains non-finite value {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeploymentError(f"{label} is not canonical JSON") from error


def _canonical_absolute(path: Path, *, label: str, must_exist: bool = True) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise DeploymentError(f"{label} must be an absolute normalized path")
    try:
        resolved = path.resolve(strict=must_exist)
    except (OSError, RuntimeError) as error:
        raise DeploymentError(f"{label} cannot be resolved") from error
    if resolved != path:
        raise DeploymentError(f"{label} must not contain symlinks or aliases")
    return resolved


OwnedFileIdentity = tuple[int, int, int, int, int]


def _read_owned_regular_with_identity(
    path: Path, *, label: str, maximum_bytes: int, required_mode: int | None = None
) -> tuple[bytes, OwnedFileIdentity]:
    path = _canonical_absolute(path, label=label)
    try:
        before = path.lstat()
    except OSError as error:
        raise DeploymentError(f"{label} cannot be inspected") from error
    if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid():
        raise DeploymentError(f"{label} must be an owned regular file")
    if stat.S_IMODE(before.st_mode) & 0o022:
        raise DeploymentError(f"{label} must not be group/world writable")
    if required_mode is not None and stat.S_IMODE(before.st_mode) != required_mode:
        raise DeploymentError(f"{label} mode must be {required_mode:04o}")
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise DeploymentError(f"{label} size is outside the accepted bounds")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ):
            raise DeploymentError(f"{label} changed while it was opened")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1 << 20, remaining))
            if not chunk:
                raise DeploymentError(f"{label} was truncated during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise DeploymentError(f"{label} grew during read")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise DeploymentError(f"{label} changed during read")
        return b"".join(chunks), (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
    finally:
        os.close(descriptor)


def _read_owned_regular(
    path: Path, *, label: str, maximum_bytes: int, required_mode: int | None = None
) -> bytes:
    payload, _identity = _read_owned_regular_with_identity(
        path,
        label=label,
        maximum_bytes=maximum_bytes,
        required_mode=required_mode,
    )
    return payload


def _read_password_file(
    path: Path, *, expected_identity: OwnedFileIdentity | None = None
) -> OwnedFileIdentity:
    payload, identity = _read_owned_regular_with_identity(
        path,
        label="SSH password file",
        maximum_bytes=MAX_PASSWORD_BYTES,
        required_mode=0o600,
    )
    password = payload[:-1] if payload.endswith(b"\n") else payload
    if not password or b"\n" in password or b"\r" in payload or b"\x00" in payload:
        raise DeploymentError(
            "SSH password file must contain exactly one nonempty password line"
        )
    if expected_identity is not None and identity != expected_identity:
        raise DeploymentError("SSH password file changed after execution preflight")
    return identity


def _descriptor_sha256(descriptor: int, *, expected_bytes: int) -> str:
    observed = os.fstat(descriptor)
    if observed.st_size != expected_bytes:
        raise DeploymentError("sealed DFU descriptor size changed")
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_bytes:
        chunk = os.pread(descriptor, min(1 << 20, expected_bytes - offset), offset)
        if not chunk:
            raise DeploymentError("sealed DFU descriptor was truncated")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _create_sealed_dfu_descriptor(
    options: DeploymentOptions, artifact: CandidateArtifact
) -> int:
    required_os = ("memfd_create", "MFD_CLOEXEC", "MFD_ALLOW_SEALING")
    if any(not hasattr(os, name) for name in required_os):
        raise DeploymentError("this host cannot create a sealed DFU descriptor")
    payload = _read_owned_regular(
        artifact.dfu_path,
        label="requested DFU for sealed execution",
        maximum_bytes=MAX_DFU_BYTES,
    )
    if (
        len(payload) != artifact.dfu_bytes
        or _sha256_bytes(payload) != artifact.dfu_sha256
        or artifact.dfu_sha256 != options.artifact_sha256
        or _sha256_bytes(payload[: artifact.fit_bytes]) != artifact.fit_sha256
    ):
        raise DeploymentError("DFU/FIT changed before sealed execution")
    descriptor = os.memfd_create(
        "plutosdr-fw-tandem-candidate",
        os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
    )
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise DeploymentError("could not populate sealed DFU descriptor")
            offset += written
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        fcntl.fcntl(descriptor, F_ADD_SEALS, REQUIRED_DFU_SEALS)
        if fcntl.fcntl(descriptor, F_GET_SEALS) != REQUIRED_DFU_SEALS:
            raise DeploymentError("DFU descriptor seal inventory is not exact")
        if (
            _descriptor_sha256(descriptor, expected_bytes=artifact.dfu_bytes)
            != artifact.dfu_sha256
        ):
            raise DeploymentError("sealed DFU descriptor hash is not exact")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _hash_owned_regular(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    expected_bytes: int | None = None,
    prefix_bytes: int | None = None,
) -> tuple[int, str, str | None]:
    path = _canonical_absolute(path, label=label)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) & 0o022
    ):
        raise DeploymentError(
            f"{label} must be an owned regular file that is not group/world writable"
        )
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise DeploymentError(f"{label} size is outside the accepted bounds")
    if expected_bytes is not None and before.st_size != expected_bytes:
        raise DeploymentError(f"{label} size differs from the artifact index")
    if prefix_bytes is not None and not 0 < prefix_bytes <= before.st_size:
        raise DeploymentError(f"{label} prefix size is outside the file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise DeploymentError(f"{label} changed while it was opened")
        whole = hashlib.sha256()
        prefix = hashlib.sha256() if prefix_bytes is not None else None
        remaining_prefix = prefix_bytes or 0
        observed_bytes = 0
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            whole.update(chunk)
            observed_bytes += len(chunk)
            if prefix is not None and remaining_prefix:
                selected = chunk[:remaining_prefix]
                prefix.update(selected)
                remaining_prefix -= len(selected)
        after = os.fstat(descriptor)
        if (
            observed_bytes != opened.st_size
            or remaining_prefix != 0
            or (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            )
        ):
            raise DeploymentError(f"{label} changed while it was hashed")
        return (
            observed_bytes,
            whole.hexdigest(),
            prefix.hexdigest() if prefix is not None else None,
        )
    finally:
        os.close(descriptor)


def _required_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise DeploymentError(f"{label} must be an object")
    return value


def _required_string(value: Any, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or any(character in value for character in "\x00\r\n")
    ):
        raise DeploymentError(f"{label} must be one exact nonempty string")
    return value


def _required_positive_int(value: Any, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise DeploymentError(f"{label} must be a positive integer")
    return value


def _required_sha(value: Any, *, label: str) -> str:
    text = _required_string(value, label=label)
    if HEX_64.fullmatch(text) is None:
        raise DeploymentError(f"{label} must be lowercase SHA-256")
    return text


def _resolve_index_member(index_path: Path, value: Any, *, label: str) -> Path:
    text = _required_string(value, label=label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise DeploymentError(f"{label} must be a canonical relative archive path")
    root = index_path.parent
    candidate = root.joinpath(*relative.parts)
    resolved = _canonical_absolute(candidate, label=label)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise DeploymentError(f"{label} escapes the evidence archive") from error
    return resolved


def load_candidate_artifact(options: DeploymentOptions) -> CandidateArtifact:
    index_path = _canonical_absolute(
        options.artifact_index_path, label="artifact index"
    )
    index_payload = _read_owned_regular(
        index_path, label="artifact index", maximum_bytes=MAX_JSON_BYTES
    )
    index_sha = _sha256_bytes(index_payload)
    if index_sha != options.artifact_index_sha256:
        raise DeploymentError("artifact index SHA-256 differs from the requested value")
    value = _parse_json(index_payload, label="artifact index")
    try:
        index = validate_artifact_index(value)
    except CandidateBindingError as error:
        raise DeploymentError(
            f"artifact index semantics are invalid: {error}"
        ) from error
    try:
        semantic_index = verify_artifact_index_semantics(
            index_path, expected_stage=str(index["stage"])
        )
    except (EvidenceError, OSError) as error:
        raise DeploymentError(
            f"candidate release evidence is not authorizing: {error}"
        ) from error
    if semantic_index != index:
        raise DeploymentError(
            "semantic release verifier returned a different artifact index"
        )

    release = _required_mapping(index.get("release"), label="artifact index release")
    source = _required_mapping(index.get("source"), label="artifact index source")
    build = _required_mapping(index.get("build"), label="artifact index build")
    artifact = _required_mapping(index.get("artifact"), label="artifact index artifact")
    firmware = _required_string(
        release.get("firmware_version"), label="release firmware version"
    )
    hardware_model = _required_string(
        release.get("hardware_model"), label="release hardware model"
    )
    if hardware_model != PLUTOPLUS_HARDWARE_MODEL:
        raise DeploymentError(
            "candidate hardware model is not the exact supported Pluto+ class"
        )
    commit = _required_string(source.get("commit"), label="source commit")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise DeploymentError("source commit must be a full lowercase commit")
    manifest_path = _resolve_index_member(
        index_path, source.get("manifest_path"), label="source manifest path"
    )
    manifest_sha = _required_sha(
        source.get("manifest_sha256"), label="source manifest SHA-256"
    )
    manifest_payload = _read_owned_regular(
        manifest_path, label="source manifest", maximum_bytes=MAX_JSON_BYTES
    )
    if _sha256_bytes(manifest_payload) != manifest_sha:
        raise DeploymentError("source manifest content differs from the artifact index")

    dfu_path = _resolve_index_member(
        index_path, artifact.get("dfu_path"), label="DFU archive path"
    )
    requested_dfu = _canonical_absolute(options.artifact_path, label="requested DFU")
    if requested_dfu != dfu_path:
        raise DeploymentError("requested DFU path differs from the artifact index")
    if requested_dfu.suffix != ".dfu" or requested_dfu.name in {
        "boot.dfu",
        "uboot-env.dfu",
    }:
        raise DeploymentError("only a firmware .dfu image may be RAM deployed")
    dfu_payload = _read_owned_regular(
        requested_dfu, label="requested DFU", maximum_bytes=MAX_DFU_BYTES
    )
    dfu_bytes = _required_positive_int(artifact.get("dfu_bytes"), label="DFU bytes")
    dfu_sha = _required_sha(artifact.get("dfu_sha256"), label="DFU SHA-256")
    fit_bytes = _required_positive_int(artifact.get("fit_bytes"), label="FIT bytes")
    fit_sha = _required_sha(artifact.get("fit_sha256"), label="FIT SHA-256")
    if len(dfu_payload) != dfu_bytes or dfu_bytes != fit_bytes + 16:
        raise DeploymentError(
            "DFU/FIT sizes do not describe one 16-byte-suffixed image"
        )
    if _sha256_bytes(dfu_payload) != dfu_sha or dfu_sha != options.artifact_sha256:
        raise DeploymentError("DFU SHA-256 differs from the index or requested value")
    if _sha256_bytes(dfu_payload[:fit_bytes]) != fit_sha:
        raise DeploymentError("FIT body SHA-256 differs from the artifact index")

    evidence = _required_mapping(index.get("evidence"), label="artifact index evidence")
    members = evidence.get("members")
    if type(members) is not list:
        raise DeploymentError("artifact index evidence members must be a list")
    evidence_roles = tuple(
        _required_string(
            _required_mapping(item, label=f"evidence member {position}").get("role"),
            label=f"evidence member {position} role",
        )
        for position, item in enumerate(members)
    )
    if evidence_roles != REQUIRED_EVIDENCE_ROLES:
        raise DeploymentError("artifact index evidence role inventory is not exact")

    candidate = CandidateArtifact(
        index=index,
        index_path=index_path,
        index_sha256=index_sha,
        firmware_version=firmware,
        hardware_model=hardware_model,
        source_commit=commit,
        source_manifest_path=manifest_path,
        source_manifest_sha256=manifest_sha,
        build_run_id=_required_positive_int(build.get("run_id"), label="build run ID"),
        build_run_attempt=_required_positive_int(
            build.get("run_attempt"), label="build run attempt"
        ),
        dfu_path=requested_dfu,
        dfu_bytes=dfu_bytes,
        dfu_sha256=dfu_sha,
        fit_bytes=fit_bytes,
        fit_sha256=fit_sha,
        evidence_roles=evidence_roles,
    )
    attest_candidate_inputs(options, candidate)
    return candidate


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeploymentError(f"git provenance command failed: {arguments}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DeploymentError(
            f"git provenance command failed: {arguments}: {detail[:512]}"
        )
    if len(completed.stdout) > MAX_HARNESS_BYTES:
        raise DeploymentError("git provenance output exceeds the accepted bound")
    return completed.stdout


def _verify_runner_provenance_at(
    repository: Path,
    *,
    index_path: Path,
    index: Mapping[str, Any],
) -> dict[str, Any]:
    repository = _canonical_absolute(repository, label="runner repository")
    if not repository.is_dir():
        raise DeploymentError("runner repository is not a directory")
    source = _required_mapping(index.get("source"), label="artifact index source")
    commit = _required_string(source.get("commit"), label="source commit")
    top = _git_bytes(repository, "rev-parse", "--show-toplevel").decode().strip()
    if Path(top).resolve() != repository:
        raise DeploymentError("runner repository is not the exact Git worktree root")

    def require_clean_head() -> None:
        head = _git_bytes(repository, "rev-parse", "--verify", "HEAD^{commit}")
        if head.decode().strip() != commit:
            raise DeploymentError("runner HEAD differs from artifact source commit")
        status = _git_bytes(
            repository,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        if status:
            raise DeploymentError("runner repository is not completely clean")

    require_clean_head()
    harness = _required_mapping(index.get("harness"), label="artifact index harness")
    files = harness.get("files")
    if type(files) is not list:
        raise DeploymentError("artifact index harness files must be a list")
    indexed = {
        _required_string(item.get("path"), label="harness path"): _required_sha(
            item.get("sha256"), label="harness SHA-256"
        )
        for item in (_required_mapping(raw, label="harness file") for raw in files)
    }
    missing = set(DEPLOYER_HARNESS_PATHS) - set(indexed)
    if missing:
        raise DeploymentError(
            f"artifact index omits deployer harness paths: {sorted(missing)}"
        )

    verified: list[dict[str, str]] = []
    for relative in DEPLOYER_HARNESS_PATHS:
        live_path = repository.joinpath(*PurePosixPath(relative).parts)
        live_path = _canonical_absolute(live_path, label=f"live harness {relative}")
        try:
            live_path.relative_to(repository)
        except ValueError as error:
            raise DeploymentError("live harness path escapes the repository") from error
        live_payload = _read_owned_regular(
            live_path,
            label=f"live harness {relative}",
            maximum_bytes=MAX_HARNESS_BYTES,
        )
        archive_path = _resolve_index_member(
            index_path, relative, label=f"archived harness {relative}"
        )
        archive_payload = _read_owned_regular(
            archive_path,
            label=f"archived harness {relative}",
            maximum_bytes=MAX_HARNESS_BYTES,
        )
        committed_payload = _git_bytes(repository, "show", f"{commit}:{relative}")
        digest = _sha256_bytes(live_payload)
        if (
            not live_payload
            or live_payload != archive_payload
            or live_payload != committed_payload
            or digest != indexed[relative]
        ):
            raise DeploymentError(
                f"live/committed/indexed deployer harness differs: {relative}"
            )
        verified.append({"path": relative, "sha256": digest})
    require_clean_head()
    return {
        "repository": str(repository),
        "commit": commit,
        "clean": True,
        "files": verified,
    }


def _verify_runner_provenance(
    *, index_path: Path, index: Mapping[str, Any]
) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[2]
    expected_module = repository / "tests/radio_hardware/tandem_ram_deploy.py"
    if expected_module != Path(__file__).resolve():
        raise DeploymentError("running deployer module is outside the repository")
    expected_binding = repository / "tests/radio_hardware/candidate_binding.py"
    if Path(validate_artifact_index.__code__.co_filename).resolve() != expected_binding:
        raise DeploymentError("running candidate validator is outside the repository")
    expected_semantic = repository / "scripts/tandem_release_evidence.py"
    if (
        Path(verify_artifact_index_semantics.__code__.co_filename).resolve()
        != expected_semantic
    ):
        raise DeploymentError(
            "running semantic evidence verifier is outside the repository"
        )
    return _verify_runner_provenance_at(
        repository,
        index_path=index_path,
        index=index,
    )


def attest_candidate_inputs(
    options: DeploymentOptions, artifact: CandidateArtifact
) -> dict[str, Any]:
    index_payload = _read_owned_regular(
        artifact.index_path,
        label="artifact index",
        maximum_bytes=MAX_JSON_BYTES,
    )
    if _sha256_bytes(index_payload) != artifact.index_sha256:
        raise DeploymentError("artifact index changed after initial validation")
    try:
        index = validate_artifact_index(
            _parse_json(index_payload, label="artifact index")
        )
    except CandidateBindingError as error:
        raise DeploymentError(f"artifact index changed semantics: {error}") from error
    if (
        index != artifact.index
        or artifact.index_sha256 != options.artifact_index_sha256
    ):
        raise DeploymentError(
            "artifact index identity changed after initial validation"
        )

    provenance = _verify_runner_provenance(index_path=artifact.index_path, index=index)
    seen_paths = {artifact.index_path.name}
    source = _required_mapping(index.get("source"), label="artifact index source")
    manifest_relative = _required_string(
        source.get("manifest_path"), label="source manifest path"
    )
    manifest_path = _resolve_index_member(
        artifact.index_path, manifest_relative, label="source manifest"
    )
    if (
        manifest_relative in seen_paths
        or manifest_path != artifact.source_manifest_path
    ):
        raise DeploymentError("source manifest aliases another candidate member")
    seen_paths.add(manifest_relative)
    _manifest_bytes, manifest_sha, _prefix = _hash_owned_regular(
        manifest_path,
        label="source manifest",
        maximum_bytes=MAX_JSON_BYTES,
    )
    if manifest_sha != artifact.source_manifest_sha256:
        raise DeploymentError("source manifest changed after initial validation")

    artifact_record = _required_mapping(
        index.get("artifact"), label="artifact index payload"
    )
    dfu_relative = _required_string(artifact_record.get("dfu_path"), label="DFU path")
    dfu_path = _resolve_index_member(
        artifact.index_path, dfu_relative, label="requested DFU"
    )
    if dfu_relative in seen_paths or dfu_path != artifact.dfu_path:
        raise DeploymentError("DFU aliases another candidate member")
    seen_paths.add(dfu_relative)
    dfu_bytes, dfu_sha, fit_sha = _hash_owned_regular(
        dfu_path,
        label="requested DFU",
        maximum_bytes=MAX_DFU_BYTES,
        expected_bytes=artifact.dfu_bytes,
        prefix_bytes=artifact.fit_bytes,
    )
    if (
        dfu_bytes != artifact.dfu_bytes
        or dfu_sha != artifact.dfu_sha256
        or fit_sha != artifact.fit_sha256
        or dfu_sha != options.artifact_sha256
    ):
        raise DeploymentError("DFU/FIT changed after initial validation")

    harness = _required_mapping(index.get("harness"), label="artifact index harness")
    harness_files = harness.get("files")
    if type(harness_files) is not list:
        raise DeploymentError("artifact index harness files must be a list")
    for position, raw in enumerate(harness_files):
        entry = _required_mapping(raw, label=f"harness file {position}")
        relative = _required_string(
            entry.get("path"), label=f"harness file {position} path"
        )
        if relative in seen_paths:
            raise DeploymentError("candidate archive aliases a harness member")
        seen_paths.add(relative)
        path = _resolve_index_member(
            artifact.index_path, relative, label=f"harness file {position}"
        )
        _size, digest, _prefix = _hash_owned_regular(
            path,
            label=f"harness file {position}",
            maximum_bytes=MAX_HARNESS_BYTES,
        )
        if digest != entry.get("sha256"):
            raise DeploymentError(f"harness file changed: {relative}")

    evidence = _required_mapping(index.get("evidence"), label="artifact index evidence")
    members = evidence.get("members")
    if type(members) is not list:
        raise DeploymentError("artifact index evidence members must be a list")
    verified_evidence: list[dict[str, Any]] = []
    for position, raw in enumerate(members):
        member = _required_mapping(raw, label=f"evidence member {position}")
        role = _required_string(
            member.get("role"), label=f"evidence member {position} role"
        )
        relative = _required_string(
            member.get("path"), label=f"evidence member {position} path"
        )
        if relative in seen_paths:
            raise DeploymentError("candidate archive aliases an evidence member")
        seen_paths.add(relative)
        expected_bytes = _required_positive_int(
            member.get("bytes"), label=f"evidence member {position} bytes"
        )
        path = _resolve_index_member(
            artifact.index_path, relative, label=f"evidence role {role}"
        )
        size, digest, _prefix = _hash_owned_regular(
            path,
            label=f"evidence role {role}",
            maximum_bytes=MAX_EVIDENCE_BYTES,
            expected_bytes=expected_bytes,
        )
        if digest != member.get("sha256"):
            raise DeploymentError(f"evidence member changed: {role}")
        verified_evidence.append({"role": role, "bytes": size, "sha256": digest})
    return {
        "artifact_index_sha256": artifact.index_sha256,
        "dfu_sha256": artifact.dfu_sha256,
        "runner_provenance": provenance,
        "evidence": verified_evidence,
    }


def load_inventory(path: Path) -> tuple[UsbDevice, ...]:
    payload = _read_owned_regular(
        path, label="USB inventory", maximum_bytes=MAX_JSON_BYTES
    )
    document = _required_mapping(
        _parse_json(payload, label="USB inventory"), label="USB inventory"
    )
    if set(document) != {"schema", "schema_version", "devices"}:
        raise DeploymentError("USB inventory keys are not exact")
    if (
        document.get("schema") != USB_INVENTORY_SCHEMA
        or type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
    ):
        raise DeploymentError("USB inventory schema is unsupported")
    values = document.get("devices")
    if type(values) is not list:
        raise DeploymentError("USB inventory devices must be a list")
    devices: list[UsbDevice] = []
    for position, value in enumerate(values):
        item = _required_mapping(value, label=f"USB inventory device {position}")
        expected_keys = {
            "topology",
            "sysfs_path",
            "serial",
            "vendor_id",
            "product_id",
            "busnum",
            "devnum",
            "network_interfaces",
        }
        if set(item) != expected_keys:
            raise DeploymentError(f"USB inventory device {position} keys are not exact")
        interfaces = item.get("network_interfaces", [])
        if type(interfaces) is not list or any(
            type(entry) is not str or SAFE_INTERFACE.fullmatch(entry) is None
            for entry in interfaces
        ):
            raise DeploymentError("USB inventory network interfaces are malformed")
        topology = _required_string(item.get("topology"), label="USB topology")
        sysfs_path = _required_string(item.get("sysfs_path"), label="USB sysfs path")
        serial = _required_string(item.get("serial"), label="USB serial")
        vendor_id = _required_string(item.get("vendor_id"), label="USB vendor").lower()
        product_id = _required_string(
            item.get("product_id"), label="USB product"
        ).lower()
        if (
            TOPOLOGY.fullmatch(topology) is None
            or sysfs_path != f"/sys/bus/usb/devices/{topology}"
            or SAFE_SERIAL.fullmatch(serial) is None
            or re.fullmatch(r"[0-9a-f]{4}", vendor_id) is None
            or re.fullmatch(r"[0-9a-f]{4}", product_id) is None
            or len(interfaces) != len(set(interfaces))
        ):
            raise DeploymentError(
                f"USB inventory device {position} identity is malformed"
            )
        devices.append(
            UsbDevice(
                topology=topology,
                sysfs_path=sysfs_path,
                serial=serial,
                vendor_id=vendor_id,
                product_id=product_id,
                busnum=_required_positive_int(
                    item.get("busnum"), label="USB bus number"
                ),
                devnum=_required_positive_int(
                    item.get("devnum"), label="USB device number"
                ),
                network_interfaces=tuple(interfaces),
            )
        )
    return tuple(devices)


def resolve_device(
    devices: Sequence[UsbDevice],
    *,
    serial: str,
    product_id: str,
    topology: str | None = None,
) -> UsbDevice:
    matches = [
        device
        for device in devices
        if device.vendor_id == USB_VENDOR
        and device.product_id == product_id
        and device.serial == serial
        and (topology is None or device.topology == topology)
    ]
    if len(matches) != 1:
        raise DeploymentError(
            f"expected exactly one {USB_VENDOR}:{product_id} USB device for serial "
            f"{serial!r}; found {[device.topology for device in matches]}"
        )
    device = matches[0]
    if (
        TOPOLOGY.fullmatch(device.topology) is None
        or device.sysfs_path != f"/sys/bus/usb/devices/{device.topology}"
        or device.busnum <= 0
        or device.devnum <= 0
    ):
        raise DeploymentError("resolved USB identity is not one stable Linux port path")
    return device


def resolve_dfu_device(
    devices: Sequence[UsbDevice], *, serial: str, topology: str
) -> UsbDevice:
    """Resolve the pre-bound Pluto DFU port, tolerating an omitted serial only."""

    matches = [
        device
        for device in devices
        if device.vendor_id == USB_VENDOR
        and device.product_id == DFU_PRODUCT
        and device.topology == topology
    ]
    if len(matches) != 1:
        raise DeploymentError(
            f"expected exactly one {USB_VENDOR}:{DFU_PRODUCT} USB device on "
            f"pre-bound topology {topology!r}; found "
            f"{[(device.topology, device.serial) for device in matches]}"
        )
    device = matches[0]
    if (
        TOPOLOGY.fullmatch(device.topology) is None
        or device.sysfs_path != f"/sys/bus/usb/devices/{device.topology}"
        or device.busnum <= 0
        or device.devnum <= 0
    ):
        raise DeploymentError("resolved USB identity is not one stable Linux port path")
    if device.serial and device.serial != serial:
        raise DeploymentError("DFU USB serial differs from the pre-attested radio")
    return device


def select_interface(device: UsbDevice, requested: str | None) -> str:
    interfaces = tuple(sorted(set(device.network_interfaces)))
    if requested is not None:
        if SAFE_INTERFACE.fullmatch(requested) is None or requested not in interfaces:
            raise DeploymentError(
                "requested USB network interface is not on the exact radio"
            )
        return requested
    if len(interfaces) != 1:
        raise DeploymentError(
            f"expected one network interface on {device.topology}; found {list(interfaces)}"
        )
    if SAFE_INTERFACE.fullmatch(interfaces[0]) is None:
        raise DeploymentError(
            "resolved USB network interface contains unsafe characters"
        )
    return interfaces[0]


def _ssh_base_argv(options: DeploymentOptions, interface: str) -> list[str]:
    if options.ssh_password_file is None:
        raise DeploymentError("SSH password file is required for an executable plan")
    return [
        "sshpass",
        "-f",
        str(options.ssh_password_file),
        "ssh",
        "-F",
        "/dev/null",
        "-B",
        interface,
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


def _request_ram_argv(options: DeploymentOptions, interface: str) -> list[str]:
    return [
        *_ssh_base_argv(options, interface),
        f"{options.ssh_user}@{options.ssh_host}",
        "/usr/sbin/device_reboot ram",
    ]


def build_command_plan(
    options: DeploymentOptions,
    device: UsbDevice,
    interface: str,
    *,
    download_path: Path | None = None,
) -> tuple[dict[str, Any], ...]:
    selected_download = (
        options.artifact_path if download_path is None else download_path
    )
    request = _request_ram_argv(options, interface)
    selector = [
        "-d",
        DFU_DEVICE_SELECTOR,
        "-p",
        device.topology,
        "-a",
        DFU_ALT,
    ]
    plan = (
        {"phase": "request-ram-mode", "argv": request},
        {
            "phase": "download-firmware-to-ram",
            "argv": ["dfu-util", *selector, "-D", str(selected_download)],
        },
        {
            "phase": "detach-into-downloaded-image",
            "argv": ["dfu-util", *selector, "-e"],
        },
    )
    validate_command_plan(
        plan,
        options=options,
        artifact=selected_download,
        topology=device.topology,
        interface=interface,
    )
    return plan


def validate_command_plan(
    plan: Sequence[Mapping[str, Any]],
    *,
    options: DeploymentOptions,
    artifact: Path,
    topology: str,
    interface: str,
) -> None:
    if len(plan) != 3:
        raise DeploymentError("RAM deployment plan must contain exactly three commands")
    commands: list[list[str]] = []
    expected_phases = (
        "request-ram-mode",
        "download-firmware-to-ram",
        "detach-into-downloaded-image",
    )
    for position, (item, phase) in enumerate(zip(plan, expected_phases, strict=True)):
        if set(item) != {"phase", "argv"} or item.get("phase") != phase:
            raise DeploymentError(
                f"RAM deployment command {position} phase/keys are not exact"
            )
        argv = item.get("argv")
        if (
            type(argv) is not list
            or not argv
            or any(
                type(token) is not str
                or not token
                or token.strip() != token
                or any(character in token for character in "\x00\r\n")
                for token in argv
            )
        ):
            raise DeploymentError("RAM deployment command argv is malformed")
        commands.append(argv)
    flattened = [token for command in commands for token in command]
    if any(
        token in {"-R", "--reset"}
        or token.lower().endswith((".frm", ".zip"))
        or token.lower() in {"qspi", "flash", "bootloader", "boot.dfu", "uboot-env.dfu"}
        or token.lower().startswith(("/dev/mtd", "/dev/mtdblock"))
        for token in flattened
    ):
        raise DeploymentError(
            "RAM deployment plan contains a persistent or unsafe target"
        )
    download, detach = commands[1], commands[2]
    expected_prefix = [
        "dfu-util",
        "-d",
        DFU_DEVICE_SELECTOR,
        "-p",
        topology,
        "-a",
        DFU_ALT,
    ]
    if (
        commands[0] != _request_ram_argv(options, interface)
        or download != [*expected_prefix, "-D", str(artifact)]
        or detach != [*expected_prefix, "-e"]
    ):
        raise DeploymentError(
            "DFU commands differ from the only authorized RAM sequence"
        )


def _receipt_output_path(path: Path, *, serial: str, archive_root: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise DeploymentError("receipt path must be absolute and normalized")
    parent = _canonical_absolute(path.parent, label="receipt parent")
    candidate = parent / path.name
    try:
        candidate.relative_to(archive_root)
    except ValueError as error:
        raise DeploymentError(
            "receipt path must be inside the artifact-index archive"
        ) from error
    if serial not in candidate.parts:
        raise DeploymentError("receipt path must be scoped to the exact serial")
    if candidate != path or path.exists() or path.is_symlink():
        raise DeploymentError(
            "receipt path must be absent, canonical, and nonsymlinked"
        )
    return candidate


def _publish_receipt(
    path: Path, receipt: Mapping[str, Any], *, archive_root: Path
) -> str:
    radio = _required_mapping(receipt.get("radio"), label="receipt radio")
    serial = _required_string(radio.get("serial"), label="receipt radio serial")
    path = _receipt_output_path(path, serial=serial, archive_root=archive_root)
    payload = (
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise DeploymentError("receipt write made no progress")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    observed = _read_owned_regular(
        path,
        label="published receipt",
        maximum_bytes=MAX_JSON_BYTES,
        required_mode=0o600,
    )
    if observed != payload:
        raise DeploymentError(
            "published receipt bytes changed after atomic publication"
        )
    return _sha256_bytes(payload)


def _open_radio_lock(serial: str) -> Any:
    path = Path(f"/tmp/plutosdr-fw-radio-{serial}.lock")
    flags = (
        os.O_CREAT
        | os.O_RDWR
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise DeploymentError(
            f"exact-radio lock cannot be opened safely: {path}"
        ) from error
    try:
        info = os.fstat(descriptor)
        path_info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
        ):
            raise DeploymentError("exact-radio lock is not an owned regular file")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.fchmod(descriptor, 0o600)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
                raise DeploymentError("exact-radio lock mode is not 0600")
        lock = os.fdopen(descriptor, "r+", encoding="utf-8")
        descriptor = -1
        return lock
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_host_route_lock(host: str) -> Any:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise DeploymentError(
            "host-route lock requires a literal IP address"
        ) from error
    if address.version != 4:
        raise DeploymentError("host-route lock requires a literal IPv4 address")
    path = Path(f"/tmp/plutosdr-fw-host-route-{str(address).replace('.', '_')}.lock")
    flags = (
        os.O_CREAT
        | os.O_RDWR
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise DeploymentError(
            f"global host-route lock cannot be opened safely: {path}"
        ) from error
    try:
        info = os.fstat(descriptor)
        path_info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
        ):
            raise DeploymentError("global host-route lock is not an owned regular file")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.fchmod(descriptor, 0o600)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
                raise DeploymentError("global host-route lock mode is not 0600")
        lock = os.fdopen(descriptor, "r+", encoding="utf-8")
        descriptor = -1
        return lock
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _attestation_is_safe(value: RuntimeAttestation) -> bool:
    return bool(
        value.tx_muted
        and value.dds_disabled
        and value.dac_selectors_zero
        and value.tandem_state == "IDLE"
        and value.fifo_level == 0
        and value.fault_flags == 0
    )


def execute_deployment(
    options: DeploymentOptions, backend: HardwareBackend
) -> tuple[dict[str, Any], str]:
    artifact = load_candidate_artifact(options)
    if options.operator_confirmation != f"RAM BOOT {options.serial}":
        raise DeploymentError("operator confirmation must be exactly RAM BOOT <serial>")
    if options.ssh_password_file is None:
        raise DeploymentError("SSH password file is required for execution")
    _read_password_file(options.ssh_password_file)
    try:
        options.ssh_password_file.relative_to(artifact.index_path.parent)
    except ValueError:
        pass
    else:
        raise DeploymentError(
            "SSH password file must be outside the candidate evidence archive"
        )
    _receipt_output_path(
        options.receipt_path,
        serial=options.serial,
        archive_root=artifact.index_path.parent,
    )

    with (
        _open_radio_lock(options.serial) as lock,
        _open_host_route_lock(options.ssh_host) as route_lock,
    ):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DeploymentError(
                "another process owns the exact radio lock"
            ) from error
        locked_info = os.fstat(lock.fileno())
        locked_path_info = Path(f"/tmp/plutosdr-fw-radio-{options.serial}.lock").lstat()
        if (locked_info.st_dev, locked_info.st_ino) != (
            locked_path_info.st_dev,
            locked_path_info.st_ino,
        ):
            raise DeploymentError("exact-radio lock path changed during acquisition")
        try:
            fcntl.flock(route_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DeploymentError(
                "another deployment owns the global SSH host-route lease"
            ) from error
        route_lock_info = os.fstat(route_lock.fileno())
        route_lock_path = Path(
            f"/tmp/plutosdr-fw-host-route-{options.ssh_host.replace('.', '_')}.lock"
        ).lstat()
        if (route_lock_info.st_dev, route_lock_info.st_ino) != (
            route_lock_path.st_dev,
            route_lock_path.st_ino,
        ):
            raise DeploymentError(
                "global host-route lock path changed during acquisition"
            )
        device = resolve_device(
            backend.inventory(), serial=options.serial, product_id=RUNTIME_PRODUCT
        )
        interface = select_interface(device, options.usb_interface)
        sealed_dfu = _create_sealed_dfu_descriptor(options, artifact)
        try:
            commands = build_command_plan(
                options,
                device,
                interface,
                download_path=Path(f"/proc/self/fd/{sealed_dfu}"),
            )
            lock.seek(0)
            lock.truncate()
            lock.write(
                f"pid={os.getpid()} suite=tandem-ram-deploy "
                f"topology={device.topology}\n"
            )
            lock.flush()
        except BaseException:
            os.close(sealed_dfu)
            raise

        try:
            route = backend.acquire_host_route(
                interface=interface, host=options.ssh_host
            )
            started = time.time_ns()
            transition_started = False
            receipt: dict[str, Any] | None = None
            operation_error: BaseException | None = None
            try:
                try:
                    pre = backend.attest_runtime(
                        device,
                        interface=interface,
                        expected_firmware=options.expected_current_firmware,
                        force_safe=True,
                    )
                    if (
                        pre.serial != options.serial
                        or pre.hardware_model != artifact.hardware_model
                        or pre.firmware_version != options.expected_current_firmware
                        or not pre.boot_id
                        or not _attestation_is_safe(pre)
                    ):
                        raise DeploymentError(
                            "pre-reboot runtime identity/state is not fail-closed"
                        )
                    attest_candidate_inputs(options, artifact)
                    transition_started = True
                    backend.request_ram_mode(commands[0]["argv"])
                    dfu_device = backend.wait_for_mode(
                        serial=options.serial,
                        topology=device.topology,
                        product_id=DFU_PRODUCT,
                        timeout_seconds=options.timeout_seconds,
                    )
                    resolve_dfu_device(
                        (dfu_device,),
                        serial=options.serial,
                        topology=device.topology,
                    )
                    backend.run_dfu(commands[1]["argv"])
                    backend.run_dfu(commands[2]["argv"])
                    returned = backend.wait_for_mode(
                        serial=options.serial,
                        topology=device.topology,
                        product_id=RUNTIME_PRODUCT,
                        timeout_seconds=options.timeout_seconds,
                    )
                    resolve_device(
                        (returned,),
                        serial=options.serial,
                        product_id=RUNTIME_PRODUCT,
                        topology=device.topology,
                    )
                    returned_interface = select_interface(
                        returned, options.usb_interface
                    )
                    backend.ensure_host_route(route, interface=returned_interface)
                    post = backend.attest_runtime(
                        returned,
                        interface=returned_interface,
                        expected_firmware=artifact.firmware_version,
                        force_safe=True,
                    )
                    if pre.boot_id == post.boot_id:
                        raise DeploymentError(
                            "RAM deployment did not produce a new boot ID"
                        )
                    if (
                        post.serial != options.serial
                        or post.hardware_model != artifact.hardware_model
                        or post.firmware_version != artifact.firmware_version
                        or not _attestation_is_safe(post)
                    ):
                        raise DeploymentError(
                            "returned runtime identity or safety state is invalid"
                        )
                    if (
                        pre.qspi_partition != "/dev/mtdblock3"
                        or post.qspi_partition != pre.qspi_partition
                        or pre.qspi_mtd_name != "qspi-linux"
                        or post.qspi_mtd_name != pre.qspi_mtd_name
                        or pre.qspi_bytes <= 0
                        or post.qspi_bytes != pre.qspi_bytes
                        or HEX_64.fullmatch(pre.qspi_sha256) is None
                        or post.qspi_sha256 != pre.qspi_sha256
                    ):
                        raise DeploymentError(
                            "RAM deployment did not prove unchanged qspi-linux firmware bytes"
                        )

                    receipt = {
                        "schema": RECEIPT_SCHEMA,
                        "schema_version": RAM_BOOT_RECEIPT_SCHEMA_VERSION,
                        "verdict": "pass",
                        "boot_mode": "ram-only",
                        "radio": {"serial": options.serial},
                        "artifact_index_sha256": artifact.index_sha256,
                        "artifact": {"dfu_sha256": artifact.dfu_sha256},
                        "runtime": {
                            "firmware_version": post.firmware_version,
                            "hardware_model": post.hardware_model,
                        },
                        "boot": {"pre_id": pre.boot_id, "post_id": post.boot_id},
                        "persistent_flash": {
                            "partition": pre.qspi_partition,
                            "mtd_name": pre.qspi_mtd_name,
                            "bytes": pre.qspi_bytes,
                            "pre_sha256": pre.qspi_sha256,
                            "post_sha256": post.qspi_sha256,
                            "unchanged": True,
                        },
                        "safety": {
                            "final_tx_muted": post.tx_muted,
                            "final_dds_disabled": post.dds_disabled,
                            "final_dac_selectors_zero": post.dac_selectors_zero,
                            "final_tandem_state": post.tandem_state,
                            "final_fifo_level": post.fifo_level,
                            "final_fault_flags": post.fault_flags,
                        },
                        "timestamps": {
                            "started_unix_ns": started,
                            "completed_unix_ns": started,
                        },
                        "topology": {
                            "usb_port": device.topology,
                            "pre_sysfs_path": device.sysfs_path,
                            "dfu_sysfs_path": dfu_device.sysfs_path,
                            "post_sysfs_path": returned.sysfs_path,
                            "network_interface": returned_interface,
                        },
                        "host_route": {
                            "destination": route.destination,
                            "interface": route.interface,
                            "source": route.source,
                            "release_verified": False,
                        },
                        "commands": [
                            {"phase": item["phase"], "argv": list(item["argv"])}
                            for item in commands
                        ],
                    }
                except BaseException as primary:  # noqa: BLE001 - release route lease
                    if transition_started:
                        try:
                            cleanup_device = backend.wait_for_mode(
                                serial=options.serial,
                                topology=device.topology,
                                product_id=RUNTIME_PRODUCT,
                                timeout_seconds=options.timeout_seconds,
                            )
                            resolve_device(
                                (cleanup_device,),
                                serial=options.serial,
                                product_id=RUNTIME_PRODUCT,
                                topology=device.topology,
                            )
                            cleanup_interface = select_interface(
                                cleanup_device, options.usb_interface
                            )
                            backend.ensure_host_route(
                                route, interface=cleanup_interface
                            )
                            cleanup = backend.attest_runtime(
                                cleanup_device,
                                interface=cleanup_interface,
                                expected_firmware=artifact.firmware_version,
                                force_safe=True,
                            )
                            if (
                                cleanup.serial != options.serial
                                or cleanup.hardware_model != artifact.hardware_model
                                or not _attestation_is_safe(cleanup)
                            ):
                                raise DeploymentError(
                                    "failure cleanup did not prove safe state"
                                )
                        except BaseException as cleanup_error:  # noqa: BLE001
                            primary = DeploymentError(
                                f"deployment failed ({primary}); safe cleanup also "
                                f"failed ({cleanup_error})"
                            )
                    operation_error = primary
            finally:
                try:
                    backend.release_host_route(route)
                except BaseException as route_error:  # noqa: BLE001 - lease cleanup
                    if operation_error is None:
                        operation_error = DeploymentError(
                            f"host-route cleanup failed ({route_error})"
                        )
                    else:
                        operation_error = DeploymentError(
                            f"deployment failed ({operation_error}); host-route cleanup "
                            f"also failed ({route_error})"
                        )
            if operation_error is not None:
                raise operation_error
            if receipt is None:
                raise DeploymentError("deployment completed without a receipt record")
            receipt["host_route"]["release_verified"] = True
            receipt["timestamps"]["completed_unix_ns"] = time.time_ns()
            try:
                validate_deployment_receipt(
                    receipt,
                    artifact_index_sha256=artifact.index_sha256,
                    serial=options.serial,
                    firmware_version=artifact.firmware_version,
                    hardware_model=artifact.hardware_model,
                    dfu_sha256=artifact.dfu_sha256,
                )
            except CandidateBindingError as error:
                raise DeploymentError(
                    f"constructed receipt semantics are invalid: {error}"
                ) from error
            # Repeat every candidate and committed-runner binding after the
            # transition and verified route cleanup, immediately before publish.
            attest_candidate_inputs(options, artifact)
            digest = _publish_receipt(
                options.receipt_path,
                receipt,
                archive_root=artifact.index_path.parent,
            )
            return receipt, digest
        finally:
            os.close(sealed_dfu)


REMOTE_IDENTITY_SCRIPT = r"""set -eu
boot_id=$(cat /proc/sys/kernel/random/boot_id)
firmware_version=$(awk '$1 == "device-fw" {print $2; exit}' /opt/VERSIONS)
qspi_partition=/dev/mtdblock3
qspi_mtd_name=$(cat /sys/class/mtd/mtd3/name)
qspi_bytes=$(cat /sys/class/mtd/mtd3/size)
qspi_sha256=$(sha256sum "$qspi_partition" | awk '{print $1}')
[ -n "$boot_id" ]
[ -n "$firmware_version" ]
[ "$qspi_mtd_name" = qspi-linux ]
case "$qspi_bytes" in ''|*[!0-9]*) exit 1;; esac
[ "$qspi_bytes" -gt 0 ]
printf 'boot_id=%s\nfirmware_version=%s\nqspi_partition=%s\nqspi_mtd_name=%s\nqspi_bytes=%s\nqspi_sha256=%s\n' \
  "$boot_id" "$firmware_version" "$qspi_partition" "$qspi_mtd_name" \
  "$qspi_bytes" "$qspi_sha256"
"""


def _first_float(value: Any) -> float:
    return float(str(value).strip().split()[0])


def _iio_channel(device: Any, name: str, output: bool) -> Any:
    value = device.find_channel(name, output)
    if value is None:
        raise DeploymentError(
            f"{getattr(device, 'id', device)!r} lacks channel {name!r}"
        )
    return value


def _iio_read(owner: Any, name: str) -> str:
    if name not in owner.attrs:
        raise DeploymentError(f"{getattr(owner, 'id', owner)!r} lacks {name!r}")
    return str(owner.attrs[name].value)


def _iio_write_numeric(
    owner: Any, name: str, value: float, *, tolerance: float
) -> float:
    if name not in owner.attrs:
        raise DeploymentError(f"{getattr(owner, 'id', owner)!r} lacks {name!r}")
    owner.attrs[name].value = str(value)
    observed = _first_float(owner.attrs[name].value)
    if not math.isfinite(observed) or abs(observed - value) > tolerance:
        raise DeploymentError(
            f"{getattr(owner, 'id', owner)!r} {name} readback {observed} "
            f"differs from {value}"
        )
    return observed


class SystemBackend:
    def __init__(
        self,
        options: DeploymentOptions,
        *,
        sysfs_root: Path = Path("/sys/bus/usb/devices"),
    ):
        self.options = options
        self.sysfs_root = sysfs_root
        self._active_route: HostRoute | None = None
        self._password_identity = (
            _read_password_file(options.ssh_password_file)
            if options.ssh_password_file is not None
            else None
        )

    def _verify_ssh_password(self) -> None:
        if self.options.ssh_password_file is None or self._password_identity is None:
            raise DeploymentError("SSH password file is required for execution")
        _read_password_file(
            self.options.ssh_password_file,
            expected_identity=self._password_identity,
        )

    def inventory(self) -> tuple[UsbDevice, ...]:
        devices: list[UsbDevice] = []
        for entry in self.sysfs_root.iterdir():
            if TOPOLOGY.fullmatch(entry.name) is None:
                continue
            target = entry.resolve()
            try:
                vendor = (
                    (target / "idVendor").read_text(encoding="ascii").strip().lower()
                )
                product = (
                    (target / "idProduct").read_text(encoding="ascii").strip().lower()
                )
                busnum = int((target / "busnum").read_text(encoding="ascii"))
                devnum = int((target / "devnum").read_text(encoding="ascii"))
            except (FileNotFoundError, PermissionError, UnicodeError, ValueError):
                continue
            try:
                serial = (target / "serial").read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                if vendor != USB_VENDOR or product != DFU_PRODUCT:
                    continue
                serial = ""
            except (PermissionError, UnicodeError):
                continue
            if not serial and (vendor != USB_VENDOR or product != DFU_PRODUCT):
                continue
            interfaces: set[str] = set()
            for usb_interface in self.sysfs_root.glob(f"{entry.name}:*"):
                net = usb_interface.resolve() / "net"
                if net.is_dir():
                    interfaces.update(item.name for item in net.iterdir())
            devices.append(
                UsbDevice(
                    topology=entry.name,
                    sysfs_path=f"/sys/bus/usb/devices/{entry.name}",
                    serial=serial,
                    vendor_id=vendor,
                    product_id=product,
                    busnum=busnum,
                    devnum=devnum,
                    network_interfaces=tuple(sorted(interfaces)),
                )
            )
        return tuple(devices)

    def _ip_json(self, arguments: Sequence[str], *, label: str) -> list[Any]:
        try:
            completed = subprocess.run(
                ["ip", "-j", "-4", *arguments],
                check=True,
                text=True,
                capture_output=True,
                timeout=self.options.timeout_seconds,
            )
            value = json.loads(
                completed.stdout,
                object_pairs_hook=_json_no_duplicates,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    DeploymentError(f"{label} contains non-finite value {item}")
                ),
            )
        except (subprocess.SubprocessError, json.JSONDecodeError) as error:
            raise DeploymentError(f"{label} failed") from error
        if type(value) is not list:
            raise DeploymentError(f"{label} did not return a JSON array")
        return value

    def _interface_source(self, interface: str) -> str:
        if SAFE_INTERFACE.fullmatch(interface) is None:
            raise DeploymentError("host-route interface is malformed")
        records = self._ip_json(
            ["address", "show", "dev", interface, "scope", "global"],
            label="host-route source discovery",
        )
        sources: list[str] = []
        for record in records:
            if not isinstance(record, Mapping) or record.get("ifname") != interface:
                raise DeploymentError("host-route source interface is not exact")
            address_records = record.get("addr_info")
            if not isinstance(address_records, list):
                raise DeploymentError("host-route address inventory is malformed")
            for address_record in address_records:
                if (
                    isinstance(address_record, Mapping)
                    and address_record.get("family") == "inet"
                    and address_record.get("scope") == "global"
                ):
                    local = address_record.get("local")
                    try:
                        parsed = ipaddress.ip_address(str(local))
                    except ValueError as error:
                        raise DeploymentError(
                            "host-route source is not an IPv4 address"
                        ) from error
                    if parsed.version != 4:
                        raise DeploymentError("host-route source is not IPv4")
                    sources.append(str(parsed))
        if len(sources) != 1:
            raise DeploymentError(
                f"expected one global IPv4 source on {interface}; found {sources}"
            )
        return sources[0]

    def _exact_routes(self, destination: str) -> list[Any]:
        return self._ip_json(
            ["route", "show", "table", "all", "exact", destination],
            label="exact host-route inventory",
        )

    @staticmethod
    def _route_record_matches(record: object, route: HostRoute) -> bool:
        if not isinstance(record, Mapping):
            return False
        destination = str(record.get("dst", ""))
        if "/" not in destination:
            destination += "/32"
        try:
            normalized = str(ipaddress.ip_network(destination, strict=True))
        except ValueError:
            return False
        return bool(
            normalized == route.destination
            and record.get("dev") == route.interface
            and record.get("prefsrc") == route.source
            and record.get("scope") == "link"
            and record.get("protocol") == "static"
            and record.get("table", "main") in {"main", 254}
            and "gateway" not in record
            and "metric" not in record
        )

    def _verify_route_get(self, route: HostRoute) -> None:
        host = route.destination.rsplit("/", 1)[0]
        records = self._ip_json(
            ["route", "get", host], label="selected host-route lookup"
        )
        if (
            len(records) != 1
            or not isinstance(records[0], Mapping)
            or records[0].get("dev") != route.interface
            or records[0].get("prefsrc") != route.source
        ):
            raise DeploymentError(
                "selected SSH host route does not use the exact interface/source"
            )

    def _add_route(self, route: HostRoute) -> None:
        try:
            subprocess.run(
                [
                    "sudo",
                    "-n",
                    "ip",
                    "route",
                    "add",
                    route.destination,
                    "dev",
                    route.interface,
                    "src",
                    route.source,
                    "scope",
                    "link",
                    "proto",
                    "static",
                ],
                check=True,
                text=True,
                capture_output=True,
                timeout=self.options.timeout_seconds,
            )
        except subprocess.SubprocessError as error:
            raise DeploymentError("exact host-route add failed") from error

    def acquire_host_route(self, *, interface: str, host: str) -> HostRoute:
        if self._active_route is not None:
            raise DeploymentError("a host-route lease is already active")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as error:
            raise DeploymentError("SSH host is not an IP address") from error
        if address.version != 4:
            raise DeploymentError("SSH host is not IPv4")
        destination = f"{address}/32"
        if self._exact_routes(destination):
            raise DeploymentError(
                f"refusing to overwrite preexisting exact route {destination}"
            )
        route = HostRoute(
            destination=destination,
            interface=interface,
            source=self._interface_source(interface),
        )
        self._active_route = route
        try:
            self._add_route(route)
            self.ensure_host_route(route, interface=interface)
        except BaseException as primary:
            try:
                self.release_host_route(route)
            except BaseException as cleanup_error:  # noqa: BLE001 - route cleanup
                raise DeploymentError(
                    f"host-route acquisition failed ({primary}); cleanup also failed "
                    f"({cleanup_error})"
                ) from primary
            raise
        return route

    def ensure_host_route(self, route: HostRoute, *, interface: str) -> None:
        if self._active_route != route or interface != route.interface:
            raise DeploymentError("host-route lease/interface is not exact")
        deadline = time.monotonic() + self.options.timeout_seconds
        last_error: DeploymentError | None = None
        while time.monotonic() < deadline:
            try:
                if self._interface_source(interface) != route.source:
                    raise DeploymentError("host-route interface source changed")
                records = self._exact_routes(route.destination)
                if not records:
                    # USB DFU re-enumeration may remove the kernel route with the
                    # netdev. Re-add only the exact tuple owned by this lease.
                    self._add_route(route)
                    records = self._exact_routes(route.destination)
                if len(records) != 1 or not self._route_record_matches(
                    records[0], route
                ):
                    raise DeploymentError(
                        "exact host-route tuple differs from the active lease"
                    )
                self._verify_route_get(route)
                return
            except DeploymentError as error:
                last_error = error
                records = self._exact_routes(route.destination)
                if records and (
                    len(records) != 1
                    or not self._route_record_matches(records[0], route)
                ):
                    raise
                time.sleep(0.25)
        raise DeploymentError(
            f"timed out verifying exact host-route lease: {last_error}"
        )

    def release_host_route(self, route: HostRoute) -> None:
        if self._active_route != route:
            raise DeploymentError("host-route release does not match the active lease")
        records = self._exact_routes(route.destination)
        if records:
            if len(records) != 1 or not self._route_record_matches(records[0], route):
                raise DeploymentError(
                    "refusing to delete a host route not owned by this lease"
                )
            try:
                subprocess.run(
                    [
                        "sudo",
                        "-n",
                        "ip",
                        "route",
                        "del",
                        route.destination,
                        "dev",
                        route.interface,
                        "src",
                        route.source,
                        "scope",
                        "link",
                        "proto",
                        "static",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=self.options.timeout_seconds,
                )
            except subprocess.SubprocessError as error:
                raise DeploymentError("exact host-route delete failed") from error
        if self._exact_routes(route.destination):
            raise DeploymentError("exact host-route deletion was not verified")
        self._active_route = None

    def _ssh_base(self, interface: str) -> list[str]:
        if self._active_route is None:
            raise DeploymentError("SSH attempted without an active host-route lease")
        self.ensure_host_route(self._active_route, interface=interface)
        self._verify_ssh_password()
        return [
            *_ssh_base_argv(self.options, interface),
            f"{self.options.ssh_user}@{self.options.ssh_host}",
        ]

    def attest_runtime(
        self,
        device: UsbDevice,
        *,
        interface: str,
        expected_firmware: str,
        force_safe: bool,
    ) -> RuntimeAttestation:
        if not force_safe:
            raise DeploymentError("runtime attestation must enforce the safe state")
        if device.serial != self.options.serial:
            raise DeploymentError("runtime USB serial differs before IIO access")

        try:
            iio_module = importlib.import_module("iio")
        except (ImportError, OSError) as error:
            raise DeploymentError(
                "host pylibiio is required for safe-state attestation"
            ) from error
        contexts = iio_module.scan_contexts()
        uri_matches: list[str] = []
        for uri, description in contexts.items():
            parsed = re.fullmatch(r"usb:(\d+)[.](\d+)[.](\d+)", str(uri))
            if (
                parsed is not None
                and int(parsed.group(1)) == device.busnum
                and int(parsed.group(2)) == device.devnum
                and self.options.serial in str(description)
            ):
                uri_matches.append(str(uri))
        if len(uri_matches) != 1:
            raise DeploymentError(
                "expected one exact bus/device/serial USB IIO context; "
                f"found {uri_matches}"
            )

        context: Any = None
        try:
            context = iio_module.Context(uri_matches[0])
            set_timeout = getattr(context, "set_timeout", None)
            if not callable(set_timeout):
                raise DeploymentError("USB IIO context cannot install a timeout")
            set_timeout(round(self.options.timeout_seconds * 1000))
            attrs = {str(key): str(value) for key, value in context.attrs.items()}
            observed_serial = attrs.get(
                "hw_serial", attrs.get("usb,serial", attrs.get("serial", ""))
            )
            context_firmware = attrs.get("fw_version", "")
            hardware_model = attrs.get("hw_model", "")
            if (
                observed_serial != self.options.serial
                or not context_firmware
                or hardware_model != PLUTOPLUS_HARDWARE_MODEL
            ):
                raise DeploymentError(
                    "USB IIO runtime identity or Pluto+ hardware model differs"
                )

            phy = context.find_device("ad9361-phy")
            tx = context.find_device("cf-ad9361-dds-core-lpc")
            tandem = context.find_device("tandem-agc")
            if any(item is None for item in (phy, tx, tandem)):
                raise DeploymentError("runtime lacks required PHY/DDS/tandem devices")
            for index in (0, 1):
                _iio_channel(phy, f"voltage{index}", False)

            failures: list[str] = []
            for index in (0, 1):
                try:
                    _iio_write_numeric(
                        _iio_channel(phy, f"voltage{index}", True),
                        "hardwaregain",
                        -80.0,
                        tolerance=0.26,
                    )
                except BaseException as error:  # noqa: BLE001 - attempt every mute path
                    failures.append(f"TX{index + 1} mute: {error}")
            for index in range(8):
                try:
                    channel = _iio_channel(tx, f"altvoltage{index}", True)
                except BaseException as error:  # noqa: BLE001 - attempt every mute path
                    failures.append(f"DDS{index} discovery: {error}")
                    continue
                for name in ("raw", "scale"):
                    try:
                        _iio_write_numeric(channel, name, 0.0, tolerance=1e-9)
                    except BaseException as error:  # noqa: BLE001 - all DDS controls
                        failures.append(f"DDS{index} {name} disable: {error}")
            for index in range(4):
                try:
                    legacy_address = 0x0414 + index * 0x40
                    selector_address = 0x0418 + index * 0x40
                    legacy = int(tx.reg_read(legacy_address))
                    tx.reg_write(legacy_address, legacy & ~1)
                    tx.reg_write(selector_address, 3)
                except BaseException as error:  # noqa: BLE001 - attempt every mute path
                    failures.append(f"DAC selector {index} ZERO: {error}")

            gains = [
                _first_float(
                    _iio_read(
                        _iio_channel(phy, f"voltage{index}", True), "hardwaregain"
                    )
                )
                for index in (0, 1)
            ]
            dds = [
                _first_float(
                    _iio_read(_iio_channel(tx, f"altvoltage{index}", True), name)
                )
                for index in range(8)
                for name in ("raw", "scale")
            ]
            selectors = [
                int(tx.reg_read(0x0418 + index * 0x40)) & 0xF for index in range(4)
            ]
            state = round(_first_float(_iio_read(tandem, "state")))
            fifo = round(_first_float(_iio_read(tandem, "fifo_level")))
            faults = round(_first_float(_iio_read(tandem, "fault_flags")))
            if failures:
                raise DeploymentError("; ".join(failures))

            completed = subprocess.run(
                [*self._ssh_base(interface), REMOTE_IDENTITY_SCRIPT],
                check=True,
                text=True,
                capture_output=True,
                timeout=self.options.timeout_seconds,
            )
            remote_fields: dict[str, str] = {}
            for line in completed.stdout.splitlines():
                if "=" not in line:
                    raise DeploymentError("runtime identity returned a malformed line")
                key, value = line.split("=", 1)
                if key in remote_fields:
                    raise DeploymentError("runtime identity returned a duplicate field")
                remote_fields[key] = value
            if set(remote_fields) != {
                "boot_id",
                "firmware_version",
                "qspi_partition",
                "qspi_mtd_name",
                "qspi_bytes",
                "qspi_sha256",
            }:
                raise DeploymentError("runtime identity field inventory is not exact")
            firmware_version = _required_string(
                remote_fields.get("firmware_version"), label="runtime firmware version"
            )
            if firmware_version != context_firmware:
                raise DeploymentError("SSH and IIO firmware identities differ")
            qspi_partition = _required_string(
                remote_fields.get("qspi_partition"), label="runtime QSPI partition"
            )
            qspi_mtd_name = _required_string(
                remote_fields.get("qspi_mtd_name"), label="runtime QSPI MTD name"
            )
            qspi_bytes_text = _required_string(
                remote_fields.get("qspi_bytes"), label="runtime QSPI bytes"
            )
            if (
                qspi_partition != "/dev/mtdblock3"
                or qspi_mtd_name != "qspi-linux"
                or not qspi_bytes_text.isdigit()
                or int(qspi_bytes_text) <= 0
            ):
                raise DeploymentError("runtime QSPI partition identity is invalid")
            qspi_sha256 = _required_sha(
                remote_fields.get("qspi_sha256"), label="runtime QSPI SHA-256"
            )
            raw = {
                "iio_uri": uri_matches[0],
                "context_firmware": context_firmware,
                "expected_firmware": expected_firmware,
                **remote_fields,
            }
            return RuntimeAttestation(
                serial=observed_serial,
                hardware_model=hardware_model,
                boot_id=_required_string(
                    remote_fields.get("boot_id"), label="runtime boot ID"
                ),
                firmware_version=firmware_version,
                qspi_partition=qspi_partition,
                qspi_mtd_name=qspi_mtd_name,
                qspi_bytes=int(qspi_bytes_text),
                qspi_sha256=qspi_sha256,
                tx_muted=len(gains) == 2
                and all(math.isfinite(value) and value <= -80.0 for value in gains),
                dds_disabled=len(dds) == 16
                and all(math.isfinite(value) and abs(value) <= 1e-9 for value in dds),
                dac_selectors_zero=selectors == [3, 3, 3, 3],
                tandem_state="IDLE" if state == 0 else f"STATE_{state}",
                fifo_level=fifo,
                fault_flags=faults,
                raw=raw,
            )
        finally:
            if context is not None:
                close = getattr(context, "close", None)
                if callable(close):
                    close()
                context = None
                gc.collect()

    def request_ram_mode(self, argv: Sequence[str]) -> None:
        if self._active_route is None:
            raise DeploymentError("RAM-mode SSH attempted without a host-route lease")
        expected = [
            *self._ssh_base(self._active_route.interface),
            "/usr/sbin/device_reboot ram",
        ]
        if list(argv) != expected:
            raise DeploymentError("RAM-mode SSH command differs from the guarded plan")
        completed = subprocess.run(
            expected,
            check=False,
            text=True,
            capture_output=True,
            timeout=self.options.timeout_seconds,
        )
        if completed.returncode not in (0, 255):
            raise DeploymentError(
                f"RAM-mode request failed before disconnect: {completed.returncode}"
            )

    def wait_for_mode(
        self, *, serial: str, topology: str, product_id: str, timeout_seconds: float
    ) -> UsbDevice:
        if product_id not in (RUNTIME_PRODUCT, DFU_PRODUCT):
            raise DeploymentError(f"unsupported USB product mode {product_id!r}")
        deadline = time.monotonic() + timeout_seconds
        last_error: DeploymentError | None = None
        while time.monotonic() < deadline:
            try:
                if product_id == DFU_PRODUCT:
                    device = resolve_dfu_device(
                        self.inventory(), serial=serial, topology=topology
                    )
                else:
                    device = resolve_device(
                        self.inventory(),
                        serial=serial,
                        product_id=product_id,
                        topology=topology,
                    )
                if product_id == RUNTIME_PRODUCT:
                    select_interface(device, self.options.usb_interface)
                return device
            except DeploymentError as error:
                last_error = error
                time.sleep(0.25)
        raise DeploymentError(
            f"timed out waiting for {USB_VENDOR}:{product_id} on {topology}: {last_error}"
        )

    def run_dfu(self, argv: Sequence[str]) -> None:
        downloaded = "-D" in argv
        inherited: tuple[int, ...] = ()
        if downloaded:
            if (
                argv[-2] != "-D"
                or re.fullmatch(r"/proc/self/fd/[0-9]+", argv[-1]) is None
            ):
                raise DeploymentError("DFU download must use the sealed descriptor")
            descriptor = int(argv[-1].rsplit("/", 1)[1])
            if fcntl.fcntl(descriptor, F_GET_SEALS) != REQUIRED_DFU_SEALS:
                raise DeploymentError("DFU download descriptor is not sealed")
            expected_bytes = os.fstat(descriptor).st_size
            if (
                _descriptor_sha256(descriptor, expected_bytes=expected_bytes)
                != self.options.artifact_sha256
            ):
                raise DeploymentError("sealed DFU bytes changed before download")
            inherited = (descriptor,)
        subprocess.run(
            list(argv),
            check=True,
            text=True,
            capture_output=True,
            timeout=self.options.timeout_seconds,
            pass_fds=inherited,
        )
        if downloaded and (
            _descriptor_sha256(inherited[0], expected_bytes=expected_bytes)
            != self.options.artifact_sha256
        ):
            raise DeploymentError("sealed DFU bytes changed during download")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radio-serial", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--artifact-index", required=True, type=Path)
    parser.add_argument("--artifact-index-sha256", required=True)
    parser.add_argument("--expected-current-firmware", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--ssh-host", default="192.168.2.1")
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-password-file", type=Path)
    parser.add_argument("--usb-interface")
    parser.add_argument("--usb-inventory", type=Path)
    parser.add_argument("--operator-confirmation")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--execute", action="store_true")
    return parser


def _options(namespace: argparse.Namespace) -> DeploymentOptions:
    serial = _required_string(namespace.radio_serial, label="radio serial")
    if SAFE_SERIAL.fullmatch(serial) is None:
        raise DeploymentError("radio serial contains unsafe characters")
    if (
        HEX_64.fullmatch(namespace.artifact_sha256) is None
        or HEX_64.fullmatch(namespace.artifact_index_sha256) is None
    ):
        raise DeploymentError("artifact and index SHA-256 values must be lowercase hex")
    if namespace.timeout_seconds < 1 or namespace.timeout_seconds > 300:
        raise DeploymentError("timeout must be within [1, 300] seconds")
    try:
        ssh_address = ipaddress.ip_address(namespace.ssh_host)
    except ValueError as error:
        raise DeploymentError("SSH host must be one literal IP address") from error
    if ssh_address.version != 4:
        raise DeploymentError("SSH host must be one literal IPv4 address")
    if SAFE_USER.fullmatch(namespace.ssh_user) is None:
        raise DeploymentError("SSH user contains unsafe characters")
    password_file = namespace.ssh_password_file
    if password_file is not None:
        password_file = _canonical_absolute(password_file, label="SSH password file")
        _read_password_file(password_file)
    elif namespace.execute:
        raise DeploymentError("--ssh-password-file is required with --execute")
    return DeploymentOptions(
        serial=serial,
        artifact_path=_canonical_absolute(namespace.artifact, label="requested DFU"),
        artifact_sha256=namespace.artifact_sha256,
        artifact_index_path=_canonical_absolute(
            namespace.artifact_index, label="artifact index"
        ),
        artifact_index_sha256=namespace.artifact_index_sha256,
        expected_current_firmware=_required_string(
            namespace.expected_current_firmware, label="expected current firmware"
        ),
        receipt_path=namespace.receipt,
        ssh_host=namespace.ssh_host,
        ssh_user=namespace.ssh_user,
        ssh_password_file=password_file,
        usb_interface=namespace.usb_interface,
        operator_confirmation=namespace.operator_confirmation,
        timeout_seconds=namespace.timeout_seconds,
    )


def _plan_document(
    options: DeploymentOptions,
    artifact: CandidateArtifact,
    inventory: Sequence[UsbDevice] | None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "plutosdr-fw.tandem-ram-deployment-plan",
        "schema_version": 1,
        "executable": False,
        "hardware_accessed": False,
        "radio_serial": options.serial,
        "artifact": {
            "path": str(artifact.dfu_path),
            "dfu_sha256": artifact.dfu_sha256,
            "dfu_bytes": artifact.dfu_bytes,
            "fit_sha256": artifact.fit_sha256,
            "fit_bytes": artifact.fit_bytes,
        },
        "artifact_index": {
            "path": str(artifact.index_path),
            "sha256": artifact.index_sha256,
            "required_evidence_roles": len(artifact.evidence_roles),
        },
        "receipt_path": str(options.receipt_path),
        "transition": {
            "method": TRANSITION_METHOD,
            "usb_reset_R_allowed": False,
            "persistent_targets_allowed": False,
        },
        "rollback": "remove power to return to the unchanged persistent QSPI image",
    }
    if inventory is None:
        document["verdict"] = "blocked"
        document["blockers"] = [
            "offline plan has no captured USB inventory; live exact-serial topology is resolved only under --execute",
            "execution also requires exact operator confirmation",
        ]
        return document
    device = resolve_device(
        inventory, serial=options.serial, product_id=RUNTIME_PRODUCT
    )
    interface = select_interface(device, options.usb_interface)
    document["usb"] = asdict(device)
    if options.ssh_password_file is None:
        document["verdict"] = "blocked"
        document["blockers"] = [
            "captured-inventory command planning requires --ssh-password-file",
            "this offline plan authorizes no device access",
        ]
        return document
    document["commands"] = list(build_command_plan(options, device, interface))
    document["verdict"] = "ready-for-review"
    document["blockers"] = [
        "this offline plan authorizes no device access",
        "execution requires exact operator confirmation",
    ]
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    namespace = parser.parse_args(argv)
    try:
        options = _options(namespace)
        artifact = load_candidate_artifact(options)
        _receipt_output_path(
            options.receipt_path,
            serial=options.serial,
            archive_root=artifact.index_path.parent,
        )
        if not namespace.execute:
            inventory = (
                load_inventory(namespace.usb_inventory)
                if namespace.usb_inventory
                else None
            )
            print(
                json.dumps(
                    _plan_document(options, artifact, inventory),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        for command in ("sshpass", "ssh", "dfu-util", "ip", "sudo"):
            if shutil.which(command) is None:
                raise DeploymentError(f"required execution tool is absent: {command}")
        try:
            importlib.import_module("iio")
        except (ImportError, OSError) as error:
            raise DeploymentError(
                "required execution dependency is absent: host pylibiio"
            ) from error
        receipt, digest = execute_deployment(options, SystemBackend(options))
        print(
            json.dumps(
                {
                    "verdict": receipt["verdict"],
                    "receipt": str(options.receipt_path),
                    "receipt_sha256": digest,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (DeploymentError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"ERROR: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
