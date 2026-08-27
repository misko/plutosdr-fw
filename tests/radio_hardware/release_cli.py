"""Guarded, serial-scoped hardware qualification entry point for a v8 release.

The module intentionally does not deploy firmware.  It opens a fresh local-USB
radio for every steady-state matrix or band-specific transient/modulated cell,
then accepts evidence only after ``Issue46Radio.close()`` has appended verified
mute/selector/DDS cleanup to the durable report.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import statistics
import subprocess
import sys
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from dataclasses import fields as dataclass_fields
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.tandem_release_evidence import (
    EvidenceError,
    verify_artifact_index_semantics,
)

from . import release_campaign as steady_campaign
from .candidate_binding import (
    REQUIRED_EVIDENCE_ROLES,
    CandidateBindingError,
    validate_artifact_index,
)
from .experiment import TX_MUTE_DB, Issue46Options, Issue46Radio
from .metadata_abi import (
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_UNSAFE_FLAGS,
    TandemEventDirection,
    TandemEventReason,
    TandemMode,
    TandemState,
    build_tandem_request,
    parse_tandem_frame_metadata,
)
from .modulated_hardware import (
    DEFAULT_MODULATED_TX2_GAIN_DB,
    MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES,
    MODE_MANUAL,
    MODE_TANDEM,
    RELEASE_MODULATED_MODES,
    ModulatedHardwareOptions,
    evaluate_modulated_hardware_report,
    modulated_mode_evidence_policy,
    run_modulated_hardware_campaign,
    validate_modulated_hardware_options,
)
from .pluto_plus_candidate import (
    validate_release_candidate_plan,
    validate_release_candidate_receipt,
    validate_release_operation_plan,
    validate_release_usb_inventory,
)
from .release_campaign import (
    BandCase,
    PolicyCase,
    ReleaseCampaignConfig,
    build_campaign_report,
    build_release_plan,
    matrix_runner_for_radio_factory,
    run_release_campaign,
)
from .tandem_quality import (
    AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    default_tx_trajectory,
    evaluate_matrix,
    expected_tandem_gain_table,
    quality_modes,
    run_tandem_quality_matrix,
    validate_options,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
    run_transient_hardware,
    transient_evidence_policy,
    validate_transient_options,
)
from .transient_quality import (
    StimulusCommand,
    analyze_immediate_dual_rx,
    calculate_transient_response,
    reconcile_tandem_events,
)

AGGREGATE_SCHEMA = "plutosdr-fw.tandem-agc-release-hardware.v2"
AGGREGATE_CHECKPOINT = "release-hardware-checkpoint.json"
AGGREGATE_REPORT = "release-hardware-report.json"
DIAGNOSTIC_PHASE = "diagnostic-2450"
DIAGNOSTIC_BAND = BandCase("diagnostic-2450mhz", 2_450_000_000)
DIAGNOSTIC_PASS = "diagnostic_passed"
DIAGNOSTIC_FAIL = "diagnostic_failed"
DEFAULT_PHASES = ("steady", "transient", "modulated", DIAGNOSTIC_PHASE)
BASELINE_POLICY = PolicyCase("baseline", "baseline")
HARNESS_SOURCE_NAMES = (
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
RUNNER_PROVENANCE_SCHEMA = "plutosdr-fw.tandem-release-runner-provenance.v1"
HOST_LIBIIO_RUNTIME_SCHEMA = "plutosdr-fw.tandem-release-host-libiio-runtime.v1"
HOST_LIBIIO_WRAPPER_MARKER = "tandem-release-host-libiio-v1"
RUNNER_PROVENANCE_PATHS = (
    "scripts/deploy_tandem_agc_ram_hardware.sh",
    "scripts/run_tandem_agc_release_hardware.sh",
    "scripts/tandem_release_device_plan.py",
    "scripts/tandem_release_evidence.py",
    "tests/radio_hardware/candidate_binding.py",
    "tests/radio_hardware/pluto_plus_candidate.py",
    "tests/radio_hardware/release_cli.py",
)
MAXIMUM_ARTIFACT_INDEX_BYTES = 8 * 1024 * 1024
MAXIMUM_DEPLOYMENT_RECEIPT_BYTES = 8 * 1024 * 1024
MAXIMUM_SOURCE_MANIFEST_BYTES = 1024 * 1024
MAXIMUM_DFU_BYTES = 256 * 1024 * 1024
MAXIMUM_EVIDENCE_MEMBER_BYTES = 512 * 1024 * 1024
MAXIMUM_HARNESS_SOURCE_BYTES = 16 * 1024 * 1024
MAXIMUM_HOST_LIBIIO_CACHE_BYTES = 16 * 1024 * 1024
HOST_LIBIIO_CMAKE_CONFIGURATION = {
    "CMAKE_BUILD_TYPE": "Release",
    "HAVE_DNS_SD": "OFF",
    "INSTALL_UDEV_RULE": "OFF",
    "PYTHON_BINDINGS": "ON",
    "WITH_AIO": "OFF",
    "WITH_DOC": "OFF",
    "WITH_EXAMPLES": "OFF",
    "WITH_IIOD": "OFF",
    "WITH_LOCAL_BACKEND": "ON",
    "WITH_NETWORK_BACKEND": "ON",
    "WITH_SERIAL_BACKEND": "OFF",
    "WITH_TESTS": "OFF",
    "WITH_USB_BACKEND": "ON",
}

# Release-grade tandem transient acquisition is intentionally a different
# transport contract from the ordinary-mode 8,192-sample captures.  Keep the
# exact values here as an independent release-side oracle: accepting values
# copied only from the report (or from the runtime's own summary) would let a
# coordinated mutation silently redefine the qualification.
_TANDEM_BATCH_PROVIDER_FRAME_SAMPLES = 65_536
_TANDEM_BATCH_KERNEL_BUFFERS = 8
_TANDEM_BATCH_FRAMES = 64
_TANDEM_BATCH_QUEUE_FRAMES = 4
_TANDEM_BATCH_ATTACK_TARGET_FRAMES = 16
_TANDEM_BATCH_RELEASE_TARGET_FRAMES = 40
_TANDEM_BATCH_MINIMUM_PARTITION_FRAMES = 8
_TANDEM_BATCH_ANCHOR_SAMPLES = 8_192
_TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES = 1_024
_TANDEM_BATCH_METADATA_CAPACITY_BYTES = 64 * 1_024
_TANDEM_BATCH_METADATA_VERSION = 5
_TANDEM_BATCH_METADATA_HEADER_BYTES = 3_256
_TANDEM_BATCH_REQUIRED_METADATA_FEATURES = 904
_TANDEM_BATCH_SAMPLE_FORMAT = 1
_TANDEM_BATCH_SIZE_T_BYTES = 8
_TANDEM_BATCH_MAX_TARGET_OVERSHOOT_SAMPLES = 16_384
_TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES = 16_384
_TANDEM_BATCH_MAX_OBSERVATIONS_PER_FRAME = 5
_TANDEM_BATCH_MAX_EVENTS_PER_FRAME = 4
_TANDEM_BATCH_MINIMUM_EVENT_SPACING_SAMPLES = 17_408
_TANDEM_BATCH_MINIMUM_TEMPERATURE_MDEG_C = -40_000
_TANDEM_BATCH_MAXIMUM_TEMPERATURE_MDEG_C = 125_000
_TANDEM_BATCH_MAX_CORE_CACHE_BYTES = 64 * 1_024 * 1_024
_TANDEM_BATCH_MAX_PYTHON_RAW_BYTES = 32 * 1_024 * 1_024
_TANDEM_BATCH_MAX_AGGREGATE_BYTES = 96 * 1_024 * 1_024
_TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES = 8 * 1_024 * 1_024
_TANDEM_BATCH_POST_CLOSE_FFT_WORKSPACE_BYTES = 8 * 1_024 * 1_024
_TANDEM_BATCH_EVIDENCE_PROJECTION_SCHEMA = "plutosdr-fw.tandem-evidence-projection.v1"
_TANDEM_BATCH_EVIDENCE_PROJECTION_METHOD = (
    "canonical-json-v1: finished tandem mode with attestation value fields "
    "replaced by fixed sentinels plus 64 normalized reparsed metadata records"
)
_TANDEM_BATCH_PHASE_ORDER = (
    "fully_pre_attack",
    "attack_bracket",
    "fully_post_attack_pre_release",
    "release_bracket",
    "fully_post_release",
)


class ReleaseCliError(RuntimeError):
    """A configuration, resume, or durable-evidence invariant failed."""


@dataclass(frozen=True)
class ReleaseHardwareOptions:
    serial: str
    firmware_version: str
    firmware_pattern: str
    libiio_source_commit: str
    harness_sources: tuple[tuple[str, str], ...]
    artifact_index_path: Path
    deployment_receipt_path: Path
    candidate_binding_json: str
    runner_attestor: Callable[[], Mapping[str, Any]] = field(
        repr=False,
        compare=False,
    )
    physical_attenuation_db: float
    output_dir: Path
    phases: tuple[str, ...]
    bands: tuple[BandCase, ...]
    policy_set: str
    repeat_cycles: int
    cycle_interval_seconds: float
    soak_deadline_seconds: float
    max_new_steady_runs: int | None
    sample_rate_hz: int
    samples_per_channel: int
    phase_max_seconds: float
    retry_failed: bool
    resume: bool
    plan_only: bool
    host_libiio_json: str | None = None
    host_libiio_attestor: Callable[[], Mapping[str, Any]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def steady_key(self) -> str:
        return "steady_characterization" if self.policy_set == "full" else "steady_soak"


@dataclass(frozen=True)
class PhaseSpec:
    key: str
    kind: str
    band: BandCase | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "band": asdict(self.band) if self.band is not None else None,
        }


@dataclass(frozen=True)
class ValidatedPhase:
    verdict: str
    cleanup_verified: bool
    summary: Mapping[str, Any]


PhaseExecutor = Callable[[PhaseSpec, Path], Path]
PhaseValidator = Callable[[PhaseSpec, Path, Path], ValidatedPhase]


def _finite_nonnegative(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("value must be finite and nonnegative")
    return parsed


def _finite_positive(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be finite and positive")
    return parsed


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _harness_sources() -> tuple[tuple[str, str], ...]:
    root = Path(__file__).resolve().parents[2]
    return tuple((name, _sha256(root / name)) for name in HARNESS_SOURCE_NAMES)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_cli_path(value: str, *, name: str) -> Path:
    if not value or value.strip() != value or "\x00" in value or "\n" in value:
        raise ReleaseCliError(f"{name} must be one canonical absolute path")
    pure = PurePosixPath(value)
    if (
        not pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or str(pure) != value
    ):
        raise ReleaseCliError(f"{name} must be one canonical absolute path")
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ReleaseCliError(f"{name} does not exist") from error
    if resolved != path:
        raise ReleaseCliError(f"{name} contains a symlink or noncanonical component")
    return path


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _validate_owned_directory(value: os.stat_result, *, name: str) -> None:
    if not stat.S_ISDIR(value.st_mode):
        raise ReleaseCliError(f"{name} is not a directory")
    if value.st_uid != os.getuid() or value.st_gid != os.getgid():
        raise ReleaseCliError(f"{name} ownership is not the invoking user/group")
    if stat.S_IMODE(value.st_mode) & 0o022:
        raise ReleaseCliError(f"{name} is group/world writable")


def _validate_owned_regular(
    value: os.stat_result,
    *,
    name: str,
    exact_mode: int | None,
) -> None:
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ReleaseCliError(f"{name} is not a singly linked regular file")
    if value.st_uid != os.getuid() or value.st_gid != os.getgid():
        raise ReleaseCliError(f"{name} ownership is not the invoking user/group")
    mode = stat.S_IMODE(value.st_mode)
    if mode & 0o7022:
        raise ReleaseCliError(f"{name} has unsafe write/special mode bits")
    if exact_mode is not None and mode != exact_mode:
        raise ReleaseCliError(f"{name} mode must be {exact_mode:04o}")


@contextmanager
def _open_candidate_root(root: Path) -> Iterator[int]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.lstat(root)
        descriptor = os.open(root, flags)
    except OSError as error:
        raise ReleaseCliError("artifact-index root cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        _validate_owned_directory(opened, name="artifact-index root")
        if _stat_identity(before) != _stat_identity(opened):
            raise ReleaseCliError("artifact-index root changed while it was opened")
        yield descriptor
        try:
            after = os.lstat(root)
        except OSError as error:
            raise ReleaseCliError(
                "artifact-index root disappeared during attestation"
            ) from error
        if _stat_identity(opened) != _stat_identity(after):
            raise ReleaseCliError("artifact-index root changed during attestation")
    finally:
        os.close(descriptor)


def _member_parts(relative: str, *, name: str) -> tuple[str, ...]:
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or str(pure) != relative
    ):
        raise ReleaseCliError(f"{name} is not a canonical relative member path")
    return pure.parts


@contextmanager
def _open_member_parent(
    root_descriptor: int, relative: str, *, name: str
) -> Iterator[tuple[int, str]]:
    parts = _member_parts(relative, name=name)
    directory = os.dup(root_descriptor)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=directory)
            except OSError as error:
                raise ReleaseCliError(
                    f"{name} has a missing, symlinked, or non-directory component"
                ) from error
            os.close(directory)
            directory = child
            _validate_owned_directory(os.fstat(directory), name=f"{name} parent")
        yield directory, parts[-1]
    finally:
        os.close(directory)


def _read_candidate_member(
    root_descriptor: int,
    root: Path,
    relative: str,
    *,
    maximum_bytes: int,
    name: str,
    expected_bytes: int | None = None,
    exact_mode: int | None = None,
    retain_payload: bool = True,
    prefix_bytes: int | None = None,
) -> tuple[bytes | None, dict[str, Any], str | None]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    with _open_member_parent(root_descriptor, relative, name=name) as (
        parent_descriptor,
        filename,
    ):
        try:
            before = os.stat(
                filename,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            descriptor = os.open(filename, flags, dir_fd=parent_descriptor)
        except OSError as error:
            raise ReleaseCliError(f"{name} cannot be opened safely") from error
        try:
            opened = os.fstat(descriptor)
            _validate_owned_regular(opened, name=name, exact_mode=exact_mode)
            if _stat_identity(before) != _stat_identity(opened):
                raise ReleaseCliError(f"{name} changed while it was opened")
            if opened.st_size <= 0 or opened.st_size > maximum_bytes:
                raise ReleaseCliError(f"{name} size is outside its safe bound")
            if expected_bytes is not None and opened.st_size != expected_bytes:
                raise ReleaseCliError(f"{name} byte length differs from its index")
            if prefix_bytes is not None and not 0 < prefix_bytes <= opened.st_size:
                raise ReleaseCliError(f"{name} prefix length is invalid")
            digest = hashlib.sha256()
            prefix_digest = hashlib.sha256() if prefix_bytes is not None else None
            remaining_prefix = prefix_bytes or 0
            payload = bytearray() if retain_payload else None
            observed_bytes = 0
            while True:
                chunk = os.read(descriptor, min(1 << 20, maximum_bytes + 1))
                if not chunk:
                    break
                observed_bytes += len(chunk)
                if observed_bytes > maximum_bytes:
                    raise ReleaseCliError(f"{name} exceeded its safe read bound")
                digest.update(chunk)
                if prefix_digest is not None and remaining_prefix:
                    prefix_chunk = chunk[:remaining_prefix]
                    prefix_digest.update(prefix_chunk)
                    remaining_prefix -= len(prefix_chunk)
                if payload is not None:
                    payload.extend(chunk)
            after_fd = os.fstat(descriptor)
            after_path = os.stat(
                filename,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                observed_bytes != opened.st_size
                or remaining_prefix
                or _stat_identity(opened) != _stat_identity(after_fd)
                or _stat_identity(opened) != _stat_identity(after_path)
            ):
                raise ReleaseCliError(f"{name} changed while it was read")
        except OSError as error:
            raise ReleaseCliError(f"{name} failed during its guarded read") from error
        finally:
            os.close(descriptor)
    absolute = root.joinpath(*_member_parts(relative, name=name))
    snapshot = {
        "path": str(absolute),
        "relative_path": relative,
        "bytes": observed_bytes,
        "sha256": digest.hexdigest(),
        "device": opened.st_dev,
        "inode": opened.st_ino,
        "mode": f"{stat.S_IMODE(opened.st_mode):04o}",
        "links": opened.st_nlink,
        "uid": opened.st_uid,
        "gid": opened.st_gid,
        "mtime_ns": opened.st_mtime_ns,
        "ctime_ns": opened.st_ctime_ns,
    }
    return (
        bytes(payload) if payload is not None else None,
        snapshot,
        prefix_digest.hexdigest() if prefix_digest is not None else None,
    )


def _strict_json(payload: bytes, *, name: str) -> dict[str, Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(f"non-finite JSON number: {token}")
        return value

    def reject_constant(token: str) -> Any:
        raise ValueError(f"non-finite JSON constant: {token}")

    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=pairs_hook,
            parse_float=finite_float,
            parse_constant=reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise ReleaseCliError(f"{name} is not strict JSON") from error
    if not isinstance(value, dict):
        raise ReleaseCliError(f"{name} must contain one JSON object")
    return value


def _source_manifest_values(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise ReleaseCliError("source manifest is not strict UTF-8") from error
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ReleaseCliError("source manifest contains a non-key/value line")
        key, value = (part.strip() for part in line.split(":", 1))
        if (
            not key
            or not value
            or key in values
            or re.fullmatch(r"[a-z0-9_]+", key) is None
            or "\x00" in value
        ):
            raise ReleaseCliError("source manifest contains an invalid field")
        values[key] = value
    if (
        values.get("schema") != "plutosdr-fw.source-manifest"
        or values.get("schema_version") != "1"
        or re.fullmatch(r"[0-9a-f]{40}", values.get("libiio_0_25_source", "")) is None
    ):
        raise ReleaseCliError("source manifest identity/source pin is invalid")
    return values


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseCliError("runner repository provenance check failed") from error


def _runner_source_environment_name(relative: str, field_name: str) -> str:
    stem = {
        "scripts/deploy_tandem_agc_ram_hardware.sh": "DEPLOY_SHELL",
        "scripts/run_tandem_agc_release_hardware.sh": "SHELL",
        "scripts/tandem_release_device_plan.py": "DEVICE_PLAN",
        "scripts/tandem_release_evidence.py": "SEMANTIC_EVIDENCE",
        "tests/radio_hardware/candidate_binding.py": "CANDIDATE_BINDING",
        "tests/radio_hardware/pluto_plus_candidate.py": "PLUTO_PLUS_CANDIDATE",
        "tests/radio_hardware/release_cli.py": "RELEASE_CLI",
    }[relative]
    return f"PLUTOSDR_FW_RUNNER_{stem}_{field_name}"


def _validate_runner_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {"schema", "repository", "commit", "clean", "sources"}
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ReleaseCliError("runner provenance shape is not exact")
    repository = _canonical_cli_path(str(value["repository"]), name="runner repository")
    commit = str(value["commit"])
    sources = value["sources"]
    if (
        value["schema"] != RUNNER_PROVENANCE_SCHEMA
        or value["clean"] is not True
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        or not isinstance(sources, Sequence)
        or isinstance(sources, (str, bytes))
        or len(sources) != len(RUNNER_PROVENANCE_PATHS)
    ):
        raise ReleaseCliError("runner provenance identity is invalid")
    normalized_sources: list[dict[str, Any]] = []
    for index, (source, expected_relative) in enumerate(
        zip(sources, RUNNER_PROVENANCE_PATHS, strict=False)
    ):
        if not isinstance(source, Mapping) or set(source) != {
            "path",
            "absolute_path",
            "sha256",
            "committed_sha256",
        }:
            raise ReleaseCliError(f"runner provenance source {index} is malformed")
        relative = str(source["path"])
        absolute = _canonical_cli_path(
            str(source["absolute_path"]), name=f"runner source {index}"
        )
        digest = str(source["sha256"])
        committed_digest = str(source["committed_sha256"])
        if (
            relative != expected_relative
            or absolute != repository / expected_relative
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or digest != committed_digest
        ):
            raise ReleaseCliError(f"runner provenance source {index} is not exact")
        normalized_sources.append(
            {
                "path": relative,
                "absolute_path": str(absolute),
                "sha256": digest,
                "committed_sha256": committed_digest,
            }
        )
    if len(normalized_sources) != len(RUNNER_PROVENANCE_PATHS):
        raise ReleaseCliError("runner provenance source inventory is not exact")
    return {
        "schema": RUNNER_PROVENANCE_SCHEMA,
        "repository": str(repository),
        "commit": commit,
        "clean": True,
        "sources": normalized_sources,
    }


def _attest_runner_provenance(environment: Mapping[str, str]) -> dict[str, Any]:
    repository_text = environment.get("PLUTOSDR_FW_RUNNER_REPOSITORY", "")
    repository = _canonical_cli_path(repository_text, name="runner repository")
    expected_repository = Path(__file__).resolve().parents[2]
    commit = environment.get("PLUTOSDR_FW_RUNNER_COMMIT", "")
    if repository != expected_repository:
        raise ReleaseCliError("runner repository path is not the imported repository")
    if _git_bytes(repository, "rev-parse", "HEAD").decode().strip() != commit:
        raise ReleaseCliError("runner commit is not the current repository HEAD")
    if _git_bytes(
        repository, "status", "--porcelain=v1", "--untracked-files=all"
    ).strip():
        raise ReleaseCliError("runner repository is not fully clean")
    sources: list[dict[str, Any]] = []
    for relative in RUNNER_PROVENANCE_PATHS:
        path_text = environment.get(
            _runner_source_environment_name(relative, "PATH"), ""
        )
        path = _canonical_cli_path(path_text, name=f"runner source {relative}")
        if path != repository / relative:
            raise ReleaseCliError(f"runner source path is unexpected: {relative}")
        flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        try:
            before = os.lstat(path)
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ReleaseCliError(
                f"runner source cannot be opened: {relative}"
            ) from error
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_uid != os.getuid()
                or opened.st_gid != os.getgid()
                or stat.S_IMODE(opened.st_mode) & 0o7002
                or opened.st_size <= 0
                or opened.st_size > MAXIMUM_HARNESS_SOURCE_BYTES
                or _stat_identity(before) != _stat_identity(opened)
            ):
                raise ReleaseCliError(f"runner source metadata is unsafe: {relative}")
            digest = hashlib.sha256()
            observed = 0
            while chunk := os.read(descriptor, 1 << 20):
                observed += len(chunk)
                digest.update(chunk)
            after_fd = os.fstat(descriptor)
            after_path = os.lstat(path)
            if (
                observed != opened.st_size
                or _stat_identity(opened) != _stat_identity(after_fd)
                or _stat_identity(opened) != _stat_identity(after_path)
            ):
                raise ReleaseCliError(f"runner source changed while read: {relative}")
        except OSError as error:
            raise ReleaseCliError(
                f"runner source failed during guarded read: {relative}"
            ) from error
        finally:
            os.close(descriptor)
        calculated = digest.hexdigest()
        committed = hashlib.sha256(
            _git_bytes(repository, "show", f"{commit}:{relative}")
        ).hexdigest()
        supplied = environment.get(
            _runner_source_environment_name(relative, "SHA256"), ""
        )
        supplied_committed = environment.get(
            _runner_source_environment_name(relative, "COMMITTED_SHA256"), ""
        )
        if (
            calculated != committed
            or calculated != supplied
            or committed != supplied_committed
        ):
            raise ReleaseCliError(
                f"runner source is not its committed blob: {relative}"
            )
        sources.append(
            {
                "path": relative,
                "absolute_path": str(path),
                "sha256": calculated,
                "committed_sha256": committed,
            }
        )
    return _validate_runner_provenance(
        {
            "schema": RUNNER_PROVENANCE_SCHEMA,
            "repository": str(repository),
            "commit": commit,
            "clean": True,
            "sources": sources,
        }
    )


def _runtime_regular_evidence(
    path: Path,
    *,
    name: str,
    maximum_bytes: int,
    retain_payload: bool = False,
) -> tuple[dict[str, Any], bytes | None]:
    path = _canonical_cli_path(str(path), name=name)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.lstat(path)
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReleaseCliError(f"{name} cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        _validate_owned_regular(opened, name=name, exact_mode=None)
        if (
            _stat_identity(before) != _stat_identity(opened)
            or opened.st_size <= 0
            or opened.st_size > maximum_bytes
        ):
            raise ReleaseCliError(f"{name} metadata is unsafe")
        digest = hashlib.sha256()
        observed = 0
        retained: list[bytes] | None = [] if retain_payload else None
        while chunk := os.read(descriptor, 1 << 20):
            observed += len(chunk)
            if observed > maximum_bytes:
                raise ReleaseCliError(f"{name} exceeded its size bound")
            digest.update(chunk)
            if retained is not None:
                retained.append(chunk)
        after_fd = os.fstat(descriptor)
        after_path = os.lstat(path)
        if (
            observed != opened.st_size
            or _stat_identity(opened) != _stat_identity(after_fd)
            or _stat_identity(opened) != _stat_identity(after_path)
        ):
            raise ReleaseCliError(f"{name} changed while it was read")
        return (
            {
                "path": str(path),
                "bytes": observed,
                "sha256": digest.hexdigest(),
                "mode": stat.S_IMODE(opened.st_mode),
            },
            b"".join(retained) if retained is not None else None,
        )
    except OSError as error:
        raise ReleaseCliError(f"{name} failed during guarded read") from error
    finally:
        os.close(descriptor)


def _runtime_regular_sha256(path: Path, *, name: str, maximum_bytes: int) -> str:
    evidence, _payload = _runtime_regular_evidence(
        path,
        name=name,
        maximum_bytes=maximum_bytes,
    )
    return str(evidence["sha256"])


def _cmake_cache_configuration(
    payload: bytes,
    *,
    source: Path,
    expected_python: str,
) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise ReleaseCliError("fresh host libiio CMake cache is not UTF-8") from error
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        typed_key, value = line.split("=", 1)
        key = typed_key.split(":", 1)[0]
        if key in values:
            raise ReleaseCliError(f"fresh host libiio CMake key is duplicated: {key}")
        values[key] = value
    expected = {
        **HOST_LIBIIO_CMAKE_CONFIGURATION,
        "CMAKE_HOME_DIRECTORY": str(source),
        "PYTHON_EXECUTABLE": expected_python,
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise ReleaseCliError("fresh host libiio CMake configuration changed")
    dynamic_keys = ("CMAKE_C_COMPILER", "CMAKE_GENERATOR", "CMAKE_MAKE_PROGRAM")
    if any(not values.get(key) for key in dynamic_keys):
        raise ReleaseCliError("fresh host libiio toolchain identity is incomplete")
    return {
        **HOST_LIBIIO_CMAKE_CONFIGURATION,
        "CMAKE_HOME_DIRECTORY": "$HOST_LIBIIO_ROOT/source",
        "PYTHON_EXECUTABLE": expected_python,
        **{key: values[key] for key in dynamic_keys},
    }


def _attest_host_libiio_preimport(
    environment: Mapping[str, str],
    *,
    expected_commit: str,
) -> dict[str, Any]:
    if (
        environment.get("PLUTOSDR_FW_LIBIIO_GUARDED_WRAPPER")
        != HOST_LIBIIO_WRAPPER_MARKER
    ):
        raise ReleaseCliError(
            "guarded host-libiio wrapper provenance is absent; use "
            "scripts/run_tandem_agc_release_hardware.sh"
        )
    repository = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_LIBIIO_REPOSITORY", ""),
        name="host libiio repository",
    )
    source = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_LIBIIO_SOURCE", ""),
        name="host libiio source snapshot",
    )
    build = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_LIBIIO_BUILD", ""),
        name="fresh host libiio build directory",
    )
    if not repository.is_dir() or not source.is_dir() or not build.is_dir():
        raise ReleaseCliError("host libiio source/build path is not a directory")
    private_root = source.parent
    if source.parent != build.parent:
        raise ReleaseCliError("host libiio source/build do not share one private root")
    _validate_owned_directory(os.lstat(private_root), name="host libiio private root")
    _validate_owned_directory(os.lstat(source), name="host libiio source snapshot")
    _validate_owned_directory(os.lstat(build), name="fresh host libiio build directory")
    if any(
        stat.S_IMODE(os.lstat(path).st_mode) != 0o700
        for path in (private_root, source, build)
    ):
        raise ReleaseCliError("host libiio private source/build mode is not 0700")
    if _git_bytes(repository, "rev-parse", "HEAD").decode().strip() != expected_commit:
        raise ReleaseCliError("host libiio source is not the manifest-pinned HEAD")
    if _git_bytes(repository, "status", "--porcelain", "--untracked-files=all").strip():
        raise ReleaseCliError("host libiio source repository is not fully clean")

    binding = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_PYLIBIIO_PATH", ""),
        name="pylibiio binding",
    )
    library = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_LIBIIO_SO_PATH", ""),
        name="built host libiio",
    )
    cache = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_PATH", ""),
        name="fresh host libiio CMake cache",
    )
    if binding != source / "bindings/python/iio.py":
        raise ReleaseCliError("pylibiio binding is outside the pinned source path")
    try:
        library.relative_to(build)
    except ValueError as error:
        raise ReleaseCliError(
            "mapped host libiio is outside the fresh build"
        ) from error
    if cache != build / "CMakeCache.txt":
        raise ReleaseCliError("host libiio CMake cache is outside the fresh build")

    expected_binding_sha = environment.get("PLUTOSDR_FW_PYLIBIIO_SHA256", "")
    expected_library_sha = environment.get("PLUTOSDR_FW_LIBIIO_SO_SHA256", "")
    expected_cache_sha = environment.get("PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256", "")
    if (
        re.fullmatch(r"[0-9a-f]{64}", expected_binding_sha) is None
        or re.fullmatch(r"[0-9a-f]{64}", expected_library_sha) is None
        or re.fullmatch(r"[0-9a-f]{64}", expected_cache_sha) is None
    ):
        raise ReleaseCliError("host libiio hash environment is malformed")
    binding_evidence, _payload = _runtime_regular_evidence(
        binding, name="pylibiio binding", maximum_bytes=MAXIMUM_HARNESS_SOURCE_BYTES
    )
    library_evidence, _payload = _runtime_regular_evidence(
        library, name="built host libiio", maximum_bytes=MAXIMUM_EVIDENCE_MEMBER_BYTES
    )
    cache_evidence, cache_payload = _runtime_regular_evidence(
        cache,
        name="fresh host libiio CMake cache",
        maximum_bytes=MAXIMUM_HOST_LIBIIO_CACHE_BYTES,
        retain_payload=True,
    )
    assert cache_payload is not None
    committed_binding_sha = hashlib.sha256(
        _git_bytes(repository, "show", f"{expected_commit}:bindings/python/iio.py")
    ).hexdigest()
    if (
        binding_evidence["sha256"] != expected_binding_sha
        or binding_evidence["sha256"] != committed_binding_sha
    ):
        raise ReleaseCliError("pylibiio bytes are not the pinned committed binding")
    if library_evidence["sha256"] != expected_library_sha:
        raise ReleaseCliError("mapped host libiio bytes changed after the fresh build")
    if cache_evidence["sha256"] != expected_cache_sha:
        raise ReleaseCliError("fresh host libiio CMake cache bytes changed")
    expected_python = environment.get("PLUTOSDR_FW_LIBIIO_PYTHON_EXECUTABLE", "")
    if not expected_python or "\x00" in expected_python or "\n" in expected_python:
        raise ReleaseCliError("host libiio Python build identity is malformed")
    cmake_configuration = _cmake_cache_configuration(
        cache_payload,
        source=source,
        expected_python=expected_python,
    )

    runner_repository = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_RUNNER_REPOSITORY", ""),
        name="host libiio wrapper repository",
    )
    wrapper = _canonical_cli_path(
        environment.get("PLUTOSDR_FW_RUNNER_SHELL_PATH", ""),
        name="host libiio wrapper source",
    )
    wrapper_sha = environment.get("PLUTOSDR_FW_RUNNER_SHELL_SHA256", "")
    wrapper_committed_sha = environment.get(
        "PLUTOSDR_FW_RUNNER_SHELL_COMMITTED_SHA256", ""
    )
    wrapper_commit = environment.get("PLUTOSDR_FW_RUNNER_COMMIT", "")
    if (
        wrapper != runner_repository / "scripts/run_tandem_agc_release_hardware.sh"
        or re.fullmatch(r"[0-9a-f]{40}", wrapper_commit) is None
        or re.fullmatch(r"[0-9a-f]{64}", wrapper_sha) is None
        or wrapper_sha != wrapper_committed_sha
        or _sha256(wrapper) != wrapper_sha
    ):
        raise ReleaseCliError("guarded host libiio wrapper identity changed")

    resume_identity = {
        "source_commit": expected_commit,
        "wrapper_commit": wrapper_commit,
        "wrapper_sha256": wrapper_sha,
        "binding_sha256": binding_evidence["sha256"],
        "library_sha256": library_evidence["sha256"],
        "cmake_configuration": cmake_configuration,
    }
    return {
        "source_commit": expected_commit,
        "repository_path": str(repository),
        "private_root_path": str(private_root),
        "source_path": str(source),
        "build_path": str(build),
        "binding": binding_evidence,
        "library": library_evidence,
        "cmake_cache": {**cache_evidence, "configuration": cmake_configuration},
        "wrapper": {
            "repository_path": str(runner_repository),
            "commit": wrapper_commit,
            "path": str(wrapper),
            "sha256": wrapper_sha,
        },
        "resume_identity": resume_identity,
    }


def _attest_imported_libiio(
    module: Any,
    environment: Mapping[str, str],
    *,
    expected_commit: str,
    maps_path: Path = Path("/proc/self/maps"),
) -> dict[str, Any]:
    preimport = _attest_host_libiio_preimport(
        environment,
        expected_commit=expected_commit,
    )
    binding = Path(str(preimport["binding"]["path"]))
    library = Path(str(preimport["library"]["path"]))
    imported = Path(str(getattr(module, "__file__", ""))).resolve(strict=True)
    if imported != binding or getattr(module, "MetadataBuffer", None) is None:
        raise ReleaseCliError("imported pylibiio is not the pinned release binding")
    mapped = {
        str(Path(line.rsplit(maxsplit=1)[-1]).resolve())
        for line in maps_path.read_text(encoding="utf-8").splitlines()
        if "/libiio.so" in line.rsplit(maxsplit=1)[-1]
    }
    if mapped != {str(library)}:
        raise ReleaseCliError("process mapped an unexpected host libiio library")
    return {
        "schema": HOST_LIBIIO_RUNTIME_SCHEMA,
        **preimport,
        "imported_binding_path": str(imported),
        "mapped_library_paths": sorted(mapped),
    }


def _validate_host_libiio_runtime(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "schema",
        "source_commit",
        "repository_path",
        "private_root_path",
        "source_path",
        "build_path",
        "binding",
        "library",
        "cmake_cache",
        "wrapper",
        "resume_identity",
        "imported_binding_path",
        "mapped_library_paths",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ReleaseCliError("host libiio runtime provenance shape is not exact")
    source_commit = value.get("source_commit")
    if (
        value.get("schema") != HOST_LIBIIO_RUNTIME_SCHEMA
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise ReleaseCliError("host libiio runtime provenance identity is invalid")

    def path_text(raw: object, *, name: str) -> str:
        if not isinstance(raw, str):
            raise ReleaseCliError(f"{name} is not an absolute path")
        pure = PurePosixPath(raw)
        if not pure.is_absolute() or str(pure) != raw or ".." in pure.parts:
            raise ReleaseCliError(f"{name} is not an absolute path")
        return raw

    normalized_paths = {
        name: path_text(value.get(name), name=f"host libiio {name}")
        for name in (
            "repository_path",
            "private_root_path",
            "source_path",
            "build_path",
            "imported_binding_path",
        )
    }

    def file_record(raw: object, *, name: str, cache: bool = False) -> dict[str, Any]:
        record = raw if isinstance(raw, Mapping) else {}
        keys = {"path", "bytes", "sha256", "mode"}
        if cache:
            keys.add("configuration")
        if set(record) != keys:
            raise ReleaseCliError(f"{name} record shape is not exact")
        path = path_text(record.get("path"), name=f"{name} path")
        byte_count = record.get("bytes")
        mode = record.get("mode")
        digest = record.get("sha256")
        if (
            type(byte_count) is not int
            or byte_count <= 0
            or type(mode) is not int
            or not 0 <= mode <= 0o7777
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ReleaseCliError(f"{name} file evidence is malformed")
        result = {
            "path": path,
            "bytes": byte_count,
            "sha256": digest,
            "mode": mode,
        }
        if cache:
            result["configuration"] = configuration(record.get("configuration"))
        return result

    def configuration(raw: object) -> dict[str, str]:
        record = raw if isinstance(raw, Mapping) else {}
        expected = {
            *HOST_LIBIIO_CMAKE_CONFIGURATION,
            "CMAKE_HOME_DIRECTORY",
            "PYTHON_EXECUTABLE",
            "CMAKE_C_COMPILER",
            "CMAKE_GENERATOR",
            "CMAKE_MAKE_PROGRAM",
        }
        if set(record) != expected or any(
            not isinstance(item, str) or not item for item in record.values()
        ):
            raise ReleaseCliError("host libiio CMake configuration is malformed")
        if record.get("CMAKE_HOME_DIRECTORY") != "$HOST_LIBIIO_ROOT/source" or any(
            record.get(key) != expected_value
            for key, expected_value in HOST_LIBIIO_CMAKE_CONFIGURATION.items()
        ):
            raise ReleaseCliError("host libiio CMake configuration is not exact")
        return {str(key): str(item) for key, item in record.items()}

    binding = file_record(value.get("binding"), name="host libiio binding")
    library = file_record(value.get("library"), name="host libiio library")
    cache = file_record(
        value.get("cmake_cache"), name="host libiio CMake cache", cache=True
    )
    wrapper_raw = value.get("wrapper")
    wrapper = wrapper_raw if isinstance(wrapper_raw, Mapping) else {}
    if set(wrapper) != {"repository_path", "commit", "path", "sha256"}:
        raise ReleaseCliError("host libiio wrapper record shape is not exact")
    wrapper_commit = wrapper.get("commit")
    wrapper_sha = wrapper.get("sha256")
    if (
        not isinstance(wrapper_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", wrapper_commit) is None
        or not isinstance(wrapper_sha, str)
        or re.fullmatch(r"[0-9a-f]{64}", wrapper_sha) is None
    ):
        raise ReleaseCliError("host libiio wrapper record is malformed")
    normalized_wrapper = {
        "repository_path": path_text(
            wrapper.get("repository_path"), name="host libiio wrapper repository"
        ),
        "commit": wrapper_commit,
        "path": path_text(wrapper.get("path"), name="host libiio wrapper path"),
        "sha256": wrapper_sha,
    }
    resume_raw = value.get("resume_identity")
    resume = resume_raw if isinstance(resume_raw, Mapping) else {}
    if set(resume) != {
        "source_commit",
        "wrapper_commit",
        "wrapper_sha256",
        "binding_sha256",
        "library_sha256",
        "cmake_configuration",
    }:
        raise ReleaseCliError("host libiio resume identity shape is not exact")
    normalized_resume = {
        "source_commit": source_commit,
        "wrapper_commit": wrapper_commit,
        "wrapper_sha256": wrapper_sha,
        "binding_sha256": binding["sha256"],
        "library_sha256": library["sha256"],
        "cmake_configuration": cache["configuration"],
    }
    if _canonical_json(resume) != _canonical_json(normalized_resume):
        raise ReleaseCliError("host libiio resume identity is internally inconsistent")
    imported = str(value["imported_binding_path"])
    mapped = value.get("mapped_library_paths")
    if imported != binding["path"] or mapped != [library["path"]]:
        raise ReleaseCliError("host libiio imported/mapped paths are inconsistent")
    private_root = PurePosixPath(normalized_paths["private_root_path"])
    source = PurePosixPath(normalized_paths["source_path"])
    build = PurePosixPath(normalized_paths["build_path"])
    wrapper_repository = PurePosixPath(normalized_wrapper["repository_path"])
    if (
        source != private_root / "source"
        or build != private_root / "build"
        or PurePosixPath(binding["path"]) != source / "bindings/python/iio.py"
        or PurePosixPath(cache["path"]) != build / "CMakeCache.txt"
        or build not in PurePosixPath(library["path"]).parents
        or PurePosixPath(normalized_wrapper["path"])
        != wrapper_repository / "scripts/run_tandem_agc_release_hardware.sh"
    ):
        raise ReleaseCliError("host libiio runtime paths are internally inconsistent")
    return {
        "schema": HOST_LIBIIO_RUNTIME_SCHEMA,
        "source_commit": source_commit,
        **normalized_paths,
        "binding": binding,
        "library": library,
        "cmake_cache": cache,
        "wrapper": normalized_wrapper,
        "resume_identity": normalized_resume,
        "mapped_library_paths": [library["path"]],
    }


def _bind_host_libiio(
    options: ReleaseHardwareOptions,
    attestor: Callable[[], Mapping[str, Any]],
) -> ReleaseHardwareOptions:
    observed = _validate_host_libiio_runtime(attestor())
    return replace(
        options,
        host_libiio_json=_canonical_json(observed),
        host_libiio_attestor=attestor,
    )


def _assert_host_libiio_unchanged(options: ReleaseHardwareOptions) -> dict[str, Any]:
    if options.host_libiio_json is None or not callable(options.host_libiio_attestor):
        raise ReleaseCliError(
            "host libiio is not bound; use the guarded release hardware wrapper"
        )
    observed = _validate_host_libiio_runtime(options.host_libiio_attestor())
    if _canonical_json(observed) != options.host_libiio_json:
        raise ReleaseCliError(
            "host libiio binding, library, or build configuration changed"
        )
    return observed


def _attest_candidate_binding(
    *,
    artifact_index_path: Path,
    deployment_receipt_path: Path,
    serial: str,
    firmware_version: str,
    libiio_source_commit: str,
    harness_sources: tuple[tuple[str, str], ...],
    runner_provenance: Mapping[str, Any],
    semantic_verify: bool = False,
) -> dict[str, Any]:
    runner = _validate_runner_provenance(runner_provenance)
    root = artifact_index_path.parent
    try:
        receipt_relative = deployment_receipt_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ReleaseCliError(
            "deployment receipt must be a descendant of the artifact-index root"
        ) from error
    index_relative = artifact_index_path.name
    if deployment_receipt_path == artifact_index_path:
        raise ReleaseCliError("artifact index and deployment receipt must differ")
    receipt_member = PurePosixPath(receipt_relative)
    if (
        len(receipt_member.parts) != 4
        or receipt_member.parts[:2] != ("hardware", "deploy")
        or receipt_member.parts[2] != serial
        or receipt_member.name != "ram-boot-receipt.json"
    ):
        raise ReleaseCliError(
            "deployment receipt path is not the exact serial-scoped member"
        )
    deploy_root = receipt_member.parent
    candidate_plan_relative = str(deploy_root / "release-candidate-plan.json")
    inventory_relative = str(deploy_root / "usb-inventory.json")
    operation_relative = str(deploy_root / "operation-plan.json")

    with _open_candidate_root(root) as root_descriptor:
        index_payload, index_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            index_relative,
            maximum_bytes=MAXIMUM_ARTIFACT_INDEX_BYTES,
            name="artifact index",
        )
        assert index_payload is not None
        try:
            artifact_index = validate_artifact_index(
                _strict_json(index_payload, name="artifact index")
            )
        except CandidateBindingError as error:
            raise ReleaseCliError(f"artifact index is invalid: {error}") from error
        if semantic_verify:
            try:
                semantic_index = verify_artifact_index_semantics(
                    artifact_index_path,
                    expected_stage=str(artifact_index["stage"]),
                )
            except (EvidenceError, OSError) as error:
                raise ReleaseCliError(
                    f"candidate release evidence is not authorizing: {error}"
                ) from error
            if semantic_index != artifact_index:
                raise ReleaseCliError(
                    "semantic release verifier returned a different artifact index"
                )
        artifact_index_sha256 = index_file["sha256"]

        release = artifact_index["release"]
        source = artifact_index["source"]
        artifact = artifact_index["artifact"]
        if release["firmware_version"] != firmware_version:
            raise ReleaseCliError("artifact index binds a different firmware version")
        if (
            release["metadata_abi"] != "frame-metadata-v5"
            or release["tandem_agc"] != "request-v2"
        ):
            raise ReleaseCliError(
                "artifact index binds a different tandem metadata ABI"
            )
        if source["commit"] != runner["commit"]:
            raise ReleaseCliError(
                "artifact index source commit differs from the runner commit"
            )

        seen_paths = {index_relative, receipt_relative}
        manifest_relative = source["manifest_path"]
        if manifest_relative in seen_paths or not manifest_relative.endswith(
            "-source.yaml"
        ):
            raise ReleaseCliError(
                "artifact source manifest member is aliased or unsafe"
            )
        seen_paths.add(manifest_relative)
        manifest_payload, manifest_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            manifest_relative,
            maximum_bytes=MAXIMUM_SOURCE_MANIFEST_BYTES,
            name="artifact source manifest",
        )
        assert manifest_payload is not None
        if manifest_file["sha256"] != source["manifest_sha256"]:
            raise ReleaseCliError("artifact source manifest SHA-256 changed")
        manifest_values = _source_manifest_values(manifest_payload)
        if manifest_values["libiio_0_25_source"] != libiio_source_commit:
            raise ReleaseCliError(
                "source manifest libiio pin differs from the guarded host source"
            )
        committed_manifest_path = f"manifests/{PurePosixPath(manifest_relative).name}"
        repository = Path(runner["repository"])
        if (
            _git_bytes(
                repository,
                "show",
                f"{runner['commit']}:{committed_manifest_path}",
            )
            != manifest_payload
        ):
            raise ReleaseCliError(
                "artifact source manifest differs from its committed source blob"
            )
        manifest_file["committed_path"] = committed_manifest_path

        dfu_relative = artifact["dfu_path"]
        if dfu_relative in seen_paths or not dfu_relative.endswith(".dfu"):
            raise ReleaseCliError(
                "artifact DFU member is aliased or has no .dfu suffix"
            )
        seen_paths.add(dfu_relative)
        dfu_bytes = artifact["dfu_bytes"]
        fit_bytes = artifact["fit_bytes"]
        if dfu_bytes != fit_bytes + 16 or dfu_bytes > MAXIMUM_DFU_BYTES:
            raise ReleaseCliError(
                "artifact DFU is not an exact bounded FIT plus suffix"
            )
        _payload, dfu_file, fit_sha256 = _read_candidate_member(
            root_descriptor,
            root,
            dfu_relative,
            maximum_bytes=MAXIMUM_DFU_BYTES,
            expected_bytes=dfu_bytes,
            prefix_bytes=fit_bytes,
            retain_payload=False,
            name="artifact DFU",
        )
        if (
            dfu_file["sha256"] != artifact["dfu_sha256"]
            or fit_sha256 != artifact["fit_sha256"]
        ):
            raise ReleaseCliError("artifact DFU/FIT SHA-256 changed")
        dfu_file["fit_bytes"] = fit_bytes
        dfu_file["fit_sha256"] = fit_sha256

        indexed_harness = {
            entry["path"]: entry["sha256"]
            for entry in artifact_index["harness"]["files"]
        }
        live_harness = dict(harness_sources)
        missing_harness = set(HARNESS_SOURCE_NAMES) - set(indexed_harness)
        if missing_harness:
            raise ReleaseCliError(
                "artifact index lacks required release/receipt harness sources: "
                + ", ".join(sorted(missing_harness))
            )
        runner_sources = {
            source_record["path"]: source_record["sha256"]
            for source_record in runner["sources"]
        }
        harness_files: list[dict[str, Any]] = []
        for relative, indexed_digest in indexed_harness.items():
            if relative in seen_paths:
                raise ReleaseCliError("artifact index aliases a harness member")
            seen_paths.add(relative)
            _payload, snapshot, _prefix = _read_candidate_member(
                root_descriptor,
                root,
                relative,
                maximum_bytes=MAXIMUM_HARNESS_SOURCE_BYTES,
                retain_payload=False,
                name=f"artifact harness {relative}",
            )
            digest = snapshot["sha256"]
            if digest != indexed_digest:
                raise ReleaseCliError(
                    f"artifact harness archive member changed: {relative}"
                )
            required = relative in live_harness
            snapshot["required_for_release_hardware"] = required
            if required:
                if digest != live_harness[relative]:
                    raise ReleaseCliError(
                        f"artifact harness does not bind the live source: {relative}"
                    )
                committed_digest = runner_sources.get(relative)
                if committed_digest is None:
                    committed_digest = hashlib.sha256(
                        _git_bytes(
                            repository,
                            "show",
                            f"{runner['commit']}:{relative}",
                        )
                    ).hexdigest()
                if digest != committed_digest:
                    raise ReleaseCliError(
                        f"artifact harness does not bind committed source: {relative}"
                    )
                snapshot["committed_sha256"] = committed_digest
            harness_files.append(snapshot)

        evidence_files: list[dict[str, Any]] = []
        for member, expected_role in zip(
            artifact_index["evidence"]["members"],
            REQUIRED_EVIDENCE_ROLES,
            strict=True,
        ):
            relative = member["path"]
            if member["role"] != expected_role or relative in seen_paths:
                raise ReleaseCliError("artifact index aliases an evidence member")
            seen_paths.add(relative)
            _payload, snapshot, _prefix = _read_candidate_member(
                root_descriptor,
                root,
                relative,
                maximum_bytes=MAXIMUM_EVIDENCE_MEMBER_BYTES,
                expected_bytes=member["bytes"],
                retain_payload=False,
                name=f"artifact evidence {expected_role}",
            )
            if snapshot["sha256"] != member["sha256"]:
                raise ReleaseCliError(
                    f"artifact evidence member changed: {expected_role}"
                )
            snapshot["role"] = expected_role
            evidence_files.append(snapshot)

        candidate_plan_payload, candidate_plan_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            candidate_plan_relative,
            maximum_bytes=MAXIMUM_DEPLOYMENT_RECEIPT_BYTES,
            exact_mode=0o600,
            name="release candidate plan",
        )
        inventory_payload, inventory_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            inventory_relative,
            maximum_bytes=MAXIMUM_DEPLOYMENT_RECEIPT_BYTES,
            exact_mode=0o600,
            name="release USB inventory",
        )
        operation_payload, operation_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            operation_relative,
            maximum_bytes=MAXIMUM_DEPLOYMENT_RECEIPT_BYTES,
            exact_mode=0o600,
            name="release operation plan",
        )
        receipt_payload, receipt_file, _prefix = _read_candidate_member(
            root_descriptor,
            root,
            receipt_relative,
            maximum_bytes=MAXIMUM_DEPLOYMENT_RECEIPT_BYTES,
            exact_mode=0o600,
            name="deployment receipt",
        )
        assert candidate_plan_payload is not None
        assert inventory_payload is not None
        assert operation_payload is not None
        assert receipt_payload is not None
        try:
            candidate_plan = validate_release_candidate_plan(
                _strict_json(candidate_plan_payload, name="release candidate plan"),
                artifact_index=artifact_index,
                artifact_index_bytes=index_file["bytes"],
                artifact_index_sha256=artifact_index_sha256,
            )
            inventory = validate_release_usb_inventory(
                _strict_json(inventory_payload, name="release USB inventory")
            )
            operation = validate_release_operation_plan(
                _strict_json(operation_payload, name="release operation plan"),
                candidate_plan=candidate_plan,
                candidate_plan_bytes=candidate_plan_file["bytes"],
                candidate_plan_sha256=candidate_plan_file["sha256"],
                usb_inventory=inventory,
                usb_inventory_bytes=inventory_file["bytes"],
                usb_inventory_sha256=inventory_file["sha256"],
                serial=serial,
            )
            deployment_receipt = validate_release_candidate_receipt(
                _strict_json(receipt_payload, name="deployment receipt"),
                candidate_plan=candidate_plan,
                candidate_plan_bytes=candidate_plan_file["bytes"],
                candidate_plan_sha256=candidate_plan_file["sha256"],
                operation_plan=operation,
                operation_plan_bytes=operation_file["bytes"],
                operation_plan_sha256=operation_file["sha256"],
                serial=serial,
            )
        except CandidateBindingError as error:
            raise ReleaseCliError(f"deployment receipt is invalid: {error}") from error

    return {
        "schema": "plutosdr-fw.tandem-release-candidate-binding.v1",
        "serial": serial,
        "firmware_version": firmware_version,
        "source_commit": source["commit"],
        "build_run_id": artifact_index["build"]["run_id"],
        "build_run_attempt": artifact_index["build"]["run_attempt"],
        "artifact_index_sha256": artifact_index_sha256,
        "dfu_sha256": dfu_file["sha256"],
        "fit_sha256": fit_sha256,
        "deployment_receipt_sha256": receipt_file["sha256"],
        "deployment_boot_pre_id": deployment_receipt["pre_runtime"]["boot_id"],
        "deployment_boot_post_id": deployment_receipt["post_runtime"]["boot_id"],
        "artifact_root": str(root),
        "runner_provenance": runner,
        "artifact_index_file": index_file,
        "artifact_index": artifact_index,
        "initial_semantic_verification": {
            "stage": artifact_index["stage"],
            "normalized_index_sha256": hashlib.sha256(
                _canonical_json(artifact_index).encode()
            ).hexdigest(),
        },
        "source_manifest_file": manifest_file,
        "source_manifest_values": manifest_values,
        "dfu_file": dfu_file,
        "harness_files": harness_files,
        "evidence_files": evidence_files,
        "deployment_receipt_file": receipt_file,
        "deployment_receipt": deployment_receipt,
    }


def _assert_release_inputs_unchanged(options: ReleaseHardwareOptions) -> None:
    live_harness = _harness_sources()
    if live_harness != options.harness_sources:
        raise ReleaseCliError("release harness source changed after plan validation")
    observed = _attest_candidate_binding(
        artifact_index_path=options.artifact_index_path,
        deployment_receipt_path=options.deployment_receipt_path,
        serial=options.serial,
        firmware_version=options.firmware_version,
        libiio_source_commit=options.libiio_source_commit,
        harness_sources=live_harness,
        runner_provenance=options.runner_attestor(),
    )
    if _canonical_json(observed) != options.candidate_binding_json:
        raise ReleaseCliError(
            "artifact, receipt, manifest, harness, evidence, or runner input changed "
            "after plan validation"
        )


def _band(value: str) -> BandCase:
    try:
        name, raw_frequency = value.split("=", 1)
        frequency = int(raw_frequency)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("band must be NAME=HZ") from error
    if not name or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None:
        raise argparse.ArgumentTypeError("band name must be a nonempty safe label")
    return BandCase(name, frequency)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run serial-attested tandem-AGC release qualification; this command "
            "never deploys or flashes firmware"
        )
    )
    parser.add_argument("--authorize-tx2-loopback", action="store_true")
    parser.add_argument("--radio-serial", required=True)
    parser.add_argument(
        "--firmware-version",
        required=True,
        help="literal complete fw_version (converted to an anchored escaped regex)",
    )
    parser.add_argument(
        "--artifact-index",
        required=True,
        help="canonical absolute candidate/final artifact-index path",
    )
    parser.add_argument(
        "--deployment-receipt",
        required=True,
        help="canonical absolute serial-scoped RAM-only receipt path",
    )
    parser.add_argument(
        "--physical-attenuation-db",
        required=True,
        type=_finite_nonnegative,
        help="finite current physical loss; TX backoff is accounted separately",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/radio-hardware/tandem-agc-release"),
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=DEFAULT_PHASES,
        help="requested phase; repeat to select a subset (default: all)",
    )
    parser.add_argument(
        "--band",
        action="append",
        type=_band,
        help="NAME=HZ; repeat for an explicit band set",
    )
    parser.add_argument(
        "--policy-set",
        choices=("full", "baseline"),
        default="full",
        help=(
            "full = one-factor characterization; baseline = repeatability/soak "
            "without multiplying policy cases"
        ),
    )
    parser.add_argument("--repeat-cycles", type=_positive_integer)
    parser.add_argument("--cycle-interval-seconds", type=_finite_nonnegative)
    parser.add_argument("--soak-deadline-seconds", type=_finite_positive)
    parser.add_argument("--max-new-steady-runs", type=_positive_integer)
    parser.add_argument("--sample-rate-hz", type=_positive_integer, default=2_500_000)
    parser.add_argument("--samples-per-channel", type=_positive_integer, default=65_536)
    parser.add_argument("--phase-max-seconds", type=_finite_positive, default=600.0)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="explicitly authorize a fresh attempt after a recorded failed phase",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the fully validated plan without importing iio or opening USB",
    )
    return parser


def parse_cli_args(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner_attestor: Callable[[], Mapping[str, Any]] | None = None,
) -> ReleaseHardwareOptions:
    parser = build_parser()
    namespace = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    if not namespace.authorize_tx2_loopback:
        parser.error("--authorize-tx2-loopback is required before any TX mutation")
    serial = namespace.radio_serial.strip()
    firmware = namespace.firmware_version.strip()
    if not serial or serial != namespace.radio_serial:
        parser.error("--radio-serial must be nonempty with no surrounding whitespace")
    if re.fullmatch(r"[A-Za-z0-9_.-]+", serial) is None:
        parser.error("--radio-serial must contain only safe immutable-ID characters")
    if not firmware or firmware != namespace.firmware_version or "\n" in firmware:
        parser.error("--firmware-version must be one exact nonempty line")
    commit = environment.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        parser.error(
            "PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT must contain the manifest-pinned "
            "40-hex host libiio commit"
        )
    try:
        artifact_index_path = _canonical_cli_path(
            namespace.artifact_index, name="artifact index"
        )
        deployment_receipt_path = _canonical_cli_path(
            namespace.deployment_receipt, name="deployment receipt"
        )
    except ReleaseCliError as error:
        parser.error(str(error))
    default_phases = DEFAULT_PHASES if namespace.policy_set == "full" else ("steady",)
    requested_phases = tuple(namespace.phase or default_phases)
    if len(set(requested_phases)) != len(requested_phases):
        parser.error("--phase values cannot be duplicated")
    phases = tuple(phase for phase in DEFAULT_PHASES if phase in requested_phases)
    bands = tuple(namespace.band or steady_campaign.DEFAULT_BANDS)
    if len({band.name for band in bands}) != len(bands):
        parser.error("band names must be unique")
    if len({band.center_frequency_hz for band in bands}) != len(bands):
        parser.error("band frequencies must be unique")
    # Full characterization is intentionally a single cycle by default.  A
    # baseline-only soak spans approximately one hour by default (t=0..3600).
    repeats = namespace.repeat_cycles
    if repeats is None:
        repeats = 1 if namespace.policy_set == "full" else 4
    interval = namespace.cycle_interval_seconds
    if interval is None:
        interval = 0.0 if namespace.policy_set == "full" else 1_200.0
    deadline = namespace.soak_deadline_seconds
    if deadline is None:
        deadline = 14_400.0 if namespace.policy_set == "full" else 5_400.0
    harness_sources = _harness_sources()
    if runner_attestor is None:
        attestor: Callable[[], Mapping[str, Any]] = lambda: _attest_runner_provenance(
            environment
        )
    else:
        # This callable boundary exists solely for hardware-free planted oracles.
        # The executable entry point never supplies it and therefore cannot bypass
        # the committed, fully clean repository checks above.
        attestor = runner_attestor
    try:
        binding = _attest_candidate_binding(
            artifact_index_path=artifact_index_path,
            deployment_receipt_path=deployment_receipt_path,
            serial=serial,
            firmware_version=firmware,
            libiio_source_commit=commit,
            harness_sources=harness_sources,
            runner_provenance=attestor(),
            semantic_verify=True,
        )
    except ReleaseCliError as error:
        parser.error(str(error))
    options = ReleaseHardwareOptions(
        serial=serial,
        firmware_version=firmware,
        firmware_pattern=r"\A" + re.escape(firmware) + r"\Z",
        libiio_source_commit=commit,
        harness_sources=harness_sources,
        artifact_index_path=artifact_index_path,
        deployment_receipt_path=deployment_receipt_path,
        candidate_binding_json=_canonical_json(binding),
        runner_attestor=attestor,
        physical_attenuation_db=namespace.physical_attenuation_db,
        # Every invocation owns exactly one immutable serial.  Scope even an
        # explicit base directory so four parallel radios cannot share state.
        output_dir=(namespace.output.resolve() / serial),
        phases=phases,
        bands=bands,
        policy_set=namespace.policy_set,
        repeat_cycles=repeats,
        cycle_interval_seconds=interval,
        soak_deadline_seconds=deadline,
        max_new_steady_runs=namespace.max_new_steady_runs,
        sample_rate_hz=namespace.sample_rate_hz,
        samples_per_channel=namespace.samples_per_channel,
        phase_max_seconds=namespace.phase_max_seconds,
        retry_failed=namespace.retry_failed,
        resume=not namespace.no_resume,
        plan_only=namespace.plan_only,
    )
    validate_release_hardware_options(options)
    try:
        _verify_release_output_plan(options, phase_specs(options))
    except ReleaseCliError as error:
        parser.error(str(error))
    return options


def _base_quality(
    options: ReleaseHardwareOptions, *, output_dir: Path, band: BandCase | None = None
) -> TandemQualityOptions:
    quality = TandemQualityOptions(
        tx_gain_trajectory_db=default_tx_trajectory("full"),
        physical_attenuation_db=options.physical_attenuation_db,
        center_frequency_hz=(
            band.center_frequency_hz
            if band is not None
            else options.bands[0].center_frequency_hz
        ),
        sample_rate_hz=options.sample_rate_hz,
        samples_per_channel=options.samples_per_channel,
        native_gain_control_modes=AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
        max_seconds=options.phase_max_seconds,
        output_dir=output_dir,
        profile="full",
    )
    validate_options(quality)
    return quality


def _steady_inputs(
    options: ReleaseHardwareOptions, work_dir: Path
) -> tuple[ReleaseCampaignConfig, TandemQualityOptions]:
    policies = () if options.policy_set == "full" else (BASELINE_POLICY,)
    config = ReleaseCampaignConfig(
        output_dir=work_dir,
        radio_serials=(options.serial,),
        repeat_cycles=options.repeat_cycles,
        cycle_interval_seconds=options.cycle_interval_seconds,
        soak_deadline_seconds=options.soak_deadline_seconds,
        bands=options.bands,
        policy_cases=policies,
    )
    base = _base_quality(options, output_dir=work_dir / "unused")
    build_release_plan(config, base)
    return config, base


def phase_specs(options: ReleaseHardwareOptions) -> tuple[PhaseSpec, ...]:
    result: list[PhaseSpec] = []
    for phase in options.phases:
        if phase == "steady":
            result.append(PhaseSpec(options.steady_key, "steady"))
        elif phase == DIAGNOSTIC_PHASE:
            result.append(
                PhaseSpec("diagnostic_2450mhz", "diagnostic", DIAGNOSTIC_BAND)
            )
        else:
            result.extend(
                PhaseSpec(f"{phase}_{band.name}", phase, band) for band in options.bands
            )
    return tuple(result)


def validate_release_hardware_options(options: ReleaseHardwareOptions) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", options.libiio_source_commit) is None:
        raise ValueError("host libiio commit must be exact 40-hex")
    if tuple(
        name for name, _digest in options.harness_sources
    ) != HARNESS_SOURCE_NAMES or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for _name, digest in options.harness_sources
    ):
        raise ValueError("release harness source manifest is incomplete or malformed")
    if (
        not options.artifact_index_path.is_absolute()
        or not options.deployment_receipt_path.is_absolute()
        or not callable(options.runner_attestor)
    ):
        raise ValueError("candidate binding paths/attestor are incomplete")
    if (options.host_libiio_json is None) != (options.host_libiio_attestor is None):
        raise ValueError(
            "host libiio provenance and attestor must be supplied together"
        )
    if options.host_libiio_json is not None:
        try:
            host_libiio = _validate_host_libiio_runtime(
                json.loads(options.host_libiio_json)
            )
        except (ReleaseCliError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("host libiio provenance JSON is invalid") from error
        if (
            _canonical_json(host_libiio) != options.host_libiio_json
            or host_libiio["source_commit"] != options.libiio_source_commit
        ):
            raise ValueError("host libiio provenance is noncanonical or mismatched")
    try:
        binding = json.loads(options.candidate_binding_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("candidate binding JSON is invalid") from error
    if (
        not isinstance(binding, Mapping)
        or binding.get("schema") != "plutosdr-fw.tandem-release-candidate-binding.v1"
        or binding.get("serial") != options.serial
        or binding.get("firmware_version") != options.firmware_version
        or _canonical_json(binding) != options.candidate_binding_json
    ):
        raise ValueError("candidate binding identity is incomplete or noncanonical")
    if re.fullmatch(options.firmware_pattern, options.firmware_version) is None:
        raise ValueError("anchored firmware regex does not match the exact version")
    if options.firmware_pattern != r"\A" + re.escape(options.firmware_version) + r"\Z":
        raise ValueError("firmware regex must be escaped and anchored exactly")
    if not options.phases or any(
        phase not in DEFAULT_PHASES for phase in options.phases
    ):
        raise ValueError("at least one supported phase is required")
    if options.policy_set not in ("full", "baseline"):
        raise ValueError("policy set must be full or baseline")
    if DIAGNOSTIC_PHASE in options.phases and options.policy_set != "full":
        raise ValueError("the 2.45 GHz diagnostic belongs only to a full campaign")
    if options.repeat_cycles <= 0:
        raise ValueError("repeat cycles must be positive")
    if options.cycle_interval_seconds < 0 or not math.isfinite(
        options.cycle_interval_seconds
    ):
        raise ValueError("cycle interval must be finite and nonnegative")
    if options.soak_deadline_seconds <= 0 or not math.isfinite(
        options.soak_deadline_seconds
    ):
        raise ValueError("soak deadline must be finite and positive")
    if not options.bands:
        raise ValueError("at least one RF band is required")
    if "steady" in options.phases:
        _steady_inputs(options, options.output_dir / "preflight-steady")
    capture = TransientCaptureOptions()
    for band in options.bands:
        quality = _base_quality(
            options, output_dir=options.output_dir / "preflight-transient", band=band
        )
        if "transient" in options.phases:
            validate_transient_options(quality, capture)
        if "modulated" in options.phases:
            validate_modulated_hardware_options(
                ModulatedHardwareOptions(
                    physical_attenuation_db=options.physical_attenuation_db,
                    center_frequency_hz=band.center_frequency_hz,
                    tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                    modes=RELEASE_MODULATED_MODES,
                    max_seconds=options.phase_max_seconds,
                    output_dir=options.output_dir / "preflight-modulated",
                )
            )
    if DIAGNOSTIC_PHASE in options.phases:
        _base_quality(
            options,
            output_dir=options.output_dir / "preflight-diagnostic-2450",
            band=DIAGNOSTIC_BAND,
        )


def _assert_harness_unchanged(options: ReleaseHardwareOptions) -> None:
    _assert_release_inputs_unchanged(options)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReleaseCliError("aggregate JSON cannot contain non-finite values")
        return value
    raise ReleaseCliError(f"aggregate JSON cannot encode {type(value)}")


def _configuration(options: ReleaseHardwareOptions) -> dict[str, Any]:
    return {
        "serial": options.serial,
        "firmware_version": options.firmware_version,
        "firmware_pattern": options.firmware_pattern,
        "libiio_source_commit": options.libiio_source_commit,
        "harness_sources": dict(options.harness_sources),
        "artifact_index_path": str(options.artifact_index_path),
        "deployment_receipt_path": str(options.deployment_receipt_path),
        "candidate_binding": json.loads(options.candidate_binding_json),
        "host_libiio": (
            json.loads(options.host_libiio_json)
            if options.host_libiio_json is not None
            else None
        ),
        "physical_attenuation_db": options.physical_attenuation_db,
        "output_dir": str(options.output_dir),
        "requested_phases": list(options.phases),
        "bands": [asdict(band) for band in options.bands],
        "non_authorizing_diagnostic": {
            "phase": DIAGNOSTIC_PHASE,
            "band": asdict(DIAGNOSTIC_BAND),
            "modes": list(
                quality_modes(
                    _base_quality(
                        options,
                        output_dir=options.output_dir / "configuration-diagnostic",
                        band=DIAGNOSTIC_BAND,
                    )
                )
            ),
            "continuation_policy": (
                "rf_quality_only_failure_is_recorded_and_nonbinding"
            ),
            "fatal_policy": (
                "identity_metadata_evidence_safety_fault_or_cleanup_failure"
            ),
            "release_claim": "none_at_2_4_ghz",
        },
        "policy_set": options.policy_set,
        "steady_campaign_kind": (
            "one_factor_characterization"
            if options.policy_set == "full"
            else "baseline_repeatability_soak"
        ),
        "repeat_cycles": options.repeat_cycles,
        "cycle_interval_seconds": options.cycle_interval_seconds,
        "soak_deadline_seconds": options.soak_deadline_seconds,
        "sample_rate_hz": options.sample_rate_hz,
        "samples_per_channel": options.samples_per_channel,
        "autonomous_native_gain_control_modes": list(
            AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
        ),
        "modulated_modes": list(RELEASE_MODULATED_MODES),
        "modulated_tx2_gain_db": DEFAULT_MODULATED_TX2_GAIN_DB,
        "phase_max_seconds": options.phase_max_seconds,
    }


def _stable_resume_configuration(value: Mapping[str, Any]) -> dict[str, Any]:
    configuration = dict(value)
    host_libiio = configuration.get("host_libiio")
    if isinstance(host_libiio, Mapping):
        configuration["host_libiio"] = {
            "schema": host_libiio.get("schema"),
            "resume_identity": host_libiio.get("resume_identity"),
        }
    return configuration


def _fingerprint(options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]) -> str:
    configuration = _stable_resume_configuration(_configuration(options))
    payload = {"schema": AGGREGATE_SCHEMA, "configuration": configuration}
    payload["plan"] = [spec.to_dict() for spec in specs]
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ReleaseCliError("aggregate JSON target or temporary path is symlinked")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ReleaseCliError("aggregate JSON parent directory is symlinked")
    temporary.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _new_checkpoint(
    options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    stamp = time.time_ns()
    host_libiio = _assert_host_libiio_unchanged(options)
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": _fingerprint(options, specs),
        "configuration": _configuration(options),
        "host_libiio_invocations": [
            {"started_unix_ns": stamp, "provenance": host_libiio}
        ],
        "started_unix_ns": stamp,
        "updated_unix_ns": stamp,
        "phases": {
            spec.key: {
                "status": "pending",
                "attempts": 0,
                "spec": spec.to_dict(),
                "history": [],
            }
            for spec in specs
        },
    }


def _aggregate_report(
    checkpoint: Mapping[str, Any], specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    phases = checkpoint["phases"]
    statuses = [phases[spec.key]["status"] for spec in specs]
    complete = [
        phases[spec.key] for spec in specs if phases[spec.key]["status"] == "complete"
    ]
    all_cleanup = len(complete) == len(specs) and all(
        record.get("cleanup_verified") is True for record in complete
    )
    all_host_libiio = len(complete) == len(specs) and all(
        isinstance(record.get("host_libiio_before_phase"), Mapping)
        and isinstance(record.get("host_libiio_after_cleanup"), Mapping)
        and _canonical_json(record["host_libiio_before_phase"])
        == _canonical_json(record["host_libiio_after_cleanup"])
        for record in complete
    )
    if any(status in ("failed", "running") for status in statuses):
        verdict = "invalid"
    elif len(complete) != len(specs):
        verdict = "incomplete"
    elif (
        not all_cleanup
        or not all_host_libiio
        or any(
            not _phase_verdict_is_acceptable(
                spec, phases[spec.key].get("phase_verdict")
            )
            for spec in specs
        )
    ):
        verdict = "fail"
    else:
        verdict = "pass"
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": checkpoint["fingerprint"],
        "verdict": verdict,
        "all_requested_phases_complete": len(complete) == len(specs),
        "all_cleanup_verified": all_cleanup,
        "all_host_libiio_verified": all_host_libiio,
        "authorizing_bands": list(checkpoint["configuration"]["bands"]),
        "diagnostics": {
            spec.key: phases[spec.key].get("phase_verdict", phases[spec.key]["status"])
            for spec in specs
            if spec.kind == "diagnostic"
        },
        "configuration": checkpoint["configuration"],
        "host_libiio_invocations": checkpoint["host_libiio_invocations"],
        "plan": [spec.to_dict() for spec in specs],
        "counts": {
            status: statuses.count(status)
            for status in ("pending", "running", "complete", "failed")
        },
        "phases": phases,
        "started_unix_ns": checkpoint["started_unix_ns"],
        "updated_unix_ns": checkpoint["updated_unix_ns"],
    }


def _phase_verdict_is_acceptable(spec: PhaseSpec, verdict: object) -> bool:
    if spec.kind == "diagnostic":
        return verdict in {DIAGNOSTIC_PASS, DIAGNOSTIC_FAIL}
    return verdict == "pass"


def _load_checkpoint(
    path: Path, options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = [spec.key for spec in specs]
    checkpoint_configuration = checkpoint.get("configuration")
    checkpoint_phases = checkpoint.get("phases")
    if (
        checkpoint.get("schema") != AGGREGATE_SCHEMA
        or checkpoint.get("fingerprint") != _fingerprint(options, specs)
        # _atomic_json deliberately canonicalizes object keys.  Phase execution
        # order belongs to ``specs``/``plan``; it cannot be recovered from JSON
        # object iteration order after that canonical serialization.
        or not isinstance(checkpoint_phases, Mapping)
        or set(checkpoint_phases) != set(expected_keys)
        or any(
            not isinstance(checkpoint_phases.get(spec.key), Mapping)
            or checkpoint_phases[spec.key].get("spec") != spec.to_dict()
            for spec in specs
        )
        or not isinstance(checkpoint_configuration, Mapping)
        or _canonical_json(_stable_resume_configuration(checkpoint_configuration))
        != _canonical_json(_stable_resume_configuration(_configuration(options)))
    ):
        raise ReleaseCliError("aggregate checkpoint differs from the requested plan")
    invocations = checkpoint.get("host_libiio_invocations")
    if not isinstance(invocations, list) or not invocations:
        raise ReleaseCliError("aggregate checkpoint lacks host libiio provenance")
    current = _assert_host_libiio_unchanged(options)
    previous = invocations[-1]
    if (
        not isinstance(previous, Mapping)
        or set(previous) != {"started_unix_ns", "provenance"}
        or type(previous.get("started_unix_ns")) is not int
        or previous["started_unix_ns"] <= 0
        or not isinstance(previous.get("provenance"), Mapping)
    ):
        raise ReleaseCliError("aggregate host libiio invocation record is malformed")
    if _canonical_json(previous["provenance"]) != _canonical_json(current):
        invocations.append({"started_unix_ns": time.time_ns(), "provenance": current})
    return checkpoint


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _require_nonsymlink_descendant(
    path: Path, trusted_root: Path, *, label: str
) -> Path:
    """Reject lexical or resolved escapes and every existing symlink component."""

    root = trusted_root.resolve(strict=False)
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ReleaseCliError(f"{label} escapes its trusted output root") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseCliError(f"{label} is not a canonical output descendant")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ReleaseCliError(f"{label} contains a symlink component")
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise ReleaseCliError(
            f"{label} resolves outside its trusted output root"
        ) from error
    if candidate != resolved:
        raise ReleaseCliError(f"{label} changes under filesystem resolution")
    return candidate


def _verify_release_output_plan(
    options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]
) -> None:
    """Validate serial/global descendants before opening the aggregate lock."""

    serial_root = options.output_dir.absolute()
    base_root = serial_root.parent.resolve(strict=False)
    _require_nonsymlink_descendant(
        serial_root, base_root, label="serial output directory"
    )
    for name in (AGGREGATE_CHECKPOINT, AGGREGATE_REPORT, "release-hardware.lock"):
        _require_nonsymlink_descendant(
            serial_root / name,
            serial_root,
            label=f"aggregate {name}",
        )
        if name != "release-hardware.lock":
            _require_nonsymlink_descendant(
                serial_root / f"{name}.tmp",
                serial_root,
                label=f"aggregate {name} temporary",
            )
    artifacts = _require_nonsymlink_descendant(
        serial_root / "artifacts", serial_root, label="phase artifact directory"
    )
    for spec in specs:
        _require_nonsymlink_descendant(
            artifacts / spec.key,
            serial_root,
            label=f"{spec.key} artifact directory",
        )


def _verify_completed(
    checkpoint: Mapping[str, Any],
    specs: Sequence[PhaseSpec],
    validator: PhaseValidator,
    root: Path,
) -> None:
    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] != "complete":
            continue
        before_raw = record.get("host_libiio_before_phase")
        after_raw = record.get("host_libiio_after_cleanup")
        if not isinstance(before_raw, Mapping) or not isinstance(after_raw, Mapping):
            raise ReleaseCliError(
                f"completed {spec.key} lacks host libiio boundary provenance"
            )
        before = _validate_host_libiio_runtime(before_raw)
        after = _validate_host_libiio_runtime(after_raw)
        configured = checkpoint.get("configuration", {}).get("host_libiio")
        configured_resume = (
            configured.get("resume_identity")
            if isinstance(configured, Mapping)
            else None
        )
        if (
            _canonical_json(before) != _canonical_json(after)
            or before["resume_identity"] != configured_resume
        ):
            raise ReleaseCliError(
                f"completed {spec.key} host libiio provenance changed"
            )
        report_path = Path(record["report_path"])
        work_dir = Path(record["work_dir"])
        _require_nonsymlink_descendant(
            work_dir, root, label=f"completed {spec.key} attempt directory"
        )
        _require_nonsymlink_descendant(
            report_path, work_dir, label=f"completed {spec.key} report"
        )
        if not _inside(work_dir, root) or not _inside(report_path, work_dir):
            raise ReleaseCliError(f"completed {spec.key} path escapes its attempt")
        if not report_path.is_file() or _sha256(report_path) != record.get(
            "report_sha256"
        ):
            raise ReleaseCliError(f"completed {spec.key} artifact changed")
        validated = validator(spec, report_path, work_dir)
        if (
            not _phase_verdict_is_acceptable(spec, validated.verdict)
            or not validated.cleanup_verified
            or _json_safe(validated.summary) != record.get("summary")
        ):
            raise ReleaseCliError(f"completed {spec.key} evidence no longer validates")


def _run_aggregate_locked(
    options: ReleaseHardwareOptions,
    executor: PhaseExecutor,
    validator: PhaseValidator,
) -> tuple[dict[str, Any], Path]:
    """Execute/resume an aggregate using injected hardware-free boundaries."""

    specs = phase_specs(options)
    root = options.output_dir
    checkpoint_path = root / AGGREGATE_CHECKPOINT
    report_path = root / AGGREGATE_REPORT
    if checkpoint_path.exists():
        if not options.resume:
            raise ReleaseCliError("aggregate checkpoint exists but resume is disabled")
        checkpoint = _load_checkpoint(checkpoint_path, options, specs)
        _verify_completed(checkpoint, specs, validator, root)
    else:
        checkpoint = _new_checkpoint(options, specs)
        _atomic_json(checkpoint_path, checkpoint)

    # A process may have died while a phase owned TX.  Never accept its artifact:
    # retain an audit entry and force a fresh attempt directory.  The subsequent
    # Issue46Radio open acquires the serial lock and mutes before configuration.
    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] == "running":
            record["history"].append(
                {
                    "attempt": record["attempts"],
                    "status": "abandoned_untrusted_interrupted_attempt",
                    "work_dir": record.get("work_dir"),
                }
            )
            record["status"] = "pending"
            record["resumable"] = False
        elif record["status"] == "failed" and options.retry_failed:
            record["history"].append(
                {
                    "attempt": record["attempts"],
                    "status": "explicitly_retried_failed_attempt",
                    "work_dir": record.get("work_dir"),
                    "error": record.get("error"),
                }
            )
            record["status"] = "pending"
            record["resumable"] = False
    checkpoint["updated_unix_ns"] = time.time_ns()
    _atomic_json(checkpoint_path, checkpoint)

    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] == "complete":
            continue
        if record["status"] == "failed":
            break
        _assert_release_inputs_unchanged(options)
        host_libiio_before = _assert_host_libiio_unchanged(options)
        resume_work = record.get("resumable") is True and record.get("work_dir")
        record["attempts"] += 1
        work_dir = (
            Path(record["work_dir"])
            if resume_work
            else root / "artifacts" / spec.key / f"attempt-{record['attempts']:04d}"
        )
        work_dir = _require_nonsymlink_descendant(
            work_dir, root, label=f"{spec.key} attempt directory"
        )
        record.pop("host_libiio_after_cleanup", None)
        record.update(
            {
                "status": "running",
                "work_dir": str(work_dir.resolve()),
                "started_unix_ns": time.time_ns(),
                "resumable": False,
                "host_libiio_before_phase": host_libiio_before,
            }
        )
        checkpoint["updated_unix_ns"] = time.time_ns()
        _atomic_json(checkpoint_path, checkpoint)
        _atomic_json(report_path, _aggregate_report(checkpoint, specs))
        try:
            try:
                returned_artifact = Path(executor(spec, work_dir.resolve()))
            finally:
                record["host_libiio_after_cleanup"] = _assert_host_libiio_unchanged(
                    options
                )
            _require_nonsymlink_descendant(
                returned_artifact,
                work_dir,
                label=f"{spec.key} returned report",
            )
            artifact = returned_artifact.resolve()
            if not artifact.is_file() or not _inside(artifact, work_dir):
                raise ReleaseCliError(
                    f"{spec.key} returned no durable report inside its attempt"
                )
            validated = validator(spec, artifact, work_dir.resolve())
            if validated.verdict == "incomplete" and spec.kind == "steady":
                record.update(
                    {
                        "status": "pending",
                        "resumable": True,
                        "report_path": str(artifact),
                        "report_sha256": _sha256(artifact),
                        "phase_verdict": "incomplete",
                        "cleanup_verified": False,
                        "summary": _json_safe(validated.summary),
                    }
                )
            elif (
                not _phase_verdict_is_acceptable(spec, validated.verdict)
                or not validated.cleanup_verified
            ):
                raise ReleaseCliError(
                    f"{spec.key} did not prove PASS plus durable cleanup"
                )
            else:
                record.update(
                    {
                        "status": "complete",
                        "completed_unix_ns": time.time_ns(),
                        "report_path": str(artifact),
                        "report_sha256": _sha256(artifact),
                        "phase_verdict": validated.verdict,
                        "cleanup_verified": True,
                        "summary": _json_safe(validated.summary),
                        "resumable": False,
                    }
                )
        except BaseException as error:  # noqa: BLE001 - persist every invalid exit
            record.update(
                {
                    "status": "failed",
                    "completed_unix_ns": time.time_ns(),
                    "error": f"{type(error).__name__}: {error}",
                    "cleanup_verified": False,
                    "resumable": False,
                }
            )
        checkpoint["updated_unix_ns"] = time.time_ns()
        _atomic_json(checkpoint_path, checkpoint)
        _atomic_json(report_path, _aggregate_report(checkpoint, specs))
        if record["status"] == "failed":
            break
        if record["status"] == "pending" and record.get("resumable") is True:
            # An explicit --max-new-steady-runs is an incremental steady-state
            # invocation, not permission to move on to unrelated TX waveforms.
            break
    report = _aggregate_report(checkpoint, specs)
    _atomic_json(report_path, report)
    return report, report_path


def run_aggregate(
    options: ReleaseHardwareOptions,
    executor: PhaseExecutor,
    validator: PhaseValidator,
) -> tuple[dict[str, Any], Path]:
    """Serialize one immutable radio's aggregate state for this invocation."""

    specs = phase_specs(options)
    _assert_release_inputs_unchanged(options)
    _assert_host_libiio_unchanged(options)
    _verify_release_output_plan(options, specs)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    _verify_release_output_plan(options, specs)
    lock_path = options.output_dir / "release-hardware.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReleaseCliError(
                f"another release invocation owns serial {options.serial}"
            ) from error
        _verify_release_output_plan(options, specs)
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()} serial={options.serial}\n")
        lock.flush()
        result = _run_aggregate_locked(options, executor, validator)
        _assert_host_libiio_unchanged(options)
        _verify_release_output_plan(options, specs)
        return result


