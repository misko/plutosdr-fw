#!/usr/bin/env python3
"""Assemble and verify immutable tandem-AGC release evidence indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.radio_hardware.candidate_binding import (
    ARTIFACT_INDEX_SCHEMA,
    REQUIRED_EVIDENCE_ROLES,
    SCHEMA_VERSION,
    CandidateBindingError,
    validate_artifact_index,
)
from tests.radio_hardware.pluto_plus_candidate import (
    validate_release_candidate_plan,
    validate_release_candidate_receipt,
    validate_release_operation_plan,
    validate_release_usb_inventory,
)

INPUT_SCHEMA = "plutosdr-fw.tandem-release-evidence-input"
ATTESTATION_SCHEMA = "plutosdr-fw.github-attestation-verification.v1"
ATTESTATION_NOT_PERFORMED_SCHEMA = "plutosdr-fw.github-attestation-not-performed.v1"
ACTIONS_RUN_SCHEMA = "plutosdr-fw.github-actions-run.v1"
INTEGRATED_VERDICT_SCHEMA = "plutosdr-fw.integrated-route-verdict.v1"
SOURCE_LOCK_SCHEMA = "plutosdr-fw.source-lock.v1"
QUALIFICATION_INDEX_SCHEMA = "plutosdr-fw.tandem-release-qualification"
FINAL_POLICY_SCHEMA = "plutosdr-fw.tandem-final-qualification-policy"
CANDIDATE_TO_FINAL_DIFF_SCHEMA = "plutosdr-fw.tandem-candidate-to-final-diff"
PUBLISHED_INDEX_SCHEMA = "plutosdr-fw.tandem-published-release"
PUBLISHED_INPUT_SCHEMA = "plutosdr-fw.tandem-published-release-input"
TAG_RECORD_SCHEMA = "plutosdr-fw.annotated-tag-record.v1"
RELEASE_VERIFICATION_SCHEMA = "plutosdr-fw.release-verification.v1"
RELEASE_INVENTORY_SCHEMA = "plutosdr-fw.github-release-inventory.v1"
REMOTE_TAG_RECORD_SCHEMA = "plutosdr-fw.git-remote-tag-record.v1"
RELEASE_INVENTORY_JQ = (
    "{tagName:.tag_name,isDraft:.draft,isPrerelease:.prerelease,url:.html_url,"
    "assets:[.assets[]|{name,size,state,url:.browser_download_url,digest}]}"
)
FINAL_CONFIRMATION_SCHEMA = "plutosdr-fw.tandem-agc-final-confirmation.v1"
FINAL_CONFIRMATION_INDEX_SCHEMA = "plutosdr-fw.tandem-agc-final-confirmation-index.v1"
SEMANTIC_VERIFIER_HARNESS_PATH = "scripts/tandem_release_evidence.py"
RELEASE_VERIFIER_HARNESS_PATH = "scripts/verify_release.sh"
RELEASE_GIT_REMOTE_URL = "https://github.com/misko/plutosdr-fw.git"
CANDIDATE_FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc32"
FINAL_FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8"
CANDIDATE_SOURCE_LOCK_REF = "refs/tags/tandem-agc-v8-rc32-source/firmware-v2"
FINAL_SOURCE_LOCK_REF = "refs/tags/tandem-agc-v8-source/firmware-v1"
GAIN_TIMELINE_CANDIDATE_FIRMWARE_VERSION = (
    "v0.45-plutoplus-spf-iio-gain-timeline-v8-rc1"
)
GAIN_TIMELINE_FINAL_FIRMWARE_VERSION = "v0.45-plutoplus-spf-iio-gain-timeline-v8"
GAIN_TIMELINE_CANDIDATE_SOURCE_LOCK_REF = (
    "refs/tags/iio-gain-timeline-v8-rc1-source/fw-v10"
)
GAIN_TIMELINE_FINAL_SOURCE_LOCK_REF = "refs/tags/iio-gain-timeline-v8-source/fw-v1"
RELEASE_RADIO_SERIALS = (
    "104000bac4950008230026001b440a003a",
    "winbond-db620818a328172c",
    "winbond-db6968136727402c",
)
PRE_HARDWARE_PROFILES = {
    ("candidate-pre-hardware", CANDIDATE_FIRMWARE_VERSION): {
        "source_lock_ref": CANDIDATE_SOURCE_LOCK_REF,
        "manifest_basename": "tandem-agc-v8-rc32-source.yaml",
        "build_ref": "refs/heads/codex/firmware-tandem-agc-v8-rc32",
        "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
        "metadata_abi": "frame-metadata-v5",
        "tandem_agc": "request-v2",
    },
    ("final-pre-confirmation", FINAL_FIRMWARE_VERSION): {
        "source_lock_ref": FINAL_SOURCE_LOCK_REF,
        "manifest_basename": "tandem-agc-v8-source.yaml",
        "build_ref": "refs/heads/main",
        "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
        "metadata_abi": "frame-metadata-v5",
        "tandem_agc": "request-v2",
    },
    (
        "candidate-pre-hardware",
        GAIN_TIMELINE_CANDIDATE_FIRMWARE_VERSION,
    ): {
        "source_lock_ref": GAIN_TIMELINE_CANDIDATE_SOURCE_LOCK_REF,
        "manifest_basename": "iio-gain-timeline-v8-rc1-source.yaml",
        "build_ref": "refs/heads/codex/iio-gain-timeline-v8-fw",
        "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9363A)",
        "metadata_abi": "frame-metadata-v5",
        "tandem_agc": "request-v2",
    },
    ("final-pre-confirmation", GAIN_TIMELINE_FINAL_FIRMWARE_VERSION): {
        "source_lock_ref": GAIN_TIMELINE_FINAL_SOURCE_LOCK_REF,
        "manifest_basename": "iio-gain-timeline-v8-rc1-source.yaml",
        "build_ref": "refs/heads/main",
        "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9363A)",
        "metadata_abi": "frame-metadata-v5",
        "tandem_agc": "request-v2",
    },
}
INDEX_FILENAMES = {
    "candidate-pre-hardware": "candidate-index.json",
    "candidate-qualified": "campaign-index.json",
    "final-pre-confirmation": "final-artifact-index.json",
    "final-qualification-policy": "final-qualification-policy.json",
    "final-qualified": "final-qualification-index.json",
    "published-release": "published-release-index.json",
}
MAX_JSON_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024
MAX_BUNDLE_MEMBERS = 256
MAX_BUNDLE_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SAFE_ID = re.compile(r"[A-Za-z0-9_.-]+")
_TAG = re.compile(r"v[0-9]+(?:[.][0-9]+)+(?:-[A-Za-z0-9_.-]+)*")
_BUNDLE_FIXED_ROLE_NAMES = {
    "bundle-inner-checksums": "SHA256SUMS",
    "dfu-suffix-check": "dfu-suffix-check.txt",
    "fit-layout": "fit-layout.txt",
    "fpga-bitstream": "system_top.bit",
    "integrated-verdict": "integrated-release-verdict.json",
    "offline-validation-summary": "offline-validation-summary.txt",
    "packed-versions": "packed-VERSIONS.txt",
    "payload-checksums": "PAYLOAD_SHA256SUMS",
    "routed-bus-skew": "system_top_bus_skew_routed.rpt",
    "routed-cdc": "system_top_cdc_routed.rpt",
    "routed-dcp": "system_top_routed.dcp",
    "routed-drc": "system_top_drc_routed.rpt",
    "routed-methodology": "system_top_methodology_drc_routed.rpt",
    "routed-route-status": "system_top_route_status.rpt",
    "routed-timing": "system_top_timing_summary_routed.rpt",
    "routed-utilization": "system_top_utilization_routed.rpt",
}
_BUNDLE_DYNAMIC_ROLES = frozenset({"provenance", "rootfs", "waiver-inventory", "xsa"})
INTEGRATED_VALIDATED_ROLES = (
    "source-manifest",
    "waiver-inventory",
    "routed-dcp",
    "routed-utilization",
    "routed-timing",
    "routed-route-status",
    "routed-drc",
    "routed-methodology",
    "routed-cdc",
    "routed-bus-skew",
)
_CAMPAIGN_PHASES = ("deploy", "full", "soak", "lifecycle")
_OPTIONAL_CAMPAIGN_DIAGNOSTIC_PHASES = frozenset({"stale-latch"})
_CAMPAIGN_FILENAMES = {
    "deploy": "ram-boot-receipt.json",
    "full": "release-hardware-report.json",
    "soak": "release-hardware-report.json",
    "lifecycle": "muted-metadata-batch-lifecycle-v5.json",
}
GAIN_TIMELINE_RELEASE_RADIO_IPS = (
    ("1040007c4a94000211000b009186843ef2", "192.168.1.18"),
    ("104000bac4950008230026001b440a003a", "192.168.1.17"),
)
GAIN_TIMELINE_RELEASE_RADIO_SERIALS = tuple(
    serial for serial, _ip in GAIN_TIMELINE_RELEASE_RADIO_IPS
)
_GAIN_TIMELINE_PHASES = ("deploy", "qualification")
_GAIN_TIMELINE_FILENAMES = {
    "deploy": "ram-boot-receipt.json",
    "qualification": "gain-timeline-report.json",
}
_GAIN_TIMELINE_PLAN_FILENAME = "gain-timeline-qualification-plan.json"
_GAIN_TIMELINE_PLAN_SCHEMA = "pluto-plus-utils.gain-timeline-qualification-plan.v2"
_GAIN_TIMELINE_REPORT_SCHEMA = "pluto-plus-utils.gain-timeline-qualification-report.v2"
_GAIN_TIMELINE_SAMPLE_RATE_HZ = 20_000_000
_GAIN_TIMELINE_SAMPLES_PER_CHANNEL = 262_144
_GAIN_TIMELINE_KERNEL_BUFFERS = 4
_GAIN_TIMELINE_RING_IQ_BYTES = 200_000_000
_GAIN_TIMELINE_CASE_COUNT = 187
RELEASE_HARDWARE_HARNESS_PATHS = (
    "scripts/deploy_tandem_agc_ram_hardware.sh",
    "scripts/run_tandem_agc_release_hardware.sh",
    "scripts/tandem_release_device_plan.py",
    "scripts/tandem_release_evidence.py",
    "tests/radio_hardware/candidate_binding.py",
    "tests/radio_hardware/experiment.py",
    "tests/radio_hardware/metadata_abi.py",
    "tests/radio_hardware/modulated_hardware.py",
    "tests/radio_hardware/modulated_quality.py",
    "tests/radio_hardware/release_campaign.py",
    "tests/radio_hardware/release_cli.py",
    "tests/radio_hardware/pluto_plus_candidate.py",
    "tests/radio_hardware/tandem_quality.py",
    "tests/radio_hardware/tone_quality.py",
    "tests/radio_hardware/transient_hardware.py",
    "tests/radio_hardware/transient_quality.py",
)
ARTIFACT_HARNESS_PATHS = tuple(
    sorted(
        {
            *RELEASE_HARDWARE_HARNESS_PATHS,
            RELEASE_VERIFIER_HARNESS_PATH,
            "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
            "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
        }
    )
)
RELEASE_RUNNER_PROVENANCE_PATHS = (
    "scripts/deploy_tandem_agc_ram_hardware.sh",
    "scripts/run_tandem_agc_release_hardware.sh",
    "scripts/tandem_release_device_plan.py",
    "scripts/tandem_release_evidence.py",
    "tests/radio_hardware/candidate_binding.py",
    "tests/radio_hardware/pluto_plus_candidate.py",
    "tests/radio_hardware/release_cli.py",
)
RELEASE_BINDING_SCHEMA = "plutosdr-fw.tandem-release-candidate-binding.v1"
RELEASE_RUNNER_SCHEMA = "plutosdr-fw.tandem-release-runner-provenance.v1"
RELEASE_HOST_LIBIIO_SCHEMA = "plutosdr-fw.tandem-release-host-libiio-runtime.v1"
RELEASE_BANDS = (
    {"name": "lnb-low-1050mhz", "center_frequency_hz": 1_050_000_000},
    {"name": "lnb-mid-1550mhz", "center_frequency_hz": 1_550_000_000},
    {"name": "lnb-high-2050mhz", "center_frequency_hz": 2_050_000_000},
    {
        "name": "table3-sentinel-4200mhz",
        "center_frequency_hz": 4_200_000_000,
    },
)
RELEASE_DIAGNOSTIC_2450 = {
    "phase": "diagnostic-2450",
    "band": {
        "name": "diagnostic-2450mhz",
        "center_frequency_hz": 2_450_000_000,
    },
    "modes": [
        "manual_fixed",
        "native_slow_attack",
        "native_fast_attack",
        "tandem_auto",
    ],
    "continuation_policy": "rf_quality_only_failure_is_recorded_and_nonbinding",
    "fatal_policy": "identity_metadata_evidence_safety_fault_or_cleanup_failure",
    "release_claim": "none_at_2_4_ghz",
}
RELEASE_COMMON_CONFIGURATION = {
    "sample_rate_hz": 2_500_000,
    "samples_per_channel": 65_536,
    "phase_max_seconds": 600.0,
}
LIFECYCLE_HARNESS_PATHS = (
    "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
    "tests/radio_hardware/candidate_binding.py",
    "tests/radio_hardware/metadata_abi.py",
    "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
)
LIFECYCLE_REPORT_FIELDS = {
    "schema",
    "verdict",
    "release_claim",
    "release_pass_eligible",
    "hardware_qualified",
    "started_unix_ns",
    "completed_unix_ns",
    "host_libiio",
    "runner_provenance",
    "expected_device_firmware_lineage",
    "device_firmware_provenance",
    "configuration",
    "output_preflight",
    "preflight",
    "normalization",
    "rx_scan",
    "full_drain",
    "post_full_drain_barrier",
    "cancel_lifecycle",
    "temperature_evidence",
    "metadata_artifacts",
    "final_tandem_status",
    "final_rx_state",
    "final_rf_state",
    "cleanup",
}


class EvidenceError(RuntimeError):
    """The evidence archive is malformed, mutable, or internally inconsistent."""


def _fail(message: str) -> None:
    raise EvidenceError(message)


def _pairs_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON object contains duplicate key {key!r}")
        result[key] = value
    return result


def _decode_json(payload: bytes, *, name: str) -> object:
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=lambda token: _fail(f"{name} contains {token}"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"{name} is not strict JSON: {error}") from error
    return value


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail(f"{name} must be a string-keyed object")
    return value


def _exact_keys(value: Mapping[str, object], keys: set[str], *, name: str) -> None:
    observed = set(value)
    if observed != keys:
        _fail(
            f"{name} keys are not exact: missing={sorted(keys - observed)} "
            f"extra={sorted(observed - keys)}"
        )


def _positive_int(value: object, *, name: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: object, *, name: str) -> int:
    if type(value) is not int or value < 0:
        _fail(f"{name} must be a nonnegative integer")
    return value


def _string(value: object, *, name: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{name} must be a bounded nonempty string")
    if value.strip() != value or any(character in value for character in "\x00\r\n"):
        _fail(f"{name} is not one canonical line")
    return value


def _sha(value: object, *, name: str) -> str:
    text = _string(value, name=name, maximum=64)
    if _SHA256.fullmatch(text) is None:
        _fail(f"{name} is not lowercase SHA-256")
    return text


def _relative(value: object, *, name: str) -> str:
    text = _string(value, name=name, maximum=1024)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != text
    ):
        _fail(f"{name} is not a canonical relative POSIX path")
    return text


def _safe_id(value: object, *, name: str) -> str:
    text = _string(value, name=name, maximum=128)
    if _SAFE_ID.fullmatch(text) is None:
        _fail(f"{name} is not a safe immutable identifier")
    return text


def _https_url(value: object, *, name: str) -> str:
    text = _string(value, name=name, maximum=2048)
    if not text.startswith("https://") or any(
        character.isspace() for character in text
    ):
        _fail(f"{name} must be one canonical HTTPS URL")
    return text


def _canonical_root(path: Path) -> Path:
    absolute = path.absolute()
    if not absolute.is_dir() or absolute.is_symlink() or absolute.resolve() != absolute:
        _fail("archive root must be an existing canonical nonsymlink directory")
    return absolute


def _member_path(root: Path, relative: str, *, name: str) -> Path:
    canonical = _relative(relative, name=name)
    candidate = root.joinpath(*PurePosixPath(canonical).parts)
    current = root
    for part in PurePosixPath(canonical).parts:
        current /= part
        if current.is_symlink():
            _fail(f"{name} contains a symlink component")
    try:
        if candidate.resolve(strict=True).relative_to(root) != Path(canonical):
            _fail(f"{name} resolves outside or aliases its archive path")
    except (FileNotFoundError, ValueError) as error:
        raise EvidenceError(f"{name} is absent or escapes the archive root") from error
    return candidate


def _hash_regular(
    path: Path,
    *,
    name: str,
    maximum: int = MAX_MEMBER_BYTES,
    prefix_bytes: int | None = None,
) -> tuple[int, str, str | None]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise EvidenceError(f"cannot open {name}: {error}") from error
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{name} is not a regular file")
        if before.st_uid != os.geteuid():
            _fail(f"{name} is not owned by the current user")
        if mode & 0o022:
            _fail(f"{name} is group/world writable")
        if before.st_size <= 0 or before.st_size > maximum:
            _fail(f"{name} size is outside 1..{maximum}")
        if prefix_bytes is not None and not 0 < prefix_bytes <= before.st_size:
            _fail(f"{name} prefix length is outside the file")
        whole = hashlib.sha256()
        prefix = hashlib.sha256() if prefix_bytes is not None else None
        remaining_prefix = prefix_bytes or 0
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            whole.update(chunk)
            if prefix is not None and remaining_prefix:
                selected = chunk[:remaining_prefix]
                prefix.update(selected)
                remaining_prefix -= len(selected)
        after = os.fstat(descriptor)
        if (
            total != before.st_size
            or remaining_prefix != 0
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            _fail(f"{name} changed while hashing")
        return total, whole.hexdigest(), prefix.hexdigest() if prefix else None
    finally:
        os.close(descriptor)


def _read_small(path: Path, *, name: str) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise EvidenceError(f"cannot open {name}: {error}") from error
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{name} is not a regular file")
        if before.st_uid != os.geteuid() or mode & 0o022:
            _fail(f"{name} has unsafe ownership or write permissions")
        if before.st_size <= 0 or before.st_size > MAX_JSON_BYTES:
            _fail(f"{name} size is outside 1..{MAX_JSON_BYTES}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if remaining != 0 or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        _fail(f"{name} changed during bounded read")
    return b"".join(chunks)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


class _DigestingReader:
    """Minimal forward-only reader used by streaming tar validation."""

    def __init__(self, descriptor: int) -> None:
        self.descriptor = descriptor
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = 1024 * 1024
        payload = os.read(self.descriptor, size)
        self.digest.update(payload)
        self.bytes_read += len(payload)
        return payload

    def tell(self) -> int:
        return self.bytes_read


def _parse_checksum_inventory(payload: bytes, *, name: str) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceError(f"{name} is not strict UTF-8") from error
    if not lines:
        _fail(f"{name} is empty")
    result: dict[str, str] = {}
    observed_names: list[str] = []
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\x00\r\n]+)", line)
        if match is None:
            _fail(f"{name} contains a malformed sha256sum line")
        digest, member_name = match.groups()
        canonical = _relative(member_name, name=f"{name} member")
        if len(PurePosixPath(canonical).parts) != 1:
            _fail(f"{name} member is not a flat bundle name")
        if canonical in result:
            _fail(f"{name} duplicates member {canonical}")
        result[canonical] = digest
        observed_names.append(canonical)
    if observed_names != sorted(observed_names):
        _fail(f"{name} members are not sorted")
    return result


def _stream_bundle_inventory(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> dict[str, dict[str, object]]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise EvidenceError(f"cannot open deployment bundle: {error}") from error
    reader = _DigestingReader(descriptor)
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or mode & 0o022
            or before.st_size != expected_bytes
        ):
            _fail("deployment bundle has unsafe or unexpected file metadata")
        inventory: dict[str, dict[str, object]] = {}
        order: list[str] = []
        total_uncompressed = 0
        try:
            with tarfile.open(fileobj=reader, mode="r|gz") as archive:
                for member in archive:
                    if len(inventory) >= MAX_BUNDLE_MEMBERS:
                        _fail("deployment bundle has too many members")
                    member_name = _relative(member.name, name="bundle member")
                    if len(PurePosixPath(member_name).parts) != 1:
                        _fail("deployment bundle member is not a flat canonical name")
                    if member_name in inventory:
                        _fail(f"deployment bundle duplicates member {member_name}")
                    if (
                        not member.isfile()
                        or member.linkname
                        or member.size <= 0
                        or member.size > MAX_MEMBER_BYTES
                        or member.uid != 0
                        or member.gid != 0
                        or stat.S_IMODE(member.mode) & 0o022
                    ):
                        _fail(f"deployment bundle member {member_name} is unsafe")
                    total_uncompressed += member.size
                    if total_uncompressed > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                        _fail("deployment bundle uncompressed size exceeds policy")
                    stream = archive.extractfile(member)
                    if stream is None:
                        _fail(f"deployment bundle member {member_name} is unreadable")
                    digest = hashlib.sha256()
                    captured = (
                        bytearray() if member_name == "system-top-bit.sha256" else None
                    )
                    if captured is not None and member.size > 4096:
                        _fail("FPGA bitstream sidecar exceeds its strict size limit")
                    observed = 0
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        observed += len(chunk)
                        digest.update(chunk)
                        if captured is not None:
                            captured.extend(chunk)
                    if observed != member.size:
                        _fail(f"deployment bundle member {member_name} is truncated")
                    inventory[member_name] = {
                        "bytes": observed,
                        "sha256": digest.hexdigest(),
                    }
                    if captured is not None:
                        inventory[member_name]["payload"] = bytes(captured)
                    order.append(member_name)
        except (tarfile.TarError, EOFError, OSError) as error:
            raise EvidenceError(
                f"deployment bundle is not a strict tar.gz: {error}"
            ) from error
        while reader.read(1024 * 1024):
            pass
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or reader.bytes_read != before.st_size
            or reader.digest.hexdigest() != expected_sha256
        ):
            _fail("deployment bundle changed or differs while streaming")
        if order != sorted(order):
            _fail("deployment bundle member order is not deterministic")
        return inventory
    finally:
        os.close(descriptor)


def _verify_bundle_sidecar(
    bundle_path: Path, *, bundle_sha256: str, bundle_name: str
) -> None:
    sidecar_path = Path(str(bundle_path) + ".sha256")
    payload = _read_small(sidecar_path, name="deployment bundle sidecar")
    if payload != f"{bundle_sha256}  {bundle_name}\n".encode():
        _fail("deployment bundle SHA-256 sidecar is not exact")


def _verify_xsa_bitstream(
    xsa_path: Path,
    raw_bitstream_path: Path,
    *,
    expected_xsa_bytes: int,
    expected_xsa_sha256: str,
    expected_bitstream_bytes: int,
    expected_bitstream_sha256: str,
) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        xsa_descriptor = os.open(xsa_path, flags)
        bit_descriptor = os.open(raw_bitstream_path, flags)
    except OSError as error:
        try:
            os.close(xsa_descriptor)
        except (NameError, OSError):
            pass
        raise EvidenceError(
            f"cannot open XSA/FPGA bitstream evidence: {error}"
        ) from error
    try:
        xsa_before = os.fstat(xsa_descriptor)
        bit_before = os.fstat(bit_descriptor)
        for metadata, expected_bytes, name in (
            (xsa_before, expected_xsa_bytes, "XSA"),
            (bit_before, expected_bitstream_bytes, "raw FPGA bitstream"),
        ):
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or metadata.st_size != expected_bytes
            ):
                _fail(f"{name} has unsafe or unexpected file metadata")
        xsa_digest = hashlib.sha256()
        while True:
            chunk = os.read(xsa_descriptor, 1024 * 1024)
            if not chunk:
                break
            xsa_digest.update(chunk)
        if xsa_digest.hexdigest() != expected_xsa_sha256:
            _fail("XSA differs from its indexed and bundled digest")
        os.lseek(xsa_descriptor, 0, os.SEEK_SET)
        try:
            with (
                os.fdopen(os.dup(xsa_descriptor), "rb") as xsa_stream,
                zipfile.ZipFile(xsa_stream, mode="r") as archive,
            ):
                infos = archive.infolist()
                if len(infos) > 100_000:
                    _fail("XSA ZIP contains too many members")
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    _fail("XSA ZIP contains duplicate members")
                matches = [info for info in infos if info.filename == "system_top.bit"]
                if len(matches) != 1:
                    _fail("XSA does not contain exactly one root system_top.bit")
                info = matches[0]
                unix_mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or info.flag_bits & 0x1
                    or (unix_mode and stat.S_ISLNK(unix_mode))
                    or info.file_size != expected_bitstream_bytes
                    or info.file_size <= 0
                    or info.file_size > MAX_MEMBER_BYTES
                ):
                    _fail("XSA system_top.bit member is unsafe or has wrong size")
                bit_digest = hashlib.sha256()
                observed = 0
                with archive.open(info, mode="r") as packed_bitstream:
                    while True:
                        xsa_chunk = packed_bitstream.read(1024 * 1024)
                        raw_chunk = os.read(bit_descriptor, 1024 * 1024)
                        if xsa_chunk != raw_chunk:
                            _fail("XSA system_top.bit differs from the raw bitstream")
                        if not xsa_chunk:
                            break
                        observed += len(xsa_chunk)
                        bit_digest.update(xsa_chunk)
                if (
                    observed != expected_bitstream_bytes
                    or bit_digest.hexdigest() != expected_bitstream_sha256
                ):
                    _fail("XSA system_top.bit digest differs from the raw bitstream")
        except (
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
            OSError,
        ) as error:
            raise EvidenceError(
                f"XSA is not a readable bounded ZIP: {error}"
            ) from error
        xsa_after = os.fstat(xsa_descriptor)
        bit_after = os.fstat(bit_descriptor)
        if (
            xsa_before.st_dev,
            xsa_before.st_ino,
            xsa_before.st_size,
            xsa_before.st_mtime_ns,
            bit_before.st_dev,
            bit_before.st_ino,
            bit_before.st_size,
            bit_before.st_mtime_ns,
        ) != (
            xsa_after.st_dev,
            xsa_after.st_ino,
            xsa_after.st_size,
            xsa_after.st_mtime_ns,
            bit_after.st_dev,
            bit_after.st_ino,
            bit_after.st_size,
            bit_after.st_mtime_ns,
        ):
            _fail("XSA/raw FPGA bitstream changed during verification")
    finally:
        os.close(xsa_descriptor)
        os.close(bit_descriptor)


def _verify_bundle_contract(
    root: Path,
    *,
    index: Mapping[str, Any],
    roles: Mapping[str, Mapping[str, Any]],
    manifest_sha256: str,
) -> None:
    bundle_entry = roles["bundle"]
    bundle_path = _member_path(root, bundle_entry["path"], name="deployment bundle")
    bundle_name = PurePosixPath(bundle_entry["path"]).name
    artifact = index["artifact"]
    dfu_name = PurePosixPath(artifact["dfu_path"]).name
    if not dfu_name.endswith("-pluto.dfu"):
        _fail("indexed DFU name is not the packaged Pluto image name")
    stem = dfu_name.removesuffix("-pluto.dfu")
    if bundle_name != f"{stem}.tar.gz":
        _fail("deployment bundle and DFU package stems differ")
    _verify_bundle_sidecar(
        bundle_path,
        bundle_sha256=bundle_entry["sha256"],
        bundle_name=bundle_name,
    )
    inventory = _stream_bundle_inventory(
        bundle_path,
        expected_bytes=bundle_entry["bytes"],
        expected_sha256=bundle_entry["sha256"],
    )

    checksum_entry = roles["bundle-inner-checksums"]
    payload_entry = roles["payload-checksums"]
    if PurePosixPath(checksum_entry["path"]).name != "SHA256SUMS":
        _fail("bundle-inner-checksums role does not name SHA256SUMS")
    if PurePosixPath(payload_entry["path"]).name != "PAYLOAD_SHA256SUMS":
        _fail("payload-checksums role does not name PAYLOAD_SHA256SUMS")
    checksums_payload = _read_small(
        _member_path(root, checksum_entry["path"], name="bundle SHA256SUMS"),
        name="bundle SHA256SUMS",
    )
    payload_checksums_payload = _read_small(
        _member_path(root, payload_entry["path"], name="bundle PAYLOAD_SHA256SUMS"),
        name="bundle PAYLOAD_SHA256SUMS",
    )
    checksums = _parse_checksum_inventory(checksums_payload, name="SHA256SUMS")
    payload_checksums = _parse_checksum_inventory(
        payload_checksums_payload, name="PAYLOAD_SHA256SUMS"
    )
    if set(inventory) != {*checksums, "SHA256SUMS"}:
        _fail("SHA256SUMS does not cover the exact deployment bundle inventory")
    for member_name, digest in checksums.items():
        if inventory[member_name]["sha256"] != digest:
            _fail(f"SHA256SUMS digest differs for bundle member {member_name}")
    if (
        inventory["SHA256SUMS"]["sha256"] != checksum_entry["sha256"]
        or inventory["SHA256SUMS"]["bytes"] != checksum_entry["bytes"]
        or inventory["PAYLOAD_SHA256SUMS"]["sha256"] != payload_entry["sha256"]
        or inventory["PAYLOAD_SHA256SUMS"]["bytes"] != payload_entry["bytes"]
    ):
        _fail("indexed checksum roles differ from the exact bundle members")

    expected_payload = {
        dfu_name,
        f"{stem}-pluto.frm",
        f"{stem}-system_top.xsa",
        f"{stem}-rootfs.cpio.gz",
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
        PurePosixPath(roles["waiver-inventory"]["path"]).name,
    }
    if set(payload_checksums) != expected_payload:
        _fail("PAYLOAD_SHA256SUMS inventory is not exact for a strict tandem v8 bundle")
    for member_name, digest in payload_checksums.items():
        if member_name not in inventory or inventory[member_name]["sha256"] != digest:
            _fail(f"PAYLOAD_SHA256SUMS digest differs for bundle member {member_name}")

    expected_role_names = dict(_BUNDLE_FIXED_ROLE_NAMES)
    expected_role_names.update(
        {
            "provenance": f"{stem}-provenance.txt",
            "rootfs": f"{stem}-rootfs.cpio.gz",
            "xsa": f"{stem}-system_top.xsa",
            "waiver-inventory": PurePosixPath(roles["waiver-inventory"]["path"]).name,
        }
    )
    for role, member_name in expected_role_names.items():
        entry = roles[role]
        if PurePosixPath(entry["path"]).name != member_name:
            _fail(f"indexed evidence role {role} has the wrong bundle member name")
        archived = inventory.get(member_name)
        if (
            archived is None
            or archived["bytes"] != entry["bytes"]
            or archived["sha256"] != entry["sha256"]
        ):
            _fail(f"indexed evidence role {role} differs from its bundle member")

    raw_bitstream_entry = roles["fpga-bitstream"]
    raw_bitstream = inventory.get("system_top.bit")
    packed_bitstream = inventory.get("packed-fpga.bit")
    bitstream_sidecar = inventory.get("system-top-bit.sha256")
    if (
        raw_bitstream is None
        or packed_bitstream is None
        or bitstream_sidecar is None
        or packed_bitstream["bytes"] != raw_bitstream["bytes"]
        or packed_bitstream["sha256"] != raw_bitstream["sha256"]
    ):
        _fail("packed DFU FPGA payload differs from the raw qualified bitstream")
    expected_bitstream_sidecar = f"{raw_bitstream['sha256']}  system_top.bit\n".encode()
    if bitstream_sidecar.get("payload") != expected_bitstream_sidecar:
        _fail("system-top-bit.sha256 is not an exact raw-bitstream sidecar")
    raw_bitstream_path = _member_path(
        root, raw_bitstream_entry["path"], name="raw FPGA bitstream"
    )
    current_bitstream_bytes, current_bitstream_sha256, _prefix = _hash_regular(
        raw_bitstream_path, name="raw FPGA bitstream"
    )
    if (
        current_bitstream_bytes != raw_bitstream["bytes"]
        or current_bitstream_sha256 != raw_bitstream["sha256"]
    ):
        _fail("raw FPGA bitstream changed after evidence indexing")
    xsa_entry = roles["xsa"]
    _verify_xsa_bitstream(
        _member_path(root, xsa_entry["path"], name="qualified XSA"),
        raw_bitstream_path,
        expected_xsa_bytes=xsa_entry["bytes"],
        expected_xsa_sha256=xsa_entry["sha256"],
        expected_bitstream_bytes=int(raw_bitstream["bytes"]),
        expected_bitstream_sha256=str(raw_bitstream["sha256"]),
    )

    manifest_name = PurePosixPath(index["source"]["manifest_path"]).name
    manifest_member = inventory.get(manifest_name)
    if manifest_member is None or manifest_member["sha256"] != manifest_sha256:
        _fail("indexed source manifest differs from the deployment bundle member")
    dfu_member = inventory.get(dfu_name)
    if (
        dfu_member is None
        or dfu_member["bytes"] != artifact["dfu_bytes"]
        or dfu_member["sha256"] != artifact["dfu_sha256"]
    ):
        _fail("indexed DFU/FIT bytes differ from the deployment bundle member")


def _write_absent(path: Path, payload: bytes, *, mode: int) -> None:
    if path.parent.is_symlink() or path.parent.resolve() != path.parent.absolute():
        _fail("output parent must be canonical and nonsymlinked")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError as error:
        raise EvidenceError(f"refusing to replace existing output: {path}") from error
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, mode)


def _manifest_values(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceError("source manifest is not strict UTF-8") from error
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            _fail(f"source manifest has a malformed line: {line}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or not value or key in values:
            _fail(f"source manifest key is empty or duplicate: {key}")
        values[key] = value
    return values


def _role_map(index: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {member["role"]: member for member in index["evidence"]["members"]}


def _resolve_local_source_lock(ref: str) -> tuple[str, str]:
    try:
        object_type = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-t", ref],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError(
            f"cannot resolve protected source lock {ref}: {error}"
        ) from error
    if object_type not in {"commit", "tag"} or _COMMIT.fullmatch(commit) is None:
        _fail("protected source lock is not a local Git tag resolving to a commit")
    return object_type, commit


def _committed_file_sha256(commit: str, relative: str) -> str:
    try:
        payload = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError(
            f"cannot read semantic verifier from indexed commit {commit}: {error}"
        ) from error
    return hashlib.sha256(payload).hexdigest()


def _pre_hardware_profile(stage: str, firmware_version: str) -> Mapping[str, str]:
    profile = PRE_HARDWARE_PROFILES.get((stage, firmware_version))
    if profile is None:
        _fail("firmware/stage pair is not an exact supported release profile")
    return profile


def _verify_profile_release(
    release: Mapping[str, object], *, stage: str
) -> Mapping[str, str]:
    firmware_version = _string(
        release.get("firmware_version"), name="profile firmware version"
    )
    profile = _pre_hardware_profile(stage, firmware_version)
    for key in ("hardware_model", "metadata_abi", "tandem_agc"):
        if release.get(key) != profile[key]:
            _fail(f"release {key} differs from the exact protected profile")
    return profile


def _verify_committed_source_manifest(
    *,
    stage: str,
    firmware_version: str,
    archived_relative: str,
    archived_sha256: str,
    commit: str,
) -> None:
    profile = _pre_hardware_profile(stage, firmware_version)
    basename = profile["manifest_basename"]
    if archived_relative != f"source/{basename}":
        _fail("source manifest archive path/name is not the protected canonical path")
    committed_sha256 = _committed_file_sha256(commit, f"manifests/{basename}")
    if archived_sha256 != committed_sha256:
        _fail("source manifest differs from the exact indexed Git commit")


def _verify_source_lock(payload: bytes, *, commit: str, expected_ref: str) -> None:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceError("source lock is not strict UTF-8") from error
    expected_prefix = f"schema={SOURCE_LOCK_SCHEMA}"
    if len(lines) != 3 or lines[0] != expected_prefix:
        _fail("source lock record shape/schema is not exact")
    fields = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    if set(fields) != {"ref", "commit"} or fields["commit"] != commit:
        _fail("source lock does not bind the indexed commit")
    if fields["ref"] != expected_ref:
        _fail(f"source lock ref is not exact: expected {expected_ref}")
    _object_type, resolved_commit = _resolve_local_source_lock(fields["ref"])
    if resolved_commit != commit:
        _fail("local protected source tag resolves to a different commit")


def _trusted_build_ref(firmware_version: str) -> str:
    matches = {
        profile["build_ref"]
        for (stage, version), profile in PRE_HARDWARE_PROFILES.items()
        if version == firmware_version
        and stage in {"candidate-pre-hardware", "final-pre-confirmation"}
    }
    if len(matches) != 1:
        _fail("firmware identity has no unique trusted protected build ref")
    return matches.pop()


def _verify_actions_run(
    payload: bytes,
    *,
    commit: str,
    run_id: int,
    run_attempt: int,
    firmware_version: str,
) -> None:
    run = _mapping(_decode_json(payload, name="Actions run"), name="Actions run")
    _exact_keys(
        run,
        {
            "schema",
            "repository",
            "workflow_path",
            "ref",
            "event",
            "id",
            "run_attempt",
            "head_sha",
            "status",
            "conclusion",
            "url",
        },
        name="Actions run",
    )
    expected_ref = _trusted_build_ref(firmware_version)
    if run != {
        "schema": ACTIONS_RUN_SCHEMA,
        "repository": "misko/plutosdr-fw",
        "workflow_path": ".github/workflows/firmware-main.yml",
        "ref": expected_ref,
        "event": "workflow_dispatch",
        "id": run_id,
        "run_attempt": run_attempt,
        "head_sha": commit,
        "status": "completed",
        "conclusion": "success",
        "url": f"https://github.com/misko/plutosdr-fw/actions/runs/{run_id}",
    }:
        _fail("Actions run is not the exact successful indexed build")


def _verify_ooc_status(payload: bytes, *, commit: str, manifest_sha: str) -> None:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceError("OOC status is not strict UTF-8") from error
    fields: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            _fail("OOC status contains a non-key/value line")
        key, value = line.split("=", 1)
        if not key or not value or key in fields:
            _fail("OOC status contains an empty or duplicate field")
        fields[key] = value
    expected = {
        "verdict": "PASS",
        "scope": "tandem_agc_axi_routed_ooc",
        "firmware_release_eligible": "false",
        "integrated_route_required": "true",
        "commit": commit,
        "evidence_manifest_sha256": manifest_sha,
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            _fail(f"OOC status field {key} is not exact")


def _verify_packed_versions(
    payload: bytes, *, firmware_version: str, manifest: Mapping[str, str]
) -> None:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceError("packed VERSIONS is not strict UTF-8") from error
    values: dict[str, str] = {}
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[0] not in values:
            values[fields[0]] = fields[1]
    expected = {
        "device-fw": firmware_version,
        "hdl": manifest.get("versions_hdl", ""),
        "buildroot": manifest.get("versions_buildroot", ""),
        "linux": manifest.get("versions_linux", ""),
        "u-boot-xlnx": manifest.get("versions_u_boot_xlnx", ""),
    }
    if any(not value for value in expected.values()) or any(
        values.get(key) != value for key, value in expected.items()
    ):
        _fail("packed VERSIONS does not match release/source identities")


def _verify_integrated_verdict(
    payload: bytes,
    *,
    commit: str,
    manifest_path: str,
    manifest_bytes: int,
    manifest_sha: str,
    roles: Mapping[str, Mapping[str, Any]],
) -> None:
    verdict = _mapping(
        _decode_json(payload, name="integrated verdict"), name="integrated verdict"
    )
    _exact_keys(
        verdict,
        {
            "schema",
            "verdict",
            "source_commit",
            "source_manifest_sha256",
            "routed_dcp_sha256",
            "waiver_inventory_sha256",
            "validated_inputs",
            "firmware_release_eligible",
        },
        name="integrated verdict",
    )
    validated_inputs: list[dict[str, object]] = []
    for role in INTEGRATED_VALIDATED_ROLES:
        if role == "source-manifest":
            validated_inputs.append(
                {
                    "role": role,
                    "path": PurePosixPath(manifest_path).name,
                    "bytes": manifest_bytes,
                    "sha256": manifest_sha,
                }
            )
            continue
        member = roles[role]
        validated_inputs.append(
            {
                "role": role,
                "path": PurePosixPath(str(member["path"])).name,
                "bytes": member["bytes"],
                "sha256": member["sha256"],
            }
        )
    expected = {
        "schema": INTEGRATED_VERDICT_SCHEMA,
        "verdict": "PASS",
        "source_commit": commit,
        "source_manifest_sha256": manifest_sha,
        "routed_dcp_sha256": roles["routed-dcp"]["sha256"],
        "waiver_inventory_sha256": roles["waiver-inventory"]["sha256"],
        "validated_inputs": validated_inputs,
        "firmware_release_eligible": True,
    }
    if verdict != expected:
        _fail("integrated verdict is not exact or release-eligible")


def _verify_attestation_record(
    payload: bytes,
    *,
    commit: str,
    run_id: int,
    run_attempt: int,
    bundle_sha: str,
    bundle_name: str,
    firmware_version: str,
) -> None:
    record = _mapping(
        _decode_json(payload, name="attestation record"), name="attestation record"
    )
    subject = _mapping(record.get("subject"), name="attestation subject")
    _exact_keys(subject, {"name", "sha256"}, name="attestation subject")
    common = {
        "repository": "misko/plutosdr-fw",
        "head_sha": commit,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "bundle_sha256": bundle_sha,
        "subject": {"name": bundle_name, "sha256": bundle_sha},
    }
    if record.get("schema") == ATTESTATION_NOT_PERFORMED_SCHEMA:
        _exact_keys(
            record,
            {
                "schema",
                *common,
                "verification_performed",
                "reason",
            },
            name="attestation record",
        )
        expected_not_performed = {
            "schema": ATTESTATION_NOT_PERFORMED_SCHEMA,
            **common,
            "verification_performed": False,
            "reason": "single-owner-operator-trust-model",
        }
        if record != expected_not_performed:
            _fail("attestation not-performed record is not exact")
        return
    _exact_keys(
        record,
        {
            "schema",
            *common,
            "command",
            "provenance",
            "tool_output",
            "verified",
            "exit_code",
        },
        name="attestation record",
    )
    command = record["command"]
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        _fail("attestation command must be an argv array")
    normalized_command = [
        _string(argument, name=f"attestation command argument {index}")
        for index, argument in enumerate(command)
    ]
    expected_command = [
        "gh",
        "attestation",
        "verify",
        bundle_name,
        "--repo",
        "misko/plutosdr-fw",
        "--format",
        "json",
    ]
    provenance = _mapping(record["provenance"], name="attestation provenance")
    _exact_keys(
        provenance,
        {
            "repository",
            "workflow_path",
            "workflow_ref",
            "source_commit",
            "run_id",
            "run_attempt",
        },
        name="attestation provenance",
    )
    tool_output = record["tool_output"]
    if not isinstance(tool_output, (Mapping, Sequence)) or isinstance(
        tool_output, (str, bytes)
    ):
        _fail("attestation record does not contain machine-readable tool output")

    def contains_scalar(value: object, expected_scalar: object) -> bool:
        if value == expected_scalar and type(value) is type(expected_scalar):
            return True
        if isinstance(value, Mapping):
            return any(
                contains_scalar(item, expected_scalar) for item in value.values()
            )
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return any(contains_scalar(item, expected_scalar) for item in value)
        return False

    for scalar in (bundle_sha, "misko/plutosdr-fw", commit, run_id, run_attempt):
        if not contains_scalar(tool_output, scalar):
            _fail(
                "attestation tool output omits an indexed subject/provenance identity"
            )
    expected = {
        "schema": ATTESTATION_SCHEMA,
        **common,
        "command": expected_command,
        "provenance": {
            "repository": "misko/plutosdr-fw",
            "workflow_path": ".github/workflows/firmware-main.yml",
            "workflow_ref": (
                ".github/workflows/firmware-main.yml@"
                f"{_trusted_build_ref(firmware_version)}"
            ),
            "source_commit": commit,
            "run_id": run_id,
            "run_attempt": run_attempt,
        },
        "tool_output": tool_output,
        "verified": True,
        "exit_code": 0,
    }
    if normalized_command != expected_command or record != expected:
        _fail("attestation record is not an exact successful verification")


def _verify_artifact_index(index_path: Path, *, expected_stage: str) -> dict[str, Any]:
    index_path = index_path.absolute()
    if not index_path.is_file() or index_path.is_symlink():
        _fail("candidate index must be a regular nonsymlink file")
    root = _canonical_root(index_path.parent)
    index_payload = _read_small(index_path, name="candidate index")
    try:
        index = validate_artifact_index(
            _decode_json(index_payload, name="candidate index")
        )
    except CandidateBindingError as error:
        raise EvidenceError(str(error)) from error
    if index["stage"] != expected_stage:
        _fail("candidate index stage differs from the requested verification stage")
    profile = _verify_profile_release(index["release"], stage=expected_stage)
    if tuple(item["path"] for item in index["harness"]["files"]) != (
        ARTIFACT_HARNESS_PATHS
    ):
        _fail("candidate index harness is not the exact release/lifecycle superset")

    sidecar = index_path.with_suffix(index_path.suffix + ".sha256")
    sidecar_payload = _read_small(sidecar, name="candidate index sidecar")
    index_sha = hashlib.sha256(index_payload).hexdigest()
    expected_sidecar = f"{index_sha}  {index_path.name}\n".encode()
    if sidecar_payload != expected_sidecar:
        _fail("candidate index sidecar is not exact")

    source = index["source"]
    manifest_path = _member_path(root, source["manifest_path"], name="source manifest")
    _manifest_bytes, manifest_sha, _ = _hash_regular(
        manifest_path, name="source manifest", maximum=MAX_JSON_BYTES
    )
    if manifest_sha != source["manifest_sha256"]:
        _fail("source manifest bytes differ from the candidate index")
    _verify_committed_source_manifest(
        stage=expected_stage,
        firmware_version=index["release"]["firmware_version"],
        archived_relative=source["manifest_path"],
        archived_sha256=manifest_sha,
        commit=source["commit"],
    )
    manifest_payload = _read_small(manifest_path, name="source manifest")
    manifest = _manifest_values(manifest_payload)
    if (
        manifest.get("schema") != "plutosdr-fw.source-manifest"
        or manifest.get("schema_version") != "1"
        or manifest.get("release_state") != "candidate"
    ):
        _fail("source manifest is not an exact candidate source manifest")

    artifact = index["artifact"]
    dfu_path = _member_path(root, artifact["dfu_path"], name="firmware DFU")
    dfu_bytes, dfu_sha, fit_sha = _hash_regular(
        dfu_path,
        name="firmware DFU",
        prefix_bytes=artifact["fit_bytes"],
    )
    if (
        dfu_bytes != artifact["dfu_bytes"]
        or dfu_sha != artifact["dfu_sha256"]
        or fit_sha != artifact["fit_sha256"]
        or artifact["fit_bytes"] + 16 != artifact["dfu_bytes"]
    ):
        _fail("DFU/FIT bytes differ from the candidate index")

    seen_paths = {source["manifest_path"], artifact["dfu_path"]}
    harness_digests: dict[str, str] = {}
    for entry in index["harness"]["files"]:
        if entry["path"] in seen_paths:
            _fail("candidate index aliases a harness/input path")
        seen_paths.add(entry["path"])
        path = _member_path(root, entry["path"], name=f"harness {entry['path']}")
        _bytes, digest, _ = _hash_regular(path, name=f"harness {entry['path']}")
        if digest != entry["sha256"]:
            _fail(f"harness file changed: {entry['path']}")
        harness_digests[entry["path"]] = digest
    semantic_digest = harness_digests.get(SEMANTIC_VERIFIER_HARNESS_PATH)
    if semantic_digest is None:
        _fail("artifact index omits the semantic release-evidence verifier")
    _live_bytes, live_digest, _prefix = _hash_regular(
        ROOT / SEMANTIC_VERIFIER_HARNESS_PATH,
        name="live semantic release-evidence verifier",
        maximum=MAX_JSON_BYTES,
    )
    committed_digest = _committed_file_sha256(
        source["commit"], SEMANTIC_VERIFIER_HARNESS_PATH
    )
    if semantic_digest != live_digest or semantic_digest != committed_digest:
        _fail("semantic release-evidence verifier is not exact live committed source")
    release_verifier_digest = harness_digests.get(RELEASE_VERIFIER_HARNESS_PATH)
    if release_verifier_digest is None:
        _fail("artifact index omits the binary release verifier")
    _live_bytes, live_release_verifier_digest, _prefix = _hash_regular(
        ROOT / RELEASE_VERIFIER_HARNESS_PATH,
        name="live binary release verifier",
        maximum=MAX_JSON_BYTES,
    )
    committed_release_verifier_digest = _committed_file_sha256(
        source["commit"], RELEASE_VERIFIER_HARNESS_PATH
    )
    if (
        release_verifier_digest != live_release_verifier_digest
        or release_verifier_digest != committed_release_verifier_digest
    ):
        _fail("binary release verifier is not exact live committed indexed source")

    roles = _role_map(index)
    role_payloads: dict[str, bytes] = {}
    for role, entry in roles.items():
        if entry["path"] in seen_paths:
            _fail("candidate index aliases an evidence/input path")
        seen_paths.add(entry["path"])
        path = _member_path(root, entry["path"], name=f"evidence role {role}")
        size, digest, _ = _hash_regular(path, name=f"evidence role {role}")
        if size != entry["bytes"] or digest != entry["sha256"]:
            _fail(f"evidence role {role} differs from the candidate index")
        if role in {
            "actions-run",
            "attestation-verification",
            "integrated-verdict",
            "ooc-evidence-manifest",
            "ooc-status",
            "packed-versions",
            "source-lock",
        }:
            role_payloads[role] = _read_small(path, name=f"evidence role {role}")

    commit = source["commit"]
    build = index["build"]
    _verify_source_lock(
        role_payloads["source-lock"],
        commit=commit,
        expected_ref=profile["source_lock_ref"],
    )
    _verify_actions_run(
        role_payloads["actions-run"],
        commit=commit,
        run_id=build["run_id"],
        run_attempt=build["run_attempt"],
        firmware_version=index["release"]["firmware_version"],
    )
    _verify_ooc_status(
        role_payloads["ooc-status"],
        commit=commit,
        manifest_sha=roles["ooc-evidence-manifest"]["sha256"],
    )
    _verify_packed_versions(
        role_payloads["packed-versions"],
        firmware_version=index["release"]["firmware_version"],
        manifest=manifest,
    )
    _verify_integrated_verdict(
        role_payloads["integrated-verdict"],
        commit=commit,
        manifest_path=source["manifest_path"],
        manifest_bytes=len(manifest_payload),
        manifest_sha=source["manifest_sha256"],
        roles=roles,
    )
    _verify_attestation_record(
        role_payloads["attestation-verification"],
        commit=commit,
        run_id=build["run_id"],
        run_attempt=build["run_attempt"],
        bundle_sha=roles["bundle"]["sha256"],
        bundle_name=PurePosixPath(roles["bundle"]["path"]).name,
        firmware_version=index["release"]["firmware_version"],
    )
    _verify_bundle_contract(
        root,
        index=index,
        roles=roles,
        manifest_sha256=manifest_sha,
    )
    return index


def _read_index_record(
    index_path: Path, *, name: str
) -> tuple[Path, bytes, Mapping[str, object], str]:
    absolute = index_path.absolute()
    if not absolute.is_file() or absolute.is_symlink():
        _fail(f"{name} must be a regular nonsymlink file")
    root = _canonical_root(absolute.parent)
    payload = _read_small(absolute, name=name)
    record = _mapping(_decode_json(payload, name=name), name=name)
    digest = hashlib.sha256(payload).hexdigest()
    sidecar = absolute.with_suffix(absolute.suffix + ".sha256")
    if _read_small(sidecar, name=f"{name} sidecar") != (
        f"{digest}  {absolute.name}\n".encode()
    ):
        _fail(f"{name} sidecar is not exact")
    return root, payload, record, digest


def _index_source_commit(index: Mapping[str, Any]) -> str:
    stage = index.get("stage")
    if stage in {"candidate-pre-hardware", "final-pre-confirmation"}:
        return str(index["source"]["commit"])
    if stage == "candidate-qualified":
        return str(index["source_commit"])
    if stage == "final-qualification-policy":
        return str(index["final_source_commit"])
    if stage in {"final-qualified", "published-release"}:
        return str(index["source_commit"])
    _fail("index stage has no defined source lineage")


def _capture_index_reference(
    root: Path, index_path: Path, *, expected_stage: str, name: str
) -> tuple[dict[str, object], dict[str, Any]]:
    absolute = index_path.absolute()
    try:
        relative = absolute.relative_to(root).as_posix()
    except ValueError as error:
        raise EvidenceError(f"{name} must be inside the archive root") from error
    canonical_path = _member_path(root, relative, name=name)
    verified = verify_index(canonical_path, expected_stage=expected_stage)
    payload = _read_small(canonical_path, name=name)
    return (
        {
            "stage": expected_stage,
            "path": relative,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        verified,
    )


def _verify_index_reference(
    root: Path,
    value: object,
    *,
    expected_stage: str,
    name: str,
) -> tuple[dict[str, Any], Path]:
    reference = _mapping(value, name=name)
    _exact_keys(reference, {"stage", "path", "bytes", "sha256"}, name=name)
    if reference["stage"] != expected_stage:
        _fail(f"{name} stage is not {expected_stage}")
    relative = _relative(reference["path"], name=f"{name} path")
    expected_bytes = _positive_int(reference["bytes"], name=f"{name} bytes")
    expected_sha = _sha(reference["sha256"], name=f"{name} SHA-256")
    path = _member_path(root, relative, name=name)
    observed_bytes, observed_sha, _prefix = _hash_regular(path, name=name)
    if observed_bytes != expected_bytes or observed_sha != expected_sha:
        _fail(f"{name} bytes differ from the lineage reference")
    verified = verify_index(path, expected_stage=expected_stage)
    return verified, path


def _capture_member(root: Path, relative: str, *, name: str) -> dict[str, object]:
    canonical = _relative(relative, name=f"{name} path")
    path = _member_path(root, canonical, name=name)
    size, digest, _prefix = _hash_regular(path, name=name)
    return {"path": canonical, "bytes": size, "sha256": digest}


def _verify_member(
    root: Path, value: object, *, name: str
) -> tuple[dict[str, object], Path]:
    member = _mapping(value, name=name)
    _exact_keys(member, {"path", "bytes", "sha256"}, name=name)
    relative = _relative(member["path"], name=f"{name} path")
    expected_bytes = _positive_int(member["bytes"], name=f"{name} bytes")
    expected_sha = _sha(member["sha256"], name=f"{name} SHA-256")
    path = _member_path(root, relative, name=name)
    size, digest, _prefix = _hash_regular(path, name=name)
    if size != expected_bytes or digest != expected_sha:
        _fail(f"{name} differs from its immutable descriptor")
    return dict(member), path


def _scan_tree_files(root: Path, relative_root: str) -> list[str]:
    canonical = _relative(relative_root, name="inventory root")
    start = _member_path(root, canonical, name="inventory root")
    if not start.is_dir():
        _fail(f"inventory root is not a directory: {canonical}")
    files: list[str] = []

    def visit(directory: Path) -> None:
        before = directory.stat(follow_symlinks=False)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.geteuid()
            or mode & 0o022
        ):
            _fail(f"evidence directory has unsafe metadata: {directory}")
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise EvidenceError(
                f"cannot inventory evidence directory: {error}"
            ) from error
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            path = Path(entry.path)
            if stat.S_ISLNK(metadata.st_mode):
                _fail(f"evidence inventory contains symlink {path}")
            if stat.S_ISDIR(metadata.st_mode):
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                try:
                    files.append(path.relative_to(root).as_posix())
                except ValueError as error:
                    raise EvidenceError(
                        "evidence inventory escaped archive root"
                    ) from error
            else:
                _fail(f"evidence inventory contains special file {path}")
        after = directory.stat(follow_symlinks=False)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(f"evidence directory changed during inventory: {directory}")

    visit(start)
    if files != sorted(files) or len(files) != len(set(files)):
        _fail("evidence file inventory is not unique and sorted")
    return files


def _phase_serials(root: Path, phases: Sequence[str]) -> tuple[str, ...]:
    hardware = _member_path(root, "hardware", name="hardware evidence root")
    if not hardware.is_dir():
        _fail("hardware evidence root is not a directory")
    top_entries = sorted(os.scandir(hardware), key=lambda entry: entry.name)
    top_names = {entry.name for entry in top_entries}
    required = set(phases)
    if not required.issubset(top_names) or not (top_names - required).issubset(
        _OPTIONAL_CAMPAIGN_DIAGNOSTIC_PHASES
    ):
        _fail("hardware evidence phase inventory is mixed or incomplete")
    serial_sets: list[set[str]] = []
    for phase in phases:
        phase_root = _member_path(root, f"hardware/{phase}", name=f"{phase} root")
        entries = sorted(os.scandir(phase_root), key=lambda entry: entry.name)
        serials: set[str] = set()
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            serial = _safe_id(entry.name, name=f"{phase} serial")
            if not stat.S_ISDIR(metadata.st_mode) or entry.is_symlink():
                _fail(f"{phase} evidence is not serial-scoped by directory")
            serials.add(serial)
        serial_sets.append(serials)
    if not serial_sets or any(values != serial_sets[0] for values in serial_sets[1:]):
        _fail("hardware evidence phases cover different radio serials")
    serials = tuple(sorted(serial_sets[0]))
    if serials != RELEASE_RADIO_SERIALS:
        _fail("hardware qualification serials differ from the exact RC32 scope")
    return serials


def _read_json_member(path: Path, *, name: str) -> Mapping[str, object]:
    return _mapping(
        _decode_json(_read_small(path, name=name), name=name),
        name=name,
    )


def _is_gain_timeline_release(artifact_index: Mapping[str, Any]) -> bool:
    release = _mapping(artifact_index.get("release"), name="artifact release")
    return release.get("firmware_version") in {
        GAIN_TIMELINE_CANDIDATE_FIRMWARE_VERSION,
        GAIN_TIMELINE_FINAL_FIRMWARE_VERSION,
    }


def _private_contract_payload(path: Path, *, name: str) -> bytes:
    try:
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise EvidenceError(f"{name} cannot be inspected: {error}") from error
    if mode != 0o600:
        _fail(f"{name} mode must be exactly 0600")
    return _read_small(path, name=name)


def _utc_timestamp(value: object, *, name: str) -> datetime:
    text = _string(value, name=name, maximum=64)
    if not text.endswith("Z"):
        _fail(f"{name} must be canonical UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise EvidenceError(f"{name} is not ISO-8601 UTC") from error
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        _fail(f"{name} is not UTC")
    return parsed


def _finite_number(value: object, *, name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{name} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed) or (positive and parsed <= 0):
        _fail(f"{name} must be a finite{' positive' if positive else ''} number")
    return parsed


def _contract_identity(
    value: object,
    *,
    payload: bytes,
    expected_path: Path,
    name: str,
) -> None:
    identity = _mapping(value, name=name)
    _exact_keys(identity, {"path", "bytes", "sha256"}, name=name)
    raw_path = _string(identity["path"], name=f"{name} path", maximum=4096)
    path = PurePosixPath(raw_path)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or Path(raw_path) != expected_path.absolute()
    ):
        _fail(f"{name} path is not the retained contract path")
    if (
        identity["bytes"] != len(payload)
        or identity["sha256"] != hashlib.sha256(payload).hexdigest()
    ):
        _fail(f"{name} does not bind the retained bytes")


def _gain_timeline_cases() -> tuple[dict[str, object], ...]:
    tiers = (
        ("regression", 200, 1),
        ("regression", 200, 2),
        ("regression", 600, 1),
        ("regression", 600, 2),
        ("soak", 5_000, 1),
    )
    cases: list[dict[str, object]] = []

    def append_matrix(transport: str) -> None:
        for buffering in ("ordinary", "ring-200mb"):
            for tandem_mode in ("hold", "auto"):
                layouts = (
                    ("single-rx0", "dual")
                    if buffering == "ordinary"
                    else ("single-rx0",)
                )
                for layout in layouts:
                    for tier, frames, repetition in tiers:
                        cases.append(
                            {
                                "profile": "matrix",
                                "transport": transport,
                                "buffering": buffering,
                                "tandem_mode": tandem_mode,
                                "layout": layout,
                                "tier": tier,
                                "sample_rate_hz": 20_000_000,
                                "rf_bandwidth_hz": 20_000_000,
                                "samples_per_channel": [262_144],
                                "frames": frames,
                                "kernel_buffers": 4,
                                "repetition": repetition,
                            }
                        )

    cases.extend(
        {
            "profile": "issue-49-usb-enodata",
            "transport": "usb",
            "buffering": "ordinary",
            "tandem_mode": "hold",
            "layout": "dual",
            "tier": "regression",
            "sample_rate_hz": 1_000_000,
            "rf_bandwidth_hz": 1_000_000,
            "samples_per_channel": [100_000],
            "frames": 100,
            "kernel_buffers": 8,
            "repetition": repetition,
        }
        for repetition in range(1, 65)
    )
    append_matrix("usb")
    for sample_rate_hz in (2_500_000, 3_000_000, 5_000_000):
        cases.extend(
            {
                "profile": "issue-54-ip-max",
                "transport": "physical-ip",
                "buffering": "ordinary",
                "tandem_mode": "hold",
                "layout": "dual",
                "tier": "regression",
                "sample_rate_hz": sample_rate_hz,
                "rf_bandwidth_hz": sample_rate_hz,
                "samples_per_channel": [4_194_304],
                "frames": 6,
                "kernel_buffers": 4,
                "repetition": repetition,
            }
            for repetition in range(1, 21)
        )
        cases.append(
            {
                "profile": "issue-54-ip-ladder",
                "transport": "physical-ip",
                "buffering": "ordinary",
                "tandem_mode": "hold",
                "layout": "dual",
                "tier": "regression",
                "sample_rate_hz": sample_rate_hz,
                "rf_bandwidth_hz": sample_rate_hz,
                "samples_per_channel": [
                    4_194_304,
                    2_097_152,
                    1_048_576,
                    524_288,
                ],
                "frames": 6,
                "kernel_buffers": 4,
                "repetition": 1,
            }
        )
    append_matrix("physical-ip")
    if len(cases) != _GAIN_TIMELINE_CASE_COUNT or any(
        case["buffering"] == "ring-200mb" and case["layout"] == "dual" for case in cases
    ):
        raise AssertionError("gain-timeline qualification cases are not canonical")
    return tuple(cases)


_GAIN_TIMELINE_CASES = _gain_timeline_cases()


def _verify_gain_timeline_plan(
    path: Path,
    *,
    operation_path: Path,
    candidate_path: Path,
    report_path: Path,
    serial: str,
    physical_ip: str,
) -> tuple[Mapping[str, object], bytes]:
    payload = _private_contract_payload(path, name=f"qualification plan {serial}")
    plan = _mapping(
        _decode_json(payload, name=f"qualification plan {serial}"),
        name=f"qualification plan {serial}",
    )
    _exact_keys(
        plan,
        {
            "schema",
            "schema_version",
            "campaign_id",
            "created_at",
            "operation_plan",
            "candidate_plan",
            "serial",
            "physical_ip",
            "report_path",
            "sample_rate_hz",
            "rf_bandwidth_hz",
            "samples_per_channel",
            "kernel_buffers",
            "ddr_ring_iq_bytes",
            "regression_frame_counts",
            "regression_repetitions",
            "soak_frame_count",
            "ordinary_layouts",
            "ring_layouts",
            "planned_case_count",
            "confirmation_phrase",
            "hardware_accessed",
        },
        name=f"qualification plan {serial}",
    )
    campaign_id = _string(
        plan["campaign_id"], name=f"qualification campaign ID {serial}", maximum=32
    )
    if re.fullmatch(r"[0-9a-f]{32}", campaign_id) is None:
        _fail("qualification campaign ID is malformed")
    _utc_timestamp(plan["created_at"], name=f"qualification plan time {serial}")
    operation_payload = _private_contract_payload(
        operation_path, name=f"operation plan {serial}"
    )
    candidate_payload = _private_contract_payload(
        candidate_path, name=f"candidate plan {serial}"
    )
    _contract_identity(
        plan["operation_plan"],
        payload=operation_payload,
        expected_path=operation_path,
        name=f"qualification operation identity {serial}",
    )
    _contract_identity(
        plan["candidate_plan"],
        payload=candidate_payload,
        expected_path=candidate_path,
        name=f"qualification candidate identity {serial}",
    )
    raw_report_path = _string(
        plan["report_path"], name=f"qualification report path {serial}", maximum=4096
    )
    if Path(raw_report_path) != report_path.absolute():
        _fail("qualification plan does not reserve the canonical archived report path")
    expected = {
        "schema": _GAIN_TIMELINE_PLAN_SCHEMA,
        "schema_version": 2,
        "serial": serial,
        "physical_ip": physical_ip,
        "sample_rate_hz": _GAIN_TIMELINE_SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": _GAIN_TIMELINE_SAMPLE_RATE_HZ,
        "samples_per_channel": _GAIN_TIMELINE_SAMPLES_PER_CHANNEL,
        "kernel_buffers": _GAIN_TIMELINE_KERNEL_BUFFERS,
        "ddr_ring_iq_bytes": _GAIN_TIMELINE_RING_IQ_BYTES,
        "regression_frame_counts": [200, 600],
        "regression_repetitions": 2,
        "soak_frame_count": 5_000,
        "ordinary_layouts": ["single-rx0", "dual"],
        "ring_layouts": ["single-rx0"],
        "planned_case_count": _GAIN_TIMELINE_CASE_COUNT,
        "confirmation_phrase": f"QUALIFY GAIN TIMELINE {serial} {campaign_id}",
        "hardware_accessed": False,
    }
    for key, expected_value in expected.items():
        if plan[key] != expected_value:
            _fail(f"qualification plan {key} is not canonical")
    return plan, payload


def _verify_gain_timeline_ring_status(
    value: object,
    *,
    samples_per_channel: int,
    receiver_count: int,
    frames: int,
    last_sample: int,
) -> None:
    status = _mapping(value, name="qualification DDR ring status")
    _exact_keys(
        status,
        {
            "version",
            "state",
            "terminal_reason",
            "error_code",
            "requested_capacity_iq_bytes",
            "admitted_capacity_iq_bytes",
            "target_frames",
            "produced_frames",
            "consumed_frames",
            "high_water_frames",
            "wrap_count",
            "producer_position",
            "consumer_position",
            "last_contiguous_sample_sequence",
            "first_unavailable_sample_sequence",
            "failure_frame_index",
            "failure_sample_sequence",
        },
        name="qualification DDR ring status",
    )
    frame_bytes = samples_per_channel * receiver_count * 4
    admitted = (_GAIN_TIMELINE_RING_IQ_BYTES // frame_bytes) * frame_bytes
    capacity_frames = admitted // frame_bytes
    expected = {
        "version": 2,
        "state": "complete",
        "terminal_reason": "target_complete",
        "error_code": 0,
        "requested_capacity_iq_bytes": _GAIN_TIMELINE_RING_IQ_BYTES,
        "admitted_capacity_iq_bytes": admitted,
        "target_frames": frames,
        "produced_frames": frames,
        "consumed_frames": frames,
        "wrap_count": frames // capacity_frames,
        "producer_position": frames % capacity_frames,
        "consumer_position": frames % capacity_frames,
        "failure_frame_index": None,
        "failure_sample_sequence": None,
    }
    for key, expected_value in expected.items():
        if status[key] != expected_value:
            _fail(f"qualification DDR ring {key} does not close")
    high_water = _positive_int(
        status["high_water_frames"], name="qualification DDR ring high-water frames"
    )
    if high_water > min(frames, capacity_frames):
        _fail("qualification DDR ring high-water mark exceeds its finite capacity")
    contiguous = _nonnegative_int(
        status["last_contiguous_sample_sequence"],
        name="qualification DDR ring contiguous boundary",
    )
    unavailable = status["first_unavailable_sample_sequence"]
    if unavailable is not None or contiguous != last_sample:
        _fail("qualification DDR ring status contradicts the gapless metadata span")


def _verify_gain_timeline_ladder(
    value: object,
    *,
    case: Mapping[str, object],
    artifact_index: Mapping[str, Any],
    serial: str,
    physical_ip: str,
    usb_uri: str,
) -> None:
    report = _mapping(value, name="qualification ladder report")
    _exact_keys(
        report,
        {
            "serial",
            "uri",
            "transport",
            "model",
            "firmware_version",
            "metadata_abi",
            "sample_rate_hz",
            "rf_bandwidth_hz",
            "channels",
            "kernel_buffers",
            "tandem_mode",
            "acceptance_mode",
            "iq_decoder",
            "ddr_burst_enabled",
            "ddr_ring_requested_iq_bytes",
            "minimum_observed_fraction",
            "cells",
            "failures",
            "largest_passing_samples_per_channel",
            "original_settings_restored",
            "continuity_claim",
        },
        name="qualification ladder report",
    )
    is_usb = case["transport"] == "usb"
    is_ring = case["buffering"] == "ring-200mb"
    channels = [0] if case["layout"] == "single-rx0" else [0, 1]
    raw_sample_ladder = case["samples_per_channel"]
    if not isinstance(raw_sample_ladder, list) or not raw_sample_ladder:
        raise AssertionError("canonical qualification case has no sample ladder")
    sample_ladder = tuple(int(item) for item in raw_sample_ladder)
    sample_rate_hz = int(case["sample_rate_hz"])
    rf_bandwidth_hz = int(case["rf_bandwidth_hz"])
    kernel_buffers = int(case["kernel_buffers"])
    expected = {
        "serial": serial,
        "uri": usb_uri if is_usb else f"ip:{physical_ip}",
        "transport": "iio_usb" if is_usb else "iio_ip",
        "model": artifact_index["release"]["hardware_model"],
        "firmware_version": artifact_index["release"]["firmware_version"],
        "metadata_abi": 4,
        "sample_rate_hz": sample_rate_hz,
        "rf_bandwidth_hz": rf_bandwidth_hz,
        "channels": channels,
        "kernel_buffers": kernel_buffers,
        "tandem_mode": case["tandem_mode"],
        "acceptance_mode": "continuity",
        "iq_decoder": "pyadi",
        "ddr_burst_enabled": False,
        "ddr_ring_requested_iq_bytes": (_GAIN_TIMELINE_RING_IQ_BYTES if is_ring else 0),
        "minimum_observed_fraction": 0.95,
        "failures": [],
        "largest_passing_samples_per_channel": sample_ladder[0],
        "original_settings_restored": True,
        "continuity_claim": (
            "passed binds FPGA counter coverage >=95%, zero overflow, exact selected-RX "
            "geometry, and at least four kernel buffers; it is not inferred from host "
            "throughput"
        ),
    }
    for key, expected_value in expected.items():
        if report[key] != expected_value:
            _fail(f"qualification ladder {key} is not exact")
    cells = report["cells"]
    if (
        not isinstance(cells, Sequence)
        or isinstance(cells, (str, bytes))
        or len(cells) != len(sample_ladder)
    ):
        _fail("qualification ladder does not contain its exact requested cells")
    frames = int(case["frames"])
    for cell_index, (raw_cell, samples_per_channel) in enumerate(
        zip(cells, sample_ladder, strict=True)
    ):
        cell = _mapping(raw_cell, name=f"qualification ladder cell {cell_index}")
        _exact_keys(
            cell,
            {
                "samples_per_channel",
                "requested_frames",
                "observed_frames",
                "observed_sample_count",
                "device_span_sample_count",
                "first_sample_sequence",
                "last_sample_sequence_exclusive",
                "missing_sample_count",
                "gap_count",
                "overflow_count",
                "iq_bytes",
                "first_frame_latency_seconds",
                "elapsed_seconds",
                "achieved_payload_mbps",
                "achieved_payload_mibps",
                "observed_fraction",
                "tandem_metadata_frames",
                "authoritative_gain_timeline_frames",
                "gain_observation_interval_samples",
                "gain_observation_count",
                "gain_observation_overflow_count",
                "gain_event_count",
                "gain_event_overflow_count",
                "ddr_burst_requested_iq_bytes",
                "ddr_burst_admitted_iq_bytes",
                "ddr_burst_frames",
                "ddr_ring_status",
                "ddr_ring_prefix_frames",
                "ddr_ring_prefix_iq_bytes",
                "ddr_ring_prefix_contiguous",
                "passed",
            },
            name=f"qualification ladder cell {cell_index}",
        )
        observed_samples = frames * samples_per_channel
        first = _nonnegative_int(
            cell["first_sample_sequence"],
            name="qualification first sample sequence",
        )
        last = _positive_int(
            cell["last_sample_sequence_exclusive"],
            name="qualification last sample sequence",
        )
        _positive_int(
            cell["gain_observation_interval_samples"],
            name="qualification gain observation interval",
        )
        exact_cell = {
            "samples_per_channel": samples_per_channel,
            "requested_frames": frames,
            "observed_frames": frames,
            "observed_sample_count": observed_samples,
            "device_span_sample_count": observed_samples,
            "last_sample_sequence_exclusive": first + observed_samples,
            "missing_sample_count": 0,
            "gap_count": 0,
            "overflow_count": 0,
            "iq_bytes": observed_samples * len(channels) * 4,
            "observed_fraction": 1.0,
            "tandem_metadata_frames": frames,
            "authoritative_gain_timeline_frames": frames,
            "gain_observation_overflow_count": 0,
            "gain_event_overflow_count": 0,
            "ddr_burst_requested_iq_bytes": 0,
            "ddr_burst_admitted_iq_bytes": 0,
            "ddr_burst_frames": 0,
            "passed": True,
        }
        for key, expected_value in exact_cell.items():
            if cell[key] != expected_value:
                _fail(f"qualification ladder cell {key} does not close")
        for key in ("gain_observation_count", "gain_event_count"):
            _nonnegative_int(cell[key], name=f"qualification ladder cell {key}")
        elapsed = _finite_number(
            cell["elapsed_seconds"],
            name="qualification elapsed seconds",
            positive=True,
        )
        first_frame_latency = _finite_number(
            cell["first_frame_latency_seconds"],
            name="qualification first-frame latency seconds",
            positive=True,
        )
        maximum_first_frame_latency = 1.0 + 8.0 * samples_per_channel / sample_rate_hz
        if (
            first_frame_latency > elapsed
            or first_frame_latency > maximum_first_frame_latency
        ):
            _fail("qualification first frame was not delivered promptly")
        mbps = _finite_number(
            cell["achieved_payload_mbps"],
            name="qualification decimal throughput",
            positive=True,
        )
        mibps = _finite_number(
            cell["achieved_payload_mibps"],
            name="qualification binary throughput",
            positive=True,
        )
        iq_bytes = int(exact_cell["iq_bytes"])
        if (
            abs(mbps - iq_bytes / elapsed / 1_000_000) > 1e-9
            or abs(mibps - iq_bytes / elapsed / (1024 * 1024)) > 1e-9
        ):
            _fail("qualification ladder throughput arithmetic does not close")
        if is_ring:
            frame_bytes = samples_per_channel * len(channels) * 4
            if (
                cell["ddr_ring_prefix_frames"] != frames
                or cell["ddr_ring_prefix_iq_bytes"] != frames * frame_bytes
                or cell["ddr_ring_prefix_contiguous"] is not True
                or cell["ddr_ring_status"] is None
            ):
                _fail("qualification DDR ring initial contiguous stream does not close")
            _verify_gain_timeline_ring_status(
                cell["ddr_ring_status"],
                samples_per_channel=samples_per_channel,
                receiver_count=len(channels),
                frames=frames,
                last_sample=last,
            )
        elif (
            cell["ddr_ring_status"] is not None
            or cell["ddr_ring_prefix_frames"] != 0
            or cell["ddr_ring_prefix_iq_bytes"] != 0
            or cell["ddr_ring_prefix_contiguous"] is not False
        ):
            _fail("ordinary qualification cell contains DDR ring evidence")


def _verify_gain_timeline_report(
    path: Path,
    *,
    plan_path: Path,
    operation_path: Path,
    candidate_path: Path,
    receipt_path: Path,
    artifact_index: Mapping[str, Any],
    serial: str,
    physical_ip: str,
) -> None:
    plan, plan_payload = _verify_gain_timeline_plan(
        plan_path,
        operation_path=operation_path,
        candidate_path=candidate_path,
        report_path=path,
        serial=serial,
        physical_ip=physical_ip,
    )
    payload = _private_contract_payload(path, name=f"qualification report {serial}")
    report = _mapping(
        _decode_json(payload, name=f"qualification report {serial}"),
        name=f"qualification report {serial}",
    )
    _exact_keys(
        report,
        {
            "schema",
            "schema_version",
            "campaign_plan",
            "started_at",
            "completed_at",
            "outcome",
            "planned_case_count",
            "boot_receipt",
            "cases",
            "restored_runtime",
            "persistent_qspi_unchanged",
            "errors",
        },
        name=f"qualification report {serial}",
    )
    _contract_identity(
        report["campaign_plan"],
        payload=plan_payload,
        expected_path=plan_path,
        name=f"qualification report plan identity {serial}",
    )
    started = _utc_timestamp(report["started_at"], name="qualification start time")
    completed = _utc_timestamp(
        report["completed_at"], name="qualification completion time"
    )
    if completed < started:
        _fail("qualification completion precedes its start")
    if (
        report["schema"] != _GAIN_TIMELINE_REPORT_SCHEMA
        or report["schema_version"] != 2
        or report["outcome"] != "pass"
        or report["planned_case_count"] != _GAIN_TIMELINE_CASE_COUNT
        or report["persistent_qspi_unchanged"] is not True
        or report["errors"] != []
    ):
        _fail("gain-timeline qualification report is not an exact passing outcome")
    receipt_payload = _private_contract_payload(
        receipt_path, name=f"RAM receipt {serial}"
    )
    receipt = _mapping(
        _decode_json(receipt_payload, name=f"RAM receipt {serial}"),
        name=f"RAM receipt {serial}",
    )
    if report["boot_receipt"] != receipt:
        _fail("qualification report embeds a different RAM receipt")
    pre_runtime = _mapping(receipt["pre_runtime"], name="qualification pre-runtime")
    post_runtime = _mapping(receipt["post_runtime"], name="qualification post-runtime")
    restored = _mapping(
        report["restored_runtime"], name="qualification restored runtime"
    )
    if set(restored) != set(pre_runtime):
        _fail(
            "qualification restored runtime shape differs from persistent pre-runtime"
        )
    for key in pre_runtime:
        if key not in {"boot_id", "usb_uri"} and restored[key] != pre_runtime[key]:
            _fail(f"qualification restored runtime differs at {key}")
    restored_usb_uri = _string(
        restored["usb_uri"], name="qualification restored USB URI", maximum=64
    )
    if re.fullmatch(r"usb:[0-9]+[.][0-9]+[.]5", restored_usb_uri) is None:
        _fail("qualification restored runtime USB URI is not concrete")
    restored_boot = _string(
        restored["boot_id"], name="qualification restored boot ID", maximum=36
    )
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        restored_boot,
    ) is None or restored_boot in {pre_runtime["boot_id"], post_runtime["boot_id"]}:
        _fail("qualification restored runtime does not prove a fresh persistent boot")
    raw_cases = report["cases"]
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes)):
        _fail("qualification cases must be an array")
    if len(raw_cases) != len(_GAIN_TIMELINE_CASES):
        _fail("qualification report does not contain all canonical cases")
    usb_uri = _string(post_runtime["usb_uri"], name="candidate runtime USB URI")
    for position, (raw_result, expected_case) in enumerate(
        zip(raw_cases, _GAIN_TIMELINE_CASES, strict=True)
    ):
        result = _mapping(raw_result, name=f"qualification result {position}")
        _exact_keys(
            result, {"case", "report", "error"}, name=f"qualification result {position}"
        )
        if result["case"] != expected_case or result["error"] is not None:
            _fail(f"qualification result {position} is missing, reordered, or failed")
        _verify_gain_timeline_ladder(
            result["report"],
            case=expected_case,
            artifact_index=artifact_index,
            serial=serial,
            physical_ip=physical_ip,
            usb_uri=usb_uri,
        )
    del plan


def _verify_receipt_report(
    path: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    serial: str,
) -> str:
    try:
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise EvidenceError(
            f"RAM deployment receipt cannot be inspected: {error}"
        ) from error
    if mode != 0o600:
        _fail("RAM deployment receipt mode must be exactly 0600")
    root = path.parents[3]
    deploy_root = path.parent
    candidate_plan_path = deploy_root / "release-candidate-plan.json"
    inventory_path = deploy_root / "usb-inventory.json"
    operation_path = deploy_root / "operation-plan.json"
    stage = str(artifact_index.get("stage", ""))
    index_name = {
        "candidate-pre-hardware": "candidate-index.json",
        "final-pre-confirmation": "final-artifact-index.json",
    }.get(stage)
    if index_name is None:
        _fail("RAM receipt parent artifact stage is not deployable")
    index_path = root / index_name
    for companion, name in (
        (candidate_plan_path, "release candidate plan"),
        (inventory_path, "release USB inventory"),
        (operation_path, "release operation plan"),
    ):
        try:
            companion_mode = stat.S_IMODE(companion.stat(follow_symlinks=False).st_mode)
        except OSError as error:
            raise EvidenceError(f"{name} cannot be inspected: {error}") from error
        if companion_mode != 0o600:
            _fail(f"{name} mode must be exactly 0600")
    index_payload = _read_small(index_path, name="candidate artifact index")
    candidate_plan_payload = _read_small(
        candidate_plan_path, name=f"release candidate plan {serial}"
    )
    inventory_payload = _read_small(
        inventory_path, name=f"release USB inventory {serial}"
    )
    operation_payload = _read_small(
        operation_path, name=f"release operation plan {serial}"
    )
    payload = _read_small(path, name=f"RAM receipt {serial}")
    try:
        candidate_plan = validate_release_candidate_plan(
            _decode_json(
                candidate_plan_payload, name=f"release candidate plan {serial}"
            ),
            artifact_index=artifact_index,
            artifact_index_bytes=len(index_payload),
            artifact_index_sha256=artifact_index_sha256,
        )
        inventory = validate_release_usb_inventory(
            _decode_json(inventory_payload, name=f"release USB inventory {serial}")
        )
        operation = validate_release_operation_plan(
            _decode_json(operation_payload, name=f"release operation plan {serial}"),
            candidate_plan=candidate_plan,
            candidate_plan_bytes=len(candidate_plan_payload),
            candidate_plan_sha256=hashlib.sha256(candidate_plan_payload).hexdigest(),
            usb_inventory=inventory,
            usb_inventory_bytes=len(inventory_payload),
            usb_inventory_sha256=hashlib.sha256(inventory_payload).hexdigest(),
            serial=serial,
        )
        validate_release_candidate_receipt(
            _decode_json(payload, name=f"RAM receipt {serial}"),
            candidate_plan=candidate_plan,
            candidate_plan_bytes=len(candidate_plan_payload),
            candidate_plan_sha256=hashlib.sha256(candidate_plan_payload).hexdigest(),
            operation_plan=operation,
            operation_plan_bytes=len(operation_payload),
            operation_plan_sha256=hashlib.sha256(operation_payload).hexdigest(),
            serial=serial,
        )
    except CandidateBindingError as error:
        raise EvidenceError(f"RAM receipt {serial} is invalid: {error}") from error
    return hashlib.sha256(payload).hexdigest()


def _require_candidate_lineage(
    value: object,
    *,
    name: str,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    receipt_sha256: str,
    serial: str,
) -> None:
    lineage = _mapping(value, name=name)
    expected = {
        "serial": serial,
        "firmware_version": artifact_index["release"]["firmware_version"],
        "source_commit": artifact_index["source"]["commit"],
        "artifact_index_sha256": artifact_index_sha256,
        "dfu_sha256": artifact_index["artifact"]["dfu_sha256"],
        "deployment_receipt_sha256": receipt_sha256,
    }
    for key, expected_value in expected.items():
        if lineage.get(key) != expected_value:
            _fail(f"{name} does not bind exact {key}")


def _verify_release_candidate_binding(
    value: object,
    *,
    configuration: Mapping[str, object],
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    receipt_sha256: str,
    serial: str,
) -> Mapping[str, object]:
    binding = _mapping(value, name="release candidate binding")
    _require_candidate_lineage(
        binding,
        name="release candidate binding",
        artifact_index=artifact_index,
        artifact_index_sha256=artifact_index_sha256,
        receipt_sha256=receipt_sha256,
        serial=serial,
    )
    if (
        binding.get("schema") != RELEASE_BINDING_SCHEMA
        or binding.get("build_run_id") != artifact_index["build"]["run_id"]
        or binding.get("build_run_attempt") != artifact_index["build"]["run_attempt"]
        or binding.get("fit_sha256") != artifact_index["artifact"]["fit_sha256"]
        or binding.get("artifact_index") != artifact_index
    ):
        _fail("release candidate binding is stale or does not bind the full index")

    semantic = _mapping(
        binding.get("initial_semantic_verification"),
        name="release semantic verification",
    )
    expected_normalized = hashlib.sha256(
        json.dumps(
            artifact_index,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if semantic != {
        "stage": artifact_index["stage"],
        "normalized_index_sha256": expected_normalized,
    }:
        _fail("release report lacks the current semantic artifact verification")

    indexed_harness = {
        str(item["path"]): str(item["sha256"])
        for item in artifact_index["harness"]["files"]
    }
    harness_sources = _mapping(
        configuration.get("harness_sources"), name="release harness sources"
    )
    if set(harness_sources) != set(RELEASE_HARDWARE_HARNESS_PATHS):
        _fail("release report harness source inventory is not exact")
    for relative in RELEASE_HARDWARE_HARNESS_PATHS:
        if (
            indexed_harness.get(relative) != harness_sources.get(relative)
            or _SHA256.fullmatch(str(harness_sources.get(relative, ""))) is None
        ):
            _fail(f"release report does not bind current harness {relative}")

    raw_harness = binding.get("harness_files")
    if not isinstance(raw_harness, Sequence) or isinstance(raw_harness, (str, bytes)):
        _fail("release candidate binding harness files are not an array")
    observed_harness: dict[str, str] = {}
    required_harness: set[str] = set()
    for position, raw_item in enumerate(raw_harness):
        item = _mapping(raw_item, name=f"release binding harness {position}")
        relative = _relative(
            item.get("relative_path"), name=f"release binding harness {position} path"
        )
        digest = _sha(
            item.get("sha256"), name=f"release binding harness {position} SHA-256"
        )
        if relative in observed_harness:
            _fail("release binding harness contains a duplicate path")
        observed_harness[relative] = digest
        required = item.get("required_for_release_hardware")
        if type(required) is not bool:
            _fail("release binding harness required flag is not boolean")
        if required:
            required_harness.add(relative)
            if item.get("committed_sha256") != digest:
                _fail("required release harness is not its committed blob")
    if observed_harness != indexed_harness or required_harness != set(
        RELEASE_HARDWARE_HARNESS_PATHS
    ):
        _fail("release binding harness differs from the artifact index")

    runner = _mapping(
        binding.get("runner_provenance"), name="release runner provenance"
    )
    raw_sources = runner.get("sources")
    if (
        runner.get("schema") != RELEASE_RUNNER_SCHEMA
        or runner.get("commit") != artifact_index["source"]["commit"]
        or runner.get("clean") is not True
        or not isinstance(raw_sources, Sequence)
        or isinstance(raw_sources, (str, bytes))
    ):
        _fail("release runner provenance is absent or stale")
    runner_paths: list[str] = []
    for position, raw_source in enumerate(raw_sources):
        source = _mapping(raw_source, name=f"release runner source {position}")
        relative = _relative(
            source.get("path"), name=f"release runner source {position} path"
        )
        digest = _sha(
            source.get("sha256"), name=f"release runner source {position} SHA-256"
        )
        if source.get("committed_sha256") != digest:
            _fail("release runner source differs from its committed blob")
        if indexed_harness.get(relative) != digest:
            _fail("release runner source differs from the indexed harness")
        runner_paths.append(relative)
    if tuple(runner_paths) != RELEASE_RUNNER_PROVENANCE_PATHS:
        _fail("release runner provenance source inventory is not exact")
    source_values = _mapping(
        binding.get("source_manifest_values"),
        name="release source manifest values",
    )
    if source_values.get("libiio_0_25_source") != configuration.get(
        "libiio_source_commit"
    ):
        _fail("release host libiio does not match the indexed source manifest")
    return binding


def _verify_release_2450_diagnostic(
    path: Path,
    *,
    record: Mapping[str, object],
    configuration: Mapping[str, object],
    name: str,
) -> None:
    report = _read_json_member(path, name=f"{name} 2.45 GHz diagnostic")
    outcome = record.get("phase_verdict")
    expected_report_verdict = {
        "diagnostic_passed": "pass",
        "diagnostic_failed": "fail",
    }.get(outcome)
    identity = _mapping(report.get("identity"), name=f"{name} diagnostic identity")
    context_attrs = _mapping(
        identity.get("context_attrs"), name=f"{name} diagnostic context"
    )
    rf = _mapping(report.get("rf"), name=f"{name} diagnostic RF")
    evaluation = _mapping(
        report.get("evaluation"), name=f"{name} diagnostic evaluation"
    )
    cleanup = _mapping(report.get("cleanup"), name=f"{name} diagnostic cleanup")
    if (
        expected_report_verdict is None
        or report.get("schema") != "plutosdr-fw.tandem-agc-quality.v1"
        or report.get("verdict") != expected_report_verdict
        or evaluation.get("verdict") != expected_report_verdict
        or "fatal_error" in report
        or "cleanup_error" in report
        or identity.get("serial") != configuration.get("serial")
        or context_attrs.get("fw_version") != configuration.get("firmware_version")
        or identity.get("libiio_source_commit")
        != configuration.get("libiio_source_commit")
        or not str(identity.get("uri", "")).startswith("usb:")
        or rf.get("center_frequency_hz_requested") != 2_450_000_000
        or rf.get("expected_tandem_gain_table_id") != 2
        or cleanup.get("verified") is not True
        or cleanup.get("failures") != []
    ):
        _fail(f"{name} 2.45 GHz diagnostic is not exact safe evidence")
    summary = _mapping(record.get("summary"), name=f"{name} diagnostic summary")
    raw_failures = evaluation.get("failures")
    if not isinstance(raw_failures, Sequence) or isinstance(raw_failures, (str, bytes)):
        _fail(f"{name} diagnostic failure list is malformed")
    failure_evidence = report.get("failure_evidence")
    expected_manifest_sha: str | None = None
    if outcome == "diagnostic_failed":
        evidence = _mapping(
            failure_evidence, name=f"{name} diagnostic failure evidence"
        )
        ledger = _mapping(
            evidence.get("iq_ledger"), name=f"{name} diagnostic IQ ledger"
        )
        expected_manifest_sha = _sha(
            ledger.get("manifest_sha256"), name=f"{name} diagnostic IQ manifest"
        )
    if summary != {
        "role": "non_authorizing_rf_quality_diagnostic",
        "center_frequency_hz": 2_450_000_000,
        "outcome": outcome,
        "rf_quality_failures": list(raw_failures),
        "failure_iq_manifest_sha256": expected_manifest_sha,
        "release_claim": "none_at_2_4_ghz",
    }:
        _fail(f"{name} 2.45 GHz diagnostic summary changed")


def _verify_release_host_and_phases(
    report: Mapping[str, object],
    *,
    configuration: Mapping[str, object],
    expected_plan: Sequence[Mapping[str, object]],
    aggregate_path: Path,
    name: str,
) -> None:
    host = _mapping(configuration.get("host_libiio"), name=f"{name} host libiio")
    if (
        host.get("schema") != RELEASE_HOST_LIBIIO_SCHEMA
        or not isinstance(host.get("resume_identity"), Mapping)
        or configuration.get("libiio_source_commit") != host.get("source_commit")
    ):
        _fail(f"{name} does not bind the current guarded host libiio")
    if report.get("all_host_libiio_verified") is not True:
        _fail(f"{name} did not verify host libiio at every phase boundary")

    invocations = report.get("host_libiio_invocations")
    if not isinstance(invocations, Sequence) or isinstance(invocations, (str, bytes)):
        _fail(f"{name} host libiio invocation inventory is not an array")
    if not invocations:
        _fail(f"{name} has no guarded host libiio invocation")
    for position, raw_invocation in enumerate(invocations):
        invocation = _mapping(
            raw_invocation, name=f"{name} host libiio invocation {position}"
        )
        _positive_int(
            invocation.get("started_unix_ns"),
            name=f"{name} host libiio invocation timestamp",
        )
        if invocation.get("provenance") != host:
            _fail(f"{name} host libiio invocation provenance changed")

    plan = report.get("plan")
    phases = _mapping(report.get("phases"), name=f"{name} phase records")
    if not isinstance(plan, Sequence) or isinstance(plan, (str, bytes)) or not plan:
        _fail(f"{name} phase plan is not a nonempty array")
    plan_keys: list[str] = []
    normalized_plan: list[dict[str, object]] = []
    for position, raw_spec in enumerate(plan):
        spec = _mapping(raw_spec, name=f"{name} phase plan {position}")
        _exact_keys(spec, {"key", "kind", "band"}, name=f"{name} phase plan")
        key = _string(spec["key"], name=f"{name} phase key")
        kind = _string(spec["kind"], name=f"{name} phase kind")
        band = spec["band"]
        if band is not None:
            band = dict(_mapping(band, name=f"{name} phase band"))
        plan_keys.append(key)
        normalized_plan.append({"key": key, "kind": kind, "band": band})
    if (
        len(set(plan_keys)) != len(plan_keys)
        or set(phases) != set(plan_keys)
        or normalized_plan != [dict(spec) for spec in expected_plan]
    ):
        _fail(f"{name} phase plan does not match the requested release phases")

    phase_root = aggregate_path.parent.absolute()
    for key in plan_keys:
        record = _mapping(phases[key], name=f"{name} phase {key}")
        raw_report = Path(
            _string(record.get("report_path"), name=f"{name} phase report path")
        )
        if not raw_report.is_absolute():
            _fail(f"{name} phase {key} report path is not absolute")
        absolute_parts = PurePosixPath(raw_report.as_posix()).parts
        suffixes = [
            absolute_parts[position:]
            for position in range(len(absolute_parts) - 2)
            if absolute_parts[position] == "artifacts"
            and absolute_parts[position + 1] == key
            and re.fullmatch(r"attempt-[0-9]{4}", absolute_parts[position + 2])
        ]
        if len(suffixes) != 1:
            _fail(f"{name} phase {key} report path is not canonical")
        raw_parts = suffixes[0]
        if (
            len(raw_parts) < 4
            or raw_parts[0] != "artifacts"
            or raw_parts[1] != key
            or int(raw_parts[2].removeprefix("attempt-")) < 1
        ):
            _fail(f"{name} phase {key} report path is not canonical")
        raw_relative = PurePosixPath(*raw_parts).as_posix()
        raw_descriptor = _capture_member(
            phase_root, raw_relative, name=f"{name} raw phase {key} report"
        )
        kind = next(item["kind"] for item in normalized_plan if item["key"] == key)
        expected_verdicts = (
            {"diagnostic_passed", "diagnostic_failed"}
            if kind == "diagnostic"
            else {"pass"}
        )
        if (
            record.get("status") != "complete"
            or record.get("phase_verdict") not in expected_verdicts
            or record.get("cleanup_verified") is not True
            or record.get("host_libiio_before_phase") != host
            or record.get("host_libiio_after_cleanup") != host
            or record.get("report_sha256") != raw_descriptor["sha256"]
            or not isinstance(record.get("summary"), Mapping)
        ):
            _fail(f"{name} phase {key} is not a current accepted result with cleanup")
        if kind == "diagnostic":
            _verify_release_2450_diagnostic(
                _member_path(
                    phase_root,
                    raw_relative,
                    name=f"{name} 2.45 GHz diagnostic report",
                ),
                record=record,
                configuration=configuration,
                name=name,
            )
    counts = _mapping(report.get("counts"), name=f"{name} phase counts")
    if counts != {
        "pending": 0,
        "running": 0,
        "complete": len(plan_keys),
        "failed": 0,
    }:
        _fail(f"{name} aggregate phase counts are not exact")


def _verify_release_hardware_report(
    path: Path,
    *,
    phase: str,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    receipt_sha256: str,
    serial: str,
) -> None:
    report = _read_json_member(path, name=f"{phase} report {serial}")
    if (
        report.get("schema") != "plutosdr-fw.tandem-agc-release-hardware.v2"
        or report.get("verdict") != "pass"
        or report.get("all_requested_phases_complete") is not True
        or report.get("all_cleanup_verified") is not True
        or report.get("all_host_libiio_verified") is not True
    ):
        _fail(f"{phase} report {serial} is not a passing complete aggregate")
    configuration = _mapping(
        report.get("configuration"), name=f"{phase} report configuration"
    )
    expected_policy = "full" if phase == "full" else "baseline"
    expected_phases = (
        ["steady", "transient", "modulated", "diagnostic-2450"]
        if phase == "full"
        else ["steady"]
    )
    expected_plan: list[dict[str, object]] = [
        {
            "key": "steady_characterization" if phase == "full" else "steady_soak",
            "kind": "steady",
            "band": None,
        }
    ]
    if phase == "full":
        for kind in ("transient", "modulated"):
            expected_plan.extend(
                {
                    "key": f"{kind}_{band['name']}",
                    "kind": kind,
                    "band": dict(band),
                }
                for band in RELEASE_BANDS
            )
        expected_plan.append(
            {
                "key": "diagnostic_2450mhz",
                "kind": "diagnostic",
                "band": dict(RELEASE_DIAGNOSTIC_2450["band"]),
            }
        )
    expected_campaign = {
        "steady_campaign_kind": (
            "one_factor_characterization"
            if phase == "full"
            else "baseline_repeatability_soak"
        ),
        "repeat_cycles": 1 if phase == "full" else 4,
        "cycle_interval_seconds": 0.0 if phase == "full" else 1_200.0,
        "soak_deadline_seconds": 14_400.0 if phase == "full" else 5_400.0,
        **RELEASE_COMMON_CONFIGURATION,
    }
    if (
        configuration.get("serial") != serial
        or configuration.get("firmware_version")
        != artifact_index["release"]["firmware_version"]
        or configuration.get("policy_set") != expected_policy
        or configuration.get("requested_phases") != expected_phases
        or configuration.get("bands") != list(RELEASE_BANDS)
        or configuration.get("non_authorizing_diagnostic") != RELEASE_DIAGNOSTIC_2450
        or any(
            configuration.get(key) != value for key, value in expected_campaign.items()
        )
    ):
        _fail(f"{phase} report {serial} configuration is not exact")
    report_phases = _mapping(report.get("phases"), name=f"{phase} report phase records")
    expected_diagnostics: dict[str, object] = {}
    if phase == "full":
        diagnostic_record = _mapping(
            report_phases.get("diagnostic_2450mhz"),
            name=f"{phase} report 2.45 GHz diagnostic phase",
        )
        expected_diagnostics["diagnostic_2450mhz"] = diagnostic_record.get(
            "phase_verdict"
        )
    if (
        report.get("authorizing_bands") != list(RELEASE_BANDS)
        or report.get("diagnostics") != expected_diagnostics
    ):
        _fail(f"{phase} report {serial} release scope is not exact")
    _verify_release_candidate_binding(
        configuration.get("candidate_binding"),
        configuration=configuration,
        artifact_index=artifact_index,
        artifact_index_sha256=artifact_index_sha256,
        receipt_sha256=receipt_sha256,
        serial=serial,
    )
    _verify_release_host_and_phases(
        report,
        configuration=configuration,
        expected_plan=expected_plan,
        aggregate_path=path,
        name=f"{phase} report {serial}",
    )


def _verify_lifecycle_report(
    path: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    receipt_sha256: str,
    serial: str,
) -> None:
    report = _read_json_member(path, name=f"lifecycle report {serial}")
    if set(report) != LIFECYCLE_REPORT_FIELDS:
        _fail(f"lifecycle report {serial} is not a current durable v5 report")
    if (
        report.get("schema") != "plutosdr-fw.muted-metadata-batch-lifecycle.v5"
        or report.get("verdict") != "PASS"
        or report.get("release_claim")
        != "none; muted host-transport lifecycle qualification only"
        or report.get("release_pass_eligible") is not False
        or report.get("hardware_qualified") is not False
    ):
        _fail(f"lifecycle report {serial} is not exact passing supplemental evidence")
    started = _positive_int(
        report.get("started_unix_ns"), name="lifecycle start timestamp"
    )
    completed = _positive_int(
        report.get("completed_unix_ns"), name="lifecycle completion timestamp"
    )
    if completed < started:
        _fail("lifecycle report completion predates its start")

    lineage = _mapping(
        report.get("expected_device_firmware_lineage"),
        name="lifecycle candidate lineage",
    )
    _require_candidate_lineage(
        lineage,
        name="lifecycle candidate lineage",
        artifact_index=artifact_index,
        artifact_index_sha256=artifact_index_sha256,
        receipt_sha256=receipt_sha256,
        serial=serial,
    )
    if (
        lineage.get("artifact_index") != artifact_index
        or lineage.get("build_run_id") != artifact_index["build"]["run_id"]
        or lineage.get("build_run_attempt") != artifact_index["build"]["run_attempt"]
        or lineage.get("fit_sha256") != artifact_index["artifact"]["fit_sha256"]
        or lineage.get("evidence_member_count") != len(REQUIRED_EVIDENCE_ROLES)
        or lineage.get("evidence_members_verified") is not True
    ):
        _fail("lifecycle lineage does not bind the complete artifact index")
    source_manifest = _mapping(
        lineage.get("source_manifest"), name="lifecycle source manifest"
    )
    source_values = _mapping(
        source_manifest.get("values"), name="lifecycle source manifest values"
    )
    libiio_commit = str(source_values.get("libiio_0_25_source", ""))
    libiio_ref = str(source_values.get("libiio_0_25_ref", ""))
    if _COMMIT.fullmatch(libiio_commit) is None or not libiio_ref.startswith(
        "refs/tags/"
    ):
        _fail("lifecycle source manifest does not bind protected host libiio")

    runner = _mapping(report.get("runner_provenance"), name="lifecycle runner")
    if (
        runner.get("host_runner_repository_commit")
        != artifact_index["source"]["commit"]
    ):
        _fail("lifecycle runner commit differs from the artifact source")
    indexed_harness = {
        str(item["path"]): str(item["sha256"])
        for item in artifact_index["harness"]["files"]
    }
    runner_fields = {
        "scripts/run_muted_metadata_batch_lifecycle_hardware.sh": (
            "shell_runner_sha256",
            "shell_runner_head_blob_sha256",
        ),
        "tests/radio_hardware/candidate_binding.py": (
            "candidate_binding_sha256",
            "candidate_binding_head_blob_sha256",
        ),
        "tests/radio_hardware/metadata_abi.py": (
            "metadata_abi_sha256",
            "metadata_abi_head_blob_sha256",
        ),
        "tests/radio_hardware/muted_metadata_batch_lifecycle.py": (
            "python_module_sha256",
            "python_module_head_blob_sha256",
        ),
    }
    for relative in LIFECYCLE_HARNESS_PATHS:
        live_field, committed_field = runner_fields[relative]
        digest = indexed_harness.get(relative)
        if (
            _SHA256.fullmatch(str(digest or "")) is None
            or runner.get(live_field) != digest
            or runner.get(committed_field) != digest
        ):
            _fail(f"lifecycle runner does not bind current harness {relative}")

    host = _mapping(report.get("host_libiio"), name="lifecycle host libiio")
    if (
        host.get("source_commit") != libiio_commit
        or host.get("protected_source_tag") != libiio_ref.removeprefix("refs/tags/")
        or _SHA256.fullmatch(str(host.get("mapped_shared_object_sha256", ""))) is None
        or host.get("runner_shared_object_sha256")
        != host.get("mapped_shared_object_sha256")
    ):
        _fail("lifecycle report does not bind the protected host libiio")

    configuration = _mapping(
        report.get("configuration"), name="lifecycle configuration"
    )
    expected_configuration = {
        "serial": serial,
        "firmware_version": artifact_index["release"]["firmware_version"],
        "kernel_version": artifact_index["release"]["kernel_version"],
        "hardware_model": artifact_index["release"]["hardware_model"],
        "sample_rate_hz": 2_500_000,
        "frame_samples_per_channel": 65_536,
        "kernel_buffers": 8,
        "batch_frames": 64,
        "metadata_capacity_bytes": 65_536,
    }
    if any(
        configuration.get(key) != value for key, value in expected_configuration.items()
    ):
        _fail("lifecycle configuration is not the required 64-frame campaign")

    full_drain = _mapping(report.get("full_drain"), name="lifecycle full drain")
    frames = full_drain.get("frames")
    if (
        not isinstance(frames, Sequence)
        or isinstance(frames, (str, bytes))
        or len(frames) != 64
        or not isinstance(report.get("cancel_lifecycle"), Mapping)
        or not isinstance(report.get("temperature_evidence"), Mapping)
        or not isinstance(report.get("device_firmware_provenance"), Mapping)
    ):
        _fail("lifecycle PASS evidence sections are incomplete")
    cleanup = _mapping(report.get("cleanup"), name="lifecycle cleanup")
    if cleanup.get("verified") is not True or cleanup.get("errors") != []:
        _fail("lifecycle cleanup is not durably verified")

    manifest = _mapping(
        report.get("metadata_artifacts"), name="lifecycle metadata artifacts"
    )
    entries = manifest.get("entries")
    if (
        manifest.get("directory_relative") != "raw-metadata"
        or manifest.get("expected_file_count") != 65
        or manifest.get("completed_file_count") != 65
        or manifest.get("total_bytes") != 65 * 3_256
        or manifest.get("inventory_state") != "complete"
        or not isinstance(entries, Sequence)
        or isinstance(entries, (str, bytes))
        or len(entries) != 65
    ):
        _fail("lifecycle metadata artifact inventory is not exact")
    manifest_digest = hashlib.sha256()
    expected_names = [
        *(f"raw-metadata/full-frame-{index:04d}.metadata.bin" for index in range(64)),
        "raw-metadata/cancel-first.metadata.bin",
    ]
    raw_metadata: dict[str, bytes] = {}
    for position, (raw_entry, expected_relative) in enumerate(
        zip(entries, expected_names, strict=True)
    ):
        entry = _mapping(raw_entry, name=f"lifecycle metadata entry {position}")
        relative = _relative(
            entry.get("relative_path"), name=f"lifecycle metadata path {position}"
        )
        expected_role = "full_drain" if position < 64 else "cancel_first"
        expected_ordinal = position if position < 64 else 0
        if (
            relative != expected_relative
            or entry.get("role") != expected_role
            or entry.get("ordinal") != expected_ordinal
            or entry.get("bytes") != 3_256
            or entry.get("write_completed") is not True
        ):
            _fail("lifecycle metadata entry identity/count changed")
        descriptor = _capture_member(
            path.parent, relative, name=f"lifecycle raw metadata {position}"
        )
        metadata_path = _member_path(
            path.parent, relative, name=f"lifecycle raw metadata {position}"
        )
        raw_metadata[relative] = _read_small(
            metadata_path, name=f"lifecycle raw metadata {position}"
        )
        if (
            descriptor["bytes"] != 3_256
            or descriptor["sha256"] != entry.get("sha256")
            or stat.S_IMODE(metadata_path.stat(follow_symlinks=False).st_mode) != 0o600
        ):
            _fail("lifecycle raw metadata bytes or digest changed")
        manifest_digest.update(relative.encode())
        manifest_digest.update(b"\0")
        manifest_digest.update(b"3256\0")
        manifest_digest.update(str(entry["sha256"]).encode())
        manifest_digest.update(b"\n")
    if manifest.get("manifest_sha256") != manifest_digest.hexdigest():
        _fail("lifecycle metadata manifest digest changed")
    from tests.radio_hardware.muted_metadata_batch_lifecycle import (
        QualificationError as LifecycleQualificationError,
    )
    from tests.radio_hardware.muted_metadata_batch_lifecycle import (
        validate_archived_pass_report,
    )

    try:
        validate_archived_pass_report(report, raw_metadata=raw_metadata)
    except LifecycleQualificationError as error:
        raise EvidenceError(
            f"lifecycle report {serial} fails the current producer oracle: {error}"
        ) from error


def _validate_campaign_archive_for_promotion(
    _root: Path,
    *,
    _artifact_index: Mapping[str, Any],
    _artifact_index_sha256: str,
) -> None:
    """Document the campaign trust boundary for the single-owner workflow.

    The live runners already validate their checkpoints before publishing a
    report. Promotion rechecks the immutable report/receipt hashes, exact
    candidate lineage, serial inventory, phase verdicts, and cleanup fields
    below. Replaying every live IIO validator from the archive would add
    substantial machinery without protecting this operator-owned workflow
    from an accidental artifact or radio mix-up.
    """


def _capture_campaign_hardware(
    root: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    _validate_campaign_archive_for_promotion(
        root,
        _artifact_index=artifact_index,
        _artifact_index_sha256=artifact_index_sha256,
    )
    serials = _phase_serials(root, _CAMPAIGN_PHASES)
    known_paths: set[str] = set()
    radios: list[dict[str, object]] = []
    for serial in serials:
        members: dict[str, dict[str, object]] = {}
        for phase in _CAMPAIGN_PHASES:
            relative = f"hardware/{phase}/{serial}/{_CAMPAIGN_FILENAMES[phase]}"
            members[phase] = _capture_member(
                root, relative, name=f"{phase} report {serial}"
            )
            known_paths.add(relative)
        receipt_path = _member_path(
            root, members["deploy"]["path"], name=f"RAM receipt {serial}"
        )
        receipt_sha = _verify_receipt_report(
            receipt_path,
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
        )
        _verify_release_hardware_report(
            _member_path(root, members["full"]["path"], name="full report"),
            phase="full",
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        _verify_release_hardware_report(
            _member_path(root, members["soak"]["path"], name="soak report"),
            phase="soak",
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        _verify_lifecycle_report(
            _member_path(root, members["lifecycle"]["path"], name="lifecycle report"),
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        radios.append({"serial": serial, **members})
    inventory = set(_scan_tree_files(root, "hardware"))
    raw_paths = sorted(inventory - known_paths)
    if inventory != known_paths | set(raw_paths):
        _fail("hardware campaign inventory cannot be made exact")
    raw_members = [
        _capture_member(root, relative, name=f"raw evidence {relative}")
        for relative in raw_paths
    ]
    return radios, raw_members


def _verify_campaign_hardware(
    root: Path,
    *,
    radios_value: object,
    raw_members_value: object,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
) -> None:
    _validate_campaign_archive_for_promotion(
        root,
        _artifact_index=artifact_index,
        _artifact_index_sha256=artifact_index_sha256,
    )
    if not isinstance(radios_value, Sequence) or isinstance(radios_value, (str, bytes)):
        _fail("qualification radios must be an array")
    if not isinstance(raw_members_value, Sequence) or isinstance(
        raw_members_value, (str, bytes)
    ):
        _fail("qualification raw members must be an array")
    observed_serials: list[str] = []
    known_paths: set[str] = set()
    for position, raw_radio in enumerate(radios_value):
        radio = _mapping(raw_radio, name=f"qualification radio {position}")
        _exact_keys(
            radio,
            {"serial", "deploy", "full", "soak", "lifecycle"},
            name=f"qualification radio {position}",
        )
        serial = _safe_id(radio["serial"], name=f"qualification serial {position}")
        observed_serials.append(serial)
        members: dict[str, tuple[dict[str, object], Path]] = {}
        for phase in _CAMPAIGN_PHASES:
            member, path = _verify_member(
                root, radio[phase], name=f"{phase} report {serial}"
            )
            expected_path = f"hardware/{phase}/{serial}/{_CAMPAIGN_FILENAMES[phase]}"
            if member["path"] != expected_path or expected_path in known_paths:
                _fail(f"{phase} report {serial} path is not canonical and unique")
            known_paths.add(expected_path)
            members[phase] = (member, path)
        receipt_sha = _verify_receipt_report(
            members["deploy"][1],
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
        )
        _verify_release_hardware_report(
            members["full"][1],
            phase="full",
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        _verify_release_hardware_report(
            members["soak"][1],
            phase="soak",
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        _verify_lifecycle_report(
            members["lifecycle"][1],
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
    if tuple(observed_serials) != RELEASE_RADIO_SERIALS:
        _fail("qualification serials differ from the exact RC32 scope")
    raw_paths: list[str] = []
    for position, value in enumerate(raw_members_value):
        member, _path = _verify_member(root, value, name=f"raw member {position}")
        raw_paths.append(str(member["path"]))
    if raw_paths != sorted(raw_paths) or len(raw_paths) != len(set(raw_paths)):
        _fail("qualification raw members are not unique and sorted")
    if known_paths & set(raw_paths):
        _fail("qualification aliases reports and raw members")
    if set(_scan_tree_files(root, "hardware")) != known_paths | set(raw_paths):
        _fail("qualification index does not cover every raw hardware member")


def _gain_timeline_serials(root: Path) -> tuple[str, ...]:
    hardware = _member_path(root, "hardware", name="gain-timeline hardware root")
    if not hardware.is_dir():
        _fail("gain-timeline hardware root is not a directory")
    top_entries = sorted(os.scandir(hardware), key=lambda entry: entry.name)
    if {entry.name for entry in top_entries} != set(_GAIN_TIMELINE_PHASES) or any(
        not entry.is_dir(follow_symlinks=False) or entry.is_symlink()
        for entry in top_entries
    ):
        _fail("gain-timeline hardware phases are mixed or incomplete")
    observed: list[set[str]] = []
    for phase in _GAIN_TIMELINE_PHASES:
        phase_root = _member_path(
            root, f"hardware/{phase}", name=f"gain-timeline {phase} root"
        )
        entries = sorted(os.scandir(phase_root), key=lambda entry: entry.name)
        serials: set[str] = set()
        for entry in entries:
            serial = _safe_id(entry.name, name=f"gain-timeline {phase} serial")
            if not entry.is_dir(follow_symlinks=False) or entry.is_symlink():
                _fail("gain-timeline evidence is not exactly serial-scoped")
            serials.add(serial)
        observed.append(serials)
    expected = set(GAIN_TIMELINE_RELEASE_RADIO_SERIALS)
    if any(serials != expected for serials in observed):
        _fail("gain-timeline qualification differs from the exact .17/.18 radio scope")
    return GAIN_TIMELINE_RELEASE_RADIO_SERIALS


def _verify_gain_timeline_radio(
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    serial: str,
    physical_ip: str,
    receipt_path: Path,
    report_path: Path,
) -> None:
    _verify_receipt_report(
        receipt_path,
        artifact_index=artifact_index,
        artifact_index_sha256=artifact_index_sha256,
        serial=serial,
    )
    deploy_root = receipt_path.parent
    qualification_root = report_path.parent
    _verify_gain_timeline_report(
        report_path,
        plan_path=qualification_root / _GAIN_TIMELINE_PLAN_FILENAME,
        operation_path=deploy_root / "operation-plan.json",
        candidate_path=deploy_root / "release-candidate-plan.json",
        receipt_path=receipt_path,
        artifact_index=artifact_index,
        serial=serial,
        physical_ip=physical_ip,
    )


def _capture_gain_timeline_hardware(
    root: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    serials = _gain_timeline_serials(root)
    expected_ips = dict(GAIN_TIMELINE_RELEASE_RADIO_IPS)
    known_paths: set[str] = set()
    radios: list[dict[str, object]] = []
    for serial in serials:
        receipt_relative = (
            f"hardware/deploy/{serial}/{_GAIN_TIMELINE_FILENAMES['deploy']}"
        )
        report_relative = (
            "hardware/qualification/"
            f"{serial}/{_GAIN_TIMELINE_FILENAMES['qualification']}"
        )
        receipt = _capture_member(root, receipt_relative, name=f"RAM receipt {serial}")
        report = _capture_member(
            root, report_relative, name=f"gain-timeline report {serial}"
        )
        known_paths.update({receipt_relative, report_relative})
        _verify_gain_timeline_radio(
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
            physical_ip=expected_ips[serial],
            receipt_path=_member_path(
                root, receipt_relative, name=f"RAM receipt {serial}"
            ),
            report_path=_member_path(
                root, report_relative, name=f"gain-timeline report {serial}"
            ),
        )
        radios.append({"serial": serial, "deploy": receipt, "qualification": report})
    inventory = set(_scan_tree_files(root, "hardware"))
    raw_paths = sorted(inventory - known_paths)
    raw_members = [
        _capture_member(root, relative, name=f"raw gain-timeline evidence {relative}")
        for relative in raw_paths
    ]
    return radios, raw_members


def _verify_gain_timeline_hardware(
    root: Path,
    *,
    radios_value: object,
    raw_members_value: object,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
) -> None:
    _gain_timeline_serials(root)
    if not isinstance(radios_value, Sequence) or isinstance(radios_value, (str, bytes)):
        _fail("gain-timeline qualification radios must be an array")
    if not isinstance(raw_members_value, Sequence) or isinstance(
        raw_members_value, (str, bytes)
    ):
        _fail("gain-timeline raw members must be an array")
    expected_ips = dict(GAIN_TIMELINE_RELEASE_RADIO_IPS)
    known_paths: set[str] = set()
    observed_serials: list[str] = []
    for position, value in enumerate(radios_value):
        radio = _mapping(value, name=f"gain-timeline radio {position}")
        _exact_keys(
            radio,
            {"serial", "deploy", "qualification"},
            name=f"gain-timeline radio {position}",
        )
        serial = _safe_id(radio["serial"], name=f"gain-timeline serial {position}")
        observed_serials.append(serial)
        receipt, receipt_path = _verify_member(
            root, radio["deploy"], name=f"gain-timeline RAM receipt {serial}"
        )
        report, report_path = _verify_member(
            root,
            radio["qualification"],
            name=f"gain-timeline qualification report {serial}",
        )
        expected_receipt = (
            f"hardware/deploy/{serial}/{_GAIN_TIMELINE_FILENAMES['deploy']}"
        )
        expected_report = (
            "hardware/qualification/"
            f"{serial}/{_GAIN_TIMELINE_FILENAMES['qualification']}"
        )
        if (
            receipt["path"] != expected_receipt
            or report["path"] != expected_report
            or expected_receipt in known_paths
            or expected_report in known_paths
        ):
            _fail("gain-timeline report paths are not canonical and unique")
        known_paths.update({expected_receipt, expected_report})
        if serial not in expected_ips:
            _fail("gain-timeline qualification includes an unexpected radio")
        _verify_gain_timeline_radio(
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
            physical_ip=expected_ips[serial],
            receipt_path=receipt_path,
            report_path=report_path,
        )
    if tuple(observed_serials) != GAIN_TIMELINE_RELEASE_RADIO_SERIALS:
        _fail("gain-timeline qualification serial order/scope is not exact")
    raw_paths: list[str] = []
    for position, value in enumerate(raw_members_value):
        member, _path = _verify_member(
            root, value, name=f"gain-timeline raw member {position}"
        )
        raw_paths.append(str(member["path"]))
    if raw_paths != sorted(raw_paths) or len(raw_paths) != len(set(raw_paths)):
        _fail("gain-timeline raw members are not unique and sorted")
    if known_paths & set(raw_paths):
        _fail("gain-timeline raw members alias reports")
    if set(_scan_tree_files(root, "hardware")) != known_paths | set(raw_paths):
        _fail("gain-timeline index does not cover every raw hardware member")


def _assemble_candidate_qualified(
    root: Path, *, parent_index_path: Path
) -> dict[str, Any]:
    parent, artifact_index = _capture_index_reference(
        root,
        parent_index_path,
        expected_stage="candidate-pre-hardware",
        name="candidate artifact index",
    )
    if _is_gain_timeline_release(artifact_index):
        radios, raw_members = _capture_gain_timeline_hardware(
            root,
            artifact_index=artifact_index,
            artifact_index_sha256=str(parent["sha256"]),
        )
    else:
        radios, raw_members = _capture_campaign_hardware(
            root,
            artifact_index=artifact_index,
            artifact_index_sha256=str(parent["sha256"]),
        )
    return {
        "schema": QUALIFICATION_INDEX_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "stage": "candidate-qualified",
        "source_commit": artifact_index["source"]["commit"],
        "parent": parent,
        "radios": radios,
        "raw_members": raw_members,
    }


def _verify_candidate_qualified(index_path: Path) -> dict[str, Any]:
    root, _payload, raw, _digest = _read_index_record(
        index_path, name="candidate qualification index"
    )
    _exact_keys(
        raw,
        {
            "schema",
            "schema_version",
            "stage",
            "source_commit",
            "parent",
            "radios",
            "raw_members",
        },
        name="candidate qualification index",
    )
    if (
        raw["schema"] != QUALIFICATION_INDEX_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
        or raw["stage"] != "candidate-qualified"
    ):
        _fail("candidate qualification index schema/stage is not exact")
    source_commit = _string(
        raw["source_commit"], name="candidate qualification source commit", maximum=40
    )
    if _COMMIT.fullmatch(source_commit) is None:
        _fail("candidate qualification source commit is invalid")
    artifact_index, _parent_path = _verify_index_reference(
        root,
        raw["parent"],
        expected_stage="candidate-pre-hardware",
        name="candidate artifact parent",
    )
    if artifact_index["source"]["commit"] != source_commit:
        _fail("candidate qualification parent source lineage differs")
    if _is_gain_timeline_release(artifact_index):
        _verify_gain_timeline_hardware(
            root,
            radios_value=raw["radios"],
            raw_members_value=raw["raw_members"],
            artifact_index=artifact_index,
            artifact_index_sha256=str(raw["parent"]["sha256"]),
        )
    else:
        _verify_campaign_hardware(
            root,
            radios_value=raw["radios"],
            raw_members_value=raw["raw_members"],
            artifact_index=artifact_index,
            artifact_index_sha256=str(raw["parent"]["sha256"]),
        )
    return dict(raw)


def _artifact_from_qualification(
    qualification: Mapping[str, Any], qualification_path: Path
) -> tuple[dict[str, Any], Path]:
    return _verify_index_reference(
        qualification_path.parent,
        qualification["parent"],
        expected_stage="candidate-pre-hardware",
        name="qualified candidate artifact parent",
    )


def _manifest_for_artifact(
    artifact_index: Mapping[str, Any], artifact_index_path: Path
) -> dict[str, str]:
    relative = artifact_index["source"]["manifest_path"]
    path = _member_path(
        artifact_index_path.parent, relative, name="lineage source manifest"
    )
    payload = _read_small(path, name="lineage source manifest")
    if (
        hashlib.sha256(payload).hexdigest()
        != artifact_index["source"]["manifest_sha256"]
    ):
        _fail("lineage source manifest differs from its artifact index")
    return _manifest_values(payload)


def _reproduce_source_diff(
    candidate_commit: str, final_commit: str
) -> dict[str, object] | None:
    """Reproduce the source delta from local Git objects, without rename inference.

    ``None`` means one or both exact commits are unavailable locally.  Callers
    must treat that result as unproven and select the full campaign.
    """

    try:
        resolved: dict[str, str] = {}
        trees: dict[str, str] = {}
        for label, commit in (("candidate", candidate_commit), ("final", final_commit)):
            resolved[label] = subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "rev-parse",
                    "--verify",
                    f"{commit}^{{commit}}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            trees[label] = subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "rev-parse",
                    "--verify",
                    f"{commit}^{{tree}}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
        raw = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "diff-tree",
                "--no-commit-id",
                "--raw",
                "-r",
                "--no-renames",
                "--no-abbrev",
                "-z",
                candidate_commit,
                final_commit,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if resolved != {"candidate": candidate_commit, "final": final_commit} or any(
        _COMMIT.fullmatch(tree) is None for tree in trees.values()
    ):
        _fail("local Git did not resolve the exact indexed commits and trees")
    fields = raw.split(b"\0")
    if fields[-1:] != [b""] or len(fields) % 2 != 1:
        _fail("local Git emitted a malformed no-renames diff inventory")
    zero_oid = "0" * 40
    changes: list[dict[str, object]] = []
    for position in range(0, len(fields) - 1, 2):
        try:
            header = fields[position].decode("ascii", errors="strict")
            path_text = fields[position + 1].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise EvidenceError(
                "local Git diff is not canonical UTF-8/ASCII"
            ) from error
        header_fields = header.split(" ")
        if len(header_fields) != 5 or not header_fields[0].startswith(":"):
            _fail("local Git emitted a malformed raw diff header")
        candidate_mode = header_fields[0][1:]
        final_mode, candidate_oid, final_oid, status_code = header_fields[1:]
        if (
            re.fullmatch(r"[0-7]{6}", candidate_mode) is None
            or re.fullmatch(r"[0-7]{6}", final_mode) is None
            or _COMMIT.fullmatch(candidate_oid) is None
            or _COMMIT.fullmatch(final_oid) is None
        ):
            _fail("local Git diff modes/object IDs are malformed")
        if status_code == "A":
            status_name = "added"
            expected_zero = (candidate_oid == zero_oid, final_oid == zero_oid)
            if expected_zero != (True, False):
                _fail("local Git added-path object IDs are inconsistent")
        elif status_code == "D":
            status_name = "deleted"
            expected_zero = (candidate_oid == zero_oid, final_oid == zero_oid)
            if expected_zero != (False, True):
                _fail("local Git deleted-path object IDs are inconsistent")
        elif status_code in {"M", "T"}:
            status_name = "modified"
            if candidate_oid == zero_oid or final_oid == zero_oid:
                _fail("local Git modified-path object IDs are inconsistent")
        else:
            _fail("local Git diff contains rename/copy/unmerged/unknown status")
        changes.append(
            {
                "path": _relative(path_text, name="local Git diff path"),
                "status": status_name,
                "candidate_blob": None if candidate_oid == zero_oid else candidate_oid,
                "final_blob": None if final_oid == zero_oid else final_oid,
            }
        )
    changes.sort(key=lambda change: str(change["path"]))
    paths = [str(change["path"]) for change in changes]
    if len(paths) != len(set(paths)):
        _fail("local Git diff contains a duplicate path")
    return {
        "candidate": {"commit": candidate_commit, "tree": trees["candidate"]},
        "final": {"commit": final_commit, "tree": trees["final"]},
        "changed_files": changes,
        "trees_identical": trees["candidate"] == trees["final"],
    }


def _decode_source_diff(
    payload: bytes,
    *,
    candidate_commit: str,
    final_commit: str,
) -> dict[str, Any]:
    raw = _mapping(
        _decode_json(payload, name="candidate-to-final source diff"),
        name="candidate-to-final source diff",
    )
    _exact_keys(
        raw,
        {"schema", "schema_version", "candidate", "final", "changed_files"},
        name="candidate-to-final source diff",
    )
    if (
        raw["schema"] != CANDIDATE_TO_FINAL_DIFF_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
    ):
        _fail("candidate-to-final source diff schema/version is not exact")
    normalized_endpoints: dict[str, dict[str, str]] = {}
    for endpoint, expected_commit in (
        ("candidate", candidate_commit),
        ("final", final_commit),
    ):
        value = _mapping(raw[endpoint], name=f"source diff {endpoint}")
        _exact_keys(value, {"commit", "tree"}, name=f"source diff {endpoint}")
        commit = _string(
            value["commit"], name=f"source diff {endpoint} commit", maximum=40
        )
        tree = _string(value["tree"], name=f"source diff {endpoint} tree", maximum=40)
        if commit != expected_commit or _COMMIT.fullmatch(tree) is None:
            _fail(f"source diff {endpoint} does not bind the indexed commit/tree")
        normalized_endpoints[endpoint] = {"commit": commit, "tree": tree}
    changed_files = raw["changed_files"]
    if not isinstance(changed_files, Sequence) or isinstance(
        changed_files, (str, bytes)
    ):
        _fail("source diff changed_files must be an array")
    normalized_changes: list[dict[str, object]] = []
    observed_paths: list[str] = []
    for position, raw_change in enumerate(changed_files):
        change = _mapping(raw_change, name=f"source diff change {position}")
        _exact_keys(
            change,
            {"path", "status", "candidate_blob", "final_blob"},
            name=f"source diff change {position}",
        )
        path = _relative(change["path"], name=f"source diff path {position}")
        status = _string(change["status"], name=f"source diff status {position}")
        if status not in {"added", "deleted", "modified"}:
            _fail("source diff status is not added/deleted/modified")
        candidate_blob = change["candidate_blob"]
        final_blob = change["final_blob"]
        for label, blob in (("candidate", candidate_blob), ("final", final_blob)):
            if blob is not None and (
                type(blob) is not str or _COMMIT.fullmatch(blob) is None
            ):
                _fail(f"source diff {label} blob is not a Git object ID or null")
        if (
            (status == "added" and (candidate_blob is not None or final_blob is None))
            or (
                status == "deleted"
                and (candidate_blob is None or final_blob is not None)
            )
            or (status == "modified" and (candidate_blob is None or final_blob is None))
        ):
            _fail("source diff blob/status relationship is inconsistent")
        observed_paths.append(path)
        normalized_changes.append(
            {
                "path": path,
                "status": status,
                "candidate_blob": candidate_blob,
                "final_blob": final_blob,
            }
        )
    if observed_paths != sorted(observed_paths) or len(observed_paths) != len(
        set(observed_paths)
    ):
        _fail("source diff paths must be unique and sorted")
    trees_identical = (
        normalized_endpoints["candidate"]["tree"]
        == normalized_endpoints["final"]["tree"]
    )
    if trees_identical != (not normalized_changes):
        _fail("source diff tree identity and changed-file inventory disagree")
    normalized: dict[str, Any] = {
        "candidate": normalized_endpoints["candidate"],
        "final": normalized_endpoints["final"],
        "changed_files": normalized_changes,
        "trees_identical": trees_identical,
    }
    reproduced = _reproduce_source_diff(candidate_commit, final_commit)
    if reproduced is None:
        normalized["trees_identical"] = False
        normalized["source_diff_reproduced"] = False
        return normalized
    if normalized != reproduced:
        _fail("candidate-to-final source diff differs from local Git objects")
    normalized["source_diff_reproduced"] = True
    return normalized


def _qualification_comparison(
    *,
    candidate_artifact: Mapping[str, Any],
    candidate_artifact_path: Path,
    final_artifact: Mapping[str, Any],
    final_artifact_path: Path,
    source_diff: Mapping[str, Any],
) -> dict[str, object]:
    release_keys = {"kernel_version", "hardware_model", "metadata_abi", "tandem_agc"}
    release_invariants_match = all(
        candidate_artifact["release"][key] == final_artifact["release"][key]
        for key in release_keys
    )
    component_pins_match = _manifest_for_artifact(
        candidate_artifact, candidate_artifact_path
    ) == _manifest_for_artifact(final_artifact, final_artifact_path)
    harness_match = candidate_artifact["harness"] == final_artifact["harness"]
    source_diff_reproduced = source_diff["source_diff_reproduced"] is True
    source_tree_identical = (
        source_diff_reproduced and source_diff["trees_identical"] is True
    )
    identity_only = all(
        (
            release_invariants_match,
            component_pins_match,
            harness_match,
            source_tree_identical,
        )
    )
    return {
        "source_diff_reproduced": source_diff_reproduced,
        "source_tree_identical": source_tree_identical,
        "release_invariants_match": release_invariants_match,
        "component_pins_match": component_pins_match,
        "harness_match": harness_match,
        "verdict": "identity-packaging-only"
        if identity_only
        else "functional-or-unproven",
    }


def _assemble_final_policy(
    root: Path,
    *,
    final_artifact_index_path: Path,
    candidate_qualified_index_path: Path,
    diff_path: Path,
) -> dict[str, Any]:
    final_reference, final_artifact = _capture_index_reference(
        root,
        final_artifact_index_path,
        expected_stage="final-pre-confirmation",
        name="final artifact index",
    )
    candidate_reference, candidate_qualification = _capture_index_reference(
        root,
        candidate_qualified_index_path,
        expected_stage="candidate-qualified",
        name="candidate qualification index",
    )
    candidate_artifact, candidate_artifact_path = _artifact_from_qualification(
        candidate_qualification, candidate_qualified_index_path.absolute()
    )
    diff_absolute = diff_path.absolute()
    try:
        diff_relative = diff_absolute.relative_to(root).as_posix()
    except ValueError as error:
        raise EvidenceError(
            "candidate-to-final diff must be inside archive root"
        ) from error
    diff_member = _capture_member(
        root, diff_relative, name="candidate-to-final source diff"
    )
    diff = _decode_source_diff(
        _read_small(diff_absolute, name="candidate-to-final source diff"),
        candidate_commit=candidate_artifact["source"]["commit"],
        final_commit=final_artifact["source"]["commit"],
    )
    comparison = _qualification_comparison(
        candidate_artifact=candidate_artifact,
        candidate_artifact_path=candidate_artifact_path,
        final_artifact=final_artifact,
        final_artifact_path=final_artifact_index_path.absolute(),
        source_diff=diff,
    )
    # v8 deliberately uses the already implemented full runner for the final
    # bytes. A reduced confirmation remains a future optimization until it has
    # a real committed producer; a hand-written four-string summary is never a
    # substitute for hardware execution.
    required_test = "full-campaign"
    return {
        "schema": FINAL_POLICY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "stage": "final-qualification-policy",
        "candidate_source_commit": candidate_artifact["source"]["commit"],
        "final_source_commit": final_artifact["source"]["commit"],
        "candidate_qualification": candidate_reference,
        "final_artifact": final_reference,
        "source_diff": diff_member,
        "comparison": comparison,
        "required_test": required_test,
    }


def _verify_final_policy(index_path: Path) -> dict[str, Any]:
    root, _payload, raw, _digest = _read_index_record(
        index_path, name="final qualification policy"
    )
    _exact_keys(
        raw,
        {
            "schema",
            "schema_version",
            "stage",
            "candidate_source_commit",
            "final_source_commit",
            "candidate_qualification",
            "final_artifact",
            "source_diff",
            "comparison",
            "required_test",
        },
        name="final qualification policy",
    )
    if (
        raw["schema"] != FINAL_POLICY_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
        or raw["stage"] != "final-qualification-policy"
    ):
        _fail("final qualification policy schema/stage is not exact")
    candidate_commit = _string(
        raw["candidate_source_commit"], name="policy candidate commit", maximum=40
    )
    final_commit = _string(
        raw["final_source_commit"], name="policy final commit", maximum=40
    )
    if (
        _COMMIT.fullmatch(candidate_commit) is None
        or _COMMIT.fullmatch(final_commit) is None
    ):
        _fail("final qualification policy source commits are invalid")
    candidate_qualification, candidate_qualification_path = _verify_index_reference(
        root,
        raw["candidate_qualification"],
        expected_stage="candidate-qualified",
        name="policy candidate qualification parent",
    )
    final_artifact, final_artifact_path = _verify_index_reference(
        root,
        raw["final_artifact"],
        expected_stage="final-pre-confirmation",
        name="policy final artifact parent",
    )
    candidate_artifact, candidate_artifact_path = _artifact_from_qualification(
        candidate_qualification, candidate_qualification_path
    )
    if (
        candidate_artifact["source"]["commit"] != candidate_commit
        or final_artifact["source"]["commit"] != final_commit
    ):
        _fail("final qualification policy source lineage differs from its parents")
    diff_member, diff_path = _verify_member(
        root, raw["source_diff"], name="policy candidate-to-final source diff"
    )
    del diff_member
    diff = _decode_source_diff(
        _read_small(diff_path, name="candidate-to-final source diff"),
        candidate_commit=candidate_commit,
        final_commit=final_commit,
    )
    comparison = _qualification_comparison(
        candidate_artifact=candidate_artifact,
        candidate_artifact_path=candidate_artifact_path,
        final_artifact=final_artifact,
        final_artifact_path=final_artifact_path,
        source_diff=diff,
    )
    observed_comparison = _mapping(raw["comparison"], name="policy comparison")
    _exact_keys(
        observed_comparison,
        {
            "source_diff_reproduced",
            "source_tree_identical",
            "release_invariants_match",
            "component_pins_match",
            "harness_match",
            "verdict",
        },
        name="policy comparison",
    )
    if dict(observed_comparison) != comparison:
        _fail("final qualification policy comparison is not reproducible")
    expected_test = "full-campaign"
    if raw["required_test"] != expected_test:
        _fail("final qualification policy required-test is not fail-closed")
    return dict(raw)


def _verify_final_confirmation_report(
    path: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    policy_sha256: str,
    receipt_sha256: str,
    serial: str,
) -> None:
    report = _read_json_member(path, name=f"final confirmation report {serial}")
    _exact_keys(
        report,
        {
            "schema",
            "schema_version",
            "verdict",
            "serial",
            "artifact_index_sha256",
            "qualification_policy_sha256",
            "deployment_receipt_sha256",
            "dfu_sha256",
            "firmware_version",
            "source_commit",
            "checks",
        },
        name=f"final confirmation report {serial}",
    )
    checks = _mapping(report["checks"], name="final confirmation checks")
    _exact_keys(
        checks,
        {"live_identity", "tx2_loopback", "protocol_v3", "cleanup"},
        name="final confirmation checks",
    )
    expected = {
        "schema": FINAL_CONFIRMATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "verdict": "pass",
        "serial": serial,
        "artifact_index_sha256": artifact_index_sha256,
        "qualification_policy_sha256": policy_sha256,
        "deployment_receipt_sha256": receipt_sha256,
        "dfu_sha256": artifact_index["artifact"]["dfu_sha256"],
        "firmware_version": artifact_index["release"]["firmware_version"],
        "source_commit": artifact_index["source"]["commit"],
        "checks": {
            "live_identity": "pass",
            "tx2_loopback": "pass",
            "protocol_v3": "pass",
            "cleanup": "pass",
        },
    }
    if dict(report) != expected:
        _fail(f"final confirmation report {serial} is not exact and passing")


def _reduced_serials(root: Path) -> tuple[str, ...]:
    hardware = _member_path(root, "hardware", name="final hardware root")
    entries = sorted(os.scandir(hardware), key=lambda entry: entry.name)
    if {entry.name for entry in entries} != {"deploy", "final-confirmation"}:
        _fail("reduced confirmation is mixed with full-campaign evidence")
    deploy_root = _member_path(root, "hardware/deploy", name="final deploy root")
    confirmation_root = _member_path(
        root, "hardware/final-confirmation", name="final confirmation root"
    )
    deploy_serials = {
        _safe_id(entry.name, name="final deploy serial")
        for entry in os.scandir(deploy_root)
        if entry.is_dir(follow_symlinks=False) and not entry.is_symlink()
    }
    deploy_entry_count = sum(1 for _entry in os.scandir(deploy_root))
    if deploy_entry_count != len(deploy_serials):
        _fail("final deploy evidence is not exactly serial-scoped")
    confirmation_serials: set[str] = set()
    aggregate_seen = False
    for entry in os.scandir(confirmation_root):
        if entry.name == "final-confirmation-index.json":
            if not entry.is_file(follow_symlinks=False) or entry.is_symlink():
                _fail("final confirmation aggregate is unsafe")
            aggregate_seen = True
        elif entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
            confirmation_serials.add(
                _safe_id(entry.name, name="final confirmation serial")
            )
        else:
            _fail("final confirmation root contains an unexpected entry")
    serials = tuple(sorted(deploy_serials))
    if (
        not aggregate_seen
        or deploy_serials != confirmation_serials
        or serials != RELEASE_RADIO_SERIALS
    ):
        _fail("reduced confirmation differs from the exact RC32 serial scope")
    return serials


def _capture_reduced_hardware(
    root: Path,
    *,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    policy_sha256: str,
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    serials = _reduced_serials(root)
    radios: list[dict[str, object]] = []
    known_paths: set[str] = set()
    for serial in serials:
        receipt_relative = f"hardware/deploy/{serial}/ram-boot-receipt.json"
        report_relative = (
            f"hardware/final-confirmation/{serial}/final-confirmation-report.json"
        )
        receipt = _capture_member(
            root, receipt_relative, name=f"final receipt {serial}"
        )
        report = _capture_member(root, report_relative, name=f"final report {serial}")
        known_paths.update({receipt_relative, report_relative})
        receipt_path = _member_path(root, receipt_relative, name="final receipt")
        receipt_sha = _verify_receipt_report(
            receipt_path,
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
        )
        _verify_final_confirmation_report(
            _member_path(root, report_relative, name="final confirmation report"),
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            policy_sha256=policy_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        radios.append({"serial": serial, "deploy": receipt, "confirmation": report})
    aggregate_relative = "hardware/final-confirmation/final-confirmation-index.json"
    aggregate = _capture_member(
        root, aggregate_relative, name="final confirmation index"
    )
    known_paths.add(aggregate_relative)
    _verify_confirmation_aggregate(
        _member_path(root, aggregate_relative, name="final confirmation index"),
        radios=radios,
        artifact_index_sha256=artifact_index_sha256,
        policy_sha256=policy_sha256,
    )
    inventory = set(_scan_tree_files(root, "hardware"))
    raw_paths = sorted(inventory - known_paths)
    raw_members = [
        _capture_member(root, path, name=f"final raw member {path}")
        for path in raw_paths
    ]
    return radios, aggregate, raw_members


def _verify_confirmation_aggregate(
    path: Path,
    *,
    radios: Sequence[Mapping[str, object]],
    artifact_index_sha256: str,
    policy_sha256: str,
) -> None:
    aggregate = _read_json_member(path, name="final confirmation aggregate")
    _exact_keys(
        aggregate,
        {
            "schema",
            "schema_version",
            "verdict",
            "artifact_index_sha256",
            "qualification_policy_sha256",
            "required_test",
            "serials",
            "reports",
        },
        name="final confirmation aggregate",
    )
    serials = [str(radio["serial"]) for radio in radios]
    reports = [
        {"serial": radio["serial"], **dict(radio["confirmation"])} for radio in radios
    ]
    expected = {
        "schema": FINAL_CONFIRMATION_INDEX_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "verdict": "pass",
        "artifact_index_sha256": artifact_index_sha256,
        "qualification_policy_sha256": policy_sha256,
        "required_test": "reduced-confirmation",
        "serials": serials,
        "reports": reports,
    }
    if dict(aggregate) != expected:
        _fail("final confirmation aggregate is not exact or does not bind all reports")


def _verify_reduced_hardware(
    root: Path,
    *,
    radios_value: object,
    aggregate_value: object,
    raw_members_value: object,
    artifact_index: Mapping[str, Any],
    artifact_index_sha256: str,
    policy_sha256: str,
) -> None:
    if not isinstance(radios_value, Sequence) or isinstance(radios_value, (str, bytes)):
        _fail("reduced-confirmation radios must be an array")
    radios: list[dict[str, object]] = []
    known_paths: set[str] = set()
    serials: list[str] = []
    for position, raw_radio in enumerate(radios_value):
        radio = _mapping(raw_radio, name=f"reduced-confirmation radio {position}")
        _exact_keys(
            radio,
            {"serial", "deploy", "confirmation"},
            name=f"reduced-confirmation radio {position}",
        )
        serial = _safe_id(radio["serial"], name="reduced-confirmation serial")
        serials.append(serial)
        receipt, receipt_path = _verify_member(
            root, radio["deploy"], name=f"final receipt {serial}"
        )
        report, report_path = _verify_member(
            root, radio["confirmation"], name=f"final confirmation {serial}"
        )
        expected_receipt = f"hardware/deploy/{serial}/ram-boot-receipt.json"
        expected_report = (
            f"hardware/final-confirmation/{serial}/final-confirmation-report.json"
        )
        if receipt["path"] != expected_receipt or report["path"] != expected_report:
            _fail("reduced-confirmation report paths are not canonical")
        known_paths.update({expected_receipt, expected_report})
        receipt_sha = _verify_receipt_report(
            receipt_path,
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            serial=serial,
        )
        _verify_final_confirmation_report(
            report_path,
            artifact_index=artifact_index,
            artifact_index_sha256=artifact_index_sha256,
            policy_sha256=policy_sha256,
            receipt_sha256=receipt_sha,
            serial=serial,
        )
        radios.append({"serial": serial, "deploy": receipt, "confirmation": report})
    if tuple(serials) != RELEASE_RADIO_SERIALS:
        _fail("reduced confirmation serials differ from the exact RC32 scope")
    aggregate, aggregate_path = _verify_member(
        root, aggregate_value, name="final confirmation aggregate"
    )
    aggregate_relative = "hardware/final-confirmation/final-confirmation-index.json"
    if aggregate["path"] != aggregate_relative:
        _fail("final confirmation aggregate path is not canonical")
    known_paths.add(aggregate_relative)
    _verify_confirmation_aggregate(
        aggregate_path,
        radios=radios,
        artifact_index_sha256=artifact_index_sha256,
        policy_sha256=policy_sha256,
    )
    if not isinstance(raw_members_value, Sequence) or isinstance(
        raw_members_value, (str, bytes)
    ):
        _fail("reduced-confirmation raw members must be an array")
    raw_paths: list[str] = []
    for position, value in enumerate(raw_members_value):
        member, _path = _verify_member(root, value, name=f"final raw member {position}")
        raw_paths.append(str(member["path"]))
    if raw_paths != sorted(raw_paths) or len(raw_paths) != len(set(raw_paths)):
        _fail("reduced-confirmation raw members are not unique and sorted")
    if known_paths & set(raw_paths):
        _fail("reduced-confirmation raw members alias reports")
    if set(_scan_tree_files(root, "hardware")) != known_paths | set(raw_paths):
        _fail("reduced-confirmation index omits raw evidence")


def _assemble_final_qualified(
    root: Path, *, final_artifact_index_path: Path, policy_index_path: Path
) -> dict[str, Any]:
    final_reference, final_artifact = _capture_index_reference(
        root,
        final_artifact_index_path,
        expected_stage="final-pre-confirmation",
        name="final artifact index",
    )
    policy_reference, policy = _capture_index_reference(
        root,
        policy_index_path,
        expected_stage="final-qualification-policy",
        name="final qualification policy",
    )
    if (
        policy["final_artifact"]["sha256"] != final_reference["sha256"]
        or policy["final_artifact"]["path"] != final_reference["path"]
    ):
        _fail("final qualification policy binds a different final artifact index")
    required_test = policy["required_test"]
    selected_evidence: dict[str, object]
    if required_test == "reduced-confirmation":
        radios, aggregate, raw_members = _capture_reduced_hardware(
            root,
            artifact_index=final_artifact,
            artifact_index_sha256=str(final_reference["sha256"]),
            policy_sha256=str(policy_reference["sha256"]),
        )
        selected_evidence = {"mode": required_test, "aggregate": aggregate}
    else:
        if _is_gain_timeline_release(final_artifact):
            radios, raw_members = _capture_gain_timeline_hardware(
                root,
                artifact_index=final_artifact,
                artifact_index_sha256=str(final_reference["sha256"]),
            )
        else:
            radios, raw_members = _capture_campaign_hardware(
                root,
                artifact_index=final_artifact,
                artifact_index_sha256=str(final_reference["sha256"]),
            )
        selected_evidence = {"mode": "full-campaign"}
    return {
        "schema": QUALIFICATION_INDEX_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "stage": "final-qualified",
        "source_commit": final_artifact["source"]["commit"],
        "required_test": required_test,
        "final_artifact": final_reference,
        "policy": policy_reference,
        "selected_evidence": selected_evidence,
        "radios": radios,
        "raw_members": raw_members,
    }


def _verify_final_qualified(index_path: Path) -> dict[str, Any]:
    root, _payload, raw, _digest = _read_index_record(
        index_path, name="final qualification index"
    )
    _exact_keys(
        raw,
        {
            "schema",
            "schema_version",
            "stage",
            "source_commit",
            "required_test",
            "final_artifact",
            "policy",
            "selected_evidence",
            "radios",
            "raw_members",
        },
        name="final qualification index",
    )
    if (
        raw["schema"] != QUALIFICATION_INDEX_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
        or raw["stage"] != "final-qualified"
    ):
        _fail("final qualification index schema/stage is not exact")
    final_artifact, _final_path = _verify_index_reference(
        root,
        raw["final_artifact"],
        expected_stage="final-pre-confirmation",
        name="qualified final artifact parent",
    )
    policy, _policy_path = _verify_index_reference(
        root,
        raw["policy"],
        expected_stage="final-qualification-policy",
        name="qualified final policy parent",
    )
    if (
        policy["final_artifact"]["sha256"] != raw["final_artifact"]["sha256"]
        or policy["final_artifact"]["path"] != raw["final_artifact"]["path"]
        or raw["source_commit"] != final_artifact["source"]["commit"]
        or raw["required_test"] != policy["required_test"]
    ):
        _fail("final qualification parent/source/required-test lineage differs")
    selected = _mapping(raw["selected_evidence"], name="selected final evidence")
    if raw["required_test"] == "reduced-confirmation":
        _exact_keys(selected, {"mode", "aggregate"}, name="selected final evidence")
        if selected["mode"] != "reduced-confirmation":
            _fail("selected final evidence mode differs from policy")
        _verify_reduced_hardware(
            root,
            radios_value=raw["radios"],
            aggregate_value=selected["aggregate"],
            raw_members_value=raw["raw_members"],
            artifact_index=final_artifact,
            artifact_index_sha256=str(raw["final_artifact"]["sha256"]),
            policy_sha256=str(raw["policy"]["sha256"]),
        )
    elif raw["required_test"] == "full-campaign":
        _exact_keys(selected, {"mode"}, name="selected final evidence")
        if selected["mode"] != "full-campaign":
            _fail("selected final evidence mode differs from policy")
        if _is_gain_timeline_release(final_artifact):
            _verify_gain_timeline_hardware(
                root,
                radios_value=raw["radios"],
                raw_members_value=raw["raw_members"],
                artifact_index=final_artifact,
                artifact_index_sha256=str(raw["final_artifact"]["sha256"]),
            )
        else:
            _verify_campaign_hardware(
                root,
                radios_value=raw["radios"],
                raw_members_value=raw["raw_members"],
                artifact_index=final_artifact,
                artifact_index_sha256=str(raw["final_artifact"]["sha256"]),
            )
    else:
        _fail("final qualification required-test is unknown")
    return dict(raw)


def _resolve_local_annotated_tag(tag_name: str) -> tuple[str, str, str]:
    try:
        object_type = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-t", tag_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        object_id = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", tag_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        target_commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{tag_name}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError(
            f"cannot resolve annotated release tag {tag_name}: {error}"
        ) from error
    if (
        object_type != "tag"
        or _COMMIT.fullmatch(object_id) is None
        or _COMMIT.fullmatch(target_commit) is None
    ):
        _fail("release tag is not an exact local annotated Git tag")
    return object_type, object_id, target_commit


def _verify_tag_record(
    payload: bytes, *, firmware_version: str, source_commit: str
) -> dict[str, object]:
    record = _mapping(
        _decode_json(payload, name="annotated tag record"), name="annotated tag record"
    )
    _exact_keys(
        record,
        {
            "schema",
            "name",
            "object_type",
            "object_id",
            "target_type",
            "target_commit",
            "signature_verification",
        },
        name="annotated tag record",
    )
    tag_name = _string(record["name"], name="release tag", maximum=256)
    if _TAG.fullmatch(tag_name) is None or tag_name != firmware_version:
        _fail("annotated tag name differs from the qualified firmware version")
    object_id = _string(record["object_id"], name="annotated tag object", maximum=40)
    target_commit = _string(
        record["target_commit"], name="annotated tag target", maximum=40
    )
    expected = {
        "schema": TAG_RECORD_SCHEMA,
        "name": tag_name,
        "object_type": "tag",
        "object_id": object_id,
        "target_type": "commit",
        "target_commit": source_commit,
        "signature_verification": "not-performed-or-claimed",
    }
    if (
        _COMMIT.fullmatch(object_id) is None
        or target_commit != source_commit
        or dict(record) != expected
    ):
        _fail("annotated tag record shape/target is not exact")
    local_type, local_object, local_target = _resolve_local_annotated_tag(tag_name)
    if (local_type, local_object, local_target) != ("tag", object_id, source_commit):
        _fail("annotated tag record differs from the exact local Git object")
    return expected


def _verify_remote_tag_record(
    payload: bytes,
    *,
    tag_name: str,
    local_tag_object: str,
    source_commit: str,
) -> dict[str, object]:
    record = _mapping(
        _decode_json(payload, name="remote annotated tag record"),
        name="remote annotated tag record",
    )
    _exact_keys(
        record,
        {"schema", "command", "exit_code", "refs"},
        name="remote annotated tag record",
    )
    tag_ref = f"refs/tags/{tag_name}"
    peeled_ref = f"{tag_ref}^{{}}"
    expected_command = [
        "git",
        "ls-remote",
        "--tags",
        RELEASE_GIT_REMOTE_URL,
        tag_ref,
        peeled_ref,
    ]
    if (
        record["schema"] != REMOTE_TAG_RECORD_SCHEMA
        or record["command"] != expected_command
        or type(record["exit_code"]) is not int
        or record["exit_code"] != 0
    ):
        _fail("remote annotated tag capture command/result is not exact")
    raw_refs = record["refs"]
    if type(raw_refs) is not list or len(raw_refs) != 2:
        _fail("remote annotated tag record must contain exactly tag and peeled refs")
    refs: list[dict[str, str]] = []
    for position, raw_ref in enumerate(raw_refs):
        ref = _mapping(raw_ref, name=f"remote annotated tag ref {position}")
        _exact_keys(
            ref,
            {"object_id", "ref"},
            name=f"remote annotated tag ref {position}",
        )
        object_id = _string(
            ref["object_id"],
            name=f"remote annotated tag ref {position} object",
            maximum=40,
        )
        if _COMMIT.fullmatch(object_id) is None:
            _fail(f"remote annotated tag ref {position} object is not a Git object ID")
        refs.append(
            {
                "object_id": object_id,
                "ref": _string(
                    ref["ref"],
                    name=f"remote annotated tag ref {position} name",
                    maximum=512,
                ),
            }
        )
    if [ref["ref"] for ref in refs] != [tag_ref, peeled_ref]:
        _fail("remote annotated tag ref inventory/order is not exact")
    if refs[0]["object_id"] != local_tag_object:
        _fail("remote annotated tag object differs from the exact local tag object")
    if refs[1]["object_id"] != source_commit:
        _fail("remote annotated tag peeled target differs from the qualified commit")
    return {
        "schema": REMOTE_TAG_RECORD_SCHEMA,
        "command": expected_command,
        "exit_code": 0,
        "refs": refs,
    }


def _verify_frm(
    path: Path, *, fit_bytes: int, fit_sha256: str, expected_sha256: str
) -> tuple[int, str]:
    size, digest, prefix = _hash_regular(
        path,
        name="published FRM",
        prefix_bytes=fit_bytes,
    )
    if size != fit_bytes + 33 or digest != expected_sha256 or prefix != fit_sha256:
        _fail("published FRM does not carry the exact qualified FIT bytes")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        body_md5 = hashlib.md5(usedforsecurity=False)
        remaining = fit_bytes
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                _fail("published FRM FIT body is truncated")
            body_md5.update(chunk)
            remaining -= len(chunk)
        trailer = os.read(descriptor, 34)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if trailer != f"{body_md5.hexdigest()}\n".encode() or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        _fail("published FRM MD5 trailer is invalid or changed during verification")
    return size, digest


def _published_asset(
    root: Path, relative: object, *, release_url: str, name: str
) -> dict[str, object]:
    path_text = _relative(relative, name=f"published {name} path")
    member = _capture_member(root, path_text, name=f"published {name}")
    member["url"] = f"{release_url}/{PurePosixPath(path_text).name}"
    return member


def _canonical_release_urls(tag_name: str) -> tuple[str, str]:
    base = "https://github.com/misko/plutosdr-fw/releases"
    return f"{base}/download/{tag_name}", f"{base}/tag/{tag_name}"


def _verify_release_inventory(
    payload: bytes,
    *,
    tag_name: str,
    published_assets: Sequence[Mapping[str, object]],
) -> None:
    record = _mapping(
        _decode_json(payload, name="GitHub release inventory"),
        name="GitHub release inventory",
    )
    _exact_keys(
        record,
        {"schema", "command", "exit_code", "result"},
        name="GitHub release inventory",
    )
    expected_command = [
        "gh",
        "api",
        f"repos/misko/plutosdr-fw/releases/tags/{tag_name}",
        "--jq",
        RELEASE_INVENTORY_JQ,
    ]
    result = _mapping(record.get("result"), name="GitHub release view result")
    _exact_keys(
        result,
        {"tagName", "isDraft", "isPrerelease", "url", "assets"},
        name="GitHub release view result",
    )
    _download_url, release_page_url = _canonical_release_urls(tag_name)
    if (
        record.get("schema") != RELEASE_INVENTORY_SCHEMA
        or record.get("command") != expected_command
        or type(record.get("exit_code")) is not int
        or record.get("exit_code") != 0
        or result.get("tagName") != tag_name
        or result.get("isDraft") is not False
        or result.get("isPrerelease") is not False
        or result.get("url") != release_page_url
    ):
        _fail("GitHub release inventory is not an exact published release")
    raw_assets = result.get("assets")
    if not isinstance(raw_assets, Sequence) or isinstance(raw_assets, (str, bytes)):
        _fail("GitHub release inventory assets must be an array")
    inventory: dict[str, Mapping[str, Any]] = {}
    for position, raw_asset in enumerate(raw_assets):
        asset = _mapping(raw_asset, name=f"GitHub release asset {position}")
        _exact_keys(
            asset,
            {"name", "size", "state", "url", "digest"},
            name=f"GitHub release asset {position}",
        )
        name = _safe_id(asset.get("name"), name=f"GitHub release asset {position} name")
        if name in inventory:
            _fail("GitHub release inventory has duplicate asset names")
        inventory[name] = asset
    expected_names = {
        PurePosixPath(str(published["path"])).name for published in published_assets
    }
    if set(inventory) != expected_names:
        _fail("GitHub release inventory is not the exact three-asset set")
    for published in published_assets:
        name = PurePosixPath(str(published["path"])).name
        remote = inventory.get(name)
        if remote is None:
            _fail(f"GitHub release inventory omits published asset {name}")
        if (
            remote.get("state") != "uploaded"
            or type(remote.get("size")) is not int
            or remote.get("size") != published["bytes"]
            or remote.get("url") != published["url"]
            or remote.get("digest") != f"sha256:{published['sha256']}"
        ):
            _fail(f"GitHub release inventory asset {name} is not exact")


def _verify_published_asset(
    root: Path, value: object, *, release_url: str, name: str
) -> tuple[dict[str, object], Path]:
    asset = _mapping(value, name=f"published {name}")
    _exact_keys(asset, {"path", "bytes", "sha256", "url"}, name=f"published {name}")
    member, path = _verify_member(
        root,
        {key: asset[key] for key in ("path", "bytes", "sha256")},
        name=f"published {name}",
    )
    expected_url = f"{release_url}/{PurePosixPath(str(member['path'])).name}"
    if _https_url(asset["url"], name=f"published {name} URL") != expected_url:
        _fail(f"published {name} URL is not exact")
    return {**member, "url": expected_url}, path


def _verify_release_manifest(
    payload: bytes,
    *,
    tag_name: str,
    source_commit: str,
    firmware_version: str,
    dfu: Mapping[str, object],
    frm: Mapping[str, object],
    bundle: Mapping[str, object],
    source_manifest: Mapping[str, str],
) -> dict[str, str]:
    values = _manifest_values(payload)
    verifier_required = {
        "release_tag",
        "asset_name",
        "image_url",
        "image_sha256",
        "device_fw",
        "firmware_source",
        "gadget_source",
        "submodule_buildroot",
        "submodule_linux",
        "submodule_u_boot_xlnx",
        "versions_hdl",
        "versions_buildroot",
        "versions_linux",
        "versions_u_boot_xlnx",
        "fpga_bitstream_md5",
        "ramdisk_md5",
        "fit_description",
    }
    missing = verifier_required - set(values)
    if missing:
        _fail(
            "published release manifest omits verify_release.sh field(s): "
            + ", ".join(sorted(missing))
        )
    expected = {
        "release_tag": tag_name,
        "asset_name": PurePosixPath(str(dfu["path"])).name,
        "image_url": str(dfu["url"]),
        "image_sha256": str(dfu["sha256"]),
        "device_fw": firmware_version,
        "firmware_source": source_commit,
        "frm_asset_name": PurePosixPath(str(frm["path"])).name,
        "frm_sha256": str(frm["sha256"]),
        "bundle_asset_name": PurePosixPath(str(bundle["path"])).name,
        "bundle_sha256": str(bundle["sha256"]),
        "hardware_qualified": "true",
    }
    if (
        values.get("schema") != "plutosdr-fw.build-manifest"
        or values.get("schema_version") != "1"
    ):
        _fail("published release manifest schema/version is not exact")
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            _fail(f"published release manifest field {key} is not exact")
    for key in (
        "gadget_source",
        "submodule_buildroot",
        "submodule_linux",
        "submodule_u_boot_xlnx",
        "versions_hdl",
        "versions_buildroot",
        "versions_linux",
        "versions_u_boot_xlnx",
    ):
        if values.get(key) != source_manifest.get(key):
            _fail(f"published release manifest field {key} differs from source lock")
    for key in (
        "gadget_source",
        "submodule_buildroot",
        "submodule_linux",
        "submodule_u_boot_xlnx",
    ):
        if _COMMIT.fullmatch(values[key]) is None:
            _fail(f"published release manifest field {key} is not a Git object ID")
    for key in ("fpga_bitstream_md5", "ramdisk_md5"):
        if re.fullmatch(r"[0-9a-f]{32}", values[key]) is None:
            _fail(f"published release manifest field {key} is not lowercase MD5")
    _string(values["fit_description"], name="published FIT description")
    return values


def _verify_release_result(
    payload: bytes,
    *,
    verifier_sha256: str,
    manifest_path: str,
    manifest_sha256: str,
    verification_image_path: str,
    dfu_sha256: str,
    tag_name: str,
    firmware_version: str,
    source_commit: str,
    release_manifest: Mapping[str, str],
) -> None:
    record = _mapping(
        _decode_json(payload, name="published verification result"),
        name="published verification result",
    )
    _exact_keys(
        record,
        {
            "schema",
            "command",
            "exit_code",
            "verifier_sha256",
            "manifest_sha256",
            "result",
        },
        name="published verification result",
    )
    image_parent = PurePosixPath(verification_image_path).parent.as_posix()
    expected_command = [
        "env",
        f"VERIFY_RELEASE_CACHE={image_parent}",
        "scripts/verify_release.sh",
        manifest_path,
        "--json",
    ]
    if record["command"] != expected_command:
        _fail("published verification command is not exact")
    recorded_verifier_sha256 = _sha(
        record["verifier_sha256"], name="published binary verifier SHA-256"
    )
    result = _mapping(record["result"], name="verify_release JSON result")
    _exact_keys(
        result,
        {
            "release_verified",
            "release_tag",
            "image",
            "image_sha256",
            "device_fw",
            "firmware_source",
            "gadget_source",
            "fpga_bitstream_md5",
            "checks_passed",
        },
        name="verify_release JSON result",
    )
    if (
        record["schema"] != RELEASE_VERIFICATION_SCHEMA
        or record["exit_code"] != 0
        or type(record["exit_code"]) is not int
        or recorded_verifier_sha256 != verifier_sha256
        or record["manifest_sha256"] != manifest_sha256
        or result.get("release_verified") is not True
        or result.get("release_tag") != tag_name
        or result.get("image") != verification_image_path
        or result.get("image_sha256") != dfu_sha256
        or result.get("device_fw") != firmware_version
        or result.get("firmware_source") != source_commit
        or result.get("gadget_source") != release_manifest["gadget_source"]
        or result.get("fpga_bitstream_md5") != release_manifest["fpga_bitstream_md5"]
        or result.get("checks_passed") != 14
        or type(result.get("checks_passed")) is not int
    ):
        _fail("published verification result is not exact and successful")


def _assemble_published_release(
    root: Path, *, final_qualification_index_path: Path, input_path: Path
) -> dict[str, Any]:
    parent, qualification = _capture_index_reference(
        root,
        final_qualification_index_path,
        expected_stage="final-qualified",
        name="final qualification index",
    )
    final_artifact, final_path = _verify_index_reference(
        root,
        qualification["final_artifact"],
        expected_stage="final-pre-confirmation",
        name="published final artifact lineage",
    )
    raw = _mapping(
        _decode_json(
            _read_small(input_path, name="published release input"),
            name="published release input",
        ),
        name="published release input",
    )
    _exact_keys(
        raw,
        {
            "schema",
            "schema_version",
            "stage",
            "release_url",
            "tag_record_path",
            "remote_tag_record_path",
            "dfu_path",
            "frm_path",
            "bundle_path",
            "release_inventory_path",
            "release_manifest_path",
            "verification_image_path",
            "verification_result_path",
        },
        name="published release input",
    )
    if (
        raw["schema"] != PUBLISHED_INPUT_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
        or raw["stage"] != "published-release"
    ):
        _fail("published release input schema/stage is not exact")
    expected_release_url, _release_page_url = _canonical_release_urls(
        final_artifact["release"]["firmware_version"]
    )
    release_url = _https_url(raw["release_url"], name="published release URL")
    if release_url != expected_release_url:
        _fail("published release URL is not the canonical repository/tag")
    tag_relative = _relative(raw["tag_record_path"], name="annotated tag record path")
    tag_member = _capture_member(root, tag_relative, name="annotated tag record")
    tag_record = _verify_tag_record(
        _read_small(
            _member_path(root, tag_relative, name="annotated tag record"),
            name="annotated tag record",
        ),
        firmware_version=final_artifact["release"]["firmware_version"],
        source_commit=final_artifact["source"]["commit"],
    )
    remote_tag_relative = _relative(
        raw["remote_tag_record_path"], name="remote annotated tag record path"
    )
    remote_tag_member = _capture_member(
        root, remote_tag_relative, name="remote annotated tag record"
    )
    _verify_remote_tag_record(
        _read_small(
            _member_path(root, remote_tag_relative, name="remote annotated tag record"),
            name="remote annotated tag record",
        ),
        tag_name=str(tag_record["name"]),
        local_tag_object=str(tag_record["object_id"]),
        source_commit=final_artifact["source"]["commit"],
    )
    dfu = _published_asset(root, raw["dfu_path"], release_url=release_url, name="DFU")
    frm = _published_asset(root, raw["frm_path"], release_url=release_url, name="FRM")
    bundle = _published_asset(
        root, raw["bundle_path"], release_url=release_url, name="bundle"
    )
    if (
        dfu["bytes"] != final_artifact["artifact"]["dfu_bytes"]
        or dfu["sha256"] != final_artifact["artifact"]["dfu_sha256"]
    ):
        _fail("published DFU differs from the qualified final artifact")
    final_roles = _role_map(final_artifact)
    if bundle["sha256"] != final_roles["bundle"]["sha256"]:
        _fail("published bundle differs from the qualified final bundle")
    _verify_frm(
        _member_path(root, str(frm["path"]), name="published FRM"),
        fit_bytes=final_artifact["artifact"]["fit_bytes"],
        fit_sha256=final_artifact["artifact"]["fit_sha256"],
        expected_sha256=str(frm["sha256"]),
    )
    inventory_relative = _relative(
        raw["release_inventory_path"], name="GitHub release inventory path"
    )
    inventory_member = _capture_member(
        root, inventory_relative, name="GitHub release inventory"
    )
    _verify_release_inventory(
        _read_small(
            _member_path(root, inventory_relative, name="GitHub release inventory"),
            name="GitHub release inventory",
        ),
        tag_name=str(tag_record["name"]),
        published_assets=(dfu, frm, bundle),
    )
    manifest_relative = _relative(
        raw["release_manifest_path"], name="published release manifest path"
    )
    manifest_member = _capture_member(
        root, manifest_relative, name="published release manifest"
    )
    manifest_payload = _read_small(
        _member_path(root, manifest_relative, name="published release manifest"),
        name="published release manifest",
    )
    release_manifest = _verify_release_manifest(
        manifest_payload,
        tag_name=str(tag_record["name"]),
        source_commit=final_artifact["source"]["commit"],
        firmware_version=final_artifact["release"]["firmware_version"],
        dfu=dfu,
        frm=frm,
        bundle=bundle,
        source_manifest=_manifest_for_artifact(final_artifact, final_path),
    )
    verification_relative = _relative(
        raw["verification_result_path"], name="published verification result path"
    )
    verification_image_relative = _relative(
        raw["verification_image_path"], name="remote verification image path"
    )
    if (
        PurePosixPath(verification_image_relative).parent.as_posix()
        != "remote-verification-cache"
        or PurePosixPath(verification_image_relative).name
        != PurePosixPath(str(dfu["path"])).name
        or verification_image_relative == dfu["path"]
    ):
        _fail("remote verification image path is not exact and separate")
    verification_image = _capture_member(
        root, verification_image_relative, name="remote verification image"
    )
    if (
        verification_image["bytes"] != dfu["bytes"]
        or verification_image["sha256"] != dfu["sha256"]
    ):
        _fail("remote verification image differs from the published DFU")
    verification_member = _capture_member(
        root, verification_relative, name="published verification result"
    )
    _verify_release_result(
        _read_small(
            _member_path(
                root, verification_relative, name="published verification result"
            ),
            name="published verification result",
        ),
        verifier_sha256=next(
            str(member["sha256"])
            for member in final_artifact["harness"]["files"]
            if member["path"] == RELEASE_VERIFIER_HARNESS_PATH
        ),
        manifest_path=manifest_relative,
        manifest_sha256=str(manifest_member["sha256"]),
        verification_image_path=verification_image_relative,
        dfu_sha256=str(dfu["sha256"]),
        tag_name=str(tag_record["name"]),
        firmware_version=final_artifact["release"]["firmware_version"],
        source_commit=final_artifact["source"]["commit"],
        release_manifest=release_manifest,
    )
    return {
        "schema": PUBLISHED_INDEX_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "stage": "published-release",
        "source_commit": final_artifact["source"]["commit"],
        "release_url": release_url,
        "parent": parent,
        "tag_record": tag_member,
        "remote_tag_record": remote_tag_member,
        "assets": {"dfu": dfu, "frm": frm, "bundle": bundle},
        "release_inventory": inventory_member,
        "release_manifest": manifest_member,
        "verification_image": verification_image,
        "verification_result": verification_member,
    }


def _verify_published_release(index_path: Path) -> dict[str, Any]:
    root, _payload, raw, _digest = _read_index_record(
        index_path, name="published release index"
    )
    _exact_keys(
        raw,
        {
            "schema",
            "schema_version",
            "stage",
            "source_commit",
            "release_url",
            "parent",
            "tag_record",
            "remote_tag_record",
            "assets",
            "release_inventory",
            "release_manifest",
            "verification_image",
            "verification_result",
        },
        name="published release index",
    )
    if (
        raw["schema"] != PUBLISHED_INDEX_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
        or raw["stage"] != "published-release"
    ):
        _fail("published release index schema/stage is not exact")
    release_url = _https_url(raw["release_url"], name="published release URL")
    qualification, _qualification_path = _verify_index_reference(
        root,
        raw["parent"],
        expected_stage="final-qualified",
        name="published final qualification parent",
    )
    final_artifact, final_path = _verify_index_reference(
        root,
        qualification["final_artifact"],
        expected_stage="final-pre-confirmation",
        name="published final artifact lineage",
    )
    if raw["source_commit"] != final_artifact["source"]["commit"]:
        _fail("published release source commit differs from qualification lineage")
    expected_release_url, _release_page_url = _canonical_release_urls(
        final_artifact["release"]["firmware_version"]
    )
    if release_url != expected_release_url:
        _fail("published release URL is not the canonical repository/tag")
    tag_member, tag_path = _verify_member(
        root, raw["tag_record"], name="published annotated tag record"
    )
    del tag_member
    tag_record = _verify_tag_record(
        _read_small(tag_path, name="annotated tag record"),
        firmware_version=final_artifact["release"]["firmware_version"],
        source_commit=final_artifact["source"]["commit"],
    )
    _remote_tag_member, remote_tag_path = _verify_member(
        root, raw["remote_tag_record"], name="published remote annotated tag record"
    )
    _verify_remote_tag_record(
        _read_small(remote_tag_path, name="remote annotated tag record"),
        tag_name=str(tag_record["name"]),
        local_tag_object=str(tag_record["object_id"]),
        source_commit=final_artifact["source"]["commit"],
    )
    assets = _mapping(raw["assets"], name="published assets")
    _exact_keys(assets, {"dfu", "frm", "bundle"}, name="published assets")
    dfu, _dfu_path = _verify_published_asset(
        root, assets["dfu"], release_url=release_url, name="DFU"
    )
    frm, frm_path = _verify_published_asset(
        root, assets["frm"], release_url=release_url, name="FRM"
    )
    bundle, _bundle_path = _verify_published_asset(
        root, assets["bundle"], release_url=release_url, name="bundle"
    )
    if (
        dfu["bytes"] != final_artifact["artifact"]["dfu_bytes"]
        or dfu["sha256"] != final_artifact["artifact"]["dfu_sha256"]
        or bundle["sha256"] != _role_map(final_artifact)["bundle"]["sha256"]
    ):
        _fail("published assets differ from the qualified final artifact")
    _verify_frm(
        frm_path,
        fit_bytes=final_artifact["artifact"]["fit_bytes"],
        fit_sha256=final_artifact["artifact"]["fit_sha256"],
        expected_sha256=str(frm["sha256"]),
    )
    _inventory_member, inventory_path = _verify_member(
        root, raw["release_inventory"], name="GitHub release inventory"
    )
    _verify_release_inventory(
        _read_small(inventory_path, name="GitHub release inventory"),
        tag_name=str(tag_record["name"]),
        published_assets=(dfu, frm, bundle),
    )
    manifest_member, manifest_path = _verify_member(
        root, raw["release_manifest"], name="published release manifest"
    )
    manifest_payload = _read_small(manifest_path, name="published release manifest")
    release_manifest = _verify_release_manifest(
        manifest_payload,
        tag_name=str(tag_record["name"]),
        source_commit=final_artifact["source"]["commit"],
        firmware_version=final_artifact["release"]["firmware_version"],
        dfu=dfu,
        frm=frm,
        bundle=bundle,
        source_manifest=_manifest_for_artifact(final_artifact, final_path),
    )
    verification_image, _verification_image_path = _verify_member(
        root, raw["verification_image"], name="remote verification image"
    )
    expected_verification_relative = (
        "remote-verification-cache/" + PurePosixPath(str(dfu["path"])).name
    )
    if (
        verification_image["path"] != expected_verification_relative
        or verification_image["bytes"] != dfu["bytes"]
        or verification_image["sha256"] != dfu["sha256"]
    ):
        _fail("remote verification image differs from the published DFU")
    verification_member, verification_path = _verify_member(
        root, raw["verification_result"], name="published verification result"
    )
    del verification_member
    _verify_release_result(
        _read_small(verification_path, name="published verification result"),
        verifier_sha256=next(
            str(member["sha256"])
            for member in final_artifact["harness"]["files"]
            if member["path"] == RELEASE_VERIFIER_HARNESS_PATH
        ),
        manifest_path=str(manifest_member["path"]),
        manifest_sha256=str(manifest_member["sha256"]),
        verification_image_path=str(verification_image["path"]),
        dfu_sha256=str(dfu["sha256"]),
        tag_name=str(tag_record["name"]),
        firmware_version=final_artifact["release"]["firmware_version"],
        source_commit=final_artifact["source"]["commit"],
        release_manifest=release_manifest,
    )
    return dict(raw)


def _assemble_input(
    input_path: Path,
    archive_root: Path,
) -> dict[str, Any]:
    raw = _mapping(
        _decode_json(
            _read_small(input_path, name="evidence input"), name="evidence input"
        ),
        name="evidence input",
    )
    _exact_keys(
        raw,
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
        name="evidence input",
    )
    if (
        raw["schema"] != INPUT_SCHEMA
        or raw["schema_version"] != SCHEMA_VERSION
        or type(raw["schema_version"]) is not int
    ):
        _fail("evidence input schema/version is not exact")

    stage = _string(raw["stage"], name="evidence input stage")
    release = _mapping(raw["release"], name="evidence input release")
    source_input = _mapping(raw["source"], name="evidence input source")
    _exact_keys(source_input, {"commit", "manifest_path"}, name="evidence input source")
    commit = _string(source_input["commit"], name="evidence source commit", maximum=40)
    if _COMMIT.fullmatch(commit) is None:
        _fail("evidence source commit is not lowercase 40-hex")
    manifest_relative = _relative(
        source_input["manifest_path"], name="evidence source manifest path"
    )
    manifest_path = _member_path(
        archive_root, manifest_relative, name="evidence source manifest"
    )
    _manifest_bytes, manifest_sha, _ = _hash_regular(
        manifest_path, name="evidence source manifest", maximum=MAX_JSON_BYTES
    )
    release_input = _mapping(raw["release"], name="evidence input release")
    firmware_version = _string(
        release_input.get("firmware_version"), name="evidence firmware version"
    )
    profile = _verify_profile_release(release, stage=stage)
    _verify_committed_source_manifest(
        stage=stage,
        firmware_version=firmware_version,
        archived_relative=manifest_relative,
        archived_sha256=manifest_sha,
        commit=commit,
    )

    build = _mapping(raw["build"], name="evidence input build")
    artifact_input = _mapping(raw["artifact"], name="evidence input artifact")
    _exact_keys(
        artifact_input, {"dfu_path", "fit_bytes"}, name="evidence input artifact"
    )
    dfu_relative = _relative(artifact_input["dfu_path"], name="evidence DFU path")
    fit_bytes = _positive_int(artifact_input["fit_bytes"], name="evidence FIT bytes")
    dfu_path = _member_path(archive_root, dfu_relative, name="evidence DFU")
    dfu_bytes, dfu_sha, fit_sha = _hash_regular(
        dfu_path, name="evidence DFU", prefix_bytes=fit_bytes
    )
    if fit_bytes + 16 != dfu_bytes or fit_sha is None:
        _fail("evidence DFU is not an exact FIT plus 16-byte suffix")

    harness_input = _mapping(raw["harness"], name="evidence input harness")
    _exact_keys(harness_input, {"paths"}, name="evidence input harness")
    harness_paths = harness_input["paths"]
    if not isinstance(harness_paths, Sequence) or isinstance(
        harness_paths, (str, bytes)
    ):
        _fail("evidence harness paths must be an array")
    harness_entries: list[dict[str, object]] = []
    for index, raw_path in enumerate(harness_paths):
        relative = _relative(raw_path, name=f"evidence harness path {index}")
        path = _member_path(archive_root, relative, name=f"evidence harness {index}")
        _bytes, digest, _ = _hash_regular(path, name=f"evidence harness {relative}")
        harness_entries.append({"path": relative, "sha256": digest})
    harness_entries.sort(key=lambda entry: str(entry["path"]))
    harness_digest_map = {
        str(entry["path"]): str(entry["sha256"]) for entry in harness_entries
    }
    semantic_digest = harness_digest_map.get(SEMANTIC_VERIFIER_HARNESS_PATH)
    if semantic_digest is None:
        _fail("evidence harness omits the semantic release-evidence verifier")
    _live_size, live_semantic_digest, _live_prefix = _hash_regular(
        ROOT / SEMANTIC_VERIFIER_HARNESS_PATH,
        name="live semantic release-evidence verifier",
        maximum=MAX_JSON_BYTES,
    )
    if (
        semantic_digest != live_semantic_digest
        or semantic_digest
        != _committed_file_sha256(commit, SEMANTIC_VERIFIER_HARNESS_PATH)
    ):
        _fail("evidence harness semantic verifier is not exact live committed source")
    release_verifier_digest = harness_digest_map.get(RELEASE_VERIFIER_HARNESS_PATH)
    if release_verifier_digest is None:
        _fail("evidence harness omits the binary release verifier")
    _live_size, live_release_verifier_digest, _live_prefix = _hash_regular(
        ROOT / RELEASE_VERIFIER_HARNESS_PATH,
        name="live binary release verifier",
        maximum=MAX_JSON_BYTES,
    )
    if (
        release_verifier_digest != live_release_verifier_digest
        or release_verifier_digest
        != _committed_file_sha256(commit, RELEASE_VERIFIER_HARNESS_PATH)
    ):
        _fail("evidence harness binary verifier is not exact live committed source")

    evidence_input = _mapping(raw["evidence"], name="evidence input members")
    _exact_keys(evidence_input, {"members"}, name="evidence input members")
    raw_members = evidence_input["members"]
    if not isinstance(raw_members, Sequence) or isinstance(raw_members, (str, bytes)):
        _fail("evidence members must be an array")
    member_paths: dict[str, str] = {}
    for index, raw_member in enumerate(raw_members):
        member = _mapping(raw_member, name=f"evidence input member {index}")
        _exact_keys(member, {"role", "path"}, name=f"evidence input member {index}")
        role = _string(member["role"], name=f"evidence input role {index}")
        if role in member_paths:
            _fail(f"evidence input duplicates role {role}")
        member_paths[role] = _relative(
            member["path"], name=f"evidence input member path {index}"
        )
    if tuple(sorted(member_paths)) != REQUIRED_EVIDENCE_ROLES:
        _fail("evidence input role inventory is not exact")
    evidence_entries: list[dict[str, object]] = []
    for role in REQUIRED_EVIDENCE_ROLES:
        relative = member_paths[role]
        path = _member_path(archive_root, relative, name=f"evidence role {role}")
        size, digest, _ = _hash_regular(path, name=f"evidence role {role}")
        evidence_entries.append(
            {"role": role, "path": relative, "bytes": size, "sha256": digest}
        )

    candidate = {
        "schema": ARTIFACT_INDEX_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "release": dict(release),
        "source": {
            "commit": commit,
            "manifest_path": manifest_relative,
            "manifest_sha256": manifest_sha,
        },
        "build": dict(build),
        "artifact": {
            "dfu_path": dfu_relative,
            "dfu_bytes": dfu_bytes,
            "dfu_sha256": dfu_sha,
            "fit_bytes": fit_bytes,
            "fit_sha256": fit_sha,
        },
        "harness": {"files": harness_entries},
        "evidence": {"members": evidence_entries},
    }
    try:
        validated = validate_artifact_index(candidate)
    except CandidateBindingError as error:
        raise EvidenceError(str(error)) from error
    if tuple(item["path"] for item in validated["harness"]["files"]) != (
        ARTIFACT_HARNESS_PATHS
    ):
        _fail("candidate index harness is not the exact release/lifecycle superset")
    roles = _role_map(validated)
    semantic_payloads = {
        role: _read_small(
            _member_path(
                root=archive_root,
                relative=roles[role]["path"],
                name=f"evidence role {role}",
            ),
            name=f"evidence role {role}",
        )
        for role in (
            "actions-run",
            "attestation-verification",
            "integrated-verdict",
            "ooc-status",
            "packed-versions",
            "source-lock",
        )
    }
    _verify_source_lock(
        semantic_payloads["source-lock"],
        commit=commit,
        expected_ref=profile["source_lock_ref"],
    )
    _verify_actions_run(
        semantic_payloads["actions-run"],
        commit=commit,
        run_id=validated["build"]["run_id"],
        run_attempt=validated["build"]["run_attempt"],
        firmware_version=validated["release"]["firmware_version"],
    )
    _verify_ooc_status(
        semantic_payloads["ooc-status"],
        commit=commit,
        manifest_sha=roles["ooc-evidence-manifest"]["sha256"],
    )
    _verify_packed_versions(
        semantic_payloads["packed-versions"],
        firmware_version=validated["release"]["firmware_version"],
        manifest=_manifest_values(_read_small(manifest_path, name="source manifest")),
    )
    _verify_integrated_verdict(
        semantic_payloads["integrated-verdict"],
        commit=commit,
        manifest_path=manifest_relative,
        manifest_bytes=_manifest_bytes,
        manifest_sha=manifest_sha,
        roles=roles,
    )
    _verify_attestation_record(
        semantic_payloads["attestation-verification"],
        commit=commit,
        run_id=validated["build"]["run_id"],
        run_attempt=validated["build"]["run_attempt"],
        bundle_sha=roles["bundle"]["sha256"],
        bundle_name=PurePosixPath(roles["bundle"]["path"]).name,
        firmware_version=validated["release"]["firmware_version"],
    )
    _verify_bundle_contract(
        archive_root,
        index=validated,
        roles=roles,
        manifest_sha256=manifest_sha,
    )
    return validated


def verify_index(index_path: Path, *, expected_stage: str) -> dict[str, Any]:
    if expected_stage in {"candidate-pre-hardware", "final-pre-confirmation"}:
        return _verify_artifact_index(
            index_path,
            expected_stage=expected_stage,
        )
    if expected_stage == "candidate-qualified":
        return _verify_candidate_qualified(index_path)
    if expected_stage == "final-qualification-policy":
        return _verify_final_policy(index_path)
    if expected_stage == "final-qualified":
        return _verify_final_qualified(index_path)
    if expected_stage == "published-release":
        return _verify_published_release(index_path)
    _fail(f"unknown release evidence stage {expected_stage}")


def verify_artifact_index_semantics(
    index_path: Path, *, expected_stage: str
) -> dict[str, Any]:
    """Return the locally authorized, candidate_binding-normalized index.

    All archive references are canonical relative paths below
    ``index_path.parent`` and are read through bounded, owned, non-writable,
    regular-file descriptors.  The function never writes, opens hardware, or
    accesses the network.  Authorization follows this project's documented
    single-owner/operator trust model: the exact local source lock and committed
    verifier are resolved, and all captured build identities, bundle checksums,
    archive members, and indexed digests must agree.  The GitHub attestation
    record is supporting, schema-validated metadata; this function does not
    claim independent DSSE or signature authentication.
    """

    if expected_stage not in {"candidate-pre-hardware", "final-pre-confirmation"}:
        _fail("semantic artifact verification requires an exact pre-hardware stage")
    return verify_index(index_path, expected_stage=expected_stage)


def assemble(
    *,
    archive_root: Path,
    output_path: Path,
    stage: str,
    input_path: Path | None = None,
    parent_index_path: Path | None = None,
    candidate_qualified_index_path: Path | None = None,
    policy_index_path: Path | None = None,
    diff_path: Path | None = None,
) -> dict[str, Any]:
    root = _canonical_root(archive_root)
    output_path = output_path.absolute()
    if output_path.parent != root:
        _fail("output must be a direct child of the archive root")
    expected_filename = INDEX_FILENAMES.get(stage)
    if expected_filename is None or output_path.name != expected_filename:
        _fail(f"output name is not exact for stage {stage}: {expected_filename}")
    if input_path is not None:
        input_path = input_path.absolute()
        if input_path.parent != root:
            _fail("input must be a direct child of the archive root")

    if stage in {"candidate-pre-hardware", "final-pre-confirmation"}:
        if (
            input_path is None
            or parent_index_path is not None
            or candidate_qualified_index_path is not None
            or policy_index_path is not None
            or diff_path is not None
        ):
            _fail("artifact-index assembly requires only --input")
        candidate = _assemble_input(
            input_path,
            root,
        )
        if candidate["stage"] != stage:
            _fail("evidence input stage differs from requested assembly stage")
    elif stage == "candidate-qualified":
        if (
            parent_index_path is None
            or input_path is not None
            or candidate_qualified_index_path is not None
            or policy_index_path is not None
            or diff_path is not None
        ):
            _fail("candidate-qualified assembly requires only --parent-index")
        candidate = _assemble_candidate_qualified(
            root, parent_index_path=parent_index_path
        )
    elif stage == "final-qualification-policy":
        if (
            parent_index_path is None
            or candidate_qualified_index_path is None
            or diff_path is None
            or input_path is not None
            or policy_index_path is not None
        ):
            _fail(
                "final-qualification-policy assembly requires --parent-index, "
                "--candidate-qualified-index, and --diff"
            )
        candidate = _assemble_final_policy(
            root,
            final_artifact_index_path=parent_index_path,
            candidate_qualified_index_path=candidate_qualified_index_path,
            diff_path=diff_path,
        )
    elif stage == "final-qualified":
        if (
            parent_index_path is None
            or policy_index_path is None
            or input_path is not None
            or candidate_qualified_index_path is not None
            or diff_path is not None
        ):
            _fail("final-qualified assembly requires --parent-index and --policy-index")
        candidate = _assemble_final_qualified(
            root,
            final_artifact_index_path=parent_index_path,
            policy_index_path=policy_index_path,
        )
    elif stage == "published-release":
        if (
            parent_index_path is None
            or input_path is None
            or candidate_qualified_index_path is not None
            or policy_index_path is not None
            or diff_path is not None
        ):
            _fail("published-release assembly requires --parent-index and --input")
        candidate = _assemble_published_release(
            root,
            final_qualification_index_path=parent_index_path,
            input_path=input_path,
        )
    else:
        _fail(f"unknown release evidence stage {stage}")
    payload = _canonical_json(candidate)
    digest = hashlib.sha256(payload).hexdigest()
    sidecar_path = output_path.with_suffix(output_path.suffix + ".sha256")
    _write_absent(output_path, payload, mode=0o644)
    # If this second absent-only publish fails, leave the immutable index in
    # place. Operators preserve the partial attempt and select a fresh root.
    _write_absent(
        sidecar_path,
        f"{digest}  {output_path.name}\n".encode(),
        mode=0o644,
    )
    return verify_index(output_path, expected_stage=stage)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--stage", required=True)
    assemble_parser.add_argument("--archive-root", required=True, type=Path)
    assemble_parser.add_argument("--input", type=Path)
    assemble_parser.add_argument("--parent-index", type=Path)
    assemble_parser.add_argument("--candidate-qualified-index", type=Path)
    assemble_parser.add_argument("--policy-index", type=Path)
    assemble_parser.add_argument("--diff", type=Path)
    assemble_parser.add_argument("--output", required=True, type=Path)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--stage", required=True)
    verify_parser.add_argument("--index", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    try:
        if namespace.command == "assemble":
            index = assemble(
                input_path=namespace.input,
                archive_root=namespace.archive_root,
                output_path=namespace.output,
                stage=namespace.stage,
                parent_index_path=namespace.parent_index,
                candidate_qualified_index_path=namespace.candidate_qualified_index,
                policy_index_path=namespace.policy_index,
                diff_path=namespace.diff,
            )
        else:
            index = verify_index(namespace.index, expected_stage=namespace.stage)
    except (EvidenceError, CandidateBindingError, OSError) as error:
        print(f"tandem release evidence failed: {error}", file=sys.stderr)
        return 1
    print(
        f"tandem release evidence PASS stage={index['stage']} "
        f"commit={_index_source_commit(index)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