def _issue_options(
    options: ReleaseHardwareOptions,
    quality: TandemQualityOptions,
    *,
    namespace: str,
    tx_gain_db: float | None = None,
) -> Issue46Options:
    return Issue46Options(
        serial=options.serial,
        uri=None,
        allow_non_usb=False,
        firmware_pattern=options.firmware_pattern,
        libiio_source_commit=options.libiio_source_commit,
        attenuation_db=options.physical_attenuation_db,
        tx_gain_db=(quality.strongest_tx_gain_db if tx_gain_db is None else tx_gain_db),
        sample_rate_hz=quality.sample_rate_hz,
        samples_per_channel=quality.samples_per_channel,
        profile="repro",
        sink="ram",
        expected="green",
        output_dir=quality.output_dir,
        max_seconds=quality.max_seconds,
        save_iq=False,
        pn_min_coherence=0.03,
        pn_min_peak_ratio=1.5,
        lock_namespace=namespace,
        center_frequency_hz=quality.center_frequency_hz,
    )


@contextmanager
def _radio_lifecycle(
    iio_module: Any,
    radio_options: Issue46Options,
    radio_factory: Callable[[Any, Issue46Options], Issue46Radio],
) -> Iterator[Issue46Radio]:
    radio = radio_factory(iio_module, radio_options)
    try:
        yield radio
    except BaseException as body_error:
        try:
            radio.close()
        except BaseException as close_error:  # noqa: BLE001
            raise BaseExceptionGroup(
                "release phase and final radio cleanup both failed",
                [body_error, close_error],
            ) from None
        raise
    else:
        radio.close()


def production_executor(
    options: ReleaseHardwareOptions,
    iio_module: Any,
    *,
    radio_factory: Callable[[Any, Issue46Options], Issue46Radio] = Issue46Radio,
) -> PhaseExecutor:
    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        _assert_harness_unchanged(options)
        if spec.kind == "steady":
            config, base = _steady_inputs(options, work_dir)

            @contextmanager
            def open_radio(
                _serial: str, quality: TandemQualityOptions
            ) -> Iterator[Issue46Radio]:
                with _radio_lifecycle(
                    iio_module,
                    _issue_options(
                        options, quality, namespace="tandem-agc-release-steady"
                    ),
                    radio_factory,
                ) as radio:
                    yield radio

            report, path = run_release_campaign(
                config,
                base,
                matrix_runner_for_radio_factory(open_radio),
                max_new_runs=options.max_new_steady_runs,
            )
            del report
            return path
        assert spec.band is not None
        if spec.kind == "diagnostic":
            quality = _base_quality(options, output_dir=work_dir, band=spec.band)
            with _radio_lifecycle(
                iio_module,
                _issue_options(
                    options, quality, namespace="tandem-agc-release-diagnostic-2450"
                ),
                radio_factory,
            ) as radio:
                _report, path = run_tandem_quality_matrix(radio, quality)
            return path
        if spec.kind == "transient":
            quality = _base_quality(options, output_dir=work_dir, band=spec.band)
            with _radio_lifecycle(
                iio_module,
                _issue_options(
                    options, quality, namespace="tandem-agc-release-transient"
                ),
                radio_factory,
            ) as radio:
                _report, path = run_transient_hardware(radio, quality)
            return path
        if spec.kind == "modulated":
            modulated = ModulatedHardwareOptions(
                physical_attenuation_db=options.physical_attenuation_db,
                center_frequency_hz=spec.band.center_frequency_hz,
                tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                modes=RELEASE_MODULATED_MODES,
                max_seconds=options.phase_max_seconds,
                output_dir=work_dir,
            )
            # The modulated signal intentionally uses its deterministic 1.024-MHz
            # sample grid rather than the tone/transient grid.
            radio_quality = replace(
                _base_quality(options, output_dir=work_dir, band=spec.band),
                sample_rate_hz=modulated.sample_rate_hz,
                samples_per_channel=modulated.capture_samples,
            )
            with _radio_lifecycle(
                iio_module,
                _issue_options(
                    options,
                    radio_quality,
                    namespace="tandem-agc-release-modulated",
                    tx_gain_db=modulated.tx2_gain_db,
                ),
                radio_factory,
            ) as radio:
                _report, path = run_modulated_hardware_campaign(radio, modulated)
            return path
        raise AssertionError(f"unsupported phase {spec.kind}")

    return execute


def _cleanup_errors(report: Mapping[str, Any]) -> list[str]:
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, Mapping):
        return ["cleanup is missing"]
    errors = []
    if set(cleanup) != {
        "verified",
        "tx1_gain_db",
        "tx2_gain_db",
        "selectors",
        "dds",
        "failures",
    }:
        errors.append("cleanup fields differ from the exact mute ledger")
    if cleanup.get("verified") is not True or cleanup.get("failures") != []:
        errors.append("cleanup was not verified without failures")
    if cleanup.get("selectors") != [3, 3, 3, 3]:
        errors.append("cleanup selectors are not all ZERO")
    for key in ("tx1_gain_db", "tx2_gain_db"):
        value = cleanup.get(key)
        if not _release_finite_number(value) or float(value) > -80.0:
            errors.append(f"cleanup {key} is not muted below -80 dB")
    dds = cleanup.get("dds")
    if not isinstance(dds, Mapping) or set(dds) != {
        f"altvoltage{index}" for index in range(8)
    }:
        errors.append("cleanup DDS coverage is incomplete")
    else:
        for name, evidence in dds.items():
            if (
                not isinstance(evidence, Mapping)
                or type(evidence.get("present")) is not bool
                or set(evidence)
                != (
                    {"present", "scale", "raw"}
                    if evidence.get("present") is True
                    else {"present"}
                )
            ):
                errors.append(f"cleanup {name} is malformed")
            elif evidence["present"] and any(
                evidence.get(attribute) != 0.0 for attribute in ("scale", "raw")
            ):
                errors.append(f"cleanup {name} is not disabled")
    return errors


def _modulated_dma_cleanup_errors(waveforms: Any) -> list[str]:
    if not isinstance(waveforms, list):
        return ["modulated waveforms are missing"]
    errors: list[str] = []
    for index, waveform in enumerate(waveforms):
        if not isinstance(waveform, Mapping):
            errors.append(f"modulated waveform {index} is malformed")
            continue
        case_id = waveform.get("case_id", index)
        cleanup = waveform.get("dma_cleanup")
        if not isinstance(cleanup, Mapping):
            errors.append(f"modulated {case_id} cyclic-DMA cleanup is missing")
            continue
        if cleanup.get("buffer_closed") is not True:
            errors.append(f"modulated {case_id} cyclic-DMA buffer was not closed")
        if cleanup.get("buffer_release_method") not in (
            "explicit_close",
            "reference_release_gc",
        ):
            errors.append(f"modulated {case_id} cyclic-DMA release method is invalid")
        if cleanup.get("failures") != []:
            errors.append(f"modulated {case_id} cyclic-DMA cleanup has failures")
        errors.extend(
            f"modulated {case_id} cyclic-DMA {error}"
            for error in _cleanup_errors({"cleanup": cleanup.get("mute")})
        )
    return errors


def _modulated_iq_convention_errors(runs: Any) -> list[str]:
    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    conventions: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            errors.append(f"modulated run {index} is malformed")
            continue
        summary = run.get("summary")
        convention = (
            summary.get("iq_convention") if isinstance(summary, Mapping) else None
        )
        if convention not in ("direct", "conjugated"):
            errors.append(
                f"modulated {run.get('mode')}/{run.get('case_id')} IQ convention "
                "is invalid"
            )
        else:
            conventions.add(convention)
    if len(conventions) > 1:
        errors.append("modulated IQ convention changed inside one hardware campaign")
    return errors


def _modulated_gain_errors(runs: Any, expected: ModulatedHardwareOptions) -> list[str]:
    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    expected_effective_attenuation = (
        expected.physical_attenuation_db - expected.tx2_gain_db
    )
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            errors.append(f"modulated run {index} is malformed")
            continue
        context = f"modulated {run.get('mode')}/{run.get('case_id')}"
        if run.get("tx2_gain_requested_db") != expected.tx2_gain_db:
            errors.append(f"{context} requested TX2 gain differs from plan")
        if run.get("tx2_gain_readback_db") != expected.tx2_gain_db:
            errors.append(f"{context} TX2 gain readback differs from plan")
        if run.get("effective_attenuation_db") != expected_effective_attenuation:
            errors.append(f"{context} effective attenuation differs from plan")
    return errors


def _modulated_raw_iq_evidence(
    runs: Any,
    *,
    work_dir: Path,
    serial: str,
    capture_samples: int,
) -> tuple[list[str], dict[str, Any] | None]:
    """Verify the bounded desired/blocker diagnostic pair against durable bytes."""

    if not isinstance(runs, list):
        return ["modulated runs are missing"], None
    errors: list[str] = []
    expected_bytes = capture_samples * 8
    if expected_bytes > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
        errors.append("planned raw-IQ artifact exceeds the 64 KiB bound")
    targets = (
        {
            "purpose": "desired_baseline",
            "case_id": "desired_only",
            "mode": MODE_MANUAL,
            "measurement_index": 0,
            "filename": "desired-only-manual-fixed-frame-0000-rx0-rx1.cs16le",
        },
        {
            "purpose": "first_blocker",
            "case_id": "blocker_00",
            "mode": MODE_MANUAL,
            "measurement_index": 0,
            "filename": "blocker-00-manual-fixed-frame-0000-rx0-rx1.cs16le",
        },
    )
    target_runs: dict[tuple[str, str], list[Mapping[str, Any]]] = {
        (target["case_id"], target["mode"]): [] for target in targets
    }
    candidates: list[tuple[str, str, int, Mapping[str, Any]]] = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        key = (run.get("case_id"), run.get("mode"))
        if key in target_runs:
            target_runs[key].append(run)
        measurements = run.get("measurements")
        if not isinstance(measurements, list):
            continue
        for frame_index, frame in enumerate(measurements):
            if isinstance(frame, Mapping) and "raw_iq_provenance" in frame:
                candidates.append(
                    (
                        str(run.get("case_id")),
                        str(run.get("mode")),
                        frame_index,
                        frame,
                    )
                )

    expected_positions = {
        (target["case_id"], target["mode"], target["measurement_index"])
        for target in targets
    }
    observed_positions = {
        (case_id, mode, frame_index)
        for case_id, mode, frame_index, _frame in candidates
    }
    if len(candidates) != 2 or observed_positions != expected_positions:
        errors.append(
            "modulated report must contain exactly two raw-IQ provenance records "
            "on the planned desired/blocker manual frames"
        )

    evidence: dict[str, Any] = {}
    digests: list[str] = []
    expected_paths = {
        (Path(serial) / "diagnostic-iq" / str(target["filename"])).as_posix()
        for target in targets
    }
    root = work_dir.resolve()
    for target in targets:
        purpose = str(target["purpose"])
        key = (str(target["case_id"]), str(target["mode"]))
        matching_runs = target_runs[key]
        if len(matching_runs) != 1:
            errors.append(f"{purpose} raw-IQ target run is missing or duplicated")
            continue
        measurements = matching_runs[0].get("measurements")
        frame_index = int(target["measurement_index"])
        if not isinstance(measurements, list) or len(measurements) <= frame_index:
            errors.append(f"{purpose} raw-IQ target frame is missing")
            continue
        frame = measurements[frame_index]
        if not isinstance(frame, Mapping):
            errors.append(f"{purpose} raw-IQ target frame is malformed")
            continue
        provenance = frame.get("raw_iq_provenance")
        if not isinstance(provenance, Mapping):
            errors.append(f"{purpose} raw-IQ provenance is missing or malformed")
            continue

        if provenance.get("purpose") != purpose:
            errors.append(f"{purpose} raw-IQ purpose differs from plan")
        if provenance.get("case_id") != target["case_id"]:
            errors.append(f"{purpose} raw-IQ case linkage differs from plan")
        if provenance.get("mode") != target["mode"]:
            errors.append(f"{purpose} raw-IQ mode linkage differs from plan")
        if provenance.get("measurement_index") != frame_index:
            errors.append(f"{purpose} raw-IQ frame linkage differs from plan")

        expected_relative_path = (
            Path(serial) / "diagnostic-iq" / str(target["filename"])
        ).as_posix()
        if provenance.get("path") != expected_relative_path:
            errors.append(f"{purpose} raw-IQ artifact path differs from plan")
        byte_count = provenance.get("bytes")
        if type(byte_count) is not int or byte_count != expected_bytes:
            errors.append(f"{purpose} raw-IQ artifact byte count differs from plan")
        if type(byte_count) is int and byte_count > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
            errors.append(f"{purpose} raw-IQ artifact exceeds the 64 KiB bound")
        digest = provenance.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append(f"{purpose} raw-IQ artifact SHA-256 is malformed")
        else:
            digests.append(digest)
        if provenance.get("encoding") != "signed-16-bit-little-endian":
            errors.append(f"{purpose} raw-IQ artifact encoding differs from plan")
        if provenance.get("channel_layout") != [
            "rx0_i",
            "rx0_q",
            "rx1_i",
            "rx1_q",
        ]:
            errors.append(f"{purpose} raw-IQ artifact channel layout differs from plan")
        if provenance.get("samples_per_channel") != capture_samples:
            errors.append(f"{purpose} raw-IQ artifact sample count differs from plan")
        if frame.get("sha256") != digest or frame.get("iq_bytes") != expected_bytes:
            errors.append(
                f"{purpose} raw-IQ provenance differs from its measurement frame"
            )

        path_value = provenance.get("path")
        if isinstance(path_value, str):
            candidate_path = work_dir / path_value
            artifact = candidate_path.resolve()
            if artifact != root and root not in artifact.parents:
                errors.append(
                    f"{purpose} raw-IQ artifact escapes the phase work directory"
                )
            elif candidate_path.is_symlink():
                errors.append(f"{purpose} raw-IQ artifact must not be a symlink")
            elif not artifact.is_file():
                errors.append(f"{purpose} raw-IQ artifact is missing")
            else:
                on_disk_bytes = artifact.stat().st_size
                if on_disk_bytes != expected_bytes:
                    errors.append(
                        f"{purpose} raw-IQ artifact on-disk byte count differs"
                    )
                elif on_disk_bytes > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
                    errors.append(
                        f"{purpose} raw-IQ artifact exceeds the on-disk 64 KiB bound"
                    )
                else:
                    payload = artifact.read_bytes()
                    if (
                        isinstance(digest, str)
                        and hashlib.sha256(payload).hexdigest() != digest
                    ):
                        errors.append(
                            f"{purpose} raw-IQ artifact on-disk SHA-256 differs"
                        )
                temporary = artifact.with_suffix(artifact.suffix + ".tmp")
                if temporary.exists():
                    errors.append(
                        f"{purpose} raw-IQ atomic-write temporary file remains"
                    )
        evidence[purpose] = dict(provenance)

    if len(digests) == 2 and len(set(digests)) != 2:
        errors.append(
            "desired and blocker raw-IQ artifact SHA-256 values are not distinct"
        )

    diagnostic_dir = work_dir / serial / "diagnostic-iq"
    if diagnostic_dir.is_symlink():
        errors.append("raw-IQ diagnostic directory must not be a symlink")
    elif diagnostic_dir.is_dir():
        actual_paths = {
            path.relative_to(work_dir).as_posix()
            for path in diagnostic_dir.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if actual_paths != expected_paths:
            errors.append("raw-IQ diagnostic directory contents differ from plan")

    return errors, evidence if not errors else None


def _modulated_continuity_errors(runs: Any, capture_samples: int) -> list[str]:
    """Recompute tandem gap evidence from the persisted metadata counters."""

    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    uint32_modulus = 1 << 32

    def exact_integer(value: Any, *, minimum: int = 0) -> bool:
        return type(value) is int and value >= minimum

    for run_index, run in enumerate(runs):
        if not isinstance(run, Mapping) or run.get("mode") != MODE_TANDEM:
            continue
        context = f"modulated tandem run {run.get('case_id', run_index)}"
        settling = run.get("settling")
        trace = settling.get("trace") if isinstance(settling, Mapping) else None
        measurements = run.get("measurements")
        if not isinstance(trace, list) or not isinstance(measurements, list):
            errors.append(f"{context} lacks frame evidence")
            continue
        if not trace or not measurements:
            errors.append(f"{context} has empty frame evidence")
            continue
        if settling.get("frames") != len(trace):
            errors.append(f"{context} settling frame count is inconsistent")

        previous_metadata: Mapping[str, Any] | None = None
        cumulative_missing = 0
        cumulative_hidden = 0
        event_hole_count = 0
        last_event_sequence: int | None = None
        unrepresented_since_event = 0
        for frame_index, frame in enumerate((*trace, *measurements)):
            frame_context = f"{context} frame {frame_index}"
            if not isinstance(frame, Mapping):
                errors.append(f"{frame_context} is malformed")
                break
            metadata = frame.get("metadata")
            continuity = frame.get("continuity")
            if not isinstance(metadata, Mapping) or not isinstance(continuity, Mapping):
                errors.append(f"{frame_context} lacks metadata gap evidence")
                break
            buffer_sequence = metadata.get("buffer_sequence")
            sample_sequence = metadata.get("first_sample_sequence")
            samples_per_channel = metadata.get("samples_per_channel")
            transition_count = metadata.get("tandem_transition_count")
            events = metadata.get("gain_events")
            if (
                not exact_integer(buffer_sequence)
                or not exact_integer(sample_sequence)
                or samples_per_channel != capture_samples
                or not exact_integer(transition_count)
                or transition_count >= uint32_modulus
                or not isinstance(events, list)
            ):
                errors.append(f"{frame_context} metadata counters are malformed")
                break
            event_sequences: list[int] = []
            if any(
                not isinstance(event, Mapping)
                or not exact_integer(event.get("event_sequence"))
                or event["event_sequence"] >= uint32_modulus
                for event in events
            ):
                errors.append(f"{frame_context} event sequences are malformed")
                break
            event_sequences.extend(int(event["event_sequence"]) for event in events)
            visible = len(event_sequences)

            if previous_metadata is None:
                buffer_delta: int | None = None
                sample_delta: int | None = None
                transition_delta: int | None = None
                missing = 0
                hidden = 0
                initial_unrepresented = transition_count - visible
                if initial_unrepresented < 0:
                    errors.append(f"{frame_context} has more events than transitions")
                    break
            else:
                buffer_delta = buffer_sequence - int(
                    previous_metadata["buffer_sequence"]
                )
                sample_delta = sample_sequence - int(
                    previous_metadata["first_sample_sequence"]
                )
                if buffer_delta <= 0 or sample_delta != buffer_delta * capture_samples:
                    errors.append(f"{frame_context} frame counters disagree")
                    break
                transition_delta = (
                    transition_count - int(previous_metadata["tandem_transition_count"])
                ) % uint32_modulus
                if transition_delta >= uint32_modulus // 2:
                    errors.append(f"{frame_context} transition counter regressed")
                    break
                missing = buffer_delta - 1
                hidden = transition_delta - visible
                initial_unrepresented = 0
                if hidden < 0 or (missing == 0 and hidden != 0):
                    errors.append(f"{frame_context} hidden transitions are invalid")
                    break
                cumulative_missing += missing
                cumulative_hidden += hidden
                unrepresented_since_event += hidden

            expected_values: dict[str, int | None] = {
                "buffer_delta": buffer_delta,
                "sample_delta": sample_delta,
                "missing_frame_count": missing,
                "transition_count_delta": transition_delta,
                "visible_event_count": visible,
                "hidden_transition_count": hidden,
                "initial_unrepresented_transition_count": initial_unrepresented,
                "cumulative_missing_frame_count": cumulative_missing,
                "cumulative_hidden_transition_count": cumulative_hidden,
            }
            if any(
                (
                    continuity.get(name) is not None
                    if expected is None
                    else type(continuity.get(name)) is not int
                    or continuity.get(name) != expected
                )
                for name, expected in expected_values.items()
            ):
                errors.append(f"{frame_context} gap evidence differs from metadata")
                break

            event_error = False
            for event_sequence in event_sequences:
                if last_event_sequence is not None:
                    delta = (event_sequence - last_event_sequence) % uint32_modulus
                    if delta == 0 or delta >= uint32_modulus // 2:
                        event_error = True
                        break
                    hole = delta - 1
                    if hole != unrepresented_since_event:
                        event_error = True
                        break
                    if hole:
                        event_hole_count += 1
                unrepresented_since_event = 0
                last_event_sequence = event_sequence
            if event_error:
                errors.append(f"{frame_context} event holes do not reconcile")
                break
            if (
                type(continuity.get("cumulative_event_sequence_hole_count")) is not int
                or continuity.get("cumulative_event_sequence_hole_count")
                != event_hole_count
            ):
                errors.append(f"{frame_context} event-hole evidence is inconsistent")
                break
            previous_metadata = metadata
    return errors


def _transient_comparison_errors(modes: Any, comparison: Any) -> list[str]:
    """Reconstruct the shared summary without upgrading ordinal diagnostics."""

    if not isinstance(modes, list) or not isinstance(comparison, list):
        return ["transient comparison cannot be reconstructed"]
    if len(modes) != len(comparison):
        return ["transient comparison count differs from modes"]
    errors: list[str] = []
    quality_fields = (
        "worst_overshoot_db",
        "ringing_peak_to_peak_db",
        "minimum_post_tone_snr_db",
        "maximum_post_clipping_fraction",
        "maximum_phase_excursion_deg",
    )
    for index, (mode, reported) in enumerate(zip(modes, comparison, strict=True)):
        if not isinstance(mode, Mapping) or not isinstance(reported, Mapping):
            errors.append(f"transient comparison entry {index} is malformed")
            continue
        hardware = mode.get("mode") == MODE_TANDEM
        responses = mode.get("responses")
        try:
            summaries: dict[str, dict[str, Any]] = {}
            for direction in ("attack", "release"):
                response = responses[direction]
                summary = {
                    "timing_qualification": response["timing_qualification"],
                    "hardware_latency_qualified": hardware,
                    "transient_observation_scope": response[
                        "transient_observation_scope"
                    ],
                    **{field: response[field] for field in quality_fields},
                }
                if hardware:
                    summary.update(
                        {
                            field: response[field]
                            for field in (
                                "signal_settling_latency_lower_samples",
                                "signal_settling_latency_upper_samples",
                                "signal_settling_latency_lower_seconds",
                                "signal_settling_latency_upper_seconds",
                            )
                        }
                    )
                else:
                    summary.update(
                        {
                            "signal_settling_latency_lower_samples": None,
                            "signal_settling_latency_upper_samples": None,
                            "signal_settling_latency_lower_seconds": None,
                            "signal_settling_latency_upper_seconds": None,
                            "observed_returned_iq_settling_span_lower_axis_units": (
                                response[
                                    "observed_returned_iq_settling_span_lower_axis_units"
                                ]
                            ),
                            "observed_returned_iq_settling_span_upper_axis_units": (
                                response[
                                    "observed_returned_iq_settling_span_upper_axis_units"
                                ]
                            ),
                        }
                    )
                summaries[direction] = summary
            expected = {
                "mode": mode["mode"],
                "timing_basis": mode["timing_basis"],
                "attack": summaries["attack"],
                "release": summaries["release"],
                "gain_evidence": mode["gain_evidence"],
            }
        except (KeyError, TypeError) as error:
            errors.append(
                f"transient comparison entry {index} cannot be reconstructed: {error}"
            )
        else:
            if reported != expected:
                errors.append(
                    f"transient comparison entry {index} differs from recomputation"
                )
    return errors


def _transient_mode_boundary_errors(
    modes: Any, quality: TandemQualityOptions
) -> list[str]:
    """Bind the safe controller and RX state on both sides of every mode."""

    if not isinstance(modes, list):
        return ["transient mode boundary evidence is missing"]
    errors: list[str] = []
    for index, mode in enumerate(modes):
        if not isinstance(mode, Mapping):
            errors.append(f"transient mode {index} boundary evidence is malformed")
            continue
        context = f"transient {mode.get('mode', index)}"
        for status_name in ("tandem_status_before", "tandem_status_after"):
            status = mode.get(status_name)
            if (
                not isinstance(status, Mapping)
                or type(status.get("state")) is not int
                or status.get("state") != int(TandemState.IDLE)
                or type(status.get("fault_flags")) is not int
                or status.get("fault_flags") != 0
                or type(status.get("fifo_level")) is not int
                or status.get("fifo_level") != 0
            ):
                errors.append(f"{context} {status_name} is not safely IDLE")
        final_state = mode.get("final_rx_state")
        gains = (
            final_state.get("gains_db") if isinstance(final_state, Mapping) else None
        )
        if (
            not isinstance(final_state, Mapping)
            or set(final_state) != {"modes", "gains_db"}
            or final_state.get("modes") != ["manual", "manual"]
            or not isinstance(gains, list)
            or len(gains) != 2
            or any(
                not _release_finite_number(value)
                or abs(float(value) - quality.manual_gain_db) > 0.1
                for value in gains
            )
        ):
            errors.append(f"{context} final RX state is not restored to manual")
    return errors


def _transient_ordinary_errors(
    modes: Any,
    capture: TransientCaptureOptions,
    quality: TandemQualityOptions,
) -> list[str]:
    """Recompute returned-IQ ordinal evidence for every ordinary mode."""

    if not isinstance(modes, list):
        return ["transient ordinary modes are missing"]
    ordinary_basis = "ordinary_returned_iq_ordinal_axis"
    expected_modes = [mode for mode in TRANSIENT_MODES if mode != MODE_TANDEM]
    ordinary = [
        mode
        for mode in modes
        if isinstance(mode, Mapping) and mode.get("mode") != MODE_TANDEM
    ]
    if [mode.get("mode") for mode in ordinary] != expected_modes:
        return ["transient ordinary mode coverage differs from policy"]
    errors: list[str] = []

    def exact_integer(value: Any, *, minimum: int = 0) -> bool:
        return type(value) is int and value >= minimum

    def finite_number(value: Any) -> bool:
        return _release_finite_number(value)

    def command_rx_state_valid(
        value: Any,
        *,
        expected_mode: str,
        require_manual_gain: bool,
    ) -> bool:
        if not isinstance(value, Mapping) or set(value) != {"modes", "gains_db"}:
            return False
        gains = value.get("gains_db")
        if (
            value.get("modes") != [expected_mode, expected_mode]
            or not isinstance(gains, list)
            or len(gains) != 2
            or any(not finite_number(gain) for gain in gains)
        ):
            return False
        return not require_manual_gain or all(
            abs(float(gain) - quality.manual_gain_db) <= 0.1 for gain in gains
        )

    def command_from_report(record: Mapping[str, Any]) -> StimulusCommand:
        return StimulusCommand(
            command_id=record["command_id"],
            requested_level_db=record["requested_level_db"],
            applied_level_db=record["applied_level_db"],
            host_before_ns=record["host_before_ns"],
            host_after_ns=record["host_after_ns"],
            sample_sequence_before=record["sample_sequence_before"],
            sample_sequence_after=record["sample_sequence_after"],
        )

    def ordinal_response(value: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(value)
        lower = result.pop("signal_settling_latency_lower_samples")
        upper = result.pop("signal_settling_latency_upper_samples")
        result.pop("signal_settling_latency_lower_seconds")
        result.pop("signal_settling_latency_upper_seconds")
        result.update(
            {
                "timing_qualification": "returned_iq_observation_only",
                "hardware_latency_qualified": False,
                "transient_observation_scope": (
                    "returned_iq_windows_with_unobserved_refill_intervals"
                ),
                "observed_returned_iq_settling_span_lower_axis_units": lower,
                "observed_returned_iq_settling_span_upper_axis_units": upper,
            }
        )
        return result

    for mode in ordinary:
        mode_name = str(mode.get("mode"))
        context = f"transient {mode_name}"
        expected_iio_mode = (
            "manual" if mode_name == MODE_MANUAL else mode_name.removeprefix("native_")
        )
        if mode.get("timing_basis") != ordinary_basis:
            errors.append(f"{context} timing basis is not returned-IQ ordinal")
        if mode.get("metadata_abi") is not None:
            errors.append(f"{context} unexpectedly reports a metadata ABI")
        preconditioning = mode.get("preconditioning")
        trace = (
            preconditioning.get("trace")
            if isinstance(preconditioning, Mapping)
            else None
        )
        baseline = mode.get("baseline_frames")
        attack = mode.get("attack_frames")
        release = mode.get("release_frames")
        if not all(
            isinstance(items, list) and items
            for items in (trace, baseline, attack, release)
        ):
            errors.append(f"{context} frame evidence is missing or empty")
            continue
        assert isinstance(trace, list)
        assert isinstance(baseline, list)
        assert isinstance(attack, list)
        assert isinstance(release, list)
        if any(
            not isinstance(frame, Mapping)
            for frame in (*trace, *baseline, *attack, *release)
        ):
            errors.append(f"{context} frame evidence is malformed")
            continue
        if (
            not isinstance(preconditioning, Mapping)
            or preconditioning.get("frame_count") != len(trace)
            or not max(2, capture.precondition_stable_frames)
            <= len(trace)
            <= capture.max_precondition_frames
        ):
            errors.append(f"{context} precondition frame count is inconsistent")
        expected_baseline = trace[-capture.baseline_frames :]
        if baseline != expected_baseline:
            errors.append(f"{context} baseline is not the retained trace tail")
        if isinstance(preconditioning, Mapping) and preconditioning.get(
            "retained_baseline_frame_indices"
        ) != [frame.get("frame_index") for frame in expected_baseline]:
            errors.append(f"{context} retained baseline indices are inconsistent")
        if len(attack) != capture.response_frames or len(release) != (
            capture.response_frames
        ):
            errors.append(f"{context} response frame count differs from policy")
        if mode.get("acquisition") != {
            "threaded": False,
            "kernel_buffers": 1,
            "queue_capacity_frames": 0,
            "response_tail_frames": 0,
        }:
            errors.append(f"{context} acquisition policy is inconsistent")

        frames_by_section = (
            ("precondition", trace),
            ("attack", attack),
            ("release", release),
        )
        frame_number = 0
        previous_refill_ns: int | None = None
        frame_records_valid = True
        for section, frames in frames_by_section:
            for section_index, frame in enumerate(frames):
                assert isinstance(frame, Mapping)
                frame_context = f"{context} {section} frame {section_index}"
                expected_start = frame_number * capture.frame_samples
                expected_gap_context = (
                    "precondition_observation"
                    if section == "precondition"
                    else (
                        "command_bracket"
                        if section_index == 0
                        else "continuous_response"
                    )
                )
                if (
                    frame.get("frame_index") != frame_number
                    or frame.get("iq_bytes") != capture.frame_samples * 8
                    or not exact_integer(frame.get("refill_monotonic_ns"))
                    or frame.get("timing_basis") != ordinary_basis
                    or frame.get("first_sample_sequence") != expected_start
                    or frame.get("sample_end_exclusive")
                    != expected_start + capture.frame_samples
                    or frame.get("sample_gap_before") is not None
                    or frame.get("physical_sample_continuity_proven") is not False
                    or frame.get("gap_context") != expected_gap_context
                    or frame.get("command_boundary_gap_allowed") is not False
                    or "metadata" in frame
                    or "continuity" in frame
                    or not isinstance(frame.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", frame["sha256"]) is None
                ):
                    errors.append(f"{frame_context} ordinal ledger is inconsistent")
                    frame_records_valid = False
                refill_ns = frame.get("refill_monotonic_ns")
                if (
                    exact_integer(refill_ns)
                    and previous_refill_ns is not None
                    and refill_ns < previous_refill_ns
                ):
                    errors.append(f"{frame_context} refill ledger regressed")
                    frame_records_valid = False
                if exact_integer(refill_ns):
                    previous_refill_ns = refill_ns
                for state_name in ("rx_state_before", "rx_state_after"):
                    state = frame.get(state_name)
                    if (
                        not isinstance(state, Mapping)
                        or state.get("modes") != [expected_iio_mode, expected_iio_mode]
                        or not isinstance(state.get("gains_db"), list)
                        or len(state["gains_db"]) != 2
                        or any(not finite_number(value) for value in state["gains_db"])
                    ):
                        errors.append(f"{frame_context} RX state is inconsistent")
                        frame_records_valid = False
                analysis = frame.get("analysis")
                windows = (
                    analysis.get("windows") if isinstance(analysis, Mapping) else None
                )
                expected_windows = capture.frame_samples // capture.window_samples
                if (
                    not isinstance(analysis, Mapping)
                    or analysis.get("first_sample_sequence") != expected_start
                    or analysis.get("samples_per_channel") != capture.frame_samples
                    or analysis.get("sample_rate_hz") != quality.sample_rate_hz
                    or analysis.get("expected_tone_hz") != quality.tone_hz
                    or not finite_number(analysis.get("selected_tone_hz"))
                    or abs(float(analysis.get("selected_tone_hz", 0)))
                    != abs(quality.tone_hz)
                    or analysis.get("window_samples") != capture.window_samples
                    or analysis.get("stride_samples") != capture.window_samples
                    or analysis.get("window_count") != expected_windows
                    or analysis.get("uncovered_tail_samples") != 0
                    or not isinstance(windows, list)
                    or len(windows) != expected_windows
                ):
                    errors.append(f"{frame_context} analysis ledger is inconsistent")
                    frame_records_valid = False
                else:
                    window_quality: list[bool] = []
                    for window_index, window in enumerate(windows):
                        if not isinstance(window, Mapping):
                            errors.append(
                                f"{frame_context} analysis window is malformed"
                            )
                            frame_records_valid = False
                            break
                        snr = window.get("tone_snr_db")
                        clipping = window.get("clipping_fraction")
                        phase_std = window.get("within_window_phase_std_deg")
                        if (
                            not isinstance(snr, list)
                            or len(snr) != 2
                            or any(not finite_number(value) for value in snr)
                            or not isinstance(clipping, list)
                            or len(clipping) != 2
                            or any(not finite_number(value) for value in clipping)
                            or any(not 0 <= float(value) <= 1 for value in clipping)
                            or not finite_number(phase_std)
                            or float(phase_std) < 0
                        ):
                            errors.append(
                                f"{frame_context} analysis quality values are malformed"
                            )
                            frame_records_valid = False
                            break
                        reasons: list[str] = []
                        for channel in (0, 1):
                            if snr[channel] < quality.thresholds.min_tone_snr_db:
                                reasons.append(f"rx{channel}_tone_snr_low")
                            if (
                                clipping[channel]
                                > quality.thresholds.max_clipping_fraction
                            ):
                                reasons.append(f"rx{channel}_clipping")
                        if phase_std > quality.thresholds.max_phase_std_deg:
                            reasons.append("within_window_phase_unstable")
                        valid = not reasons
                        window_quality.append(valid)
                        if (
                            window.get("window_index") != window_index
                            or window.get("offset_start")
                            != window_index * capture.window_samples
                            or window.get("offset_end_exclusive")
                            != (window_index + 1) * capture.window_samples
                            or window.get("sample_start")
                            != expected_start + window_index * capture.window_samples
                            or window.get("sample_end_exclusive")
                            != expected_start
                            + (window_index + 1) * capture.window_samples
                            or window.get("quality_reasons") != reasons
                            or window.get("quality_valid") is not valid
                        ):
                            errors.append(
                                f"{frame_context} analysis window ledger is inconsistent"
                            )
                            frame_records_valid = False
                    if analysis.get("quality_valid") is not all(window_quality):
                        errors.append(
                            f"{frame_context} analysis quality ledger is inconsistent"
                        )
                        frame_records_valid = False
                frame_number += 1

        if frame_records_valid:
            tolerance = 0.1 if mode_name == MODE_MANUAL else 1.0
            stable_run: list[Mapping[str, Any]] = []
            for trace_index, frame in enumerate(trace):
                assert isinstance(frame, Mapping)
                candidate = [*stable_run, frame]
                stable = True
                for channel in (0, 1):
                    gains = [
                        float(item[state]["gains_db"][channel])
                        for item in candidate
                        for state in ("rx_state_before", "rx_state_after")
                    ]
                    stable &= max(gains) - min(gains) <= tolerance
                stable_run = candidate if stable else [frame]
                if frame.get("precondition_stable_run") != len(stable_run):
                    errors.append(
                        f"{context} precondition stability ledger is inconsistent"
                    )
                    break
                if (
                    trace_index < len(trace) - 1
                    and len(stable_run) >= capture.precondition_stable_frames
                ):
                    errors.append(f"{context} precondition continued after stability")
                    break
            if len(stable_run) < capture.precondition_stable_frames:
                errors.append(f"{context} precondition never established stability")

        commands = mode.get("commands")
        anchor = mode.get("conditioning_anchor")
        if (
            not isinstance(commands, list)
            or len(commands) != 3
            or any(not isinstance(command, Mapping) for command in commands)
            or not isinstance(anchor, Mapping)
        ):
            errors.append(f"{context} commands are missing or malformed")
            continue
        assert all(isinstance(command, Mapping) for command in commands)
        initial, attack_command_record, release_command_record = commands
        command_records_valid = True
        expected_command_ids = ("weak_initial", "strong_attack", "weak_release")
        if tuple(command.get("command_id") for command in commands) != (
            expected_command_ids
        ):
            errors.append(f"{context} command order differs from policy")
            command_records_valid = False
        expected_levels = (
            capture.weak_stimulus_tx_gain_db,
            capture.strong_stimulus_tx_gain_db,
            capture.weak_stimulus_tx_gain_db,
        )
        for command, expected_level in zip(commands, expected_levels, strict=True):
            before = command.get("host_before_ns")
            after = command.get("host_after_ns")
            applied = command.get("applied_level_db")
            effective = (
                quality.physical_attenuation_db - float(applied)
                if finite_number(applied)
                else None
            )
            if (
                not exact_integer(before)
                or not exact_integer(after)
                or not before <= after
                or command.get("host_jitter_ns") != after - before
                or after - before > capture.max_host_jitter_ns
                or not finite_number(command.get("requested_level_db"))
                or float(command["requested_level_db"]) != expected_level
                or not finite_number(applied)
                or abs(float(applied) - expected_level) > capture.readback_tolerance_db
                or command.get("effective_attenuation_db") != effective
            ):
                errors.append(f"{context} command write ledger is inconsistent")
                command_records_valid = False
            if effective is not None and effective < 30.0:
                errors.append(
                    f"{context} command violates the 30 dB effective-attenuation "
                    "boundary"
                )
        for command_index, command in enumerate(commands):
            command_expected_mode = (
                "manual" if command_index == 0 else expected_iio_mode
            )
            require_manual_gain = command_expected_mode == "manual"
            for state_name in ("rx_state_before", "rx_state_after"):
                if not command_rx_state_valid(
                    command.get(state_name),
                    expected_mode=command_expected_mode,
                    require_manual_gain=require_manual_gain,
                ):
                    errors.append(
                        f"{context} {command.get('command_id', command_index)} "
                        f"{state_name} does not prove the required RX state"
                    )
                    command_records_valid = False
        attack_lower = baseline[-1].get("sample_end_exclusive")
        attack_upper = attack[0].get("sample_end_exclusive")
        release_lower = attack[-1].get("sample_end_exclusive")
        release_upper = release[0].get("sample_end_exclusive")
        command_bounds = (
            (attack_command_record, attack_lower, attack_upper),
            (release_command_record, release_lower, release_upper),
        )
        bounds_valid = all(
            exact_integer(lower) and exact_integer(upper, minimum=1)
            for _command, lower, upper in command_bounds
        )
        if not bounds_valid or (
            initial.get("sample_sequence_before") is not None
            or initial.get("sample_sequence_after") is not None
            or initial.get("sample_uncertainty") is not None
            or initial.get("timing_role") != "pre_session_conditioning_write"
            or initial.get("sample_timing_basis") is not None
            or initial.get("sample_anchor_policy")
            != "unbounded in sample time; the write predates the open capture session"
            or any(
                command.get("sample_sequence_before") != lower
                or command.get("sample_sequence_after") != upper
                or command.get("sample_uncertainty") != upper - lower
                or not 0 < upper - lower <= capture.max_sample_uncertainty
                or command.get("timing_role")
                != "host_write_positioned_on_returned_iq_ordinal_axis"
                or command.get("sample_timing_basis") != ordinary_basis
                or command.get("sample_anchor_policy")
                != "last returned pre-command IQ ordinal through end of first "
                "returned post-command frame; unobserved hardware intervals excluded"
                or "sample_counter_bracket" in command
                for command, lower, upper in command_bounds
            )
        ):
            errors.append(f"{context} command ordinal bracket is inconsistent")
            command_records_valid = False
        anchor_lower = baseline[0].get("first_sample_sequence")
        anchor_upper = baseline[-1].get("sample_end_exclusive")
        if (
            not exact_integer(anchor_lower)
            or not exact_integer(anchor_upper, minimum=1)
            or anchor.get("command_id") != "weak_conditioning_anchor"
            or anchor.get("requested_level_db") != initial.get("requested_level_db")
            or anchor.get("applied_level_db") != initial.get("applied_level_db")
            or anchor.get("host_before_ns") != initial.get("host_before_ns")
            or anchor.get("host_after_ns") != initial.get("host_after_ns")
            or anchor.get("host_jitter_ns") != initial.get("host_jitter_ns")
            or anchor.get("sample_sequence_before") != anchor_lower
            or anchor.get("sample_sequence_after") != anchor_upper
            or anchor.get("sample_uncertainty") != anchor_upper - anchor_lower
            or anchor.get("timing_role") != "observed_stable_conditioning_interval"
            or anchor.get("sample_timing_basis") != ordinary_basis
            or anchor.get("sample_anchor_policy")
            != "retained stable baseline interval; not the initial write time"
        ):
            errors.append(f"{context} conditioning anchor is inconsistent")
            command_records_valid = False

        if not frame_records_valid or not command_records_valid:
            continue
        for frames, command in (
            (baseline, None),
            (attack, attack_command_record),
            (release, release_command_record),
        ):
            for frame in frames:
                for window in frame["analysis"]["windows"]:
                    lower = (
                        command.get("sample_sequence_before")
                        if command is not None
                        else None
                    )
                    upper = (
                        command.get("sample_sequence_after")
                        if command is not None
                        else None
                    )
                    intersects = bool(
                        command is not None
                        and type(lower) is int
                        and type(upper) is int
                        and window["sample_start"] < upper
                        and window["sample_end_exclusive"] > lower
                    )
                    if not intersects and window.get("quality_valid") is not True:
                        errors.append(
                            f"{context} has a quality-invalid returned-IQ window "
                            "outside a command interval"
                        )
                        break

        responses = mode.get("responses")
        try:
            anchor_command = command_from_report(anchor)
            attack_command = command_from_report(attack_command_record)
            release_command = command_from_report(release_command_record)
            response_kwargs = {
                "sample_rate_hz": quality.sample_rate_hz,
                "baseline_windows": capture.baseline_windows,
                "steady_windows": capture.steady_windows,
                "stable_windows": capture.stable_windows,
                "settling_tolerance_db": capture.settling_tolerance_db,
                "ringing_deadband_db": capture.ringing_deadband_db,
                "max_host_jitter_ns": capture.max_host_jitter_ns,
                "max_sample_uncertainty": capture.max_sample_uncertainty,
            }
            attack_windows = [
                window
                for frame in (*baseline, *attack)
                for window in frame["analysis"]["windows"]
            ]
            release_windows = [
                window
                for frame in (*attack, *release)
                for window in frame["analysis"]["windows"]
            ]
            recomputed_responses = {
                "attack": ordinal_response(
                    calculate_transient_response(
                        attack_windows,
                        previous_command=anchor_command,
                        command=attack_command,
                        **response_kwargs,
                    )
                ),
                "release": ordinal_response(
                    calculate_transient_response(
                        release_windows,
                        previous_command=attack_command,
                        command=release_command,
                        **response_kwargs,
                    )
                ),
            }
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{context} responses cannot be recomputed: {error}")
        else:
            if responses != _json_safe(recomputed_responses):
                errors.append(f"{context} responses differ from recomputation")

        gain = mode.get("gain_evidence")
        if mode_name == MODE_MANUAL:
            gain_values: list[list[float]] = [[], []]
            for frame in (*baseline, *attack, *release):
                for state_name in ("rx_state_before", "rx_state_after"):
                    for channel in (0, 1):
                        gain_values[channel].append(
                            float(frame[state_name]["gains_db"][channel])
                        )
            expected_gain = {
                "evidence_valid": True,
                "timing_qualification": "not_applicable_fixed_gain",
                "hardware_latency_qualified": False,
                "expected_gain_db": quality.manual_gain_db,
                "gain_span_db": [max(values) - min(values) for values in gain_values],
                "maximum_readback_error_db": [
                    max(abs(value - quality.manual_gain_db) for value in values)
                    for values in gain_values
                ],
            }
            if any(value > 0.1 for value in expected_gain["gain_span_db"]) or any(
                value > 0.1 for value in expected_gain["maximum_readback_error_db"]
            ):
                errors.append(f"{context} manual RX gain moved outside policy")
        else:

            def gain_at_end(frames: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
                selected = frames[-min(3, len(frames)) :]
                return tuple(
                    float(
                        statistics.median(
                            float(frame["rx_state_after"]["gains_db"][channel])
                            for frame in selected
                        )
                    )
                    for channel in (0, 1)
                )  # type: ignore[return-value]

            weak = gain_at_end(baseline)
            strong = gain_at_end(attack)
            returned = gain_at_end(release)

            def gain_bounds(
                frames: Sequence[Mapping[str, Any]],
                *,
                command: StimulusCommand,
                reference: tuple[float, float],
                sign: int,
            ) -> list[dict[str, Any]]:
                assert command.sample_sequence_before is not None
                assert command.sample_sequence_after is not None
                results = []
                for channel in (0, 1):
                    found = None
                    for frame in frames:
                        before_gain = float(
                            frame["rx_state_before"]["gains_db"][channel]
                        )
                        after_gain = float(frame["rx_state_after"]["gains_db"][channel])
                        evidence = None
                        observed = 0.0
                        if sign * (before_gain - reference[channel]) >= (
                            capture.minimum_native_gain_change_db
                        ):
                            evidence = "pre_refill_readback"
                            observed = before_gain
                        elif sign * (after_gain - reference[channel]) >= (
                            capture.minimum_native_gain_change_db
                        ):
                            evidence = "post_refill_readback"
                            observed = after_gain
                        if evidence is not None:
                            found = {
                                "rx_channel": channel,
                                "evidence": evidence,
                                "observed_gain_db": observed,
                                "returned_iq_observation_span_lower_axis_units": max(
                                    0,
                                    int(frame["first_sample_sequence"])
                                    - command.sample_sequence_after,
                                ),
                                "returned_iq_observation_span_upper_axis_units": max(
                                    0,
                                    int(frame["sample_end_exclusive"])
                                    - command.sample_sequence_before,
                                ),
                                "hardware_latency_qualified": False,
                            }
                            break
                    if found is None:
                        raise ValueError("native gain change is not represented")
                    results.append(found)
                return results

            try:
                attack_bounds = gain_bounds(
                    attack,
                    command=attack_command,
                    reference=weak,
                    sign=-1,
                )
                release_bounds = gain_bounds(
                    release,
                    command=release_command,
                    reference=strong,
                    sign=1,
                )
            except ValueError as error:
                errors.append(f"{context} gain evidence cannot be recomputed: {error}")
                continue
            expected_gain = {
                "evidence_valid": True,
                "timing_qualification": "returned_iq_observation_only",
                "hardware_latency_qualified": False,
                "minimum_required_change_db": capture.minimum_native_gain_change_db,
                "weak_gain_db": list(weak),
                "strong_gain_db": list(strong),
                "returned_weak_gain_db": list(returned),
                "attack_gain_change_db": [
                    strong[index] - weak[index] for index in (0, 1)
                ],
                "release_gain_change_db": [
                    returned[index] - strong[index] for index in (0, 1)
                ],
                "attack_returned_iq_observation_bounds": attack_bounds,
                "release_returned_iq_observation_bounds": release_bounds,
            }
        if gain != expected_gain:
            errors.append(f"{context} gain evidence differs from recomputation")
    return errors


def _release_exact_int(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _release_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _release_json_identical(value: Any, expected: Any) -> bool:
    """Compare JSON evidence without Python's bool/int/float equality aliases."""

    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(
            _release_json_identical(value[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _release_json_identical(item, expected_item)
            for item, expected_item in zip(value, expected, strict=True)
        )
    return value == expected


def _release_extend_low32_near(raw: int, *, reference: int) -> int:
    """Extend one low32 sample counter to the unambiguous value near reference."""

    modulus = 1 << 32
    candidate = (reference & ~(modulus - 1)) | raw
    choices = (candidate - modulus, candidate, candidate + modulus)
    result = min(choices, key=lambda item: abs(item - reference))
    if result < 0 or result >= 1 << 64 or abs(result - reference) >= modulus // 2:
        raise ValueError("low32 sample counter is ambiguous around the batch")
    return result


def _tandem_batch_memory_values() -> dict[str, int]:
    iq_frame_bytes = _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
    cache_bytes = _TANDEM_BATCH_FRAMES * (
        iq_frame_bytes
        + _TANDEM_BATCH_METADATA_CAPACITY_BYTES
        + 2 * _TANDEM_BATCH_SIZE_T_BYTES
    )
    python_raw_bytes = _TANDEM_BATCH_FRAMES * iq_frame_bytes
    python_raw_metadata_bytes = (
        _TANDEM_BATCH_FRAMES * _TANDEM_BATCH_METADATA_CAPACITY_BYTES
    )
    aggregate_bytes = sum(
        (
            cache_bytes,
            iq_frame_bytes,
            python_raw_bytes,
            iq_frame_bytes,
            _TANDEM_BATCH_METADATA_CAPACITY_BYTES,
            _TANDEM_BATCH_METADATA_CAPACITY_BYTES,
            _TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES,
            python_raw_metadata_bytes,
            _TANDEM_BATCH_KERNEL_BUFFERS * iq_frame_bytes,
        )
    )
    post_close_materialization_bytes = sum(
        (
            python_raw_bytes,
            python_raw_metadata_bytes,
            _TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES,
            _TANDEM_BATCH_POST_CLOSE_FFT_WORKSPACE_BYTES,
        )
    )
    return {
        "iq_frame_bytes": iq_frame_bytes,
        "batch_cache_bytes": cache_bytes,
        "maximum_python_raw_bytes": python_raw_bytes,
        "maximum_python_raw_metadata_bytes": python_raw_metadata_bytes,
        "post_close_fft_workspace_bytes": (
            _TANDEM_BATCH_POST_CLOSE_FFT_WORKSPACE_BYTES
        ),
        "capture_phase_envelope_bytes": aggregate_bytes,
        "post_close_materialization_envelope_bytes": (post_close_materialization_bytes),
        "maximum_phase_envelope_bytes": max(
            aggregate_bytes, post_close_materialization_bytes
        ),
        "aggregate_resident_bytes": aggregate_bytes,
    }


def _release_recursive_evidence_bytes(value: Any) -> int:
    """Measure one decoded evidence graph without double-counting shared objects."""

    seen: set[int] = set()

    def measure(item: Any) -> int:
        identity = id(item)
        if identity in seen:
            return 0
        seen.add(identity)
        total = sys.getsizeof(item)
        if isinstance(item, Mapping):
            return total + sum(
                measure(key) + measure(child) for key, child in item.items()
            )
        if isinstance(item, (list, tuple, set, frozenset)):
            return total + sum(measure(child) for child in item)
        if is_dataclass(item) and not isinstance(item, type):
            return total + sum(
                measure(getattr(item, field.name)) for field in dataclass_fields(item)
            )
        return total

    return measure(value)


def _release_canonical_tandem_evidence_bytes(
    mode: Mapping[str, Any], parsed_metadata: Sequence[Any]
) -> bytes:
    """Independently encode the alias-free retained-evidence projection."""

    mode_projection = dict(mode)
    acquisition_value = mode.get("acquisition")
    if not isinstance(acquisition_value, Mapping):
        raise TypeError("tandem canonical projection lacks acquisition evidence")
    acquisition_projection = dict(acquisition_value)
    ledger_value = acquisition_value.get("memory_ledger")
    if not isinstance(ledger_value, Mapping):
        raise TypeError("tandem canonical projection lacks its memory ledger")
    ledger_projection = dict(ledger_value)
    ledger_projection.update(
        {
            "measured_finished_mode_and_parsed_metadata_bytes": 0,
            "measured_evidence_within_reservation": True,
            "canonical_evidence_projection_bytes": 0,
            "canonical_evidence_projection_sha256": "0" * 64,
        }
    )
    acquisition_projection["memory_ledger"] = ledger_projection
    mode_projection["acquisition"] = acquisition_projection
    projection = {
        "schema": _TANDEM_BATCH_EVIDENCE_PROJECTION_SCHEMA,
        "mode": mode_projection,
        "reparsed_metadata": [
            _release_tandem_metadata_dict(metadata) for metadata in parsed_metadata
        ],
    }
    return json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _tandem_batch_partition(
    frames: Sequence[Mapping[str, Any]],
    *,
    attack_lower: int,
    attack_upper: int,
    release_lower: int,
    release_upper: int,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    phases: list[str] = []
    groups: dict[str, dict[str, Any]] = {
        name: {"count": 0, "frame_indices": []} for name in _TANDEM_BATCH_PHASE_ORDER
    }
    for index, frame in enumerate(frames):
        start = frame.get("first_sample_sequence")
        end = frame.get("sample_end_exclusive")
        if not _release_exact_int(start) or not _release_exact_int(end, minimum=1):
            raise ValueError(f"batch frame {index} has malformed sample bounds")
        if start >= end:
            raise ValueError(f"batch frame {index} has an empty sample range")
        if end <= attack_lower:
            phase = "fully_pre_attack"
        elif start < attack_upper:
            phase = "attack_bracket"
        elif end <= release_lower:
            phase = "fully_post_attack_pre_release"
        elif start < release_upper:
            phase = "release_bracket"
        else:
            phase = "fully_post_release"
        phases.append(phase)
        groups[phase]["frame_indices"].append(index)
        groups[phase]["count"] += 1
    return phases, groups


def _tandem_batch_stable_suffix(
    frames: Sequence[Mapping[str, Any]],
    frame_indices: Sequence[int],
    *,
    tolerance_db: float,
) -> dict[str, Any]:
    """Recompute one exact event/endpoint/RF-stable eight-frame suffix."""

    selected_indices = list(frame_indices[-_TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:])
    if len(selected_indices) != _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:
        raise ValueError("stable partition suffix does not contain eight frames")
    selected = [frames[index] for index in selected_indices]
    metadata = [frame.get("metadata") for frame in selected]
    analyses = [frame.get("analysis") for frame in selected]
    if any(not isinstance(item, Mapping) for item in (*metadata, *analyses)):
        raise ValueError("stable partition suffix has malformed evidence")
    typed_metadata = [item for item in metadata if isinstance(item, Mapping)]
    typed_analyses = [item for item in analyses if isinstance(item, Mapping)]
    transition_counts = {item.get("tandem_transition_count") for item in typed_metadata}
    endpoints = {tuple(item.get("bench_gain_indices", [])) for item in typed_metadata}
    events = [
        event
        for item in typed_metadata
        for event in (
            item.get("gain_events")
            if isinstance(item.get("gain_events"), list)
            else [None]
        )
    ]
    windows_by_frame = [analysis.get("windows") for analysis in typed_analyses]
    if (
        len(transition_counts) != 1
        or any(not _release_exact_int(value) for value in transition_counts)
        or len(endpoints) != 1
        or any(
            len(endpoint) != 2
            or endpoint[0] != endpoint[1]
            or any(not _release_exact_int(value) for value in endpoint)
            for endpoint in endpoints
        )
        or events
        or any(
            not isinstance(windows, list) or not windows for windows in windows_by_frame
        )
    ):
        raise ValueError("stable partition suffix is not event/endpoint stable")
    typed_windows = [
        windows for windows in windows_by_frame if isinstance(windows, list)
    ]
    if any(
        not isinstance(window, Mapping) or window.get("quality_valid") is not True
        for windows in typed_windows
        for window in windows
    ):
        raise ValueError("stable partition suffix has invalid RF windows")
    if any(
        not isinstance(window.get("tone_dbfs"), list)
        or len(window["tone_dbfs"]) != 2
        or any(not _release_finite_number(value) for value in window["tone_dbfs"])
        for windows in typed_windows
        for window in windows
    ):
        raise ValueError("stable partition suffix RF values are malformed")
    try:
        frame_channel_medians = [
            [
                float(
                    statistics.median(
                        float(window["tone_dbfs"][channel]) for window in windows
                    )
                )
                for channel in (0, 1)
            ]
            for windows in typed_windows
        ]
    except (
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        statistics.StatisticsError,
    ) as error:
        raise ValueError("stable partition suffix RF values are malformed") from error
    all_windows = [window for windows in typed_windows for window in windows]
    suffix_channel_medians = [
        float(
            statistics.median(
                float(window["tone_dbfs"][channel]) for window in all_windows
            )
        )
        for channel in (0, 1)
    ]
    maximum_deviations = [
        max(
            abs(row[channel] - suffix_channel_medians[channel])
            for row in frame_channel_medians
        )
        for channel in (0, 1)
    ]
    maximum_window_deviations = [
        max(
            abs(float(window["tone_dbfs"][channel]) - suffix_channel_medians[channel])
            for window in all_windows
        )
        for channel in (0, 1)
    ]
    if any(value > tolerance_db for value in maximum_window_deviations):
        raise ValueError("stable partition suffix exceeds its RF tolerance")
    endpoint = next(iter(endpoints))
    return {
        "frame_indices": selected_indices,
        "required_frame_count": _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES,
        "transition_count": next(iter(transition_counts)),
        "bench_gain_indices": list(endpoint),
        "event_count": 0,
        "rf_window_count": sum(len(windows) for windows in typed_windows),
        "rf_quality_valid": True,
        "frame_channel_median_tone_dbfs": frame_channel_medians,
        "suffix_channel_median_tone_dbfs": suffix_channel_medians,
        "maximum_frame_median_deviation_db": maximum_deviations,
        "maximum_frame_median_deviation_limit_db": tolerance_db,
        "maximum_window_deviation_db": maximum_window_deviations,
        "maximum_window_deviation_limit_db": tolerance_db,
    }


def _tandem_batch_rf_quality_policy(
    frames: Sequence[Mapping[str, Any]],
    stable_suffixes: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently replay the transient steady-suffix RF policy."""

    phases = (
        "fully_pre_attack",
        "fully_post_attack_pre_release",
        "fully_post_release",
    )
    stable_indices: list[int] = []
    for phase in phases:
        suffix = stable_suffixes.get(phase)
        indices = suffix.get("frame_indices") if isinstance(suffix, Mapping) else None
        if (
            not isinstance(indices, list)
            or len(indices) != _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES
            or any(not _release_exact_int(index) for index in indices)
        ):
            raise ValueError(f"{phase} RF suffix evidence is malformed")
        stable_indices.extend(indices)
    if len(set(stable_indices)) != len(stable_indices) or any(
        index < 0 or index >= len(frames) for index in stable_indices
    ):
        raise ValueError("RF suffix frame inventory is invalid")

    strict_indices = set(stable_indices)
    diagnostic_indices = [
        index for index in range(len(frames)) if index not in strict_indices
    ]
    diagnostic_invalid_window_count = 0
    diagnostic_reason_counts: dict[str, int] = {}
    for index, frame in enumerate(frames):
        analysis = frame.get("analysis")
        windows = analysis.get("windows") if isinstance(analysis, Mapping) else None
        if not isinstance(windows, list) or not windows:
            raise ValueError("RF policy encountered malformed analysis")
        for window in windows:
            if not isinstance(window, Mapping):
                raise ValueError("RF policy encountered malformed window")
            valid = window.get("quality_valid") is True
            if index in strict_indices and not valid:
                raise ValueError("stable RF suffix contains an invalid window")
            if index in strict_indices or valid:
                continue
            reasons = window.get("quality_reasons")
            if not isinstance(reasons, list) or not all(
                isinstance(reason, str) and reason for reason in reasons
            ):
                raise ValueError("diagnostic RF window has malformed quality reasons")
            diagnostic_invalid_window_count += 1
            for reason in reasons:
                diagnostic_reason_counts[reason] = (
                    diagnostic_reason_counts.get(reason, 0) + 1
                )
    return {
        "policy": (
            "strict RF quality is required only in each exact event-free "
            "eight-frame steady suffix; conditioning and commanded-response "
            "windows are retained diagnostic evidence and cannot authorize PASS"
        ),
        "strict_phase_order": list(phases),
        "strict_frame_indices": stable_indices,
        "strict_frame_count": len(stable_indices),
        "strict_window_quality_valid": True,
        "diagnostic_frame_indices": diagnostic_indices,
        "diagnostic_frame_count": len(diagnostic_indices),
        "diagnostic_invalid_window_count": diagnostic_invalid_window_count,
        "diagnostic_quality_reason_counts": dict(
            sorted(diagnostic_reason_counts.items())
        ),
        "diagnostic_windows_authorize_pass": False,
    }


def _tandem_batch_pre_attack_conditioning(
    frames: Sequence[Mapping[str, Any]],
    frame_indices: Sequence[int],
) -> dict[str, Any]:
    """Recompute the exact startup-conditioning and quiet-suffix ledger."""

    pre_indices = list(frame_indices)
    quiet_indices = pre_indices[-_TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:]
    startup_indices = pre_indices[:-_TANDEM_BATCH_MINIMUM_PARTITION_FRAMES]
    if len(quiet_indices) != _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:
        raise ValueError("pre-attack conditioning lacks eight quiet frames")
    quiet_metadata: list[Mapping[str, Any]] = []
    for index in quiet_indices:
        frame = frames[index]
        metadata = frame.get("metadata")
        continuity = frame.get("continuity")
        if not isinstance(metadata, Mapping) or not isinstance(continuity, Mapping):
            raise TypeError("pre-attack quiet suffix lacks metadata continuity")
        if (
            metadata.get("gain_events") != []
            or continuity.get("buffer_delta") != 1
            or continuity.get("sample_delta") != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            or continuity.get("missing_frame_count") != 0
            or continuity.get("provider_gap_accepted") is not False
            or continuity.get("transition_count_delta") != 0
            or continuity.get("visible_event_count") != 0
            or continuity.get("hidden_transition_count") != 0
            or continuity.get("initial_unrepresented_transition_count") != 0
        ):
            raise ValueError("pre-attack quiet suffix contains a transition or gap")
        quiet_metadata.append(metadata)
    transition_counts = {
        metadata.get("tandem_transition_count") for metadata in quiet_metadata
    }
    endpoints = {
        tuple(metadata.get("bench_gain_indices", [])) for metadata in quiet_metadata
    }
    if (
        len(transition_counts) != 1
        or any(not _release_exact_int(value) for value in transition_counts)
        or len(endpoints) != 1
        or any(
            len(endpoint) != 2
            or endpoint[0] != endpoint[1]
            or any(not _release_exact_int(value) for value in endpoint)
            for endpoint in endpoints
        )
    ):
        raise ValueError("pre-attack quiet suffix changed endpoint or count")
    first_continuity = frames[pre_indices[0]].get("continuity")
    if not isinstance(first_continuity, Mapping):
        raise TypeError("pre-attack first frame lacks continuity")
    initial_unrepresented = first_continuity.get(
        "initial_unrepresented_transition_count"
    )
    if not _release_exact_int(initial_unrepresented):
        raise ValueError("pre-attack startup count is malformed")
    visible_events = 0
    for index in pre_indices:
        metadata = frames[index].get("metadata")
        events = metadata.get("gain_events") if isinstance(metadata, Mapping) else None
        if not isinstance(events, list):
            raise TypeError("pre-attack startup events are malformed")
        visible_events += len(events)
    transition_count = next(iter(transition_counts))
    if transition_count != initial_unrepresented + visible_events:
        raise ValueError("pre-attack startup transition ledger is inconsistent")
    endpoint = next(iter(endpoints))
    return {
        "policy": (
            "retain every fully-pre-attack frame as conditioning; use only the "
            "final contiguous event-free eight-frame suffix as the response anchor"
        ),
        "startup_prefix_frame_indices": startup_indices,
        "startup_prefix_frame_count": len(startup_indices),
        "quiet_suffix_frame_indices": quiet_indices,
        "quiet_suffix_frame_count": len(quiet_indices),
        "startup_initial_unrepresented_transition_count": initial_unrepresented,
        "startup_visible_event_count": visible_events,
        "startup_transition_count": transition_count,
        "quiet_suffix_transition_count": transition_count,
        "quiet_suffix_bench_gain_indices": [endpoint[0], endpoint[1]],
        "startup_is_conditioning_only": True,
        "startup_is_response_direction_proof": False,
    }


def _transient_batch_schedule_errors(
    value: Any,
    command: Mapping[str, Any],
    *,
    command_id: str,
    requested_level_db: float,
    target_frames: int,
    s0_raw: int,
    first_batch_sample: int,
    last_batch_sample_exclusive: int,
    initiating_refill_completion_ns: int,
    capture: TransientCaptureOptions,
) -> tuple[list[str], tuple[int, int] | None]:
    """Recompute one S0-relative one-write A→initial→B→C schedule."""

    context = f"transient tandem {command_id}"
    if not isinstance(value, Mapping):
        return [f"{context} schedule diagnostics are missing"], None
    errors: list[str] = []
    expected_fields = {
        "status",
        "qualified",
        "current_stage",
        "failure_stage",
        "failure_error",
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "target",
        "worker_in_flight_observations",
        "tx1_mute_assurance",
        "write_ack",
        "counter_reads",
        "raw_bracket",
        "deferred_tx2_readback",
    }
    if set(value) != expected_fields:
        errors.append(f"{context} schedule diagnostic fields changed")
    if (
        value.get("status") != "complete"
        or value.get("qualified") is not True
        or value.get("current_stage") != "complete"
        or value.get("failure_stage") is not None
        or value.get("failure_error") is not None
        or value.get("command_id") != command_id
        or value.get("requested_level_db") != requested_level_db
    ):
        errors.append(f"{context} schedule is not exactly qualified")

    worker = value.get("worker_in_flight_observations")
    if not isinstance(worker, list) or worker != [
        {
            "stage": "pre_tx1_mute_assurance",
            "first_refill_in_flight": True,
        },
        {"stage": "exact_tx2_write", "first_refill_in_flight": True},
    ]:
        errors.append(f"{context} was not issued during the initiating refill")

    target = value.get("target")
    if not isinstance(target, Mapping):
        return [*errors, f"{context} frozen target is missing"], None
    target_samples = target_frames * _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
    target_raw = (s0_raw + target_samples) % (1 << 32)
    raw_p = target.get("last_below_raw")
    raw_a = target.get("raw_a_prewrite")
    poll_count = target.get("poll_read_count")
    polls = target.get("poll_observations")
    if (
        set(target)
        != {
            "s0_raw",
            "offset_frames",
            "offset_samples",
            "target_raw",
            "last_below_raw",
            "raw_a_prewrite",
            "poll_read_count",
            "poll_observations",
            "total_requested_sleep_samples",
            "overshoot_samples",
            "overshoot_limit_samples",
        }
        or target.get("s0_raw") != s0_raw
        or target.get("offset_frames") != target_frames
        or target.get("offset_samples") != target_samples
        or target.get("target_raw") != target_raw
        or not _release_exact_int(raw_p)
        or raw_p >= 1 << 32
        or not _release_exact_int(raw_a)
        or raw_a >= 1 << 32
        or not _release_exact_int(poll_count, minimum=2)
        or poll_count > 64
        or not isinstance(polls, list)
        or len(polls) != poll_count
        or any(not isinstance(observation, Mapping) for observation in polls)
        or target.get("overshoot_limit_samples")
        != _TANDEM_BATCH_MAX_TARGET_OVERSHOOT_SAMPLES
    ):
        errors.append(f"{context} frozen target ledger is inconsistent")
        return errors, None

    prior_advance = -1
    expected_total_sleep = 0
    for index, observation in enumerate(polls):
        if not isinstance(observation, Mapping) or set(observation) != {
            "raw",
            "advance_samples",
            "remaining_samples",
            "phase",
            "requested_sleep_samples",
        }:
            errors.append(f"{context} target poll {index} is malformed")
            continue
        raw = observation.get("raw")
        advance = observation.get("advance_samples")
        remaining = observation.get("remaining_samples")
        sleep_samples = observation.get("requested_sleep_samples")
        if (
            not _release_exact_int(raw)
            or raw >= 1 << 32
            or not _release_exact_int(advance)
            or advance >= 1 << 31
            or raw != (s0_raw + advance) % (1 << 32)
            or advance < prior_advance
            or not _release_exact_int(remaining)
            or not _release_exact_int(sleep_samples)
        ):
            errors.append(f"{context} target poll {index} counter is inconsistent")
            continue
        prior_advance = advance
        if index == len(polls) - 1:
            expected_remaining = 0
            expected_phase = "target_reached"
            expected_sleep = 0
            if raw != raw_a or advance < target_samples:
                errors.append(f"{context} target poll does not terminate at A")
        else:
            expected_remaining = target_samples - advance
            if expected_remaining <= 0:
                errors.append(f"{context} reached its target before the final poll")
                continue
            if expected_remaining > _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES:
                expected_phase = "coarse_sleep"
                expected_sleep = (
                    expected_remaining - _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
                )
            elif expected_remaining > 2 * 4_096:
                expected_phase = "fine_sleep"
                expected_sleep = 4_096
            else:
                expected_phase = "tail_poll"
                expected_sleep = 0
            expected_total_sleep += expected_sleep
        if (
            remaining != expected_remaining
            or observation.get("phase") != expected_phase
            or sleep_samples != expected_sleep
        ):
            errors.append(f"{context} target poll {index} pacing is inconsistent")
    if (
        polls[-2].get("raw") != raw_p
        or target.get("total_requested_sleep_samples") != expected_total_sleep
    ):
        errors.append(f"{context} last-below or sleep ledger is inconsistent")

    raw_bracket = value.get("raw_bracket")
    if not isinstance(raw_bracket, Mapping):
        return [*errors, f"{context} raw command bracket is missing"], None
    raw_initial = raw_bracket.get("raw_post_write_initial")
    raw_b = raw_bracket.get("raw_b_first_advance")
    raw_c = raw_bracket.get("raw_c_causal_advance")
    if (
        set(raw_bracket)
        != {
            "register_address",
            "counter_width_bits",
            "counter_source",
            "raw_a_prewrite",
            "raw_post_write_initial",
            "raw_b_first_advance",
            "raw_c_causal_advance",
            "initial_from_a_samples",
            "b_from_initial_samples",
            "c_from_b_samples",
            "post_write_read_count",
            "causal_uncertainty_samples",
            "causal_uncertainty_limit_samples",
            "worker_in_flight_at_command",
        }
        or raw_bracket.get("register_address") != "0x800000b8"
        or raw_bracket.get("counter_width_bits") != 32
        or raw_bracket.get("counter_source")
        != "coherent FPGA RX sample counter low word"
        or raw_bracket.get("raw_a_prewrite") != raw_a
        or any(
            not _release_exact_int(item) or item >= 1 << 32
            for item in (raw_initial, raw_b, raw_c)
        )
        or raw_bracket.get("worker_in_flight_at_command") is not True
        or raw_bracket.get("causal_uncertainty_limit_samples")
        != _TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES
    ):
        errors.append(f"{context} A-to-initial-to-B-to-C ledger is malformed")
        return errors, None
    initial_delta = (raw_initial - raw_a) % (1 << 32)
    b_delta = (raw_b - raw_initial) % (1 << 32)
    c_delta = (raw_c - raw_b) % (1 << 32)
    uncertainty = initial_delta + b_delta + c_delta
    if (
        initial_delta >= 1 << 31
        or not 0 < b_delta < 1 << 31
        or not 0 < c_delta < 1 << 31
        or raw_bracket.get("initial_from_a_samples") != initial_delta
        or raw_bracket.get("b_from_initial_samples") != b_delta
        or raw_bracket.get("c_from_b_samples") != c_delta
        or raw_bracket.get("causal_uncertainty_samples") != uncertainty
        or not 0 < uncertainty <= _TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES
        or not _release_exact_int(raw_bracket.get("post_write_read_count"), minimum=3)
        or raw_bracket.get("post_write_read_count") > 9
    ):
        errors.append(f"{context} causal command bracket is inconsistent")

    overshoot = ((raw_a - s0_raw) % (1 << 32)) - target_samples
    if (
        not 0 <= overshoot <= _TANDEM_BATCH_MAX_TARGET_OVERSHOOT_SAMPLES
        or target.get("overshoot_samples") != overshoot
    ):
        errors.append(f"{context} target overshoot is inconsistent")
    try:
        s0 = _release_extend_low32_near(s0_raw, reference=first_batch_sample)
    except ValueError as error:
        errors.append(f"{context} cannot extend S0: {error}")
        return errors, None
    target_sample = s0 + target_samples
    extended_a = s0 + (raw_a - s0_raw) % (1 << 32)
    extended_p = s0 + (raw_p - s0_raw) % (1 << 32)
    extended_initial = extended_a + initial_delta
    extended_b = extended_initial + b_delta
    extended_c = extended_a + uncertainty
    if (
        not first_batch_sample <= target_sample < last_batch_sample_exclusive
        or not target_sample <= extended_a < extended_c <= last_batch_sample_exclusive
        or command.get("sample_sequence_before") != extended_a
        or command.get("sample_sequence_after") != extended_c
        or command.get("sample_uncertainty") != uncertainty
    ):
        errors.append(f"{context} bound sample interval differs from its raw schedule")

    bound_bracket = command.get("sample_counter_bracket")
    expected_bound_bracket = {
        "register_address": "0x800000b8",
        "counter_width_bits": 32,
        "counter_source": "coherent FPGA RX sample counter low word",
        "first_batch_sample": first_batch_sample,
        "last_batch_sample_exclusive": last_batch_sample_exclusive,
        "post_open_s0_raw": s0_raw,
        "post_open_s0_sample": s0,
        "target_offset_frames": target_frames,
        "target_offset_samples": target_samples,
        "target_raw": target_raw,
        "target_sample": target_sample,
        "last_below_raw": raw_p,
        "last_below_sample": extended_p,
        "raw_a_prewrite": raw_a,
        "a_prewrite_sample": extended_a,
        "raw_post_write_initial": raw_initial,
        "post_write_initial_sample": extended_initial,
        "raw_b_first_advance": raw_b,
        "b_first_advance_sample": extended_b,
        "raw_c_causal_advance": raw_c,
        "c_causal_advance_sample": extended_c,
        "target_overshoot_samples": overshoot,
        "target_overshoot_limit_samples": (_TANDEM_BATCH_MAX_TARGET_OVERSHOOT_SAMPLES),
        "causal_uncertainty_samples": uncertainty,
        "causal_uncertainty_limit_samples": (
            _TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES
        ),
        "command_interval": "[A,C)",
    }
    if not _release_json_identical(bound_bracket, expected_bound_bracket):
        errors.append(f"{context} bound counter bracket differs from recomputation")
    if (
        command.get("rx_state_before") is not None
        or command.get("rx_state_after") is not None
        or command.get("timing_role")
        != "s0_targeted_one_write_bracketed_by_coherent_fpga_counter"
        or command.get("sample_timing_basis") != "hardware_sample_counter"
        or command.get("sample_anchor_policy")
        != (
            "post-open S0 plus frozen target; exact one-TX2-write interval is "
            "[A,C) during initiating batch refill"
        )
    ):
        errors.append(f"{context} timing role or RX scope is inconsistent")

    write_ack = value.get("write_ack")
    readback = value.get("deferred_tx2_readback")
    tx1 = value.get("tx1_mute_assurance")
    if not all(isinstance(item, Mapping) for item in (write_ack, readback, tx1)):
        return [*errors, f"{context} write/readback/TX1 evidence is malformed"], (
            extended_a,
            extended_c,
        )
    assert isinstance(write_ack, Mapping)
    assert isinstance(readback, Mapping)
    assert isinstance(tx1, Mapping)
    write_before = write_ack.get("host_before_ns")
    write_after = write_ack.get("host_after_ns")
    if (
        set(write_ack)
        != {
            "operation",
            "attempt_count",
            "host_before_ns",
            "host_after_ns",
            "host_jitter_ns",
            "acknowledged",
            "error",
        }
        or write_ack.get("operation") != "one_exact_tx2_hardwaregain_write"
        or write_ack.get("attempt_count") != 1
        or not _release_exact_int(write_before)
        or not _release_exact_int(write_after)
        or write_after < write_before
        or write_ack.get("host_jitter_ns") != write_after - write_before
        or write_after - write_before > capture.max_host_jitter_ns
        or write_ack.get("acknowledged") is not True
        or write_ack.get("error") is not None
        or command.get("host_before_ns") != write_before
        or command.get("host_after_ns") != write_after
        or command.get("host_jitter_ns") != write_after - write_before
    ):
        errors.append(f"{context} exact one-write evidence is inconsistent")
    observed = readback.get("observed_level_db")
    read_before = readback.get("host_before_ns")
    read_after = readback.get("host_after_ns")
    if (
        set(readback)
        != {
            "operation",
            "attempt_count",
            "host_before_ns",
            "host_after_ns",
            "observed_level_db",
            "tolerance_db",
            "passed",
            "error",
        }
        or readback.get("operation") != "one_exact_tx2_hardwaregain_read"
        or readback.get("attempt_count") != 1
        or not _release_exact_int(read_before)
        or not _release_exact_int(read_after)
        or read_after < read_before
        or not _release_finite_number(observed)
        or abs(float(observed) - requested_level_db) > capture.readback_tolerance_db
        or readback.get("tolerance_db") != capture.readback_tolerance_db
        or readback.get("passed") is not True
        or readback.get("error") is not None
        or value.get("applied_level_db") != observed
        or command.get("applied_level_db") != observed
    ):
        errors.append(f"{context} deferred TX2 readback is inconsistent")

    if set(tx1) != {"pre", "post"}:
        errors.append(f"{context} TX1 mute assurance phases changed")
    tx1_times: dict[str, tuple[int, int]] = {}
    for phase in ("pre", "post"):
        evidence = tx1.get(phase)
        if not isinstance(evidence, Mapping):
            errors.append(f"{context} TX1 {phase} mute assurance is missing")
            continue
        before = evidence.get("host_before_ns")
        after = evidence.get("host_after_ns")
        level = evidence.get("observed_level_db")
        if (
            set(evidence)
            != {
                "attempt_count",
                "host_before_ns",
                "host_after_ns",
                "observed_level_db",
                "passed",
                "error",
            }
            or evidence.get("attempt_count") != 1
            or not _release_exact_int(before)
            or not _release_exact_int(after)
            or after < before
            or not _release_finite_number(level)
            or abs(float(level) - TX_MUTE_DB) > 0.26
            or evidence.get("passed") is not True
            or evidence.get("error") is not None
        ):
            errors.append(f"{context} TX1 {phase} mute assurance is inconsistent")
        elif isinstance(before, int) and isinstance(after, int):
            tx1_times[phase] = (before, after)

    counter_reads = value.get("counter_reads")
    post_count = raw_bracket.get("post_write_read_count")
    valid_post_count = (
        post_count
        if _release_exact_int(post_count, minimum=3) and post_count <= 9
        else 0
    )
    if (
        not isinstance(counter_reads, list)
        or valid_post_count == 0
        or len(counter_reads) != poll_count + valid_post_count
    ):
        errors.append(f"{context} counter-read count differs from its ledgers")
    else:
        previous_host_after: int | None = None
        for ordinal, observation in enumerate(counter_reads):
            if not isinstance(observation, Mapping):
                errors.append(f"{context} counter read {ordinal} is malformed")
                continue
            before = observation.get("host_before_ns")
            after = observation.get("host_after_ns")
            if (
                set(observation)
                != {
                    "ordinal",
                    "role",
                    "host_before_ns",
                    "host_after_ns",
                    "raw",
                    "error",
                }
                or observation.get("ordinal") != ordinal
                or not _release_exact_int(before)
                or not _release_exact_int(after)
                or after < before
                or (previous_host_after is not None and before < previous_host_after)
                or not _release_exact_int(observation.get("raw"))
                or observation.get("raw") >= 1 << 32
                or observation.get("error") is not None
            ):
                errors.append(f"{context} counter read {ordinal} is inconsistent")
            if isinstance(after, int):
                previous_host_after = after
        if any(not isinstance(item, Mapping) for item in counter_reads):
            return errors, (extended_a, extended_c)
        if [item.get("raw") for item in counter_reads[:poll_count]] != [
            item.get("raw") for item in polls
        ]:
            errors.append(f"{context} target polls differ from counter diagnostics")
        roles = [item.get("role") for item in counter_reads]
        post_roles = roles[poll_count:]
        if (
            roles[: poll_count - 1] != ["target_poll"] * (poll_count - 1)
            or roles[poll_count - 1] != "raw_a_prewrite"
            or not post_roles
            or post_roles[0] != "raw_post_write_initial"
            or post_roles[-1] != "raw_c_causal_advance"
            or post_roles.count("raw_b_first_advance") != 1
            or any(
                role
                not in {
                    "raw_post_write_initial",
                    "post_write_advance_candidate",
                    "raw_b_first_advance",
                    "raw_c_causal_advance",
                }
                for role in post_roles
            )
        ):
            errors.append(f"{context} counter-read roles are inconsistent")
        role_values = {
            "raw_a_prewrite": raw_a,
            "raw_post_write_initial": raw_initial,
            "raw_b_first_advance": raw_b,
            "raw_c_causal_advance": raw_c,
        }
        for role, raw in role_values.items():
            matches = [item for item in counter_reads if item.get("role") == role]
            if len(matches) != 1 or matches[0].get("raw") != raw:
                errors.append(f"{context} {role} counter diagnostic is inconsistent")
        if "raw_b_first_advance" in post_roles:
            b_index = post_roles.index("raw_b_first_advance")
            pre_b_candidates = counter_reads[poll_count + 1 : poll_count + b_index]
            post_b_candidates = counter_reads[
                poll_count + b_index + 1 : len(counter_reads) - 1
            ]
            if (
                b_index < 1
                or b_index >= len(post_roles) - 1
                or any(
                    item.get("role") != "post_write_advance_candidate"
                    or item.get("raw") != raw_initial
                    for item in pre_b_candidates
                )
                or any(
                    item.get("role") != "post_write_advance_candidate"
                    or item.get("raw") != raw_b
                    for item in post_b_candidates
                )
            ):
                errors.append(
                    f"{context} post-write counter state machine is inconsistent"
                )
        if (
            isinstance(write_before, int)
            and counter_reads[poll_count - 1].get("host_after_ns") > write_before
        ) or (
            isinstance(write_after, int)
            and counter_reads[poll_count].get("host_before_ns") < write_after
        ):
            errors.append(f"{context} write is not between A and the initial read")
        causal_read = next(
            (
                item
                for item in counter_reads
                if item.get("role") == "raw_c_causal_advance"
            ),
            None,
        )
        if (
            isinstance(causal_read, Mapping)
            and isinstance(read_before, int)
            and causal_read.get("host_after_ns") > read_before
        ):
            errors.append(f"{context} TX2 readback was not deferred until after C")

    if isinstance(write_after, int) and write_after > initiating_refill_completion_ns:
        errors.append(f"{context} write did not finish during the initiating refill")
    if (
        "pre" in tx1_times
        and isinstance(counter_reads, list)
        and counter_reads
        and isinstance(counter_reads[0], Mapping)
        and _release_exact_int(counter_reads[0].get("host_before_ns"))
        and tx1_times["pre"][1] > counter_reads[0]["host_before_ns"]
    ):
        errors.append(f"{context} target polling preceded TX1 mute assurance")
    if (
        "pre" in tx1_times
        and isinstance(write_before, int)
        and tx1_times["pre"][1] > write_before
    ) or (
        "post" in tx1_times
        and isinstance(read_after, int)
        and tx1_times["post"][0] < read_after
    ):
        errors.append(f"{context} TX1 assurance chronology is inconsistent")

    return errors, (extended_a, extended_c)


def _transient_batch_frame_errors(
    frames: Any,
    *,
    phases: Sequence[str],
    quality: TandemQualityOptions,
) -> tuple[list[str], list[Mapping[str, Any]]]:
    """Recompute every retained tandem frame, metadata, event, and quality ledger."""

    if not isinstance(frames, list) or len(frames) != _TANDEM_BATCH_FRAMES:
        return ["transient tandem batch must contain exactly 64 frames"], []
    if len(phases) != len(frames):
        return ["transient tandem partition does not cover the full batch"], []
    if any(not isinstance(frame, Mapping) for frame in frames):
        return ["transient tandem batch frame is malformed"], []

    typed_frames = [frame for frame in frames if isinstance(frame, Mapping)]
    errors: list[str] = []
    previous_metadata: Mapping[str, Any] | None = None
    previous_event: Mapping[str, Any] | None = None
    previous_refill_ns: int | None = None
    stream_id: int | None = None
    ownership_epoch: int | None = None
    threshold_provenance: int | None = None
    metadata_features: int | None = None
    gain_index_range: tuple[int, int] | None = None
    temperature_valid_seen = False
    temperature_valid_count = 0
    temperature_omission_count = 0
    required_flags = (
        FLAG_SAMPLE_SEQUENCE_VALID
        | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
        | FLAG_TANDEM_METADATA_VALID
    )
    expected_gain_table_id = int(
        expected_tandem_gain_table(quality.center_frequency_hz)
    )
    expected_threshold_provenance = (
        quality.tandem_low_power_threshold
        | quality.tandem_large_lmt_overload_threshold << 8
        | quality.tandem_large_adc_overload_threshold << 16
        | quality.tandem_small_adc_overload_threshold << 24
    )
    uint32_modulus = 1 << 32
    expected_frame_fields = {
        "analysis",
        "artifact_policy",
        "artifact_write_status",
        "batch_phase",
        "command_boundary_gap_allowed",
        "continuity",
        "first_sample_sequence",
        "frame_index",
        "gap_context",
        "iq_bytes",
        "iq_path",
        "metadata",
        "physical_sample_continuity_proven",
        "raw_metadata_bytes",
        "raw_metadata_path",
        "raw_metadata_sha256",
        "refill_monotonic_ns",
        "sample_end_exclusive",
        "sample_gap_before",
        "sha256",
        "timing_basis",
    }
    expected_analysis_fields = {
        "first_sample_sequence",
        "samples_per_channel",
        "sample_rate_hz",
        "expected_tone_hz",
        "selected_tone_hz",
        "window_samples",
        "stride_samples",
        "window_count",
        "uncovered_tail_samples",
        "windows",
        "quality_valid",
    }

    for index, (frame, phase) in enumerate(zip(typed_frames, phases, strict=True)):
        context = f"transient tandem batch frame {index}"
        refill_ns = frame.get("refill_monotonic_ns")
        if (
            set(frame) != expected_frame_fields
            or not _release_exact_int(frame.get("frame_index"))
            or frame.get("frame_index") != index
            or not _release_exact_int(frame.get("iq_bytes"), minimum=1)
            or frame.get("iq_bytes") != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
            or not _release_exact_int(frame.get("sample_end_exclusive"), minimum=1)
            or not _release_exact_int(refill_ns)
            or (
                previous_refill_ns is not None
                and _release_exact_int(refill_ns)
                and refill_ns < previous_refill_ns
            )
            or frame.get("timing_basis") != "hardware_sample_counter"
            or frame.get("physical_sample_continuity_proven") is not True
            or frame.get("batch_phase") != phase
            or frame.get("gap_context") != phase
            or frame.get("command_boundary_gap_allowed") is not False
            or not isinstance(frame.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(frame.get("sha256"))) is None
        ):
            errors.append(f"{context} capture ledger is inconsistent")
        if _release_exact_int(refill_ns):
            previous_refill_ns = refill_ns

        analysis = frame.get("analysis")
        windows = analysis.get("windows") if isinstance(analysis, Mapping) else None
        first = frame.get("first_sample_sequence")
        expected_windows = (
            _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            // _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
        )
        if (
            not isinstance(analysis, Mapping)
            or set(analysis) != expected_analysis_fields
            or not _release_exact_int(first)
            or analysis.get("first_sample_sequence") != first
            or analysis.get("samples_per_channel")
            != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            or analysis.get("sample_rate_hz") != quality.sample_rate_hz
            or analysis.get("expected_tone_hz") != quality.tone_hz
            or not _release_finite_number(analysis.get("selected_tone_hz"))
            or abs(float(analysis.get("selected_tone_hz", 0))) != abs(quality.tone_hz)
            or analysis.get("window_samples") != _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
            or analysis.get("stride_samples") != _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
            or analysis.get("window_count") != expected_windows
            or analysis.get("uncovered_tail_samples") != 0
            or not isinstance(windows, list)
            or len(windows) != expected_windows
        ):
            errors.append(f"{context} analysis ledger is inconsistent")
        else:
            window_validities: list[bool] = []
            for window_index, window in enumerate(windows):
                if not isinstance(window, Mapping):
                    errors.append(f"{context} analysis window is malformed")
                    break
                snr = window.get("tone_snr_db")
                tones = window.get("tone_dbfs")
                clipping = window.get("clipping_fraction")
                phase_rad = window.get("phase_difference_rad")
                phase_deg = window.get("phase_difference_deg")
                phase_std = window.get("within_window_phase_std_deg")
                if (
                    set(window)
                    != {
                        "window_index",
                        "offset_start",
                        "offset_end_exclusive",
                        "sample_start",
                        "sample_end_exclusive",
                        "tone_dbfs",
                        "mean_tone_dbfs",
                        "tone_snr_db",
                        "clipping_fraction",
                        "phase_difference_rad",
                        "phase_difference_deg",
                        "within_window_phase_std_deg",
                        "quality_valid",
                        "quality_reasons",
                    }
                    or not isinstance(tones, list)
                    or len(tones) != 2
                    or any(not _release_finite_number(value) for value in tones)
                    or not _release_finite_number(window.get("mean_tone_dbfs"))
                    or not math.isclose(
                        float(window.get("mean_tone_dbfs")),
                        statistics.mean(float(value) for value in tones),
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                    or not isinstance(snr, list)
                    or len(snr) != 2
                    or any(not _release_finite_number(value) for value in snr)
                    or not isinstance(clipping, list)
                    or len(clipping) != 2
                    or any(not _release_finite_number(value) for value in clipping)
                    or any(not 0 <= float(value) <= 1 for value in clipping)
                    or not _release_finite_number(phase_rad)
                    or not _release_finite_number(phase_deg)
                    or not math.isclose(
                        float(phase_deg),
                        math.degrees(float(phase_rad)),
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                    or not _release_finite_number(phase_std)
                    or float(phase_std) < 0
                ):
                    errors.append(f"{context} analysis quality is malformed")
                    break
                reasons: list[str] = []
                for channel in (0, 1):
                    if snr[channel] < quality.thresholds.min_tone_snr_db:
                        reasons.append(f"rx{channel}_tone_snr_low")
                    if clipping[channel] > quality.thresholds.max_clipping_fraction:
                        reasons.append(f"rx{channel}_clipping")
                if phase_std > quality.thresholds.max_phase_std_deg:
                    reasons.append("within_window_phase_unstable")
                valid = not reasons
                window_validities.append(valid)
                expected_start = (
                    int(first) + window_index * _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
                )
                if (
                    window.get("window_index") != window_index
                    or window.get("offset_start")
                    != window_index * _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
                    or window.get("offset_end_exclusive")
                    != (window_index + 1) * _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
                    or window.get("sample_start") != expected_start
                    or window.get("sample_end_exclusive")
                    != expected_start + _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
                    or window.get("quality_reasons") != reasons
                    or window.get("quality_valid") is not valid
                ):
                    errors.append(f"{context} analysis window ledger is inconsistent")
                    break
            if analysis.get("quality_valid") is not all(window_validities):
                errors.append(f"{context} analysis quality ledger is inconsistent")

        metadata = frame.get("metadata")
        continuity = frame.get("continuity")
        if not isinstance(metadata, Mapping) or not isinstance(continuity, Mapping):
            errors.append(f"{context} lacks metadata continuity evidence")
            continue
        buffer_sequence = metadata.get("buffer_sequence")
        first_sample = metadata.get("first_sample_sequence")
        transition_count = metadata.get("tandem_transition_count")
        current_stream = metadata.get("stream_id")
        current_epoch = metadata.get("ownership_epoch")
        events = metadata.get("gain_events")
        endpoint = metadata.get("bench_gain_indices")
        index_range = metadata.get("gain_index_range")
        current_provenance = metadata.get("threshold_provenance")
        if (
            set(metadata)
            != {
                "version",
                "header_bytes",
                "features",
                "stream_id",
                "buffer_sequence",
                "first_sample_sequence",
                "samples_per_channel",
                "iq_payload_bytes",
                "flags",
                "enabled_scan_mask",
                "sample_format",
                "channel_count",
                "observation_count",
                "observation_capacity",
                "event_capacity",
                "ownership_epoch",
                "tandem_state",
                "tandem_state_name",
                "tandem_fault_flags",
                "tandem_transition_count",
                "gain_table_id",
                "threshold_provenance",
                "gain_db_range",
                "initial_gain_db",
                "gain_index_range",
                "bench_gain_indices",
                "rx1_gain_index",
                "rx2_gain_index",
                "event_count",
                "observation_overflow_count",
                "event_overflow_count",
                "temperature_mdeg_c",
                "gain_event_count",
                "gain_events",
            }
            or metadata.get("version") != _TANDEM_BATCH_METADATA_VERSION
            or metadata.get("header_bytes") != _TANDEM_BATCH_METADATA_HEADER_BYTES
            or not _release_exact_int(metadata.get("features"))
            or metadata.get("features") & _TANDEM_BATCH_REQUIRED_METADATA_FEATURES
            != _TANDEM_BATCH_REQUIRED_METADATA_FEATURES
            or not _release_exact_int(buffer_sequence)
            or not _release_exact_int(first_sample)
            or metadata.get("samples_per_channel")
            != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            or metadata.get("iq_payload_bytes")
            != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
            or metadata.get("enabled_scan_mask") != 0x0F
            or metadata.get("sample_format") != _TANDEM_BATCH_SAMPLE_FORMAT
            or metadata.get("channel_count") != 2
            or metadata.get("observation_capacity") != 64
            or metadata.get("event_capacity") != 64
            or not _release_exact_int(transition_count)
            or transition_count >= uint32_modulus
            or not _release_exact_int(current_stream, minimum=1)
            or not _release_exact_int(current_epoch, minimum=1)
            or not isinstance(events, list)
            or not isinstance(endpoint, list)
            or len(endpoint) != 2
            or any(not _release_exact_int(value) for value in endpoint)
            or endpoint[0] != endpoint[1]
            or metadata.get("rx1_gain_index") != endpoint[0]
            or metadata.get("rx2_gain_index") != endpoint[1]
            or not isinstance(index_range, list)
            or len(index_range) != 2
            or any(not _release_exact_int(value) for value in index_range)
            or index_range[0] > index_range[1]
            or not index_range[0] <= endpoint[0] <= index_range[1]
            or not _release_exact_int(metadata.get("flags"))
            or metadata.get("flags") & TANDEM_UNSAFE_FLAGS
            or metadata.get("flags") & required_flags != required_flags
            or metadata.get("tandem_state") != int(TandemState.ARMED_AUTO)
            or metadata.get("tandem_state_name") != "armed_auto"
            or metadata.get("gain_table_id") != expected_gain_table_id
            or metadata.get("gain_db_range") != [0, 62]
            or metadata.get("initial_gain_db") != 62
            or current_provenance != expected_threshold_provenance
            or not _release_exact_int(metadata.get("observation_count"), minimum=1)
            or metadata.get("observation_count")
            > _TANDEM_BATCH_MAX_OBSERVATIONS_PER_FRAME
            or len(events) > _TANDEM_BATCH_MAX_EVENTS_PER_FRAME
        ):
            errors.append(f"{context} metadata counters or gains are malformed")
            continue
        temperature = metadata.get("temperature_mdeg_c")
        if temperature is None:
            if temperature_valid_seen:
                errors.append(
                    f"{context} temperature became unavailable after a valid sample"
                )
            temperature_omission_count += 1
        elif (
            not _release_exact_int(temperature)
            or not _TANDEM_BATCH_MINIMUM_TEMPERATURE_MDEG_C
            <= temperature
            <= _TANDEM_BATCH_MAXIMUM_TEMPERATURE_MDEG_C
        ):
            errors.append(f"{context} temperature violates provider provenance")
        else:
            temperature_valid_seen = True
            temperature_valid_count += 1
        if threshold_provenance is None:
            threshold_provenance = int(current_provenance)
        elif current_provenance != threshold_provenance:
            errors.append(f"{context} threshold provenance changed")
        current_features = metadata.get("features")
        if metadata_features is None:
            metadata_features = int(current_features)
        elif current_features != metadata_features:
            errors.append(f"{context} metadata feature mask changed")
        if (
            metadata.get("event_count") != len(events)
            or metadata.get("gain_event_count") != len(events)
            or metadata.get("tandem_fault_flags") != 0
            or metadata.get("observation_overflow_count") != 0
            or metadata.get("event_overflow_count") != 0
        ):
            errors.append(f"{context} reports an event-count, fault, or overflow error")
        if (
            frame.get("first_sample_sequence") != first_sample
            or frame.get("sample_end_exclusive")
            != first_sample + _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
        ):
            errors.append(f"{context} IQ sample range differs from metadata")

        if previous_metadata is None:
            stream_id = int(current_stream)
            ownership_epoch = int(current_epoch)
            gain_index_range = (int(index_range[0]), int(index_range[1]))
            buffer_delta: int | None = None
            sample_delta: int | None = None
            transition_delta: int | None = None
            initial_unrepresented = int(transition_count) - len(events)
            # AUTO enters at the request maximum while the weak conditioning
            # stimulus is already present.  It can therefore converge before
            # the first retained provider frame.  The pre-attack conditioning
            # ledger reconciles those startup transitions and the final quiet
            # suffix; startup is never used as response-direction proof.
            if buffer_sequence != 0 or initial_unrepresented < 0:
                errors.append(
                    "transient tandem first frame has an invalid session origin"
                )
        else:
            if current_stream != stream_id or current_epoch != ownership_epoch:
                errors.append(f"{context} stream or ownership epoch changed")
            if tuple(index_range) != gain_index_range:
                errors.append(f"{context} gain-index range changed")
            buffer_delta = int(buffer_sequence) - int(
                previous_metadata["buffer_sequence"]
            )
            sample_delta = int(first_sample) - int(
                previous_metadata["first_sample_sequence"]
            )
            transition_delta = (
                int(transition_count)
                - int(previous_metadata["tandem_transition_count"])
            ) % uint32_modulus
            initial_unrepresented = 0
            if (
                buffer_delta != 1
                or sample_delta != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            ):
                errors.append(f"{context} is not contiguous with the prior frame")
            if transition_delta != len(events):
                errors.append(f"{context} contains a hidden transition")

        expected_continuity = {
            "buffer_delta": buffer_delta,
            "sample_delta": sample_delta,
            "missing_frame_count": 0,
            "sample_gap_before": 0,
            "provider_gap_accepted": False,
            "gap_context": phase,
            "command_boundary_gap_allowed": False,
            "transition_count_delta": transition_delta,
            "visible_event_count": len(events),
            "hidden_transition_count": 0,
            "initial_unrepresented_transition_count": initial_unrepresented,
            "cumulative_missing_frame_count": 0,
            "cumulative_hidden_transition_count": 0,
            "cumulative_event_sequence_hole_count": 0,
        }
        if (
            not _release_json_identical(dict(continuity), expected_continuity)
            or frame.get("sample_gap_before") != 0
        ):
            errors.append(f"{context} continuity differs from metadata")

        for event_index, event in enumerate(events):
            event_context = f"{context} event {event_index}"
            if not isinstance(event, Mapping):
                errors.append(f"{event_context} is malformed")
                continue
            event_sample = event.get("sample_sequence")
            event_sequence = event.get("event_sequence")
            flags = event.get("flags")
            direction = event.get("direction")
            reason = event.get("reason")
            rx1_gain = event.get("rx1_gain_index")
            rx2_gain = event.get("rx2_gain_index")
            flags_valid = _release_exact_int(flags) and flags <= 0x3F
            expected_direction = (flags >> 4) & 0x3 if flags_valid else None
            expected_reason = flags & 0xF if flags_valid else None
            try:
                direction_name = TandemEventDirection(expected_direction).name.lower()
                reason_name = TandemEventReason(expected_reason).name.lower()
            except (TypeError, ValueError):
                direction_name = None
                reason_name = None
            if (
                set(event)
                != {
                    "sample_sequence",
                    "event_sequence",
                    "flags",
                    "direction",
                    "direction_name",
                    "reason",
                    "reason_name",
                    "rx1_gain_index",
                    "rx2_gain_index",
                }
                or not _release_exact_int(event_sample)
                or not _release_exact_int(event_sequence)
                or event_sequence >= uint32_modulus
                or not flags_valid
                or direction_name is None
                or reason_name is None
                or direction != expected_direction
                or event.get("direction_name") != direction_name
                or reason != expected_reason
                or event.get("reason_name") != reason_name
                or not _release_exact_int(rx1_gain)
                or not _release_exact_int(rx2_gain)
                or rx1_gain != rx2_gain
                or not first_sample
                <= event_sample
                < first_sample + _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
                or not index_range[0] <= rx1_gain <= index_range[1]
            ):
                errors.append(f"{event_context} is malformed")
                continue
            step = 1 if direction == int(TandemEventDirection.INCREASE) else -1
            prior_gain = (
                previous_event.get("rx1_gain_index")
                if previous_event is not None
                else previous_metadata.get("bench_gain_indices", [None])[0]
                if previous_metadata is not None
                else None
            )
            if previous_event is not None:
                sequence_delta = (
                    int(event_sequence) - int(previous_event["event_sequence"])
                ) % uint32_modulus
                event_spacing = event_sample - previous_event["sample_sequence"]
                if (
                    sequence_delta != 1
                    or event_spacing < _TANDEM_BATCH_MINIMUM_EVENT_SPACING_SAMPLES
                ):
                    errors.append(
                        f"{event_context} is not globally contiguous and ordered"
                    )
            if prior_gain is not None and rx1_gain != prior_gain + step:
                errors.append(f"{event_context} is not an exact paired gain step")
            previous_event = event
        if events and isinstance(events[-1], Mapping):
            if endpoint != [events[-1].get("rx1_gain_index")] * 2:
                errors.append(f"{context} endpoint differs from its final event")
        elif events:
            errors.append(f"{context} final event is malformed")
        elif previous_metadata is not None and endpoint != previous_metadata.get(
            "bench_gain_indices"
        ):
            errors.append(f"{context} endpoint changed without an event")
        previous_metadata = metadata

    if (
        temperature_valid_count < 1
        or temperature_valid_count + temperature_omission_count != _TANDEM_BATCH_FRAMES
    ):
        errors.append("transient tandem batch lacks valid temperature evidence")
    return errors, typed_frames


def _release_tandem_metadata_dict(metadata: Any) -> dict[str, Any]:
    """Normalize independently parsed ABI-v5 metadata into report form."""

    return {
        "version": metadata.version,
        "header_bytes": metadata.header_bytes,
        "features": metadata.features,
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "iq_payload_bytes": metadata.iq_payload_bytes,
        "flags": metadata.flags,
        "enabled_scan_mask": metadata.enabled_scan_mask,
        "sample_format": metadata.sample_format,
        "channel_count": metadata.channel_count,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_capacity": metadata.event_capacity,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_fault_flags": metadata.tandem_fault_flags,
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "threshold_provenance": metadata.threshold_provenance,
        "gain_db_range": [metadata.minimum_gain_db, metadata.maximum_gain_db],
        "initial_gain_db": metadata.initial_gain_db,
        "gain_index_range": [
            metadata.minimum_gain_index,
            metadata.maximum_gain_index,
        ],
        "bench_gain_indices": list(metadata.bench_gain_indices),
        "rx1_gain_index": metadata.rx1_gain_index,
        "rx2_gain_index": metadata.rx2_gain_index,
        "event_count": metadata.event_count,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
        "temperature_mdeg_c": metadata.ad9361_temperature_mdeg_c,
        "gain_event_count": len(metadata.gain_events),
        "gain_events": [
            {
                "sample_sequence": int(event.sample_sequence),
                "event_sequence": int(event.event_sequence),
                "flags": int(event.flags),
                "direction": int(event.direction),
                "direction_name": event.direction.name.lower(),
                "reason": int(event.reason),
                "reason_name": event.reason.name.lower(),
                "rx1_gain_index": int(event.rx1_gain_index),
                "rx2_gain_index": int(event.rx2_gain_index),
            }
            for event in metadata.gain_events
        ],
    }


def _transient_batch_request_errors(
    value: Any, quality: TandemQualityOptions
) -> list[str]:
    """Independently rebuild and decode the frozen AUTO62 metadata request."""

    request = build_tandem_request(
        mode=TandemMode.AUTO,
        initial_gain_db=62,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=_TANDEM_BATCH_PROVIDER_FRAME_SAMPLES,
    )
    decoded = {
        "magic": 0x54465053,
        "abi_version": 1,
        "request_bytes": 104,
        "required_features": 0x7,
        "mode": int(TandemMode.AUTO),
        "observation_capacity": 64,
        "event_capacity": 64,
        "minimum_gain_db": 0,
        "maximum_gain_db": 62,
        "initial_gain_db": 62,
        "power_measurement_samples": quality.tandem_power_measurement_samples,
        "low_power_dwell_periods": quality.tandem_low_power_dwell_periods,
        "cooldown_periods": quality.tandem_cooldown_periods,
        "pulse_high_cycles": 4,
        "pulse_low_cycles": 4,
        "detector_blanking_cycles": 8,
        "low_power_threshold": quality.tandem_low_power_threshold,
        "large_lmt_overload_threshold": (quality.tandem_large_lmt_overload_threshold),
        "large_adc_overload_threshold": (quality.tandem_large_adc_overload_threshold),
        "small_adc_overload_threshold": (quality.tandem_small_adc_overload_threshold),
        "observation_overflow_policy": 0,
        "event_overflow_policy": 0,
        **{f"reserved_{index}": 0 for index in range(8)},
    }
    expected = {
        "wire_bytes": 104,
        "wire_hex": request.hex(),
        "sha256": hashlib.sha256(request).hexdigest(),
        "decoded": decoded,
    }
    if len(request) != 104 or not _release_json_identical(value, expected):
        return ["transient tandem AUTO62 metadata request differs from policy"]
    return []


def _transient_batch_sidecar_errors(
    frames: Sequence[Mapping[str, Any]],
    *,
    phase_root: Path,
    serial: str,
    quality: TandemQualityOptions,
) -> tuple[list[str], dict[str, Any], tuple[Any, ...]]:
    """Re-read, hash, parse, and FFT every mandatory tandem sidecar."""

    errors: list[str] = []
    parsed_metadata: list[Any] = []
    reported_paths: set[str] = set()
    trusted_root = phase_root.resolve()
    artifact_directory = trusted_root / serial / "transient-iq" / MODE_TANDEM / "batch"
    expected_names: set[str] = set()
    required_flags = (
        FLAG_SAMPLE_SEQUENCE_VALID
        | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
        | FLAG_TANDEM_METADATA_VALID
    )

    if phase_root.is_symlink() or (trusted_root / serial).is_symlink():
        errors.append("transient tandem artifact root or report directory is symlinked")

    for index, frame in enumerate(frames):
        context = f"transient tandem batch frame {index}"
        expected_records = (
            (
                "iq_path",
                "sha256",
                "iq_bytes",
                f"frame-{index:04d}.cs16",
                _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8,
            ),
            (
                "raw_metadata_path",
                "raw_metadata_sha256",
                "raw_metadata_bytes",
                f"frame-{index:04d}.metadata.bin",
                _TANDEM_BATCH_METADATA_HEADER_BYTES,
            ),
        )
        if frame.get("artifact_policy") != "mandatory_exact_release_sidecars":
            errors.append(f"{context} mandatory artifact policy is missing")
        if frame.get("artifact_write_status") != {
            "iq_write_completed": True,
            "raw_metadata_write_completed": True,
        }:
            errors.append(f"{context} sidecar write did not complete")
        payloads: dict[str, bytes] = {}
        for path_key, digest_key, byte_key, filename, exact_bytes in expected_records:
            expected_names.add(filename)
            reported = frame.get(path_key)
            digest = frame.get(digest_key)
            byte_count = frame.get(byte_key)
            if (
                not isinstance(reported, str)
                or not reported
                or "\\" in reported
                or PurePosixPath(reported).is_absolute()
                or ".." in PurePosixPath(reported).parts
                or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
                or not _release_exact_int(byte_count, minimum=1)
            ):
                errors.append(f"{context} {path_key} ledger is malformed")
                continue
            relative = PurePosixPath(reported)
            expected_relative = PurePosixPath(
                serial, "transient-iq", MODE_TANDEM, "batch", filename
            )
            if relative != expected_relative or reported in reported_paths:
                errors.append(
                    f"{context} {path_key} path is escaped, duplicated, or renamed"
                )
                continue
            reported_paths.add(reported)
            path = trusted_root.joinpath(*relative.parts)
            current = trusted_root
            symlinked = False
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    symlinked = True
                    break
            try:
                contained = path.resolve().is_relative_to(trusted_root)
                file_size = path.stat().st_size
            except (OSError, RuntimeError, ValueError):
                contained = False
                file_size = None
            if (
                symlinked
                or not contained
                or not path.is_file()
                or byte_count != exact_bytes
                or file_size != exact_bytes
            ):
                errors.append(f"{context} {path_key} is missing or symlinked")
                continue
            try:
                payload = path.read_bytes()
            except (OSError, ValueError) as error:
                errors.append(f"{context} {path_key} cannot be read: {error}")
                continue
            computed_digest = hashlib.sha256(payload).hexdigest()
            if (
                len(payload) != byte_count
                or computed_digest != digest
                or (exact_bytes is not None and len(payload) != exact_bytes)
            ):
                errors.append(f"{context} {path_key} size or SHA-256 differs")
                continue
            payloads[path_key] = payload
        raw_iq = payloads.get("iq_path")
        if raw_iq is not None:
            try:
                recomputed_analysis = _json_safe(
                    analyze_immediate_dual_rx(
                        raw_iq,
                        first_sample_sequence=int(frame["first_sample_sequence"]),
                        sample_rate_hz=quality.sample_rate_hz,
                        expected_tone_hz=quality.tone_hz,
                        window_samples=_TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES,
                        min_tone_snr_db=quality.thresholds.min_tone_snr_db,
                        max_clipping_fraction=(
                            quality.thresholds.max_clipping_fraction
                        ),
                        max_phase_std_deg=quality.thresholds.max_phase_std_deg,
                    )
                )
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                errors.append(f"{context} IQ sidecar cannot be reanalyzed: {error}")
            else:
                if not _release_json_identical(
                    frame.get("analysis"), recomputed_analysis
                ):
                    errors.append(
                        f"{context} analysis differs from mandatory IQ sidecar"
                    )

        raw_metadata = payloads.get("raw_metadata_path")
        if raw_metadata is not None:
            try:
                parsed = parse_tandem_frame_metadata(raw_metadata)
                recomputed_metadata = _release_tandem_metadata_dict(parsed)
            except (TypeError, ValueError) as error:
                errors.append(
                    f"{context} raw metadata sidecar cannot be parsed: {error}"
                )
            else:
                parsed_metadata.append(parsed)
                expected_provenance = (
                    quality.tandem_low_power_threshold
                    | quality.tandem_large_lmt_overload_threshold << 8
                    | quality.tandem_large_adc_overload_threshold << 16
                    | quality.tandem_small_adc_overload_threshold << 24
                )
                if (
                    parsed.version != _TANDEM_BATCH_METADATA_VERSION
                    or parsed.header_bytes != _TANDEM_BATCH_METADATA_HEADER_BYTES
                    or parsed.header_bytes != len(raw_metadata)
                    or parsed.features & _TANDEM_BATCH_REQUIRED_METADATA_FEATURES
                    != _TANDEM_BATCH_REQUIRED_METADATA_FEATURES
                    or parsed.flags & required_flags != required_flags
                    or parsed.samples_per_channel
                    != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
                    or parsed.iq_payload_bytes
                    != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
                    or parsed.enabled_scan_mask != 0x0F
                    or parsed.sample_format != _TANDEM_BATCH_SAMPLE_FORMAT
                    or parsed.channel_count != 2
                    or parsed.observation_capacity != 64
                    or parsed.event_capacity != 64
                    or parsed.observation_count
                    > _TANDEM_BATCH_MAX_OBSERVATIONS_PER_FRAME
                    or parsed.event_count > _TANDEM_BATCH_MAX_EVENTS_PER_FRAME
                    or parsed.threshold_provenance != expected_provenance
                ):
                    errors.append(
                        f"{context} parsed raw metadata violates the physics policy"
                    )
                if not _release_json_identical(
                    frame.get("metadata"), recomputed_metadata
                ):
                    errors.append(
                        f"{context} metadata differs from mandatory raw sidecar"
                    )

    if artifact_directory.is_symlink():
        errors.append("transient tandem artifact directory is symlinked")
    elif artifact_directory.is_dir():
        try:
            observed_names: set[str] = set()
            inventory_excessive = False
            for item in artifact_directory.iterdir():
                observed_names.add(item.name)
                if len(observed_names) > len(expected_names):
                    inventory_excessive = True
                    break
        except OSError as error:
            errors.append(
                f"transient tandem artifact inventory cannot be read: {error}"
            )
        else:
            if inventory_excessive or observed_names != expected_names:
                errors.append(
                    "transient tandem artifact directory contains missing, extra, "
                    "or temporary files"
                )
    else:
        errors.append("transient tandem artifact directory is missing")
    entries = [
        {
            "frame_index": index,
            "iq_path": frame.get("iq_path"),
            "iq_bytes": frame.get("iq_bytes"),
            "iq_sha256": frame.get("sha256"),
            "raw_metadata_path": frame.get("raw_metadata_path"),
            "raw_metadata_bytes": frame.get("raw_metadata_bytes"),
            "raw_metadata_sha256": frame.get("raw_metadata_sha256"),
            "write_status": frame.get("artifact_write_status"),
        }
        for index, frame in enumerate(frames)
    ]
    encoded = json.dumps(
        entries, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    manifest = {
        "path_root": "quality.output_dir",
        "relative_directory": (f"{serial}/transient-iq/{MODE_TANDEM}/batch"),
        "frame_count": _TANDEM_BATCH_FRAMES,
        "file_count": 2 * _TANDEM_BATCH_FRAMES,
        "iq_total_bytes": (
            _TANDEM_BATCH_FRAMES * _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
        ),
        "raw_metadata_total_bytes": sum(
            frame.get("raw_metadata_bytes", 0)
            if _release_exact_int(frame.get("raw_metadata_bytes"))
            else 0
            for frame in frames
        ),
        "completed_iq_files": _TANDEM_BATCH_FRAMES,
        "completed_raw_metadata_files": _TANDEM_BATCH_FRAMES,
        "write_complete": True,
        "entries": entries,
        "entries_canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    return errors, manifest, tuple(parsed_metadata)


def _transient_batch_slice_source_errors(
    source: Any,
    frame: Mapping[str, Any],
    *,
    role: str,
    phase_root: Path,
    serial: str,
    quality: TandemQualityOptions,
) -> list[str]:
    """Recompute one exact 8,192-sample conditioning slice from its IQ file."""

    context = f"transient tandem {role}"
    if not isinstance(source, Mapping):
        return [f"{context} source is missing"]
    fields = {
        "role",
        "source_frame_index",
        "source_frame_sha256",
        "sample_offset_in_frame",
        "samples_per_channel",
        "byte_offset_in_frame",
        "byte_end_exclusive_in_frame",
        "iq_bytes",
        "first_sample_sequence",
        "sample_end_exclusive",
        "sha256",
        "analysis",
    }
    offset_samples = _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES - _TANDEM_BATCH_ANCHOR_SAMPLES
    byte_start = offset_samples * 8
    byte_end = _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
    first_sample = frame.get("first_sample_sequence")
    expected_first = (
        int(first_sample) + offset_samples if _release_exact_int(first_sample) else None
    )
    errors: list[str] = []
    if (
        set(source) != fields
        or source.get("role") != role
        or source.get("source_frame_index") != frame.get("frame_index")
        or source.get("source_frame_sha256") != frame.get("sha256")
        or source.get("sample_offset_in_frame") != offset_samples
        or source.get("samples_per_channel") != _TANDEM_BATCH_ANCHOR_SAMPLES
        or source.get("byte_offset_in_frame") != byte_start
        or source.get("byte_end_exclusive_in_frame") != byte_end
        or source.get("iq_bytes") != _TANDEM_BATCH_ANCHOR_SAMPLES * 8
        or source.get("first_sample_sequence") != expected_first
        or source.get("sample_end_exclusive")
        != (
            expected_first + _TANDEM_BATCH_ANCHOR_SAMPLES
            if expected_first is not None
            else None
        )
        or re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256"))) is None
    ):
        errors.append(f"{context} slice ledger is inconsistent")

    relative = frame.get("iq_path")
    frame_index = frame.get("frame_index")
    expected_relative = (
        PurePosixPath(
            serial,
            "transient-iq",
            MODE_TANDEM,
            "batch",
            f"frame-{frame_index:04d}.cs16",
        )
        if _release_exact_int(frame_index)
        else None
    )
    if (
        not isinstance(relative, str)
        or expected_relative is None
        or PurePosixPath(relative) != expected_relative
        or PurePosixPath(relative).is_absolute()
        or ".." in PurePosixPath(relative).parts
        or "\\" in relative
    ):
        return [*errors, f"{context} source IQ path is not canonical"]
    trusted_root = phase_root.resolve()
    path = trusted_root.joinpath(*expected_relative.parts)
    current = trusted_root
    symlinked = phase_root.is_symlink()
    for part in expected_relative.parts:
        current = current / part
        if current.is_symlink():
            symlinked = True
            break
    try:
        contained = path.resolve().is_relative_to(trusted_root)
        exact_size = path.stat().st_size
    except (OSError, RuntimeError, ValueError) as error:
        return [*errors, f"{context} source IQ cannot be inspected: {error}"]
    if (
        symlinked
        or not contained
        or not path.is_file()
        or exact_size != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES * 8
    ):
        return [*errors, f"{context} source IQ path or size is unsafe"]
    try:
        full_raw = path.read_bytes()
    except (OSError, ValueError) as error:
        return [*errors, f"{context} source IQ cannot be read: {error}"]
    raw = full_raw[byte_start:byte_end]
    if (
        len(raw) != _TANDEM_BATCH_ANCHOR_SAMPLES * 8
        or hashlib.sha256(raw).hexdigest() != source.get("sha256")
        or expected_first is None
    ):
        return [*errors, f"{context} slice bytes differ from the source frame"]
    try:
        recomputed = _json_safe(
            analyze_immediate_dual_rx(
                raw,
                first_sample_sequence=expected_first,
                sample_rate_hz=quality.sample_rate_hz,
                expected_tone_hz=quality.tone_hz,
                window_samples=_TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES,
                min_tone_snr_db=quality.thresholds.min_tone_snr_db,
                max_clipping_fraction=quality.thresholds.max_clipping_fraction,
                max_phase_std_deg=quality.thresholds.max_phase_std_deg,
            )
        )
    except (TypeError, ValueError, RuntimeError) as error:
        errors.append(f"{context} slice cannot be reanalyzed: {error}")
    else:
        if (
            not _release_json_identical(source.get("analysis"), recomputed)
            or recomputed.get("quality_valid") is not True
        ):
            errors.append(f"{context} slice analysis differs from IQ bytes")
    return errors


def _release_stimulus_from_record(record: Mapping[str, Any]) -> StimulusCommand:
    return StimulusCommand(
        command_id=record["command_id"],
        requested_level_db=record["requested_level_db"],
        applied_level_db=record["applied_level_db"],
        host_before_ns=record["host_before_ns"],
        host_after_ns=record["host_after_ns"],
        sample_sequence_before=record["sample_sequence_before"],
        sample_sequence_after=record["sample_sequence_after"],
    )


def _transient_batch_analysis_summary_errors(
    mode: Mapping[str, Any],
    frames: Sequence[Mapping[str, Any]],
    *,
    groups: Mapping[str, Mapping[str, Any]],
    attack_command: Mapping[str, Any],
    release_command: Mapping[str, Any],
    phase_root: Path,
    serial: str,
    capture: TransientCaptureOptions,
    quality: TandemQualityOptions,
) -> list[str]:
    """Cross-bind anchors, response windows, responses, and event conclusions."""

    errors: list[str] = []
    pre_indices = groups["fully_pre_attack"]["frame_indices"]
    middle_indices = groups["fully_post_attack_pre_release"]["frame_indices"]
    if not pre_indices or not middle_indices:
        return ["transient tandem conditioning anchors lack stable source frames"]
    anchor_frame = frames[pre_indices[-1]]
    release_baseline_frame = frames[middle_indices[-1]]
    conditioning_anchor = mode.get("conditioning_anchor")
    source = (
        conditioning_anchor.get("source")
        if isinstance(conditioning_anchor, Mapping)
        else None
    )
    initial_command = mode.get("commands", [{}])[0]
    expected_anchor_fields = {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "timing_role",
        "sample_timing_basis",
        "sample_anchor_policy",
        "source",
    }
    if (
        not isinstance(conditioning_anchor, Mapping)
        or not isinstance(initial_command, Mapping)
        or set(conditioning_anchor) != expected_anchor_fields
        or conditioning_anchor.get("command_id") != "weak_conditioning_anchor"
        or any(
            conditioning_anchor.get(key) != initial_command.get(key)
            for key in (
                "requested_level_db",
                "applied_level_db",
                "host_before_ns",
                "host_after_ns",
                "host_jitter_ns",
            )
        )
        or not isinstance(source, Mapping)
        or conditioning_anchor.get("sample_sequence_before")
        != source.get("first_sample_sequence")
        or conditioning_anchor.get("sample_sequence_after")
        != source.get("sample_end_exclusive")
        or conditioning_anchor.get("sample_uncertainty") != _TANDEM_BATCH_ANCHOR_SAMPLES
        or conditioning_anchor.get("timing_role") != "exact_retained_pre_attack_tail"
        or conditioning_anchor.get("sample_timing_basis") != "hardware_sample_counter"
        or conditioning_anchor.get("sample_anchor_policy")
        != (
            "exact final 8192 samples of the final fully-pre-attack frame; "
            "conditioning evidence, not initial-write timing"
        )
    ):
        errors.append("transient tandem conditioning anchor is inconsistent")
    errors.extend(
        _transient_batch_slice_source_errors(
            source,
            anchor_frame,
            role="weak_conditioning_tail",
            phase_root=phase_root,
            serial=serial,
            quality=quality,
        )
    )

    observations = mode.get("response_observations")
    release_observation = (
        observations.get("release") if isinstance(observations, Mapping) else None
    )
    release_baseline = (
        release_observation.get("baseline_anchor")
        if isinstance(release_observation, Mapping)
        else None
    )
    errors.extend(
        _transient_batch_slice_source_errors(
            release_baseline,
            release_baseline_frame,
            role="strong_pre_release_tail",
            phase_root=phase_root,
            serial=serial,
            quality=quality,
        )
    )

    attack_start = (
        source.get("first_sample_sequence") if isinstance(source, Mapping) else None
    )
    attack_end = release_command.get("sample_sequence_before")
    release_start = (
        release_baseline.get("first_sample_sequence")
        if isinstance(release_baseline, Mapping)
        else None
    )
    release_end = frames[-1].get("sample_end_exclusive")
    selected_windows: dict[str, list[Mapping[str, Any]]] = {}
    selection = (
        "all complete persisted batch-frame windows inside the stated half-open "
        "sample interval"
    )
    for name, lower, upper, baseline in (
        ("attack", attack_start, attack_end, source),
        ("release", release_start, release_end, release_baseline),
    ):
        observation = (
            observations.get(name) if isinstance(observations, Mapping) else None
        )
        if not _release_exact_int(lower) or not _release_exact_int(upper, minimum=1):
            errors.append(f"transient tandem {name} observation bounds are malformed")
            continue
        windows: list[Mapping[str, Any]] = []
        frame_indices: list[int] = []
        for frame_index, frame in enumerate(frames):
            analysis = frame.get("analysis")
            frame_windows = (
                analysis.get("windows") if isinstance(analysis, Mapping) else None
            )
            if not isinstance(frame_windows, list):
                continue
            chosen = [
                window
                for window in frame_windows
                if isinstance(window, Mapping)
                and _release_exact_int(window.get("sample_start"))
                and _release_exact_int(window.get("sample_end_exclusive"), minimum=1)
                and window["sample_start"] >= lower
                and window["sample_end_exclusive"] <= upper
            ]
            if chosen:
                frame_indices.append(frame_index)
                windows.extend(chosen)
        contiguous = bool(windows) and all(
            previous.get("sample_end_exclusive") == current.get("sample_start")
            for previous, current in pairwise(windows)
        )
        expected_observation = {
            "frame_indices": frame_indices,
            "sample_sequence_before": (
                windows[0].get("sample_start") if windows else None
            ),
            "sample_sequence_after": (
                windows[-1].get("sample_end_exclusive") if windows else None
            ),
            "window_samples": _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES,
            "window_count": len(windows),
            "selection": selection,
            "baseline_anchor": baseline,
        }
        if not contiguous or not _release_json_identical(
            observation, expected_observation
        ):
            errors.append(
                f"transient tandem {name} observation ledger differs from batch"
            )
        selected_windows[name] = windows

    expected_baseline_frames = [source] if isinstance(source, Mapping) else []
    expected_attack_frames = [
        frames[index]
        for index in (
            groups["attack_bracket"]["frame_indices"]
            + groups["fully_post_attack_pre_release"]["frame_indices"]
        )
    ]
    expected_release_frames = [
        frames[index]
        for index in (
            groups["release_bracket"]["frame_indices"]
            + groups["fully_post_release"]["frame_indices"]
        )
    ]
    try:
        startup_conditioning = _tandem_batch_pre_attack_conditioning(
            frames, pre_indices
        )
        pre_attack_suffix = _tandem_batch_stable_suffix(
            frames,
            pre_indices,
            tolerance_db=capture.settling_tolerance_db,
        )
    except (IndexError, KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem pre-attack conditioning is invalid: {error}")
        startup_conditioning = {}
        pre_attack_suffix = {}
    expected_preconditioning = {
        "frame_count": len(pre_indices),
        "trace_frame_indices": pre_indices,
        "retained_baseline_frame_indices": pre_indices[
            -_TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:
        ],
        "response_anchor_frame_index": pre_indices[-1],
        "auto_initial_gain_db": 62,
        **startup_conditioning,
        "quiet_suffix": pre_attack_suffix,
    }
    if (
        not _release_json_identical(
            mode.get("baseline_frames"), expected_baseline_frames
        )
        or not _release_json_identical(
            mode.get("attack_frames"), expected_attack_frames
        )
        or not _release_json_identical(
            mode.get("release_frames"), expected_release_frames
        )
        or not _release_json_identical(
            mode.get("preconditioning"), expected_preconditioning
        )
    ):
        errors.append("transient tandem retained analysis partitions changed")

    try:
        anchor_stimulus = _release_stimulus_from_record(conditioning_anchor)
        attack_stimulus = _release_stimulus_from_record(attack_command)
        release_stimulus = _release_stimulus_from_record(release_command)
        kwargs = {
            "sample_rate_hz": quality.sample_rate_hz,
            "baseline_windows": capture.baseline_windows,
            "steady_windows": capture.steady_windows,
            "stable_windows": capture.stable_windows,
            "settling_tolerance_db": capture.settling_tolerance_db,
            "ringing_deadband_db": capture.ringing_deadband_db,
            "max_host_jitter_ns": capture.max_host_jitter_ns,
            "max_sample_uncertainty": min(
                capture.max_sample_uncertainty,
                _TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES,
            ),
        }
        recomputed_responses = {
            "attack": dict(
                calculate_transient_response(
                    selected_windows["attack"],
                    previous_command=anchor_stimulus,
                    command=attack_stimulus,
                    **kwargs,
                )
            ),
            "release": dict(
                calculate_transient_response(
                    selected_windows["release"],
                    previous_command=attack_stimulus,
                    command=release_stimulus,
                    **kwargs,
                )
            ),
        }
        for response in recomputed_responses.values():
            response.update(
                {
                    "timing_qualification": "fpga_sample_counter_bounded",
                    "hardware_latency_qualified": True,
                    "transient_observation_scope": (
                        "continuous_hardware_sample_record"
                    ),
                }
            )
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem responses cannot be recomputed: {error}")
    else:
        if not _release_json_identical(
            mode.get("responses"), _json_safe(recomputed_responses)
        ):
            errors.append("transient tandem responses differ from recomputation")

    try:
        visible_events = [
            event for frame in frames for event in frame["metadata"]["gain_events"]
        ]
        recomputed_gain = dict(
            reconcile_tandem_events(
                (anchor_stimulus, attack_stimulus, release_stimulus),
                visible_events,
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=capture.max_host_jitter_ns,
                max_sample_uncertainty=capture.max_sample_uncertainty,
                max_latency_samples=capture.max_event_latency_samples,
            )
        )
        recomputed_gain.update(
            {
                "timing_qualification": "fpga_sample_counter_bounded",
                "hardware_latency_qualified": True,
            }
        )
    except (KeyError, TypeError, ValueError, UnboundLocalError) as error:
        errors.append(f"transient tandem gain evidence cannot be recomputed: {error}")
    else:
        if not _release_json_identical(
            mode.get("gain_evidence"), _json_safe(recomputed_gain)
        ):
            errors.append("transient tandem gain evidence differs from recomputation")
    return errors


def _transient_batch_contract_errors(
    modes: Any,
    capture: TransientCaptureOptions,
    quality: TandemQualityOptions,
    *,
    phase_root: Path,
    serial: str,
) -> list[str]:
    """Independently validate the release-only one-batch tandem v2 contract."""

    if not isinstance(modes, list):
        return ["transient modes are missing"]
    tandem_modes = [
        mode
        for mode in modes
        if isinstance(mode, Mapping) and mode.get("mode") == MODE_TANDEM
    ]
    if len(tandem_modes) != 1:
        return ["transient tandem mode is missing or duplicated"]
    mode = tandem_modes[0]
    errors: list[str] = []
    if set(mode) != {
        "mode",
        "verdict",
        "timing_basis",
        "commands",
        "batch_frames",
        "partition",
        "conditioning_anchor",
        "response_observations",
        "responses",
        "gain_evidence",
        "metadata_request",
        "acquisition",
        "baseline_frames",
        "attack_frames",
        "release_frames",
        "preconditioning",
        "metadata_abi",
        "tandem_status_before",
        "tandem_status_after",
        "final_rx_state",
    }:
        errors.append("transient tandem mode ledger fields changed")
    if (
        quality.tandem_power_measurement_samples * (quality.tandem_cooldown_periods + 1)
        != _TANDEM_BATCH_MINIMUM_EVENT_SPACING_SAMPLES
    ):
        errors.append("transient tandem event-spacing physics policy changed")
    if (
        mode.get("timing_basis") != "hardware_sample_counter"
        or mode.get("metadata_abi") != 2
    ):
        errors.append("transient tandem timing or metadata ABI is inconsistent")
    errors.extend(
        _transient_batch_request_errors(mode.get("metadata_request"), quality)
    )

    acquisition = mode.get("acquisition")
    if not isinstance(acquisition, Mapping):
        return [*errors, "transient tandem batch acquisition ledger is missing"]
    expected_acquisition_fields = {
        "transport",
        "provider_frame_samples",
        "kernel_buffers",
        "batch_frames",
        "queue_capacity_frames",
        "metadata_capacity_bytes",
        "metadata_physics_policy",
        "metadata_abi",
        "configured_batch_frames",
        "configured_batch_cache_bytes",
        "batch_cache_attested",
        "memory_ledger",
        "s0_read",
        "post_open_s0_raw",
        "targets",
        "schedule_diagnostics",
        "schedule_frozen_before_worker_start",
        "schedule_plan",
        "unbound_commands",
        "initiating_batch_refill_calls",
        "public_refill_calls",
        "cached_replay_refill_calls",
        "batch_cache_fully_replayed",
        "initiating_refill_completion_monotonic_ns",
        "produced_frames",
        "consumed_frames",
        "discarded_tail_frames",
        "pre_close_tandem_status",
        "buffer_close_completed",
        "post_close_tandem_status",
        "close_counter_ledger",
        "artifact_manifest",
        "shutdown",
    }
    if set(acquisition) != expected_acquisition_fields:
        errors.append("transient tandem acquisition ledger fields changed")
    memory = _tandem_batch_memory_values()
    reported_memory = acquisition.get("memory_ledger")
    measured_evidence_bytes = (
        reported_memory.get("measured_finished_mode_and_parsed_metadata_bytes")
        if isinstance(reported_memory, Mapping)
        else None
    )
    canonical_projection_bytes = (
        reported_memory.get("canonical_evidence_projection_bytes")
        if isinstance(reported_memory, Mapping)
        else None
    )
    canonical_projection_sha256 = (
        reported_memory.get("canonical_evidence_projection_sha256")
        if isinstance(reported_memory, Mapping)
        else None
    )
    expected_memory_ledger = {
        "core_batch_cache_bytes": memory["batch_cache_bytes"],
        "ordinary_libiio_c_buffer_bytes": memory["iq_frame_bytes"],
        "maximum_python_retained_raw_bytes": memory["maximum_python_raw_bytes"],
        "maximum_python_retained_raw_metadata_bytes": memory[
            "maximum_python_raw_metadata_bytes"
        ],
        "transient_buffer_read_bytearray_bytes": memory["iq_frame_bytes"],
        "ctypes_refill_scratch_bytes": _TANDEM_BATCH_METADATA_CAPACITY_BYTES,
        "returned_metadata_bytes": _TANDEM_BATCH_METADATA_CAPACITY_BYTES,
        "parsed_evidence_reservation_bytes": (
            _TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES
        ),
        "device_k8_dma_reservation_bytes": (
            _TANDEM_BATCH_KERNEL_BUFFERS * memory["iq_frame_bytes"]
        ),
        "post_close_fft_workspace_bytes": memory["post_close_fft_workspace_bytes"],
        "capture_phase_envelope_bytes": memory["capture_phase_envelope_bytes"],
        "post_close_materialization_envelope_bytes": memory[
            "post_close_materialization_envelope_bytes"
        ],
        "maximum_phase_envelope_bytes": memory["maximum_phase_envelope_bytes"],
        "aggregate_resident_bytes": memory["aggregate_resident_bytes"],
        "maximum_aggregate_bytes": _TANDEM_BATCH_MAX_AGGREGATE_BYTES,
        "within_cap": True,
        "measured_finished_mode_and_parsed_metadata_bytes": (measured_evidence_bytes),
        "measured_evidence_within_reservation": True,
        "canonical_evidence_projection_method": (
            _TANDEM_BATCH_EVIDENCE_PROJECTION_METHOD
        ),
        "canonical_evidence_projection_bytes": canonical_projection_bytes,
        "canonical_evidence_projection_sha256": canonical_projection_sha256,
        "accounting_scope": (
            "campaign-owned conservative payload envelope; excludes interpreter, "
            "library and allocator state, thread stacks, JSON serialization, and "
            "page cache"
        ),
        "phase_overlap_policy": (
            "core batch cache and K8 DMA capture precede normal close; the 8MiB "
            "FFT workspace is counted only in the post-close materialization "
            "envelope, and the larger conservative capture envelope governs"
        ),
        "python_raw_ownership": (
            "retained list, queue4, and producer own disjoint frames from the "
            "same exact 64-frame batch"
        ),
    }
    expected_metadata_physics = {
        "protocol_version": _TANDEM_BATCH_METADATA_VERSION,
        "header_bytes": _TANDEM_BATCH_METADATA_HEADER_BYTES,
        "required_features": _TANDEM_BATCH_REQUIRED_METADATA_FEATURES,
        "required_flags": (
            FLAG_SAMPLE_SEQUENCE_VALID
            | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
            | FLAG_TANDEM_METADATA_VALID
        ),
        "sample_format": _TANDEM_BATCH_SAMPLE_FORMAT,
        "observation_capacity": 64,
        "event_capacity": 64,
        "maximum_observations_per_frame": (_TANDEM_BATCH_MAX_OBSERVATIONS_PER_FRAME),
        "maximum_events_per_frame": _TANDEM_BATCH_MAX_EVENTS_PER_FRAME,
        "minimum_event_spacing_samples": (_TANDEM_BATCH_MINIMUM_EVENT_SPACING_SAMPLES),
    }
    if memory != {
        "iq_frame_bytes": 524_288,
        "batch_cache_bytes": 37_749_760,
        "maximum_python_raw_bytes": 33_554_432,
        "maximum_python_raw_metadata_bytes": 4_194_304,
        "post_close_fft_workspace_bytes": 8_388_608,
        "capture_phase_envelope_bytes": 89_261_056,
        "post_close_materialization_envelope_bytes": 54_525_952,
        "maximum_phase_envelope_bytes": 89_261_056,
        "aggregate_resident_bytes": 89_261_056,
    }:
        raise AssertionError("release-side tandem memory constants changed")
    if (
        acquisition.get("transport") != "single_metadata_batch"
        or acquisition.get("provider_frame_samples")
        != _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
        or acquisition.get("kernel_buffers") != _TANDEM_BATCH_KERNEL_BUFFERS
        or acquisition.get("batch_frames") != _TANDEM_BATCH_FRAMES
        or acquisition.get("queue_capacity_frames") != _TANDEM_BATCH_QUEUE_FRAMES
        or acquisition.get("metadata_capacity_bytes")
        != _TANDEM_BATCH_METADATA_CAPACITY_BYTES
        or not _release_json_identical(
            acquisition.get("metadata_physics_policy"), expected_metadata_physics
        )
        or acquisition.get("metadata_abi") != 2
        or acquisition.get("configured_batch_frames") != _TANDEM_BATCH_FRAMES
        or acquisition.get("configured_batch_cache_bytes")
        != memory["batch_cache_bytes"]
        or acquisition.get("batch_cache_attested") is not True
        or not _release_json_identical(
            acquisition.get("memory_ledger"), expected_memory_ledger
        )
        or not _release_exact_int(measured_evidence_bytes, minimum=1)
        or measured_evidence_bytes > _TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES
        or not _release_exact_int(canonical_projection_bytes, minimum=1)
        or canonical_projection_bytes > measured_evidence_bytes
        or re.fullmatch(r"[0-9a-f]{64}", str(canonical_projection_sha256)) is None
    ):
        errors.append("transient tandem transport or memory ledger is inconsistent")

    s0_raw = acquisition.get("post_open_s0_raw")
    s0_read = acquisition.get("s0_read")
    targets = acquisition.get("targets")
    schedules = acquisition.get("schedule_diagnostics")
    if (
        not _release_exact_int(s0_raw)
        or s0_raw >= 1 << 32
        or not isinstance(s0_read, Mapping)
        or set(s0_read) != {"host_before_ns", "host_after_ns", "raw"}
        or not _release_exact_int(s0_read.get("host_before_ns"))
        or not _release_exact_int(s0_read.get("host_after_ns"))
        or s0_read.get("host_after_ns") < s0_read.get("host_before_ns")
        or s0_read.get("raw") != s0_raw
        or not isinstance(targets, Mapping)
        or set(targets) != {"strong_attack", "weak_release"}
        or not isinstance(schedules, Mapping)
        or set(schedules) != {"strong_attack", "weak_release"}
    ):
        errors.append("transient tandem S0, target, or schedule coverage is invalid")
        return errors
    target_plan = {
        "strong_attack": _TANDEM_BATCH_ATTACK_TARGET_FRAMES,
        "weak_release": _TANDEM_BATCH_RELEASE_TARGET_FRAMES,
    }
    for command_id, offset_frames in target_plan.items():
        target = targets.get(command_id)
        expected_target = {
            "offset_frames": offset_frames,
            "offset_samples": (offset_frames * _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES),
            "target_raw": (
                s0_raw + offset_frames * _TANDEM_BATCH_PROVIDER_FRAME_SAMPLES
            )
            % (1 << 32),
        }
        if not _release_json_identical(target, expected_target):
            errors.append(
                f"transient tandem {command_id} frozen target differs from S0"
            )

    commands = mode.get("commands")
    if (
        not isinstance(commands, list)
        or len(commands) != 3
        or any(not isinstance(command, Mapping) for command in commands)
        or [command.get("command_id") for command in commands]
        != ["weak_initial", "strong_attack", "weak_release"]
    ):
        return [*errors, "transient tandem command order differs from policy"]
    initial_command, attack_command, release_command = commands
    assert isinstance(initial_command, Mapping)
    assert isinstance(attack_command, Mapping)
    assert isinstance(release_command, Mapping)
    requested_levels = {
        "weak_initial": capture.weak_stimulus_tx_gain_db,
        "strong_attack": capture.strong_stimulus_tx_gain_db,
        "weak_release": capture.weak_stimulus_tx_gain_db,
    }
    schedule_plan = acquisition.get("schedule_plan")
    schedule_times: list[Any] = []
    if isinstance(schedule_plan, Mapping):
        schedule_times = [
            schedule_plan.get("s0_read_host_after_ns"),
            schedule_plan.get("targets_frozen_host_ns"),
            schedule_plan.get("worker_start_requested_ns"),
            schedule_plan.get("worker_start_returned_ns"),
        ]
    expected_schedule_commands = [
        {
            "command_id": command_id,
            "requested_level_db": requested_levels[command_id],
            **targets[command_id],
        }
        for command_id in ("strong_attack", "weak_release")
        if isinstance(targets.get(command_id), Mapping)
    ]
    if (
        acquisition.get("schedule_frozen_before_worker_start") is not True
        or not isinstance(schedule_plan, Mapping)
        or set(schedule_plan)
        != {
            "s0_read_host_after_ns",
            "targets_frozen_host_ns",
            "worker_start_requested_ns",
            "worker_start_returned_ns",
            "commands",
        }
        or len(schedule_times) != 4
        or any(not _release_exact_int(value) for value in schedule_times)
        or schedule_times != sorted(schedule_times)
        or schedule_plan.get("s0_read_host_after_ns") != s0_read.get("host_after_ns")
        or not _release_json_identical(
            schedule_plan.get("commands"), expected_schedule_commands
        )
        or not _release_exact_int(initial_command.get("host_after_ns"))
        or initial_command.get("host_after_ns") > s0_read.get("host_before_ns")
    ):
        errors.append(
            "transient tandem targets were not durably frozen before worker start"
        )
    attack_schedule = schedules.get("strong_attack")
    attack_tx1 = (
        attack_schedule.get("tx1_mute_assurance")
        if isinstance(attack_schedule, Mapping)
        else None
    )
    attack_tx1_pre = attack_tx1.get("pre") if isinstance(attack_tx1, Mapping) else None
    attack_tx1_pre_start = (
        attack_tx1_pre.get("host_before_ns")
        if isinstance(attack_tx1_pre, Mapping)
        else None
    )
    worker_start_returned_ns = (
        schedule_plan.get("worker_start_returned_ns")
        if isinstance(schedule_plan, Mapping)
        else None
    )
    if (
        not _release_exact_int(worker_start_returned_ns)
        or not _release_exact_int(attack_tx1_pre_start)
        or worker_start_returned_ns > attack_tx1_pre_start
    ):
        errors.append(
            "transient tandem worker start did not precede command scheduling"
        )
    command_common_fields = {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "effective_attenuation_db",
        "rx_state_before",
        "rx_state_after",
        "timing_role",
        "sample_timing_basis",
        "sample_anchor_policy",
    }
    for command in commands:
        command_id = str(command.get("command_id"))
        requested = requested_levels.get(command_id)
        applied = command.get("applied_level_db")
        effective = (
            quality.physical_attenuation_db - float(applied)
            if _release_finite_number(applied)
            else None
        )
        if (
            not _release_json_identical(command.get("requested_level_db"), requested)
            or not _release_finite_number(applied)
            or abs(float(applied) - float(requested)) > capture.readback_tolerance_db
            or not _release_json_identical(
                command.get("effective_attenuation_db"), effective
            )
        ):
            errors.append(f"transient tandem {command_id} gain ledger is inconsistent")
        if effective is not None and effective < 30.0:
            errors.append(
                f"transient tandem {command_id} violates the 30 dB safety boundary"
            )
        expected_command_fields = command_common_fields | (
            {"sample_counter_bracket"} if command_id != "weak_initial" else set()
        )
        if set(command) != expected_command_fields:
            errors.append(
                f"transient tandem {command_id} command record fields changed"
            )
    if (
        not _release_exact_int(initial_command.get("host_before_ns"))
        or not _release_exact_int(initial_command.get("host_after_ns"))
        or initial_command.get("host_after_ns") < initial_command.get("host_before_ns")
        or initial_command.get("host_jitter_ns")
        != initial_command.get("host_after_ns") - initial_command.get("host_before_ns")
        or initial_command.get("host_jitter_ns") > capture.max_host_jitter_ns
        or initial_command.get("sample_sequence_before") is not None
        or initial_command.get("sample_sequence_after") is not None
        or initial_command.get("sample_uncertainty") is not None
        or initial_command.get("rx_state_before") is not None
        or initial_command.get("rx_state_after") is not None
        or initial_command.get("timing_role") != "pre_session_weak_conditioning_write"
        or initial_command.get("sample_timing_basis") is not None
        or initial_command.get("sample_anchor_policy")
        != ("unbounded in hardware sample time; write predates AUTO62 batch ownership")
    ):
        errors.append("transient tandem initial command is not sample-unbounded")

    frames_value = mode.get("batch_frames")
    if not isinstance(frames_value, list) or len(frames_value) != _TANDEM_BATCH_FRAMES:
        return [*errors, "transient tandem batch must contain exactly 64 frames"]
    first_frame = frames_value[0]
    last_frame = frames_value[-1]
    if not isinstance(first_frame, Mapping) or not isinstance(last_frame, Mapping):
        return [*errors, "transient tandem batch endpoints are malformed"]
    first_batch_sample = first_frame.get("first_sample_sequence")
    last_batch_sample_exclusive = last_frame.get("sample_end_exclusive")
    completion_ns = acquisition.get("initiating_refill_completion_monotonic_ns")
    if (
        not _release_exact_int(first_batch_sample)
        or not _release_exact_int(last_batch_sample_exclusive, minimum=1)
        or not _release_exact_int(completion_ns)
        or completion_ns != first_frame.get("refill_monotonic_ns")
    ):
        return [*errors, "transient tandem batch bounds or refill clock are malformed"]

    intervals: dict[str, tuple[int, int]] = {}
    for command_id, command in (
        ("strong_attack", attack_command),
        ("weak_release", release_command),
    ):
        schedule_errors, interval = _transient_batch_schedule_errors(
            schedules[command_id],
            command,
            command_id=command_id,
            requested_level_db=requested_levels[command_id],
            target_frames=target_plan[command_id],
            s0_raw=s0_raw,
            first_batch_sample=first_batch_sample,
            last_batch_sample_exclusive=last_batch_sample_exclusive,
            initiating_refill_completion_ns=completion_ns,
            capture=capture,
        )
        errors.extend(schedule_errors)
        if interval is not None:
            intervals[command_id] = interval
    unbound_commands = acquisition.get("unbound_commands")
    if not isinstance(unbound_commands, Mapping) or set(unbound_commands) != {
        "strong_attack",
        "weak_release",
    }:
        errors.append("transient tandem unbound command ledger is incomplete")
    else:
        for command_id, bound in (
            ("strong_attack", attack_command),
            ("weak_release", release_command),
        ):
            unbound = unbound_commands.get(command_id)
            schedule = schedules.get(command_id)
            write_ack = (
                schedule.get("write_ack") if isinstance(schedule, Mapping) else None
            )
            expected_unbound = {
                "command_id": command_id,
                "requested_level_db": requested_levels[command_id],
                "applied_level_db": bound.get("applied_level_db"),
                "host_before_ns": bound.get("host_before_ns"),
                "host_after_ns": bound.get("host_after_ns"),
                "host_jitter_ns": bound.get("host_jitter_ns"),
                "sample_sequence_before": None,
                "sample_sequence_after": None,
                "sample_uncertainty": None,
                "effective_attenuation_db": bound.get("effective_attenuation_db"),
            }
            if (
                not _release_json_identical(unbound, expected_unbound)
                or not isinstance(schedule, Mapping)
                or schedule.get("applied_level_db") != bound.get("applied_level_db")
                or not isinstance(write_ack, Mapping)
                or write_ack.get("host_before_ns") != bound.get("host_before_ns")
                or write_ack.get("host_after_ns") != bound.get("host_after_ns")
            ):
                errors.append(
                    f"transient tandem {command_id} unbound/bound command changed"
                )
    if set(intervals) != {"strong_attack", "weak_release"}:
        return errors
    attack_lower, attack_upper = intervals["strong_attack"]
    release_lower, release_upper = intervals["weak_release"]
    if not attack_lower < attack_upper <= release_lower < release_upper:
        errors.append("transient tandem attack/release schedules overlap or reorder")
    attack_diagnostics = schedules["strong_attack"]
    release_diagnostics = schedules["weak_release"]
    if isinstance(attack_diagnostics, Mapping) and isinstance(
        release_diagnostics, Mapping
    ):
        attack_post = attack_diagnostics.get("tx1_mute_assurance")
        release_pre = release_diagnostics.get("tx1_mute_assurance")
        attack_post_record = (
            attack_post.get("post") if isinstance(attack_post, Mapping) else None
        )
        release_pre_record = (
            release_pre.get("pre") if isinstance(release_pre, Mapping) else None
        )
        initial_after = initial_command.get("host_after_ns")
        attack_write = attack_diagnostics.get("write_ack")
        attack_pre_record = (
            attack_post.get("pre") if isinstance(attack_post, Mapping) else None
        )
        attack_pre_start = (
            attack_pre_record.get("host_before_ns")
            if isinstance(attack_pre_record, Mapping)
            else None
        )
        attack_post_end = (
            attack_post_record.get("host_after_ns")
            if isinstance(attack_post_record, Mapping)
            else None
        )
        release_pre_start = (
            release_pre_record.get("host_before_ns")
            if isinstance(release_pre_record, Mapping)
            else None
        )
        attack_write_end = (
            attack_write.get("host_after_ns")
            if isinstance(attack_write, Mapping)
            else None
        )
        release_write_start = release_command.get("host_before_ns")
        if (
            not isinstance(attack_post_record, Mapping)
            or not isinstance(release_pre_record, Mapping)
            or not isinstance(attack_pre_record, Mapping)
            or not isinstance(attack_write, Mapping)
            or not _release_exact_int(initial_after)
            or not _release_exact_int(attack_pre_start)
            or not _release_exact_int(attack_post_end)
            or not _release_exact_int(release_pre_start)
            or not _release_exact_int(attack_write_end)
            or not _release_exact_int(release_write_start)
            or initial_after > attack_pre_start
            or attack_post_end > release_pre_start
            or attack_write_end > release_write_start
        ):
            errors.append(
                "transient tandem initial/attack/release host chronology is inconsistent"
            )

    try:
        phases, expected_groups = _tandem_batch_partition(
            [frame for frame in frames_value if isinstance(frame, Mapping)],
            attack_lower=attack_lower,
            attack_upper=attack_upper,
            release_lower=release_lower,
            release_upper=release_upper,
        )
    except ValueError as error:
        return [*errors, f"transient tandem partition cannot be recomputed: {error}"]
    partition = mode.get("partition")
    stable_suffixes: dict[str, Any] = {}
    for phase in (
        "fully_pre_attack",
        "fully_post_attack_pre_release",
        "fully_post_release",
    ):
        try:
            stable_suffixes[phase] = _tandem_batch_stable_suffix(
                [frame for frame in frames_value if isinstance(frame, Mapping)],
                expected_groups[phase]["frame_indices"],
                tolerance_db=capture.settling_tolerance_db,
            )
        except (IndexError, KeyError, TypeError, ValueError) as error:
            errors.append(f"transient tandem {phase} stable suffix is invalid: {error}")
    try:
        pre_attack_conditioning = _tandem_batch_pre_attack_conditioning(
            [frame for frame in frames_value if isinstance(frame, Mapping)],
            expected_groups["fully_pre_attack"]["frame_indices"],
        )
    except (IndexError, KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem pre-attack conditioning is invalid: {error}")
        pre_attack_conditioning = {}
    try:
        rf_quality_policy = _tandem_batch_rf_quality_policy(
            [frame for frame in frames_value if isinstance(frame, Mapping)],
            stable_suffixes,
        )
    except (IndexError, KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem RF quality policy is invalid: {error}")
        rf_quality_policy = {}
    expected_partition = {
        "phase_order": list(_TANDEM_BATCH_PHASE_ORDER),
        "phase_by_frame": phases,
        "groups": expected_groups,
        "minimum_required_fully_pre_attack_frames": (
            _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES
        ),
        "minimum_required_fully_post_attack_pre_release_frames": (
            _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES
        ),
        "minimum_required_fully_post_release_frames": (
            _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES
        ),
        "frame_count": _TANDEM_BATCH_FRAMES,
        "pre_attack_conditioning": pre_attack_conditioning,
        "stable_suffixes": stable_suffixes,
        "rf_quality_policy": rf_quality_policy,
    }
    if not _release_json_identical(partition, expected_partition):
        errors.append("transient tandem five-way partition differs from recomputation")
    pre_attack_endpoint = stable_suffixes.get("fully_pre_attack", {}).get(
        "bench_gain_indices"
    )
    middle_endpoint = stable_suffixes.get("fully_post_attack_pre_release", {}).get(
        "bench_gain_indices"
    )
    final_endpoint = stable_suffixes.get("fully_post_release", {}).get(
        "bench_gain_indices"
    )
    endpoint_triplet = (pre_attack_endpoint, middle_endpoint, final_endpoint)
    if any(
        not isinstance(endpoint, list)
        or len(endpoint) != 2
        or any(not _release_exact_int(value) for value in endpoint)
        or endpoint[0] != endpoint[1]
        for endpoint in endpoint_triplet
    ) or not all(
        middle_endpoint[channel] < pre_attack_endpoint[channel]
        and final_endpoint[channel] > middle_endpoint[channel]
        for channel in (0, 1)
    ):
        errors.append(
            "transient tandem stable endpoints do not prove the commanded "
            "attack decrease and release increase"
        )
    for phase in (
        "fully_pre_attack",
        "fully_post_attack_pre_release",
        "fully_post_release",
    ):
        if expected_groups[phase]["count"] < _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES:
            errors.append(f"transient tandem partition {phase} lacks eight frames")
    if (
        not expected_groups["attack_bracket"]["count"]
        or not expected_groups["release_bracket"]["count"]
    ):
        errors.append("transient tandem command bracket lacks a retained frame")

    frame_errors, frames = _transient_batch_frame_errors(
        frames_value,
        phases=phases,
        quality=quality,
    )
    errors.extend(frame_errors)
    if frame_errors:
        return errors
    artifact_manifest: dict[str, Any] | None = None
    reparsed_metadata: tuple[Any, ...] = ()
    if frames:
        sidecar_errors, artifact_manifest, reparsed_metadata = (
            _transient_batch_sidecar_errors(
                frames,
                phase_root=phase_root,
                serial=serial,
                quality=quality,
            )
        )
        errors.extend(sidecar_errors)
        if sidecar_errors:
            return errors
        canonical_mode = dict(mode)
        frames_by_index = {
            frame.get("frame_index"): frame
            for frame in frames
            if _release_exact_int(frame.get("frame_index"))
        }
        for key in ("attack_frames", "release_frames"):
            selected = mode.get(key)
            if isinstance(selected, list) and all(
                isinstance(frame, Mapping)
                and frame.get("frame_index") in frames_by_index
                for frame in selected
            ):
                canonical_mode[key] = [
                    frames_by_index[frame["frame_index"]] for frame in selected
                ]
        conditioning = mode.get("conditioning_anchor")
        source = (
            conditioning.get("source") if isinstance(conditioning, Mapping) else None
        )
        if isinstance(source, Mapping) and mode.get("baseline_frames") == [source]:
            canonical_mode["baseline_frames"] = [source]
            observations = mode.get("response_observations")
            if isinstance(observations, Mapping):
                canonical_observations = dict(observations)
                attack_observation = observations.get("attack")
                if (
                    isinstance(attack_observation, Mapping)
                    and attack_observation.get("baseline_anchor") == source
                ):
                    canonical_attack = dict(attack_observation)
                    canonical_attack["baseline_anchor"] = source
                    canonical_observations["attack"] = canonical_attack
                    canonical_mode["response_observations"] = canonical_observations
        manifest_value = acquisition.get("artifact_manifest")
        if isinstance(manifest_value, Mapping) and isinstance(
            manifest_value.get("entries"), list
        ):
            canonical_entries: list[Any] = []
            for entry in manifest_value["entries"]:
                canonical_entry = dict(entry) if isinstance(entry, Mapping) else entry
                frame_index = (
                    entry.get("frame_index") if isinstance(entry, Mapping) else None
                )
                frame = frames_by_index.get(frame_index)
                if (
                    isinstance(canonical_entry, dict)
                    and isinstance(frame, Mapping)
                    and canonical_entry.get("write_status")
                    == frame.get("artifact_write_status")
                ):
                    canonical_entry["write_status"] = frame["artifact_write_status"]
                canonical_entries.append(canonical_entry)
            canonical_manifest = dict(manifest_value)
            canonical_manifest["entries"] = canonical_entries
            canonical_acquisition = dict(acquisition)
            canonical_acquisition["artifact_manifest"] = canonical_manifest
            canonical_mode["acquisition"] = canonical_acquisition
        independently_measured_evidence_bytes = _release_recursive_evidence_bytes(
            (canonical_mode, reparsed_metadata)
        )
        try:
            canonical_evidence = _release_canonical_tandem_evidence_bytes(
                mode, reparsed_metadata
            )
        except (TypeError, ValueError) as error:
            errors.append(
                f"transient tandem canonical evidence cannot be encoded: {error}"
            )
            canonical_evidence = b""
        canonical_digest = hashlib.sha256(canonical_evidence).hexdigest()
        if (
            len(reparsed_metadata) != _TANDEM_BATCH_FRAMES
            or independently_measured_evidence_bytes
            > _TANDEM_BATCH_PARSED_EVIDENCE_RESERVATION_BYTES
            or not _release_exact_int(measured_evidence_bytes, minimum=1)
            or len(canonical_evidence) != canonical_projection_bytes
            or canonical_digest != canonical_projection_sha256
            or len(canonical_evidence) > measured_evidence_bytes
        ):
            errors.append(
                "transient tandem canonical/live evidence does not fit its "
                "8MiB reservation"
            )
        errors.extend(
            _transient_batch_analysis_summary_errors(
                mode,
                frames,
                groups=expected_groups,
                attack_command=attack_command,
                release_command=release_command,
                phase_root=phase_root,
                serial=serial,
                capture=capture,
                quality=quality,
            )
        )
    if (
        artifact_manifest is None
        or acquisition.get("artifact_manifest") != artifact_manifest
    ):
        errors.append("transient tandem aggregate artifact manifest changed")
    if (
        acquisition.get("initiating_batch_refill_calls") != 1
        or acquisition.get("public_refill_calls") != _TANDEM_BATCH_FRAMES
        or acquisition.get("cached_replay_refill_calls") != _TANDEM_BATCH_FRAMES - 1
        or acquisition.get("batch_cache_fully_replayed") is not True
        or acquisition.get("produced_frames") != _TANDEM_BATCH_FRAMES
        or acquisition.get("consumed_frames") != _TANDEM_BATCH_FRAMES
        or acquisition.get("discarded_tail_frames") != 0
    ):
        errors.append("transient tandem full 1+63 replay ledger is inconsistent")

    shutdown = acquisition.get("shutdown")
    if not isinstance(shutdown, Mapping):
        errors.append("transient tandem shutdown ledger is missing")
    elif (
        set(shutdown)
        != {
            "events",
            "worker_in_flight_before_shutdown",
            "cancel_required",
            "cancel_called",
            "cancel_succeeded",
            "worker_stopped",
            "batch_fully_consumed",
            "shutdown_path",
        }
        or shutdown.get("worker_in_flight_before_shutdown") is not False
        or shutdown.get("cancel_required") is not False
        or shutdown.get("cancel_called") is not False
        or shutdown.get("cancel_succeeded") is not None
        or shutdown.get("worker_stopped") is not True
        or shutdown.get("batch_fully_consumed") is not True
        or shutdown.get("shutdown_path") != "normal_close_after_full_cache_replay"
        or not isinstance(shutdown.get("events"), list)
    ):
        errors.append("transient tandem normal-close shutdown ledger is inconsistent")
    else:
        previous_event_ns: int | None = None
        if [
            event.get("event") if isinstance(event, Mapping) else None
            for event in shutdown["events"]
        ] != [
            "prejoin_mute_start",
            "prejoin_mute_complete",
            "worker_stop_start",
            "worker_stop_complete",
        ]:
            errors.append("transient tandem successful shutdown stages changed")
        last_refill_ns = frames[-1].get("refill_monotonic_ns") if frames else None
        first_shutdown_ns = (
            shutdown["events"][0].get("monotonic_ns")
            if shutdown["events"] and isinstance(shutdown["events"][0], Mapping)
            else None
        )
        if (
            not _release_exact_int(last_refill_ns)
            or not _release_exact_int(first_shutdown_ns)
            or first_shutdown_ns < last_refill_ns
        ):
            errors.append(
                "transient tandem shutdown began before full cache replay completed"
            )
        for index, event in enumerate(shutdown["events"]):
            if (
                not isinstance(event, Mapping)
                or set(event) != {"event", "monotonic_ns"}
                or not isinstance(event.get("event"), str)
                or not _release_exact_int(event.get("monotonic_ns"))
                or (
                    previous_event_ns is not None
                    and event["monotonic_ns"] < previous_event_ns
                )
            ):
                errors.append(
                    f"transient tandem shutdown event {index} is inconsistent"
                )
                break
            previous_event_ns = event["monotonic_ns"]
        if any(
            event.get("event", "").startswith("cancel")
            for event in shutdown["events"]
            if isinstance(event, Mapping)
        ):
            errors.append("transient tandem successful shutdown unexpectedly cancelled")

    status_fields = {
        "state",
        "fault_flags",
        "overflow_count",
        "fifo_level",
        "ownership_epoch",
        "transition_count",
        "rx1_gain_index",
        "rx2_gain_index",
    }
    pre_close = acquisition.get("pre_close_tandem_status")
    post_close = acquisition.get("post_close_tandem_status")
    tandem_before = mode.get("tandem_status_before")
    last_transition_count: int | None = None
    if frames:
        last_metadata = frames[-1].get("metadata")
        if isinstance(last_metadata, Mapping) and _release_exact_int(
            last_metadata.get("tandem_transition_count")
        ):
            last_transition_count = int(last_metadata["tandem_transition_count"])
    if (
        not isinstance(pre_close, Mapping)
        or set(pre_close) != status_fields
        or any(not _release_exact_int(value) for value in pre_close.values())
        or pre_close.get("state") != int(TandemState.ARMED_AUTO)
        or pre_close.get("fault_flags") != 0
        or pre_close.get("overflow_count") != 0
        or pre_close.get("ownership_epoch", 0) <= 0
        or pre_close.get("fifo_level", 65) > 64
        or pre_close.get("rx1_gain_index") != pre_close.get("rx2_gain_index")
        or pre_close.get("rx1_gain_index", 128) > 127
        or pre_close.get("transition_count", 1 << 32) >= 1 << 32
    ):
        errors.append("transient tandem pre-close owned status is inconsistent")
    if (
        isinstance(pre_close, Mapping)
        and last_transition_count is not None
        and _release_exact_int(pre_close.get("transition_count"))
    ):
        frame_to_preclose_delta = (
            int(pre_close["transition_count"]) - last_transition_count
        ) % (1 << 32)
        if frame_to_preclose_delta > 64:
            errors.append(
                "transient tandem last-frame to pre-close transition delta is "
                "ambiguous or excessive"
            )
    if (
        acquisition.get("buffer_close_completed") is not True
        or not isinstance(post_close, Mapping)
        or set(post_close) != status_fields
        or any(not _release_exact_int(value) for value in post_close.values())
        or post_close.get("state") != int(TandemState.IDLE)
        or post_close.get("fault_flags") != 0
        or post_close.get("overflow_count") != 0
        or post_close.get("fifo_level") != 0
        or post_close.get("ownership_epoch") != 0
        or post_close.get("rx1_gain_index") != post_close.get("rx2_gain_index")
        or post_close.get("rx1_gain_index", 128) > 127
        or post_close.get("transition_count", 1 << 32) >= 1 << 32
    ):
        errors.append("transient tandem post-close status is not safely unowned IDLE")
    close_ledger = acquisition.get("close_counter_ledger")
    last_metadata = frames[-1].get("metadata") if frames else None
    close_inputs_valid = (
        isinstance(pre_close, Mapping)
        and isinstance(post_close, Mapping)
        and isinstance(last_metadata, Mapping)
        and _release_exact_int(last_transition_count)
        and _release_exact_int(pre_close.get("transition_count"))
        and pre_close.get("transition_count") < 1 << 32
        and _release_exact_int(post_close.get("transition_count"))
        and post_close.get("transition_count") < 1 << 32
    )
    if close_inputs_valid:
        assert isinstance(pre_close, Mapping)
        assert isinstance(post_close, Mapping)
        assert isinstance(last_metadata, Mapping)
        assert isinstance(last_transition_count, int)
        frame_delta = (int(pre_close["transition_count"]) - last_transition_count) % (
            1 << 32
        )
        close_delta = (
            int(post_close["transition_count"]) - int(pre_close["transition_count"])
        ) % (1 << 32)
        expected_close_ledger = {
            "last_frame_transition_count": last_transition_count,
            "pre_transition_count": pre_close.get("transition_count"),
            "post_transition_count": post_close.get("transition_count"),
            "last_frame_to_pre_close_forward_delta": frame_delta,
            "transition_count_forward_delta": close_delta,
            "maximum_forward_delta": 64,
            "pre_fifo_level": pre_close.get("fifo_level"),
            "post_fifo_level": post_close.get("fifo_level"),
            "pre_endpoint": [
                pre_close.get("rx1_gain_index"),
                pre_close.get("rx2_gain_index"),
            ],
            "post_endpoint": [
                post_close.get("rx1_gain_index"),
                post_close.get("rx2_gain_index"),
            ],
            "exact_retired_tail_count_claim": None,
            "policy": (
                "preserve forward modulo-u32 diagnostics across RELEASE without "
                "claiming an exact retired FIFO tail count"
            ),
        }
        endpoint = last_metadata.get("bench_gain_indices")
        index_range = last_metadata.get("gain_index_range")
        endpoint_values = (
            [endpoint[0]] if isinstance(endpoint, list) and len(endpoint) == 2 else []
        ) + [
            pre_close.get("rx1_gain_index"),
            post_close.get("rx1_gain_index"),
        ]
        endpoint_policy_valid = (
            isinstance(index_range, list)
            and len(index_range) == 2
            and all(_release_exact_int(value) for value in index_range)
            and all(_release_exact_int(value) for value in endpoint_values)
            and all(
                index_range[0] <= value <= index_range[1] for value in endpoint_values
            )
            and abs(endpoint_values[1] - endpoint_values[0]) <= frame_delta
            and (frame_delta - abs(endpoint_values[1] - endpoint_values[0])) % 2 == 0
            and abs(endpoint_values[2] - endpoint_values[1]) <= close_delta
            and (close_delta - abs(endpoint_values[2] - endpoint_values[1])) % 2 == 0
        )
        if (
            frame_delta > 64
            or close_delta > 64
            or not _release_json_identical(close_ledger, expected_close_ledger)
            or pre_close.get("ownership_epoch") != last_metadata.get("ownership_epoch")
            or not endpoint_policy_valid
        ):
            errors.append(
                "transient tandem close counter/endpoint ledger is inconsistent"
            )
    else:
        errors.append("transient tandem close counter ledger cannot be recomputed")
    if (
        not isinstance(tandem_before, Mapping)
        or set(tandem_before) != status_fields
        or any(not _release_exact_int(value) for value in tandem_before.values())
        or tandem_before.get("state") != int(TandemState.IDLE)
        or tandem_before.get("fault_flags") != 0
        or tandem_before.get("overflow_count") != 0
        or tandem_before.get("fifo_level") != 0
        or tandem_before.get("ownership_epoch") != 0
        or tandem_before.get("transition_count", 1 << 32) >= 1 << 32
        or tandem_before.get("rx1_gain_index") != tandem_before.get("rx2_gain_index")
        or tandem_before.get("rx1_gain_index", 128) > 127
    ):
        errors.append("transient tandem pre-session status is not safely unowned IDLE")
    tandem_after = mode.get("tandem_status_after")
    if isinstance(post_close, Mapping) and tandem_after != post_close:
        errors.append(
            "transient tandem post-close status changed before mode completion"
        )

    return errors


def _identity_errors(
    report: Mapping[str, Any], options: ReleaseHardwareOptions
) -> list[str]:
    identity = report.get("identity")
    if not isinstance(identity, Mapping):
        return ["identity is missing"]
    errors = []
    if identity.get("serial") != options.serial:
        errors.append("serial differs from plan")
    if identity.get("libiio_source_commit") != options.libiio_source_commit:
        errors.append("host libiio commit differs from plan")
    attrs = identity.get("context_attrs")
    if (
        not isinstance(attrs, Mapping)
        or attrs.get("fw_version") != options.firmware_version
    ):
        errors.append("firmware version differs from exact plan")
    uri = identity.get("uri")
    if not isinstance(uri, str) or not uri.startswith("usb:"):
        errors.append("radio transport is not dynamically resolved local USB")
    return errors


def _soak_temperature_errors(
    options: ReleaseHardwareOptions, records: Mapping[str, Any]
) -> list[str]:
    if options.policy_set != "baseline":
        return []
    errors = []
    for run_id, record in records.items():
        if record.get("status") != "complete":
            continue
        temperature = record.get("summary", {}).get("temperature")
        if (
            not isinstance(temperature, Mapping)
            or temperature.get("available") is not True
            or type(temperature.get("count")) is not int
            or temperature["count"] <= 0
        ):
            errors.append(f"baseline soak run {run_id} lacks temperature evidence")
    return errors


def _diagnostic_failure_iq_errors(
    report: Mapping[str, Any],
    *,
    work_dir: Path,
    expected_options: TandemQualityOptions,
) -> tuple[list[str], dict[str, Any] | None]:
    """Replay the bounded write-on-failure IQ ledger for the 2.45 GHz diagnostic."""

    errors: list[str] = []
    raw_evidence = report.get("failure_evidence")
    if not isinstance(raw_evidence, Mapping):
        return ["failed diagnostic lacks failure evidence"], None
    raw_ledger = raw_evidence.get("iq_ledger")
    if not isinstance(raw_ledger, Mapping):
        return ["failed diagnostic lacks its IQ ledger"], None
    ledger = dict(raw_ledger)
    manifest_relative = ledger.get("manifest_relative_path")
    manifest_sha256 = ledger.get("manifest_sha256")
    if (
        manifest_relative != "failure-iq-manifest.json"
        or not isinstance(manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
    ):
        errors.append("diagnostic IQ manifest identity is malformed")
        return errors, ledger
    manifest_path = work_dir / manifest_relative
    try:
        _require_nonsymlink_descendant(
            manifest_path, work_dir, label="diagnostic IQ manifest"
        )
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError, ReleaseCliError) as error:
        errors.append(f"diagnostic IQ manifest cannot be read safely: {error}")
        return errors, ledger
    expected_manifest = {
        key: value
        for key, value in ledger.items()
        if key not in {"manifest_relative_path", "manifest_sha256"}
    }
    if (
        hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256
        or manifest != expected_manifest
        or ledger.get("schema") != "plutosdr-fw.tandem-agc-failure-iq.v1"
        or ledger.get("maximum_bytes") != 128 * 1024 * 1024
        or ledger.get("tandem_detail_maximum_bytes") != 32 * 1024 * 1024
    ):
        errors.append("diagnostic IQ manifest bytes or bounds differ from its ledger")
    planned_frames = (
        len(quality_modes(expected_options))
        * len(expected_options.tx_gain_trajectory_db)
        * expected_options.measurement_frames
    )
    expected_frame_bytes = expected_options.samples_per_channel * 8
    if ledger.get("preflight") != {
        "planned_accepted_frames": planned_frames,
        "reserved_offending_frames": 1,
        "expected_frame_bytes": expected_frame_bytes,
        "required_bytes": (planned_frames + 1) * expected_frame_bytes,
    }:
        errors.append("diagnostic IQ preflight differs from the exact matrix")
    evaluation = report.get("evaluation")
    expected_failures = (
        list(evaluation.get("failures", [])) if isinstance(evaluation, Mapping) else []
    )
    if ledger.get("trigger") != {
        "kind": "matrix_evaluation_failed",
        "failures": expected_failures,
    }:
        errors.append("diagnostic IQ trigger differs from the RF-quality failure")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or len(entries) != planned_frames:
        errors.append("diagnostic IQ ledger does not cover every accepted frame")
        return errors, ledger
    seen_paths: set[str] = set()
    retained_bytes = 0
    for ordinal, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, Mapping):
            errors.append("diagnostic IQ ledger contains a non-record entry")
            continue
        relative = raw_entry.get("relative_path")
        digest = raw_entry.get("sha256")
        if (
            raw_entry.get("ordinal") != ordinal
            or raw_entry.get("role") != "accepted_measurement"
            or raw_entry.get("bytes") != expected_frame_bytes
            or not isinstance(relative, str)
            or not relative.startswith("failure-iq/accepted-")
            or relative in seen_paths
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            errors.append(f"diagnostic IQ entry {ordinal} is malformed")
            continue
        seen_paths.add(relative)
        path = work_dir / relative
        try:
            _require_nonsymlink_descendant(
                path, work_dir, label=f"diagnostic IQ entry {ordinal}"
            )
            payload = path.read_bytes()
        except (OSError, ReleaseCliError) as error:
            errors.append(f"diagnostic IQ entry {ordinal} is unsafe: {error}")
            continue
        if (
            len(payload) != expected_frame_bytes
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            errors.append(f"diagnostic IQ entry {ordinal} bytes changed")
        retained_bytes += len(payload)
    if ledger.get("retained_bytes") != retained_bytes:
        errors.append("diagnostic IQ retained-byte total is inconsistent")
    return errors, ledger


def production_validator(options: ReleaseHardwareOptions) -> PhaseValidator:
    def validate(spec: PhaseSpec, path: Path, work_dir: Path) -> ValidatedPhase:
        _assert_harness_unchanged(options)

        def reject_nonfinite_json(value: str) -> None:
            raise ValueError(f"non-finite JSON constant {value!r}")

        try:
            disk = json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=reject_nonfinite_json,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ReleaseCliError("phase report is not strict finite JSON") from error
        if not isinstance(disk, Mapping):
            raise ReleaseCliError("phase report root is not a JSON object")

        def contains_nonfinite(value: Any) -> bool:
            if isinstance(value, float):
                return not math.isfinite(value)
            if isinstance(value, Mapping):
                return any(contains_nonfinite(item) for item in value.values())
            if isinstance(value, list):
                return any(contains_nonfinite(item) for item in value)
            return False

        if contains_nonfinite(disk):
            raise ReleaseCliError("phase report is not strict finite JSON")
        if spec.kind == "steady":
            config, base = _steady_inputs(options, work_dir)
            plan = build_release_plan(config, base)
            checkpoint_path = work_dir / steady_campaign.CHECKPOINT_NAME
            if path != (work_dir / steady_campaign.REPORT_NAME).resolve():
                raise ReleaseCliError("steady report path differs from plan")
            checkpoint = steady_campaign._load_checkpoint(checkpoint_path, plan)
            steady_campaign._verify_completed_artifacts(plan, checkpoint)
            expected = build_campaign_report(plan, checkpoint, config)
            if disk != expected:
                raise ReleaseCliError("steady report differs from its checkpoint")
            identity_failures: list[str] = []
            cleanup_failures: list[str] = []
            complete = 0
            for run, record in zip(plan.runs, checkpoint["runs"].values(), strict=True):
                if record["status"] != "complete":
                    continue
                complete += 1
                child = json.loads(Path(record["report_path"]).read_text())
                identity_failures.extend(_identity_errors(child, options))
                cleanup_failures.extend(_cleanup_errors(child))
                if (
                    child.get("rf", {}).get("center_frequency_hz_requested")
                    != run.band.center_frequency_hz
                ):
                    identity_failures.append("steady RF band differs from plan")
            if identity_failures or cleanup_failures:
                raise ReleaseCliError(
                    "; ".join((*identity_failures, *cleanup_failures))
                )
            temperature_failures = _soak_temperature_errors(options, checkpoint["runs"])
            if temperature_failures:
                raise ReleaseCliError("; ".join(temperature_failures))
            verdict = str(disk.get("verdict"))
            cleanup_verified = verdict == "pass" and complete == len(plan.runs)
            return ValidatedPhase(
                verdict,
                cleanup_verified,
                {
                    "campaign_kind": _configuration(options)["steady_campaign_kind"],
                    "policy_set": options.policy_set,
                    "complete_runs": complete,
                    "planned_runs": len(plan.runs),
                    "temperature": disk.get("temperature"),
                    "repeatability": disk.get("repeatability"),
                },
            )
        if spec.kind == "diagnostic":
            assert spec.band == DIAGNOSTIC_BAND
            expected_options = _base_quality(
                options, output_dir=work_dir, band=DIAGNOSTIC_BAND
            )
            expected_path = (
                work_dir / options.serial / "tandem-agc-quality-report.json"
            ).resolve()
            errors: list[str] = []
            if path != expected_path or path.parent.is_symlink():
                errors.append("2.45 GHz diagnostic report path differs from plan")
            if (
                disk.get("schema") != "plutosdr-fw.tandem-agc-quality.v1"
                or disk.get("verdict") not in {"pass", "fail"}
                or "fatal_error" in disk
                or "cleanup_error" in disk
            ):
                errors.append(
                    "2.45 GHz diagnostic is not a completed RF-quality report"
                )
            errors.extend(_identity_errors(disk, options))
            errors.extend(_cleanup_errors(disk))
            rf = disk.get("rf")
            if (
                not isinstance(rf, Mapping)
                or rf.get("center_frequency_hz_requested")
                != DIAGNOSTIC_BAND.center_frequency_hz
                or rf.get("expected_tandem_gain_table_id") != 2
            ):
                errors.append("2.45 GHz diagnostic RF identity differs from plan")
            expected_configuration = _json_safe(
                {
                    **asdict(expected_options),
                    "output_dir": str(work_dir),
                    "thresholds": asdict(expected_options.thresholds),
                    "minimum_effective_attenuation_db": (
                        expected_options.minimum_effective_attenuation_db
                    ),
                }
            )
            if disk.get("configuration") != expected_configuration:
                errors.append("2.45 GHz diagnostic configuration differs from plan")
            observed_modes = [
                item.get("mode")
                for item in disk.get("modes", [])
                if isinstance(item, Mapping)
            ]
            if observed_modes != list(quality_modes(expected_options)):
                errors.append("2.45 GHz diagnostic mode coverage differs from plan")
            preflight = disk.get("manual_fixture_preflight")
            if not isinstance(preflight, Mapping) or preflight.get("valid") is not True:
                errors.append("2.45 GHz diagnostic did not pass fixture preflight")
            try:
                recomputed = _json_safe(evaluate_matrix(disk))
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                errors.append(f"2.45 GHz diagnostic cannot be recomputed: {error}")
                recomputed = None
            if recomputed is not None and disk.get("evaluation") != recomputed:
                errors.append(
                    "2.45 GHz diagnostic evaluation differs from recomputation"
                )
            report_verdict = disk.get("verdict")
            if isinstance(recomputed, Mapping) and report_verdict != recomputed.get(
                "verdict"
            ):
                errors.append("2.45 GHz diagnostic verdict differs from evaluation")
            iq_ledger: dict[str, Any] | None = None
            if report_verdict == "fail":
                iq_errors, iq_ledger = _diagnostic_failure_iq_errors(
                    disk, work_dir=work_dir, expected_options=expected_options
                )
                errors.extend(iq_errors)
            elif (work_dir / "failure-iq-manifest.json").exists():
                errors.append("passing 2.45 GHz diagnostic retained failure-only IQ")
            if errors:
                raise ReleaseCliError("; ".join(errors))
            phase_verdict = (
                DIAGNOSTIC_PASS if report_verdict == "pass" else DIAGNOSTIC_FAIL
            )
            evaluation = disk["evaluation"]
            return ValidatedPhase(
                phase_verdict,
                True,
                {
                    "role": "non_authorizing_rf_quality_diagnostic",
                    "center_frequency_hz": DIAGNOSTIC_BAND.center_frequency_hz,
                    "outcome": phase_verdict,
                    "rf_quality_failures": list(evaluation.get("failures", [])),
                    "failure_iq_manifest_sha256": (
                        None if iq_ledger is None else iq_ledger["manifest_sha256"]
                    ),
                    "release_claim": "none_at_2_4_ghz",
                },
            )
        expected_schema = {
            "transient": "plutosdr-fw.tandem-agc-transient.v2",
            "modulated": "plutosdr-fw.modulated-hardware.v1",
        }[spec.kind]
        errors = []
        if disk.get("schema") != expected_schema or disk.get("verdict") != "pass":
            errors.append("phase schema or verdict is invalid")
        errors.extend(_identity_errors(disk, options))
        errors.extend(_cleanup_errors(disk))
        assert spec.band is not None
        rf = disk.get("rf")
        if (
            not isinstance(rf, Mapping)
            or rf.get("center_frequency_hz_requested") != spec.band.center_frequency_hz
        ):
            errors.append("phase RF band differs from plan")
        if spec.kind == "transient":
            expected_transient_fields = {
                "schema",
                "started_unix_ns",
                "identity",
                "bench_port_mapping",
                "trajectory_db",
                "required_modes",
                "rf",
                "configuration",
                "safety",
                "evidence_policy",
                "modes",
                "failure_evidence",
                "comparison",
                "verdict",
                "elapsed_seconds",
                "completed_unix_ns",
                "cleanup",
            }
            if (
                set(disk) != expected_transient_fields
                or disk.get("failure_evidence") is not None
                or not _release_exact_int(disk.get("started_unix_ns"))
                or not _release_exact_int(disk.get("completed_unix_ns"))
                or disk.get("completed_unix_ns") < disk.get("started_unix_ns")
                or not _release_finite_number(disk.get("elapsed_seconds"))
                or disk.get("elapsed_seconds") < 0
            ):
                errors.append("transient top-level PASS ledger is inconsistent")
            if disk.get("bench_port_mapping") != {
                "stimulus": "bench TX2 = AD9361/IIO TX2",
                "receivers": [
                    "bench RX0 = AD9361/IIO RX1",
                    "bench RX1 = AD9361/IIO RX2",
                ],
            }:
                errors.append("transient bench port mapping differs from plan")
            expected_report_path = (
                work_dir / options.serial / "tandem-agc-transient-report.json"
            ).resolve()
            if path != expected_report_path or path.parent.is_symlink():
                errors.append("transient report path differs from its phase plan")
            transient_quality = _base_quality(
                options, output_dir=work_dir, band=spec.band
            )
            center_readback = (
                rf.get("center_frequency_hz_readback")
                if isinstance(rf, Mapping)
                else None
            )
            if (
                not isinstance(rf, Mapping)
                or rf.get("center_frequency_hz_requested")
                != transient_quality.center_frequency_hz
                or rf.get("tone_hz") != transient_quality.tone_hz
                or rf.get("dds_scale") != transient_quality.dds_scale
                or not isinstance(center_readback, Mapping)
                or any(
                    type(center_readback.get(name)) is not int
                    or abs(
                        center_readback[name] - transient_quality.center_frequency_hz
                    )
                    > 2
                    for name in ("rx_lo_hz", "tx_lo_hz")
                )
            ):
                errors.append("transient RF readback differs from plan")
            expected_quality = _json_safe(asdict(transient_quality))
            assert isinstance(expected_quality, dict)
            expected_quality["output_dir"] = str(work_dir)
            expected_capture = TransientCaptureOptions()
            expected_trajectory = [
                expected_capture.weak_stimulus_tx_gain_db,
                expected_capture.strong_stimulus_tx_gain_db,
                expected_capture.weak_stimulus_tx_gain_db,
            ]
            if disk.get("trajectory_db") != expected_trajectory:
                errors.append("transient stimulus trajectory differs from plan")
            expected_safety = {
                "physical_attenuation_db": transient_quality.physical_attenuation_db,
                "strongest_tx_gain_db": (expected_capture.strong_stimulus_tx_gain_db),
                "minimum_effective_attenuation_db": (
                    transient_quality.physical_attenuation_db
                    - expected_capture.strong_stimulus_tx_gain_db
                ),
                "required_effective_attenuation_db": 30.0,
                "tx1_policy": "muted below -80 dB for the entire campaign",
            }
            if disk.get("safety") != expected_safety:
                errors.append("transient safety policy differs from plan")
            expected_configuration = {
                "quality": expected_quality,
                "transient_capture": _json_safe(asdict(expected_capture)),
                "kernel_buffers": 1,
                "tandem_transport": {
                    "provider_frame_samples": (_TANDEM_BATCH_PROVIDER_FRAME_SAMPLES),
                    "kernel_buffers": _TANDEM_BATCH_KERNEL_BUFFERS,
                    "batch_frames": _TANDEM_BATCH_FRAMES,
                    "queue_capacity_frames": _TANDEM_BATCH_QUEUE_FRAMES,
                    "metadata_abi": 2,
                },
            }
            if disk.get("configuration") != expected_configuration:
                errors.append("transient configuration differs from plan")
            expected_evidence_policy = transient_evidence_policy(expected_capture)
            critical_tandem_policy = {
                "tandem_provider_frame_samples": (_TANDEM_BATCH_PROVIDER_FRAME_SAMPLES),
                "tandem_kernel_buffers": _TANDEM_BATCH_KERNEL_BUFFERS,
                "tandem_batch_frames": _TANDEM_BATCH_FRAMES,
                "tandem_capture_queue_frames": _TANDEM_BATCH_QUEUE_FRAMES,
                "tandem_attack_target_frames_after_s0": (
                    _TANDEM_BATCH_ATTACK_TARGET_FRAMES
                ),
                "tandem_release_target_frames_after_s0": (
                    _TANDEM_BATCH_RELEASE_TARGET_FRAMES
                ),
                "tandem_maximum_target_overshoot_samples": (
                    _TANDEM_BATCH_MAX_TARGET_OVERSHOOT_SAMPLES
                ),
                "tandem_maximum_a_to_c_uncertainty_samples": (
                    _TANDEM_BATCH_MAX_CAUSAL_UNCERTAINTY_SAMPLES
                ),
                "tandem_required_partition_frames": (
                    _TANDEM_BATCH_MINIMUM_PARTITION_FRAMES
                ),
                "tandem_conditioning_tail_samples": _TANDEM_BATCH_ANCHOR_SAMPLES,
                "tandem_analysis_window_samples": (
                    _TANDEM_BATCH_ANALYSIS_WINDOW_SAMPLES
                ),
                "tandem_batch_cache_bytes": 37_749_760,
                "tandem_aggregate_resident_bytes": 89_261_056,
                "tandem_success_close": "full 1+63 replay; normal close; no cancel",
                "tandem_post_close": (
                    "IDLE/fault0/overflow0/FIFO0/unowned; retain pre-close "
                    "diagnostics without exact retired-tail claim"
                ),
            }
            if disk.get("evidence_policy") != expected_evidence_policy or any(
                expected_evidence_policy.get(key) != value
                for key, value in critical_tandem_policy.items()
            ):
                errors.append("transient evidence policy differs from plan")
            mode_records_value = disk.get("modes")
            if not isinstance(mode_records_value, list) or any(
                not isinstance(item, Mapping) for item in mode_records_value
            ):
                errors.append("transient mode records are malformed")
                mode_records: list[Mapping[str, Any]] = []
            else:
                mode_records = [
                    item for item in mode_records_value if isinstance(item, Mapping)
                ]
            if disk.get("required_modes") != list(TRANSIENT_MODES) or [
                item.get("mode") for item in mode_records
            ] != list(TRANSIENT_MODES):
                errors.append("transient mode coverage differs from plan")
            comparison_value = disk.get("comparison")
            if not isinstance(comparison_value, list) or any(
                not isinstance(item, Mapping) for item in comparison_value
            ):
                comparison: list[Mapping[str, Any]] = []
                errors.append("transient comparison records are malformed")
            else:
                comparison = [
                    item for item in comparison_value if isinstance(item, Mapping)
                ]
            if len(comparison) != len(TRANSIENT_MODES) or [
                item.get("mode") for item in comparison
            ] != list(TRANSIENT_MODES):
                errors.append("transient comparison coverage differs from plan")
            for index, mode in enumerate(mode_records):
                if mode.get("verdict") != "pass":
                    errors.append("transient mode verdict is not pass")
                    continue
                gain = mode.get("gain_evidence")
                responses = mode.get("responses")
                if (
                    not isinstance(gain, Mapping)
                    or gain.get("evidence_valid") is not True
                ):
                    errors.append("transient gain evidence is invalid")
                if not isinstance(responses, Mapping) or any(
                    not isinstance(responses.get(direction), Mapping)
                    or responses[direction].get("evidence_valid") is not True
                    for direction in ("attack", "release")
                ):
                    errors.append("transient attack/release response is invalid")
                if (
                    isinstance(comparison, list)
                    and index < len(comparison)
                    and comparison[index].get("gain_evidence") != gain
                ):
                    errors.append("transient comparison changed gain evidence")
            errors.extend(_transient_comparison_errors(mode_records, comparison))
            errors.extend(
                _transient_mode_boundary_errors(mode_records, transient_quality)
            )
            errors.extend(
                _transient_ordinary_errors(
                    mode_records,
                    expected_capture,
                    transient_quality,
                )
            )
            errors.extend(
                _transient_batch_contract_errors(
                    mode_records,
                    expected_capture,
                    transient_quality,
                    phase_root=work_dir,
                    serial=options.serial,
                )
            )
            summary = {
                "mode_count": len(mode_records),
                "comparison": comparison,
            }
        else:
            expected_options = ModulatedHardwareOptions(
                physical_attenuation_db=options.physical_attenuation_db,
                center_frequency_hz=spec.band.center_frequency_hz,
                tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                modes=RELEASE_MODULATED_MODES,
                max_seconds=options.phase_max_seconds,
                output_dir=work_dir,
            )
            # Durable JSON normalizes dataclass tuples (notably blocker_points)
            # to arrays.  Compare the same JSON-domain representation rather
            # than a Python tuple against the decoded list.
            expected_configuration = _json_safe(asdict(expected_options))
            assert isinstance(expected_configuration, dict)
            expected_configuration["output_dir"] = str(work_dir)
            expected_configuration["minimum_effective_attenuation_db"] = (
                expected_options.minimum_effective_attenuation_db
            )
            if disk.get("configuration") != expected_configuration:
                errors.append("modulated configuration differs from plan")
            if disk.get("mode_evidence_policy") != modulated_mode_evidence_policy():
                errors.append("modulated mode evidence policy differs from plan")
            expected_case_ids = [
                "desired_only",
                *(
                    f"blocker_{index:02d}"
                    for index in range(len(expected_options.blocker_points))
                ),
            ]
            waveforms = disk.get("waveforms")
            if (
                not isinstance(waveforms, list)
                or [item.get("case_id") for item in waveforms] != expected_case_ids
                or [item.get("kind") for item in waveforms]
                != [
                    "desired_only",
                    *("composite_blocker" for _ in expected_case_ids[1:]),
                ]
            ):
                errors.append("modulated waveform cases differ from plan")
            errors.extend(_modulated_dma_cleanup_errors(waveforms))
            runs = disk.get("runs")
            run_records = runs if isinstance(runs, list) else []
            observed = [
                (item.get("case_id"), item.get("mode"))
                for item in run_records
                if isinstance(item, Mapping)
            ]
            expected = [
                (case_id, mode)
                for case_id in expected_case_ids
                for mode in expected_options.modes
            ]
            if observed != expected:
                errors.append("modulated mode/blocker coverage differs from plan")
            errors.extend(_modulated_gain_errors(runs, expected_options))
            errors.extend(_modulated_iq_convention_errors(runs))
            errors.extend(
                _modulated_continuity_errors(runs, expected_options.capture_samples)
            )
            raw_iq_errors, raw_iq_provenance = _modulated_raw_iq_evidence(
                runs,
                work_dir=work_dir,
                serial=options.serial,
                capture_samples=expected_options.capture_samples,
            )
            errors.extend(raw_iq_errors)
            evaluation = disk.get("evaluation")
            if (
                not isinstance(evaluation, Mapping)
                or evaluation.get("valid") is not True
            ):
                errors.append("modulated quality evaluation is invalid")
            else:
                recomputed_evaluation = _json_safe(
                    evaluate_modulated_hardware_report(
                        disk,
                        expected_options.degradation_thresholds,
                        expected_modes=expected_options.modes,
                    )
                )
                if evaluation != recomputed_evaluation:
                    errors.append(
                        "modulated quality evaluation differs from recomputation"
                    )
            summary = {
                "run_count": len(observed),
                "evaluation": evaluation,
                "raw_iq_provenance": raw_iq_provenance,
            }
        if errors:
            raise ReleaseCliError("; ".join(errors))
        return ValidatedPhase("pass", True, summary)

    return validate


def plan_document(options: ReleaseHardwareOptions) -> dict[str, Any]:
    _assert_release_inputs_unchanged(options)
    specs = phase_specs(options)
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": _fingerprint(options, specs),
        "configuration": _configuration(options),
        "plan": [spec.to_dict() for spec in specs],
        "deployment_performed": False,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner_attestor: Callable[[], Mapping[str, Any]] | None = None,
) -> int:
    environment = os.environ if environ is None else environ
    options = parse_cli_args(
        argv,
        environ=environment,
        runner_attestor=runner_attestor,
    )
    if options.plan_only:
        print(json.dumps(plan_document(options), indent=2, sort_keys=True))
        return 0
    try:
        _attest_host_libiio_preimport(
            environment,
            expected_commit=options.libiio_source_commit,
        )
    except ReleaseCliError as error:
        raise SystemExit(
            f"host libiio provenance is not authorizing before import: {error}"
        ) from error
    try:
        import iio
    except ImportError as error:
        raise SystemExit(
            "manifest-pinned pylibiio is not importable; use the guarded shell runner"
        ) from error

    def host_libiio_attestor() -> Mapping[str, Any]:
        return _attest_imported_libiio(
            iio,
            environment,
            expected_commit=options.libiio_source_commit,
        )

    try:
        options = _bind_host_libiio(
            options,
            host_libiio_attestor,
        )
    except ReleaseCliError as error:
        raise SystemExit(
            f"host libiio provenance is not authorizing: {error}"
        ) from error
    report, path = run_aggregate(
        options,
        production_executor(options, iio),
        production_validator(options),
    )
    print(f"aggregate report: {path}")
    print(f"aggregate verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
