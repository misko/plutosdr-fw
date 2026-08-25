"""Guarded, RF-muted USB metadata-batch lifecycle qualification.

This module deliberately has no transmit-arm operation.  Its only TX writes
are independent fail-closed mute barriers: both hardware attenuators at
-89.75 dB, all DDS raw/scale attributes at zero, and all DAC selectors at ZERO.
The acquisition request is tandem HOLD at 40 dB, so no gain event is expected.
"""

# Fail-safe mute, close, unlock, and evidence persistence must also run for
# cancellation signals and other non-Exception exits.
# ruff: noqa: BLE001

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import gc
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import struct
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    GAIN_OBSERVATION_BYTES,
    TANDEM_UNSAFE_FLAGS,
    V5_PREFIX_BYTES,
    TandemFrameMetadata,
    TandemGainTable,
    TandemMode,
    TandemState,
    build_tandem_request,
    close_iio_object,
    create_metadata_buffer,
    parse_tandem_frame_metadata,
)

SCHEMA = "plutosdr-fw.muted-metadata-batch-lifecycle.v2"
EXACT_LIBIIO_COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
EXACT_LIBIIO_TAG = "tandem-agc-v8-rc3-source/libiio-v1"
DEFAULT_R18_SERIAL = "1040007c4a94000211000b009186843ef2"
EXPECTED_FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc3"
EXPECTED_FIRMWARE_PATTERN = r"\Av0[.]41-plutoplus-spf-tandem-agc-v8-rc3\Z"
EXPECTED_KERNEL_VERSION = "5.15.0-g77a1f2352162"
EXPECTED_HARDWARE_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
TX_MUTE_DB = -89.75
DAC_SELECT_ZERO = 0x3
CENTER_FREQUENCY_HZ = 915_000_000
SAMPLE_RATE_HZ = 2_500_000
RF_BANDWIDTH_HZ = 1_500_000
LO_READBACK_TOLERANCE_HZ = 2
SAMPLE_RATE_READBACK_TOLERANCE_HZ = 250
RF_BANDWIDTH_READBACK_TOLERANCE_HZ = 2
FRAME_SAMPLES = 65_536
KERNEL_BUFFERS = 8
BATCH_FRAMES = 64
METADATA_CAPACITY = 64 * 1024
HOLD_GAIN_DB = 40
EXPECTED_IQ_BYTES = FRAME_SAMPLES * 8
IQ_EVIDENCE_POLICY = (
    "returned IQ is not retained; byte length and SHA-256 are in-process "
    "diagnostics only and are not independently revalidated"
)
EXPECTED_BATCH_CACHE_BYTES = BATCH_FRAMES * (
    EXPECTED_IQ_BYTES + METADATA_CAPACITY + 2 * ctypes.sizeof(ctypes.c_size_t)
)
REQUIRED_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
REQUIRED_FLAGS = (
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_TANDEM_METADATA_VALID
)
EXACT_METADATA_FEATURES = 0x000003FF
EXACT_HOLD_METADATA_FLAGS = (
    REQUIRED_FLAGS
    | (1 << 0)
    | (1 << 1)
    | (1 << 10)
    | (1 << 15)
    | (1 << 16)
    | (1 << 18)
    | (1 << 19)
)
GAIN_OBSERVATION = struct.Struct("<QQIHBBbbHI")
GAIN_OBSERVATION_FLAGS = 0x0003
PROVIDER_OBSERVATION_INTERVAL_SAMPLES = FRAME_SAMPLES // 4
EXPECTED_GAIN_TABLE = TandemGainTable.MHZ_200_1300
EXPECTED_MINIMUM_GAIN_DB = 0
EXPECTED_MAXIMUM_GAIN_DB = 62
EXPECTED_MINIMUM_GAIN_INDEX = 3
EXPECTED_MAXIMUM_GAIN_INDEX = 65
EXPECTED_HOLD_GAIN_INDEX = EXPECTED_MINIMUM_GAIN_INDEX + HOLD_GAIN_DB
EXPECTED_THRESHOLD_PROVENANCE = 20 | (58 << 8) | (49 << 16) | (48 << 24)
RX_SCAN_IDS = ("voltage0", "voltage1", "voltage2", "voltage3")
RX_SCAN_MASK = 0x0F
RX_SCAN_SAMPLE_BYTES = 8
RX_SCAN_FORMAT = {
    "length": 16,
    "bits": 12,
    "shift": 0,
    "is_signed": True,
    "is_be": False,
    "repeat": 1,
}
RF_CHANNELS = (
    ("rx0", "voltage0", False),
    ("rx1", "voltage1", False),
    ("tx0", "voltage0", True),
    ("tx1", "voltage1", True),
)
RAW_METADATA_DIRECTORY = "raw-metadata"
RAW_METADATA_BYTES = 3_256
RAW_METADATA_FILE_COUNT = BATCH_FRAMES + 1
MAXIMUM_SIGNED_64 = (1 << 63) - 1
MAXIMUM_UNSIGNED_64 = (1 << 64) - 1
MAXIMUM_JSON_NODES = 200_000
MAXIMUM_JSON_DEPTH = 64
MAXIMUM_JSON_STRING_BYTES = 1_048_576
MAXIMUM_CMAKE_CACHE_BYTES = 1_048_576
MAXIMUM_LIBIIO_BYTES = 67_108_864
MAXIMUM_PYLIBIIO_BYTES = 8_388_608


class QualificationError(RuntimeError):
    """Evidence is unsafe, incomplete, or inconsistent."""


class _AtomicPromotionError(QualificationError):
    def __init__(self, message: str, target_identity: tuple[int, int] | None):
        super().__init__(message)
        self.target_identity = target_identity


def _require_nonsymlink_path(path: pathlib.Path, *, include_leaf: bool) -> None:
    """Reject symlinks in an absolute output path without resolving them away."""

    if not path.is_absolute() or ".." in path.parts:
        raise QualificationError("output path must be absolute and normalized")
    current = pathlib.Path(path.anchor)
    try:
        for part in path.parts[1:-1]:
            current /= part
            if current.is_symlink():
                raise QualificationError(
                    f"output path component is a symlink: {current}"
                )
            if current.exists() and not current.is_dir():
                raise QualificationError(
                    f"output path ancestor is not a directory: {current}"
                )
        if include_leaf and path.is_symlink():
            raise QualificationError(f"output path is a symlink: {path}")
    except (OSError, ValueError) as error:
        raise QualificationError("output path cannot be inspected safely") from error


def _prepare_fresh_output_path(path: pathlib.Path) -> dict[str, Any]:
    """Create only fresh nonsymlink parents before opening the radio context."""

    path = path.absolute()
    if path.suffix != ".json":
        raise QualificationError("output path must name a JSON file")
    _require_nonsymlink_path(path, include_leaf=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    artifact_directory = path.parent / RAW_METADATA_DIRECTORY
    _require_nonsymlink_path(temporary, include_leaf=True)
    _require_nonsymlink_path(artifact_directory, include_leaf=True)
    if path.exists() or temporary.exists() or artifact_directory.exists():
        raise QualificationError(
            "output report, temporary path, and metadata directory must be fresh"
        )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_stat = path.parent.stat(follow_symlinks=False)
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) != 0o700:
        raise QualificationError("fresh output parent must be private mode 0700")
    _require_nonsymlink_path(path, include_leaf=True)
    _require_nonsymlink_path(temporary, include_leaf=True)
    _require_nonsymlink_path(artifact_directory, include_leaf=True)
    if path.exists() or temporary.exists() or artifact_directory.exists():
        raise QualificationError("output report changed during fresh-path preflight")
    return {
        "verified": True,
        "absolute_report_path": str(path),
        "absolute_temporary_path": str(temporary),
        "absolute_raw_metadata_directory": str(artifact_directory),
        "report_existed_before_context": False,
        "temporary_existed_before_context": False,
        "raw_metadata_directory_existed_before_context": False,
        "symlink_components": 0,
    }


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_exact_owned_regular_file(
    path: pathlib.Path, *, expected_bytes: int, name: str
) -> bytes:
    """Bound a no-follow evidence read and reject replacement while open."""

    _require_nonsymlink_path(path, include_leaf=True)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise QualificationError(f"{name} cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_size != expected_bytes
        ):
            raise QualificationError(f"{name} size/type/owner changed")
        chunks: list[bytes] = []
        remaining = expected_bytes + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) or len(payload) != expected_bytes:
            raise QualificationError(f"{name} changed while reading")
        return payload
    except OSError as error:
        raise QualificationError(f"{name} cannot be read safely") from error
    finally:
        os.close(descriptor)


def _read_bounded_owned_regular_file(
    path: pathlib.Path, *, maximum_bytes: int, name: str
) -> bytes:
    """Read a small protected host file without following or reallocating."""

    _require_nonsymlink_path(path, include_leaf=True)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise QualificationError(f"{name} cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or not 0 < before.st_size <= maximum_bytes
        ):
            raise QualificationError(f"{name} size/type/owner changed")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) or len(payload) != before.st_size:
            raise QualificationError(f"{name} changed while reading")
        return payload
    except OSError as error:
        raise QualificationError(f"{name} cannot be read safely") from error
    finally:
        os.close(descriptor)


def _sha256_bounded_owned_regular_file(
    path: pathlib.Path, *, maximum_bytes: int, name: str
) -> str:
    return hashlib.sha256(
        _read_bounded_owned_regular_file(path, maximum_bytes=maximum_bytes, name=name)
    ).hexdigest()


def _json_payload(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _unlink_same_inode(path: pathlib.Path, identity: tuple[int, int]) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (
        (info.st_dev, info.st_ino) == identity
        and stat.S_ISREG(info.st_mode)
        and info.st_uid == os.getuid()
    ):
        path.unlink()


def _best_effort_unlink_same_inode(
    path: pathlib.Path, identity: tuple[int, int]
) -> None:
    """Remove only our inode without masking the operation's primary failure."""

    try:
        _unlink_same_inode(path, identity)
    except OSError:
        pass


def _path_matches_owned_identity(
    path: pathlib.Path, identity: tuple[int, int] | None
) -> bool:
    if identity is None:
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        (info.st_dev, info.st_ino) == identity
        and stat.S_ISREG(info.st_mode)
        and info.st_uid == os.getuid()
        and not path.is_symlink()
    )


def _atomic_json(
    path: pathlib.Path,
    value: Mapping[str, Any],
    *,
    replace_existing: bool = False,
    expected_existing_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    path = path.absolute()
    _require_nonsymlink_path(path, include_leaf=True)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    _require_nonsymlink_path(temporary, include_leaf=True)
    if temporary.exists():
        raise QualificationError(f"atomic report temporary path exists: {temporary}")
    if replace_existing:
        try:
            existing = path.lstat()
        except OSError as error:
            raise QualificationError("owned report to replace is absent") from error
        if (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != os.getuid()
            or path.is_symlink()
            or (existing.st_dev, existing.st_ino) != expected_existing_identity
        ):
            raise QualificationError("owned report to replace changed")
    elif path.exists():
        raise QualificationError(f"atomic report path is not fresh: {path}")
    payload = _json_payload(value)
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        temporary_identity = os.fstat(descriptor)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    identity = (temporary_identity.st_dev, temporary_identity.st_ino)
    target_identity: tuple[int, int] | None = None
    try:
        if replace_existing:
            temporary.replace(path)
            target_identity = identity
        else:
            os.link(temporary, path, follow_symlinks=False)
            target_identity = identity
            _unlink_same_inode(temporary, identity)
    except OSError as error:
        _best_effort_unlink_same_inode(temporary, identity)
        if target_identity is not None:
            # A failed cleanup after a successful hard-link promotion must not
            # leave an apparently authoritative PASS behind.  The identity
            # check prevents deleting a raced-in file owned by another writer.
            _best_effort_unlink_same_inode(path, target_identity)
        raise _AtomicPromotionError(
            "atomic report promotion failed without overwrite", target_identity
        ) from error
    try:
        _fsync_directory(path.parent)
        if temporary.exists() or not _path_matches_owned_identity(path, identity):
            raise QualificationError(
                "atomic report promotion did not produce one owned file"
            )
    except BaseException as error:
        raise _AtomicPromotionError(
            "atomic report promotion did not become durable", identity
        ) from error
    return identity


def _atomic_bytes(path: pathlib.Path, payload: bytes) -> None:
    path = path.absolute()
    _require_nonsymlink_path(path, include_leaf=True)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_nonsymlink_path(path, include_leaf=True)
    if path.exists():
        raise QualificationError(f"metadata artifact is not fresh: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    _require_nonsymlink_path(temporary, include_leaf=True)
    if temporary.exists():
        raise QualificationError(f"metadata temporary is not fresh: {temporary}")
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        temporary_identity = os.fstat(descriptor)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    identity = (temporary_identity.st_dev, temporary_identity.st_ino)
    try:
        os.link(temporary, path, follow_symlinks=False)
        _unlink_same_inode(temporary, identity)
    except OSError as error:
        _best_effort_unlink_same_inode(temporary, identity)
        _best_effort_unlink_same_inode(path, identity)
        raise QualificationError(
            f"metadata artifact promotion failed without overwrite: {path}"
        ) from error
    _fsync_directory(path.parent)
    if temporary.exists() or path.is_symlink() or not path.is_file():
        raise QualificationError(f"metadata artifact promotion failed: {path}")


def _metadata_relative_path(role: str, ordinal: int) -> pathlib.PurePosixPath:
    if role == "full_drain" and 0 <= ordinal < BATCH_FRAMES:
        name = f"full-frame-{ordinal:04d}.metadata.bin"
    elif role == "cancel_first" and ordinal == 0:
        name = "cancel-first.metadata.bin"
    else:
        raise QualificationError(f"invalid raw metadata identity: {role}/{ordinal}")
    return pathlib.PurePosixPath(RAW_METADATA_DIRECTORY) / name


def _metadata_manifest_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(str(entry["relative_path"]).encode())
        digest.update(b"\0")
        digest.update(str(entry["bytes"]).encode())
        digest.update(b"\0")
        digest.update(str(entry["sha256"]).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _new_metadata_artifact_manifest(
    captures: Sequence[tuple[str, int, bytes]],
) -> dict[str, Any]:
    if len(captures) != RAW_METADATA_FILE_COUNT:
        raise QualificationError(
            f"retained {len(captures)} raw metadata records, expected "
            f"{RAW_METADATA_FILE_COUNT}"
        )
    entries: list[dict[str, Any]] = []
    identities: set[tuple[str, int]] = set()
    for role, ordinal, payload in captures:
        identity = (role, ordinal)
        if identity in identities:
            raise QualificationError(f"duplicate raw metadata identity: {identity}")
        identities.add(identity)
        if len(payload) != RAW_METADATA_BYTES:
            raise QualificationError(
                f"raw metadata {role}/{ordinal} has {len(payload)} bytes"
            )
        entries.append(
            {
                "role": role,
                "ordinal": ordinal,
                "relative_path": _metadata_relative_path(role, ordinal).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "write_completed": False,
            }
        )
    expected_identities = {
        *(("full_drain", index) for index in range(BATCH_FRAMES)),
        ("cancel_first", 0),
    }
    if identities != expected_identities:
        raise QualificationError("raw metadata capture inventory is incomplete")
    return {
        "policy": "retain, reread, hash, and reparse all 64 drain plus cancel-first metadata records",
        "directory_relative": RAW_METADATA_DIRECTORY,
        "expected_file_count": RAW_METADATA_FILE_COUNT,
        "completed_file_count": 0,
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "manifest_digest_method": "sha256(path NUL bytes NUL sha256 LF) in entry order",
        "manifest_sha256": _metadata_manifest_digest(entries),
        "inventory_state": "predeclared",
        "entries": entries,
    }


def _write_metadata_artifacts(
    output_path: pathlib.Path,
    captures: Sequence[tuple[str, int, bytes]],
    manifest: dict[str, Any],
) -> None:
    by_identity = {(role, ordinal): payload for role, ordinal, payload in captures}
    for entry in manifest["entries"]:
        relative = pathlib.PurePosixPath(entry["relative_path"])
        target = output_path.parent / pathlib.Path(*relative.parts)
        payload = by_identity[(entry["role"], entry["ordinal"])]
        _atomic_bytes(target, payload)
        entry["write_completed"] = True
        manifest["completed_file_count"] += 1
    manifest["inventory_state"] = "complete"
    artifact_directory = output_path.parent / RAW_METADATA_DIRECTORY
    expected_names = {
        pathlib.PurePosixPath(entry["relative_path"]).name
        for entry in manifest["entries"]
    }
    observed = list(artifact_directory.iterdir())
    if (
        {path.name for path in observed} != expected_names
        or any(path.is_symlink() or not path.is_file() for path in observed)
        or any(path.name.endswith(".tmp") for path in observed)
    ):
        raise QualificationError("raw metadata post-write inventory changed")
    _fsync_directory(artifact_directory)


def _error_record(error: BaseException) -> dict[str, Any]:
    return {
        "type": type(error).__name__,
        "errno": getattr(error, "errno", None),
        "message": str(error),
    }


def _first_float(value: Any) -> float:
    return float(str(value).strip().split()[0])


def _read_attr(owner: Any, name: str) -> str:
    if name not in owner.attrs:
        raise QualificationError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
    return str(owner.attrs[name].value)


def _write_numeric(owner: Any, name: str, value: float, *, tolerance: float) -> float:
    if name not in owner.attrs:
        raise QualificationError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
    owner.attrs[name].value = str(value)
    observed = _first_float(owner.attrs[name].value)
    if not math.isfinite(observed) or abs(observed - value) > tolerance:
        raise QualificationError(
            f"{getattr(owner, 'id', owner)!r} {name} readback {observed} "
            f"differs from {value}"
        )
    return observed


def _channel(device: Any, name: str, output: bool) -> Any:
    value = device.find_channel(name, output)
    if value is None:
        raise QualificationError(f"{device.id} lacks channel {name!r}, output={output}")
    return value


def _selector_address(index: int) -> int:
    return 0x0418 + index * 0x40


def _legacy_address(index: int) -> int:
    return 0x0414 + index * 0x40


def _mapped_libiio() -> list[str]:
    paths = {
        str(pathlib.Path(line.rsplit(maxsplit=1)[-1]).resolve())
        for line in pathlib.Path("/proc/self/maps")
        .read_text(encoding="utf-8")
        .splitlines()
        if "/libiio.so" in line.rsplit(maxsplit=1)[-1]
    }
    return sorted(paths)


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_bytes(repository: pathlib.Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise QualificationError(
            f"runner git provenance command failed: {' '.join(arguments)}"
        ) from error


def _attest_mapped_libiio() -> dict[str, Any]:
    mapped = _mapped_libiio()
    if len(mapped) != 1:
        raise QualificationError(f"expected one mapped libiio, got {mapped}")
    mapped_path = pathlib.Path(mapped[0]).resolve()
    expected_path_text = os.environ.get("PLUTOSDR_FW_LIBIIO_PATH", "")
    build_text = os.environ.get("PLUTOSDR_FW_LIBIIO_BUILD", "")
    source_text = os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE", "")
    expected_sha = os.environ.get("PLUTOSDR_FW_LIBIIO_SHA256", "")
    if not all((expected_path_text, build_text, source_text)):
        raise QualificationError("runner omitted libiio path/build/source attestation")
    expected_path = pathlib.Path(expected_path_text).resolve()
    build = pathlib.Path(build_text).resolve()
    source = pathlib.Path(source_text).resolve()
    if mapped_path != expected_path or not mapped_path.is_relative_to(build):
        raise QualificationError(
            f"mapped libiio {mapped_path} is not runner build artifact {expected_path}"
        )
    calculated_sha = _sha256_bounded_owned_regular_file(
        mapped_path,
        maximum_bytes=MAXIMUM_LIBIIO_BYTES,
        name="mapped libiio",
    )
    if calculated_sha != expected_sha:
        raise QualificationError(
            f"mapped libiio SHA-256 {calculated_sha} != runner {expected_sha}"
        )
    cache = build / "CMakeCache.txt"
    home = None
    try:
        cache_text = _read_bounded_owned_regular_file(
            cache,
            maximum_bytes=MAXIMUM_CMAKE_CACHE_BYTES,
            name="libiio CMake cache",
        ).decode("utf-8")
    except UnicodeDecodeError as error:
        raise QualificationError("libiio CMake cache is not UTF-8") from error
    for line in cache_text.splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
            home = pathlib.Path(line.split("=", 1)[1]).resolve()
            break
    if home != source:
        raise QualificationError(
            f"libiio build source {home} does not match runner source {source}"
        )
    return {
        "source_commit": EXACT_LIBIIO_COMMIT,
        "protected_source_tag": EXACT_LIBIIO_TAG,
        "source_directory": str(source),
        "build_directory": str(build),
        "mapped_shared_objects": [str(mapped_path)],
        "mapped_shared_object": str(mapped_path),
        "mapped_shared_object_sha256": calculated_sha,
        "runner_shared_object_sha256": expected_sha,
    }


def _attest_host_libiio(iio_module: Any) -> dict[str, Any]:
    """Close the exact protected host source graph before any radio context."""

    record = _attest_mapped_libiio()
    source = pathlib.Path(record["source_directory"])
    if (
        _git_bytes(source, "rev-parse", "HEAD").decode().strip() != EXACT_LIBIIO_COMMIT
        or _git_bytes(source, "rev-parse", f"refs/tags/{EXACT_LIBIIO_TAG}^{{commit}}")
        .decode()
        .strip()
        != EXACT_LIBIIO_COMMIT
        or _git_bytes(source, "status", "--porcelain", "--untracked-files=no").strip()
    ):
        raise QualificationError("host libiio source graph is not exact and clean")
    pylibiio = pathlib.Path(iio_module.__file__).resolve()
    expected_pylibiio = source / "bindings/python/iio.py"
    if pylibiio != expected_pylibiio or not pylibiio.is_file():
        raise QualificationError("host pylibiio is outside the protected source")
    expected_blob = hashlib.sha256(
        _git_bytes(
            source,
            "show",
            f"{EXACT_LIBIIO_COMMIT}:bindings/python/iio.py",
        )
    ).hexdigest()
    if (
        _sha256_bounded_owned_regular_file(
            pylibiio,
            maximum_bytes=MAXIMUM_PYLIBIIO_BYTES,
            name="host pylibiio",
        )
        != expected_blob
    ):
        raise QualificationError("host pylibiio differs from the exact commit blob")
    record["pylibiio_file"] = str(pylibiio)
    return record


def _attest_runner_provenance() -> dict[str, str]:
    commit = os.environ.get("PLUTOSDR_FW_RUNNER_COMMIT", "")
    module_sha = os.environ.get("PLUTOSDR_FW_RUNNER_MODULE_SHA256", "")
    module_head_sha = os.environ.get("PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256", "")
    shell_sha = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_SHA256", "")
    shell_head_sha = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256", "")
    shell_text = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_PATH", "")
    metadata_abi_sha = os.environ.get("PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256", "")
    metadata_abi_head_sha = os.environ.get(
        "PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256", ""
    )
    metadata_abi_text = os.environ.get("PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH", "")
    module_path = pathlib.Path(__file__).resolve()
    repository = module_path.parents[2]
    shell_path = pathlib.Path(shell_text).resolve() if shell_text else pathlib.Path()
    metadata_abi_path = (
        pathlib.Path(metadata_abi_text).resolve()
        if metadata_abi_text
        else pathlib.Path()
    )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise QualificationError("runner firmware-repository commit is invalid")
    if _git_bytes(repository, "rev-parse", "HEAD").decode().strip() != commit:
        raise QualificationError("runner commit is not the live repository HEAD")
    if not shell_text or not shell_path.is_absolute() or not shell_path.is_file():
        raise QualificationError("runner shell path is absent or non-absolute")
    if (
        not metadata_abi_text
        or not metadata_abi_path.is_absolute()
        or not metadata_abi_path.is_file()
        or metadata_abi_path != module_path.parent / "metadata_abi.py"
    ):
        raise QualificationError(
            "runner metadata ABI path is absent, non-absolute, or unexpected"
        )
    calculated_module_sha = _sha256_file(module_path)
    calculated_shell_sha = _sha256_file(shell_path)
    calculated_metadata_abi_sha = _sha256_file(metadata_abi_path)
    expected_paths = {
        module_path: "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
        shell_path: "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
        metadata_abi_path: "tests/radio_hardware/metadata_abi.py",
    }
    for observed_path, relative in expected_paths.items():
        if observed_path != repository / relative:
            raise QualificationError(
                f"runner source path is unexpected: {observed_path}"
            )
        blob_sha = hashlib.sha256(
            _git_bytes(repository, "show", f"{commit}:{relative}")
        ).hexdigest()
        expected_sha = {
            module_path: module_head_sha,
            shell_path: shell_head_sha,
            metadata_abi_path: metadata_abi_head_sha,
        }[observed_path]
        if blob_sha != expected_sha:
            raise QualificationError(f"runner commit blob changed: {relative}")
    if (
        calculated_module_sha != module_sha
        or calculated_module_sha != module_head_sha
        or calculated_shell_sha != shell_sha
        or calculated_shell_sha != shell_head_sha
        or calculated_metadata_abi_sha != metadata_abi_sha
        or calculated_metadata_abi_sha != metadata_abi_head_sha
    ):
        raise QualificationError("runner source SHA-256 does not match its process")
    return {
        "firmware_repo_commit": commit,
        "firmware_repository": str(repository),
        "python_module_path": str(module_path),
        "python_module_sha256": calculated_module_sha,
        "python_module_head_blob_sha256": module_head_sha,
        "shell_runner_path": str(shell_path),
        "shell_runner_sha256": calculated_shell_sha,
        "shell_runner_head_blob_sha256": shell_head_sha,
        "metadata_abi_path": str(metadata_abi_path),
        "metadata_abi_sha256": calculated_metadata_abi_sha,
        "metadata_abi_head_blob_sha256": metadata_abi_head_sha,
    }


def _read_mute(phy: Any, tx: Any) -> dict[str, Any]:
    gains = [
        _first_float(_read_attr(_channel(phy, f"voltage{i}", True), "hardwaregain"))
        for i in (0, 1)
    ]
    dds: dict[str, Any] = {}
    for index in range(8):
        name = f"altvoltage{index}"
        channel = tx.find_channel(name, True)
        record: dict[str, Any] = {"present": channel is not None}
        if channel is not None:
            for attribute in ("raw", "scale"):
                if attribute in channel.attrs:
                    record[attribute] = _first_float(channel.attrs[attribute].value)
        dds[name] = record
    selectors = [int(tx.reg_read(_selector_address(i))) & 0xF for i in range(4)]
    failures: list[str] = []
    if any(not math.isfinite(gain) or gain > -80.0 for gain in gains):
        failures.append(f"TX hardware gains are not muted: {gains}")
    if selectors != [DAC_SELECT_ZERO] * 4:
        failures.append(f"DAC selectors are not ZERO: {selectors}")
    expected_dds = {f"altvoltage{i}" for i in range(8)}
    if set(dds) != expected_dds or any(not item["present"] for item in dds.values()):
        failures.append("DDS evidence does not cover all eight channels")
    for name, item in dds.items():
        for attribute in ("raw", "scale"):
            if (
                attribute not in item
                or not math.isfinite(float(item[attribute]))
                or abs(float(item[attribute])) > 1e-9
            ):
                failures.append(f"{name} {attribute} is not zero")
    return {
        "verified": not failures,
        "tx1_gain_db": gains[0],
        "tx2_gain_db": gains[1],
        "selectors": selectors,
        "dds": dds,
        "failures": failures,
    }


def _force_mute(phy: Any, tx: Any) -> dict[str, Any]:
    failures: list[str] = []
    for index in (0, 1):
        try:
            _write_numeric(
                _channel(phy, f"voltage{index}", True),
                "hardwaregain",
                TX_MUTE_DB,
                tolerance=0.26,
            )
        except BaseException as error:  # preserve attempts on every mute path
            failures.append(f"TX{index + 1} gain mute: {error}")
    for index in range(8):
        channel = tx.find_channel(f"altvoltage{index}", True)
        if channel is None:
            failures.append(f"DDS altvoltage{index} missing")
            continue
        for attribute in ("raw", "scale"):
            try:
                _write_numeric(channel, attribute, 0.0, tolerance=1e-9)
            except BaseException as error:
                failures.append(f"DDS altvoltage{index} {attribute}: {error}")
    for index in range(4):
        try:
            legacy = int(tx.reg_read(_legacy_address(index)))
            tx.reg_write(_legacy_address(index), legacy & ~1)
            tx.reg_write(_selector_address(index), DAC_SELECT_ZERO)
        except BaseException as error:
            failures.append(f"DAC selector {index} ZERO: {error}")
    evidence = _read_mute(phy, tx)
    failures.extend(evidence["failures"])
    evidence["failures"] = failures
    evidence["verified"] = not failures
    if failures:
        raise QualificationError("; ".join(failures))
    return evidence


def _read_rx_state(phy: Any) -> dict[str, list[Any]]:
    channels = [_channel(phy, f"voltage{i}", False) for i in (0, 1)]
    return {
        "modes": [_read_attr(channel, "gain_control_mode") for channel in channels],
        "gains_db": [
            _first_float(_read_attr(channel, "hardwaregain")) for channel in channels
        ],
    }


def _read_integer_attr(owner: Any, name: str) -> int:
    value = _first_float(_read_attr(owner, name))
    if not math.isfinite(value):
        raise QualificationError(
            f"{getattr(owner, 'id', owner)!r} {name} is not finite"
        )
    return round(value)


def _read_rf_state(phy: Any) -> dict[str, Any]:
    channels: dict[str, dict[str, int]] = {}
    for role, channel_id, output in RF_CHANNELS:
        channel = _channel(phy, channel_id, output)
        channels[role] = {
            "sampling_frequency_hz": _read_integer_attr(channel, "sampling_frequency"),
            "rf_bandwidth_hz": _read_integer_attr(channel, "rf_bandwidth"),
        }
    return {
        "rx_lo_hz": _read_integer_attr(_channel(phy, "altvoltage0", True), "frequency"),
        "tx_lo_hz": _read_integer_attr(_channel(phy, "altvoltage1", True), "frequency"),
        "channels": channels,
    }


def _configure_manual_40(phy: Any) -> dict[str, list[Any]]:
    channels = [_channel(phy, f"voltage{i}", False) for i in (0, 1)]
    for channel in channels:
        channel.attrs["gain_control_mode"].value = "manual"
    for channel in channels:
        _write_numeric(channel, "hardwaregain", HOLD_GAIN_DB, tolerance=0.1)
    state = _read_rx_state(phy)
    if state["modes"] != ["manual", "manual"] or any(
        abs(gain - HOLD_GAIN_DB) > 0.1 for gain in state["gains_db"]
    ):
        raise QualificationError(f"RX manual-40 readback failed: {state}")
    return state


def _normalization_numeric_operation(
    owner: Any,
    *,
    ordinal: int,
    target: str,
    attribute: str,
    requested: float,
    tolerance: float,
) -> dict[str, Any]:
    host_before_ns = time.monotonic_ns()
    observed = _write_numeric(owner, attribute, requested, tolerance=tolerance)
    host_after_ns = time.monotonic_ns()
    return {
        "ordinal": ordinal,
        "target": target,
        "attribute": attribute,
        "requested": requested,
        "readback": observed,
        "tolerance": tolerance,
        "host_before_ns": host_before_ns,
        "host_after_ns": host_after_ns,
    }


def _normalization_string_operation(
    owner: Any,
    *,
    ordinal: int,
    target: str,
    attribute: str,
    requested: str,
) -> dict[str, Any]:
    if attribute not in owner.attrs:
        raise QualificationError(f"{getattr(owner, 'id', owner)!r} lacks {attribute}")
    host_before_ns = time.monotonic_ns()
    owner.attrs[attribute].value = requested
    observed = str(owner.attrs[attribute].value)
    host_after_ns = time.monotonic_ns()
    if observed != requested:
        raise QualificationError(
            f"{getattr(owner, 'id', owner)!r} {attribute} readback "
            f"{observed!r} differs from {requested!r}"
        )
    return {
        "ordinal": ordinal,
        "target": target,
        "attribute": attribute,
        "requested": requested,
        "readback": observed,
        "tolerance": None,
        "host_before_ns": host_before_ns,
        "host_after_ns": host_after_ns,
    }


def _normalize_before_hold(
    phy: Any,
    tx: Any,
    tandem: Any,
    *,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize RF/RX under a completed mute barrier before any buffer opens."""

    if preflight.get("verdict") != "GO":
        raise QualificationError("normalization requires a completed safe preflight")
    started_ns = time.monotonic_ns()
    mute_barrier = _force_mute(phy, tx)
    mute_barrier_completed_ns = time.monotonic_ns()
    status_before = _require_idle(_status(tandem), label="normalization mute barrier")
    operations: list[dict[str, Any]] = []

    def add_numeric(
        owner: Any,
        target: str,
        attribute: str,
        requested: float,
        tolerance: float,
    ) -> None:
        operations.append(
            _normalization_numeric_operation(
                owner,
                ordinal=len(operations),
                target=target,
                attribute=attribute,
                requested=requested,
                tolerance=tolerance,
            )
        )

    add_numeric(
        _channel(phy, "altvoltage0", True),
        "rx_lo",
        "frequency",
        CENTER_FREQUENCY_HZ,
        LO_READBACK_TOLERANCE_HZ,
    )
    add_numeric(
        _channel(phy, "altvoltage1", True),
        "tx_lo",
        "frequency",
        CENTER_FREQUENCY_HZ,
        LO_READBACK_TOLERANCE_HZ,
    )
    for role, channel_id, output in RF_CHANNELS:
        channel = _channel(phy, channel_id, output)
        add_numeric(
            channel,
            role,
            "sampling_frequency",
            SAMPLE_RATE_HZ,
            SAMPLE_RATE_READBACK_TOLERANCE_HZ,
        )
        add_numeric(
            channel,
            role,
            "rf_bandwidth",
            RF_BANDWIDTH_HZ,
            RF_BANDWIDTH_READBACK_TOLERANCE_HZ,
        )
    for index in (0, 1):
        channel = _channel(phy, f"voltage{index}", False)
        operations.append(
            _normalization_string_operation(
                channel,
                ordinal=len(operations),
                target=f"rx{index}",
                attribute="gain_control_mode",
                requested="manual",
            )
        )
    for index in (0, 1):
        add_numeric(
            _channel(phy, f"voltage{index}", False),
            f"rx{index}",
            "hardwaregain",
            HOLD_GAIN_DB,
            0.1,
        )

    rf_after = _read_rf_state(phy)
    rx_after = _read_rx_state(phy)
    mute_after = _read_mute(phy, tx)
    if not mute_after["verified"]:
        raise QualificationError(
            "normalization lost the mute barrier: " + "; ".join(mute_after["failures"])
        )
    status_after = _require_idle(_status(tandem), label="normalization readback")
    completed_ns = time.monotonic_ns()
    result = {
        "verified": True,
        "policy": (
            "safe preflight, complete mute barrier, then RF/RX normalization; "
            "zero metadata buffers until every readback passes"
        ),
        "started_monotonic_ns": started_ns,
        "mute_barrier_completed_monotonic_ns": mute_barrier_completed_ns,
        "completed_monotonic_ns": completed_ns,
        "metadata_buffer_open_count_before": 0,
        "metadata_buffer_open_count_after": 0,
        "mute_barrier": mute_barrier,
        "tandem_status_before": status_before,
        "operations": operations,
        "rf_state_after": rf_after,
        "rx_state_after": rx_after,
        "mute_after": mute_after,
        "tandem_status_after": status_after,
        "expected_gain_table": {
            "selection_basis": "common RX/TX LO at or below 1300000000 Hz",
            "center_frequency_hz": CENTER_FREQUENCY_HZ,
            "gain_table_id": int(EXPECTED_GAIN_TABLE),
            "gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
            "hold_frame_attestation_required": True,
        },
    }
    _validate_normalization(result)
    return result


def _configure_dual_complex_rx_scan(rx: Any) -> dict[str, Any]:
    """Attest four signed LE16 lanes with 12 significant, unshifted bits."""

    expected_ids = set(RX_SCAN_IDS)
    scan_channels: dict[str, Any] = {}
    for channel in rx.channels:
        if not channel.scan_element:
            continue
        if channel.id in expected_ids:
            if channel.id in scan_channels:
                raise QualificationError(f"duplicate RX scan channel {channel.id!r}")
            scan_channels[channel.id] = channel
    if set(scan_channels) != expected_ids:
        missing = sorted(expected_ids - set(scan_channels))
        raise QualificationError(f"RX scan layout lacks channels {missing}")

    layout: list[dict[str, Any]] = []
    observed_indices: list[int] = []
    for expected_index, channel_id in enumerate(RX_SCAN_IDS):
        channel = scan_channels[channel_id]
        try:
            observed_index = channel.index
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its scan index"
            ) from error
        if type(observed_index) is not int:
            raise QualificationError(
                f"RX {channel_id} scan index is not an exact integer"
            )
        if observed_index != expected_index:
            raise QualificationError(
                f"RX {channel_id} scan index {observed_index}, expected "
                f"{expected_index}"
            )
        if observed_index in observed_indices:
            raise QualificationError(f"duplicate RX scan index {observed_index}")
        observed_indices.append(observed_index)

        observed_format: dict[str, Any] | None = None
        try:
            data_format = channel.data_format
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its scan format"
            ) from error
        try:
            observed_format = {
                "length": data_format.length,
                "bits": data_format.bits,
                "shift": data_format.shift,
                "is_signed": data_format.is_signed,
                "is_be": data_format.is_be,
                "repeat": data_format.repeat,
            }
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its complete scan format"
            ) from error
        for field in ("length", "bits", "shift", "repeat"):
            if type(observed_format[field]) is not int:
                raise QualificationError(
                    f"RX {channel_id} scan format {field} is not an exact integer"
                )
        for field in ("is_signed", "is_be"):
            if type(observed_format[field]) is not bool:
                raise QualificationError(
                    f"RX {channel_id} scan format {field} is not an exact boolean"
                )
        if observed_format != RX_SCAN_FORMAT:
            raise QualificationError(
                f"RX {channel_id} scan format {observed_format}, expected "
                f"{RX_SCAN_FORMAT}"
            )
        layout.append(
            {
                "id": channel_id,
                "index": observed_index,
                "format": observed_format,
            }
        )

    for channel in rx.channels:
        if channel.scan_element:
            channel.enabled = channel.id in expected_ids

    enabled_readback: list[tuple[int, str]] = []
    for channel in rx.channels:
        if not channel.scan_element:
            continue
        enabled = channel.enabled
        if type(enabled) is not bool:
            raise QualificationError(
                f"RX {channel.id} enabled readback is not an exact boolean"
            )
        if not enabled:
            continue
        index = channel.index
        if type(index) is not int:
            raise QualificationError(
                f"enabled RX {channel.id} scan index is not an exact integer"
            )
        enabled_readback.append((index, channel.id))
    enabled_readback.sort()
    expected_readback = list(enumerate(RX_SCAN_IDS))
    if enabled_readback != expected_readback:
        raise QualificationError(
            f"RX enabled scan readback changed: {enabled_readback}"
        )
    enabled_ids = [channel_id for _, channel_id in enabled_readback]
    enabled_mask = sum(1 << index for index, _ in enabled_readback)
    if enabled_mask != RX_SCAN_MASK:
        raise QualificationError(
            f"RX enabled scan mask 0x{enabled_mask:02x}, expected 0x{RX_SCAN_MASK:02x}"
        )
    sample_size = rx.sample_size
    if type(sample_size) is not int:
        raise QualificationError("dual-complex RX sample size is not an exact integer")
    if sample_size != RX_SCAN_SAMPLE_BYTES:
        raise QualificationError(
            f"dual-complex RX sample size is {sample_size}, expected "
            f"{RX_SCAN_SAMPLE_BYTES}"
        )
    return {
        "enabled_channel_ids": enabled_ids,
        "enabled_scan_mask": enabled_mask,
        "sample_size_bytes": sample_size,
        "layout": layout,
    }


_STATUS_NAMES = (
    "state",
    "fault_flags",
    "overflow_count",
    "fifo_level",
    "ownership_epoch",
    "transition_count",
    "rx1_gain_index",
    "rx2_gain_index",
)


def _status(tandem: Any) -> dict[str, int]:
    return {name: int(_read_attr(tandem, name)) for name in _STATUS_NAMES}


def _require_idle(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(status) != set(_STATUS_NAMES) or any(
        type(status.get(name)) is not int for name in _STATUS_NAMES
    ):
        raise QualificationError(f"{label} status fields are not exact integers")
    result = {name: status[name] for name in _STATUS_NAMES}
    required = {
        "state": int(TandemState.IDLE),
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": 0,
        "transition_count": 0,
    }
    if any(result[name] != expected for name, expected in required.items()):
        raise QualificationError(f"{label} is not clean IDLE: {result}")
    if (
        result["rx1_gain_index"] != result["rx2_gain_index"]
        or not 0 <= result["rx1_gain_index"] <= 0x7F
    ):
        raise QualificationError(f"{label} endpoints are not paired: {result}")
    return result


def _require_hold(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(status) != set(_STATUS_NAMES) or any(
        type(status.get(name)) is not int for name in _STATUS_NAMES
    ):
        raise QualificationError(f"{label} status fields are not exact integers")
    result = {name: status[name] for name in _STATUS_NAMES}
    if (
        result["state"] != int(TandemState.ARMED_HOLD)
        or not 1 <= result["ownership_epoch"] <= 0xFFFFFFFF
        or result["fault_flags"] != 0
        or result["overflow_count"] != 0
        or result["fifo_level"] != 0
        or result["transition_count"] != 0
        or result["rx1_gain_index"] != result["rx2_gain_index"]
        or result["rx1_gain_index"] != EXPECTED_HOLD_GAIN_INDEX
    ):
        raise QualificationError(f"{label} is not clean owned HOLD: {result}")
    return result


def _require_post_hold_idle(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    result = _require_idle(status, label=label)
    if result["rx1_gain_index"] != EXPECTED_HOLD_GAIN_INDEX:
        raise QualificationError(f"{label} did not preserve HOLD endpoint: {result}")
    return result


def _wait_idle(tandem: Any, *, label: str) -> dict[str, int]:
    deadline = time.monotonic() + 2.0
    while True:
        current = _status(tandem)
        try:
            return _require_idle(current, label=label)
        except QualificationError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def _frame_record(
    ordinal: int, metadata_bytes: bytes, iq: bytes, duration_ns: int
) -> tuple[dict[str, Any], TandemFrameMetadata]:
    metadata = parse_tandem_frame_metadata(metadata_bytes)
    if len(iq) != EXPECTED_IQ_BYTES:
        raise QualificationError(
            f"frame {ordinal} IQ bytes {len(iq)} != {EXPECTED_IQ_BYTES}"
        )
    record = _frame_evidence(
        ordinal,
        metadata,
        duration_ns=duration_ns,
        returned_iq_sha256_in_process=hashlib.sha256(iq).hexdigest(),
        metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
    )
    if record["metadata_bytes"] != len(metadata_bytes):
        raise QualificationError(
            f"frame {ordinal} metadata bytes {len(metadata_bytes)} changed"
        )
    return record, metadata


def _frame_evidence(
    ordinal: int,
    metadata: TandemFrameMetadata,
    *,
    duration_ns: int,
    returned_iq_sha256_in_process: str,
    metadata_sha256: str,
) -> dict[str, Any]:
    """Build the JSON-domain record separately from wire parsing for oracles."""

    return {
        "ordinal": ordinal,
        "refill_duration_ns": duration_ns,
        "returned_iq_bytes_in_process": EXPECTED_IQ_BYTES,
        "returned_iq_sha256_in_process": returned_iq_sha256_in_process,
        "metadata_bytes": metadata.header_bytes,
        "metadata_sha256": metadata_sha256,
        "version": metadata.version,
        "header_bytes": metadata.header_bytes,
        "features": metadata.features,
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "iq_payload_bytes": metadata.iq_payload_bytes,
        "enabled_scan_mask": metadata.enabled_scan_mask,
        "sample_format": metadata.sample_format,
        "channel_count": metadata.channel_count,
        "flags": metadata.flags,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_capacity": metadata.event_capacity,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_fault_flags": metadata.tandem_fault_flags,
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "gain_table_name": metadata.gain_table_id.name.lower(),
        "threshold_provenance": metadata.threshold_provenance,
        "minimum_gain_db": metadata.minimum_gain_db,
        "maximum_gain_db": metadata.maximum_gain_db,
        "initial_gain_db": metadata.initial_gain_db,
        "minimum_gain_index": metadata.minimum_gain_index,
        "maximum_gain_index": metadata.maximum_gain_index,
        "rx1_gain_index": metadata.rx1_gain_index,
        "rx2_gain_index": metadata.rx2_gain_index,
        "ad9361_temperature_mdeg_c": metadata.ad9361_temperature_mdeg_c,
        "event_count": metadata.event_count,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
    }


def _validate_hold_metadata(metadata: TandemFrameMetadata, *, ordinal: int) -> None:
    if metadata.stream_id <= 0 or metadata.ownership_epoch <= 0:
        raise QualificationError(f"frame {ordinal} stream/epoch is not nonzero")
    if metadata.features != EXACT_METADATA_FEATURES:
        raise QualificationError(f"frame {ordinal} feature mask changed")
    if metadata.flags != EXACT_HOLD_METADATA_FLAGS:
        raise QualificationError(f"frame {ordinal} flag mask changed")
    if metadata.flags & TANDEM_UNSAFE_FLAGS or metadata.tandem_fault_flags:
        raise QualificationError(f"frame {ordinal} carries an unsafe flag")
    if (
        metadata.version != 5
        or metadata.header_bytes != 3_256
        or metadata.samples_per_channel != FRAME_SAMPLES
        or metadata.iq_payload_bytes != EXPECTED_IQ_BYTES
        or metadata.enabled_scan_mask != 0x0F
        or metadata.sample_format != 1
        or metadata.channel_count != 2
        or metadata.observation_capacity != 64
        or metadata.event_capacity != 64
    ):
        raise QualificationError(f"frame {ordinal} wire layout changed")
    if (
        not 1 <= metadata.observation_count <= 5
        or metadata.threshold_provenance != EXPECTED_THRESHOLD_PROVENANCE
    ):
        raise QualificationError(f"frame {ordinal} observation/provenance is invalid")
    if metadata.tandem_state is not TandemState.ARMED_HOLD:
        raise QualificationError(f"frame {ordinal} is not HOLD")
    if type(metadata.ad9361_temperature_mdeg_c) is not int or not (
        -100_000 <= metadata.ad9361_temperature_mdeg_c <= 200_000
    ):
        raise QualificationError(f"frame {ordinal} temperature evidence is invalid")
    if (
        metadata.gain_table_id is not EXPECTED_GAIN_TABLE
        or metadata.minimum_gain_db != EXPECTED_MINIMUM_GAIN_DB
        or metadata.maximum_gain_db != EXPECTED_MAXIMUM_GAIN_DB
        or metadata.initial_gain_db != HOLD_GAIN_DB
        or metadata.minimum_gain_index != EXPECTED_MINIMUM_GAIN_INDEX
        or metadata.maximum_gain_index != EXPECTED_MAXIMUM_GAIN_INDEX
    ):
        raise QualificationError(f"frame {ordinal} HOLD gain provenance changed")
    if not (
        metadata.rx1_gain_index == metadata.rx2_gain_index == EXPECTED_HOLD_GAIN_INDEX
    ):
        raise QualificationError(f"frame {ordinal} endpoint is torn or out of range")
    if (
        metadata.tandem_transition_count != 0
        or metadata.event_count != 0
        or metadata.gain_events
    ):
        raise QualificationError(f"frame {ordinal} contains a gain event")
    if metadata.observation_overflow_count or metadata.event_overflow_count:
        raise QualificationError(f"frame {ordinal} reports metadata overflow")


def validate_full_drain_frames(
    frames: Sequence[TandemFrameMetadata],
    *,
    status_after_open: Mapping[str, Any],
    status_before_close: Mapping[str, Any],
    frame_samples: int = FRAME_SAMPLES,
) -> dict[str, Any]:
    """Require one exact 64-frame, event-free HOLD stream."""

    if len(frames) != BATCH_FRAMES:
        raise QualificationError(
            f"full drain returned {len(frames)} frames, expected {BATCH_FRAMES}"
        )
    first = frames[0]
    open_status = _require_hold(status_after_open, label="full-drain open binding")
    close_status = _require_hold(status_before_close, label="full-drain close binding")
    if open_status != close_status:
        raise QualificationError("full-drain owned status changed")
    if first.buffer_sequence != 0:
        raise QualificationError("full drain did not begin at buffer sequence zero")
    for ordinal, metadata in enumerate(frames):
        _validate_hold_metadata(metadata, ordinal=ordinal)
        if (
            metadata.stream_id != first.stream_id
            or metadata.ownership_epoch != first.ownership_epoch
        ):
            raise QualificationError("stream ID or ownership epoch changed")
        if metadata.buffer_sequence != ordinal:
            raise QualificationError(f"buffer sequence at {ordinal} is not exact")
        expected_sample = first.first_sample_sequence + ordinal * frame_samples
        if metadata.first_sample_sequence != expected_sample:
            raise QualificationError(f"sample sequence at {ordinal} is not contiguous")
        if metadata.samples_per_channel != frame_samples:
            raise QualificationError(f"sample count at {ordinal} changed")
        if (
            metadata.ownership_epoch != open_status["ownership_epoch"]
            or metadata.rx1_gain_index != open_status["rx1_gain_index"]
            or metadata.rx2_gain_index != open_status["rx2_gain_index"]
        ):
            raise QualificationError(
                f"frame {ordinal} does not bind to owned HOLD status"
            )
    return {
        "verified": True,
        "frame_count": len(frames),
        "stream_id": first.stream_id,
        "ownership_epoch": first.ownership_epoch,
        "buffer_sequence_range": [0, BATCH_FRAMES - 1],
        "sample_sequence_range": [
            first.first_sample_sequence,
            first.first_sample_sequence + BATCH_FRAMES * frame_samples,
        ],
        "sample_gaps": 0,
        "gain_events": 0,
        "faults": 0,
        "overflows": 0,
    }


def _hold_request() -> bytes:
    return build_tandem_request(
        mode=TandemMode.HOLD,
        initial_gain_db=HOLD_GAIN_DB,
        samples_per_channel=FRAME_SAMPLES,
    )


def _new_buffer(iio_module: Any, rx: Any) -> Any:
    value, abi = create_metadata_buffer(
        iio_module,
        rx,
        FRAME_SAMPLES,
        metadata_capacity=METADATA_CAPACITY,
        tandem_request=_hold_request(),
        batch_frames=BATCH_FRAMES,
    )
    if abi != 2:
        close_iio_object(value)
        raise QualificationError(f"metadata ABI {abi} is not request ABI 2")
    if value.batch_frames != BATCH_FRAMES:
        close_iio_object(value)
        raise QualificationError("pylibiio batch frame readback changed")
    return value


def _full_drain(
    iio_module: Any,
    rx: Any,
    tandem: Any,
    *,
    raw_metadata_sink: list[tuple[str, int, bytes]] | None = None,
    normalization_completed_ns: int | None = None,
) -> dict[str, Any]:
    rx.set_kernel_buffers_count(KERNEL_BUFFERS)
    open_requested_ns = time.monotonic_ns()
    if (
        normalization_completed_ns is not None
        and open_requested_ns < normalization_completed_ns
    ):
        raise QualificationError("metadata buffer open predates normalization")
    buffer = _new_buffer(iio_module, rx)
    frames: list[TandemFrameMetadata] = []
    records: list[dict[str, Any]] = []
    close_method = "explicit_normal_close"
    try:
        status_open = _require_hold(_status(tandem), label="full-drain open")
        for ordinal in range(BATCH_FRAMES):
            started = time.monotonic_ns()
            metadata_bytes = bytes(buffer.refill())
            completed = time.monotonic_ns()
            iq = bytes(buffer.read())
            record, metadata = _frame_record(
                ordinal, metadata_bytes, iq, completed - started
            )
            if raw_metadata_sink is not None:
                raw_metadata_sink.append(("full_drain", ordinal, metadata_bytes))
            records.append(record)
            frames.append(metadata)
        status_before_close = _require_hold(
            _status(tandem), label="full-drain before close"
        )
        cache_bytes = int(buffer.batch_cache_bytes)
        if cache_bytes != EXPECTED_BATCH_CACHE_BYTES:
            raise QualificationError(
                f"batch cache bound {cache_bytes} != {EXPECTED_BATCH_CACHE_BYTES}"
            )
        continuity = validate_full_drain_frames(
            frames,
            status_after_open=status_open,
            status_before_close=status_before_close,
        )
    finally:
        close_iio_object(buffer)
        buffer = None
        gc.collect()
    status_after_close = _require_post_hold_idle(
        _wait_idle(tandem, label="full-drain close"),
        label="full-drain close endpoint",
    )
    close_completed_ns = time.monotonic_ns()
    return {
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "metadata_capacity_bytes": METADATA_CAPACITY,
        "batch_cache_bound_bytes": cache_bytes,
        "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        "normalization_completed_monotonic_ns": normalization_completed_ns,
        "first_buffer_open_requested_monotonic_ns": open_requested_ns,
        "status_after_open": status_open,
        "status_before_close": status_before_close,
        "close_method": close_method,
        "close_completed_monotonic_ns": close_completed_ns,
        "frames": records,
        "continuity": continuity,
        "status_after_close": status_after_close,
    }


def _post_full_drain_barrier(phy: Any, tx: Any, tandem: Any) -> dict[str, Any]:
    """Re-establish mute and IDLE before any later lifecycle activity."""

    started_ns = time.monotonic_ns()
    mute = _force_mute(phy, tx)
    mute_completed_ns = time.monotonic_ns()
    tandem_status = _require_post_hold_idle(
        _wait_idle(tandem, label="post-full mute barrier"),
        label="post-full mute barrier endpoint",
    )
    idle_verified_ns = time.monotonic_ns()
    rx_state = _read_rx_state(phy)
    if rx_state["modes"] != ["manual", "manual"] or any(
        not math.isfinite(gain) or abs(gain - HOLD_GAIN_DB) > 0.1
        for gain in rx_state["gains_db"]
    ):
        raise QualificationError("post-full RX readback is not retained manual40")
    completed_ns = time.monotonic_ns()
    return {
        "verified": True,
        "policy": "force mute, verify closed HOLD IDLE, then read RX without writes",
        "started_monotonic_ns": started_ns,
        "mute_completed_monotonic_ns": mute_completed_ns,
        "idle_verified_monotonic_ns": idle_verified_ns,
        "completed_monotonic_ns": completed_ns,
        "metadata_buffer_open_count": 0,
        "operation_order": ["force_mute", "verify_idle", "read_rx_state"],
        "mute": mute,
        "tandem_status": tandem_status,
        "rx_state": rx_state,
    }


def _expect_oserror(call: Any, expected_errno: int, *, label: str) -> dict[str, Any]:
    try:
        call()
    except OSError as error:
        if error.errno != expected_errno:
            raise QualificationError(
                f"{label} errno {error.errno}, expected {expected_errno}"
            ) from error
        return _error_record(error)
    raise QualificationError(f"{label} unexpectedly succeeded")


def _cancel_lifecycle(
    iio_module: Any,
    rx: Any,
    phy: Any,
    tx: Any,
    tandem: Any,
    *,
    raw_metadata_sink: list[tuple[str, int, bytes]] | None = None,
) -> dict[str, Any]:
    rx.set_kernel_buffers_count(KERNEL_BUFFERS)
    old_open_requested_ns = time.monotonic_ns()
    old = _new_buffer(iio_module, rx)
    busy: Any = None
    fresh: Any = None
    result: dict[str, Any] = {
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "old_buffer_open_requested_monotonic_ns": old_open_requested_ns,
        "operation_order": [],
    }
    try:
        result["status_after_old_open"] = _require_hold(
            _status(tandem), label="cancel old open"
        )
        started = time.monotonic_ns()
        metadata_bytes = bytes(old.refill())
        completed = time.monotonic_ns()
        iq = bytes(old.read())
        first_record, first_metadata = _frame_record(
            0, metadata_bytes, iq, completed - started
        )
        if raw_metadata_sink is not None:
            raw_metadata_sink.append(("cancel_first", 0, metadata_bytes))
        _validate_hold_metadata(first_metadata, ordinal=0)
        if first_metadata.buffer_sequence != 0:
            raise QualificationError(
                "canceled session first frame is not sequence zero"
            )
        old_status = result["status_after_old_open"]
        if (
            first_metadata.ownership_epoch != old_status["ownership_epoch"]
            or first_metadata.rx1_gain_index != old_status["rx1_gain_index"]
            or first_metadata.rx2_gain_index != old_status["rx2_gain_index"]
        ):
            raise QualificationError(
                "canceled session first frame does not bind to owned HOLD status"
            )
        result["first_returned_cached_frame"] = first_record
        result["operation_order"].append("first_cached_frame_returned")
        old.cancel()
        result["operation_order"].append("old_buffer_cancel")

        def attempt_busy_open() -> None:
            nonlocal busy
            busy = _new_buffer(iio_module, rx)

        result["second_open_error"] = _expect_oserror(
            attempt_busy_open, errno.EBUSY, label="second metadata open"
        )
        result["operation_order"].append("second_open_ebusy")
        result["poison_refill_error"] = _expect_oserror(
            old.refill, errno.EBADF, label="old poisoned refill"
        )
        result["operation_order"].append("old_refill_ebadf")
        close_iio_object(old)
        old = None
        gc.collect()
        result["old_buffer_close_completed_monotonic_ns"] = time.monotonic_ns()
        result["operation_order"].append("old_buffer_close")
        result["mute_after_old_close_started_monotonic_ns"] = time.monotonic_ns()
        result["mute_after_old_close"] = _force_mute(phy, tx)
        result["mute_after_old_close_completed_monotonic_ns"] = time.monotonic_ns()
        result["operation_order"].append("mute_after_old_close")
        result["status_after_old_close"] = _require_post_hold_idle(
            _wait_idle(tandem, label="canceled old close"),
            label="canceled old close endpoint",
        )
        result["old_close_idle_verified_monotonic_ns"] = time.monotonic_ns()
        result["operation_order"].append("verify_old_close_idle")

        result["fresh_buffer_open_requested_monotonic_ns"] = time.monotonic_ns()
        fresh = _new_buffer(iio_module, rx)
        result["operation_order"].append("fresh_buffer_open")
        result["status_after_fresh_open"] = _require_hold(
            _status(tandem), label="fresh recovery open"
        )
        close_iio_object(fresh)
        fresh = None
        gc.collect()
        result["operation_order"].append("fresh_buffer_close")
        result["status_after_fresh_close"] = _require_post_hold_idle(
            _wait_idle(tandem, label="fresh recovery close"),
            label="fresh recovery close endpoint",
        )
        result["fresh_buffer_close_completed_monotonic_ns"] = time.monotonic_ns()
        result["verified"] = True
        return result
    finally:
        close_iio_object(busy)
        close_iio_object(fresh)
        close_iio_object(old)
        gc.collect()


def _attest_identity(
    context: Any,
    *,
    serial: str,
    uri: str,
    firmware_pattern: str,
) -> dict[str, Any]:
    if serial != DEFAULT_R18_SERIAL:
        raise QualificationError("lifecycle gate is frozen to the exact R18 serial")
    if firmware_pattern != EXPECTED_FIRMWARE_PATTERN:
        raise QualificationError("lifecycle gate requires the exact RC3 pattern")
    if not uri.startswith("usb:"):
        raise QualificationError("lifecycle gate requires a local USB context")
    attrs = {str(name): str(value) for name, value in context.attrs.items()}
    observed_serial = attrs.get("hw_serial", attrs.get("serial", ""))
    if observed_serial != serial:
        raise QualificationError(
            f"opened serial {observed_serial!r}, expected {serial!r}"
        )
    firmware = attrs.get("fw_version", "")
    if (
        firmware != EXPECTED_FIRMWARE_VERSION
        or re.fullmatch(firmware_pattern, firmware) is None
    ):
        raise QualificationError(
            f"firmware {firmware!r} does not fullmatch {firmware_pattern!r}"
        )
    expected_attrs = {
        "hw_model": EXPECTED_HARDWARE_MODEL,
        "hw_serial": DEFAULT_R18_SERIAL,
        "fw_version": EXPECTED_FIRMWARE_VERSION,
        "ad9361-phy,model": "ad9361",
        "local,kernel": EXPECTED_KERNEL_VERSION,
        "iio,buffer-metadata": "2",
    }
    for name, expected in expected_attrs.items():
        if attrs.get(name) != expected:
            raise QualificationError(
                f"context attribute {name!r} {attrs.get(name)!r} != {expected!r}"
            )
    if attrs.get("uri", uri) != uri:
        raise QualificationError("opened context URI does not bind to USB discovery")
    return {
        "serial": observed_serial,
        "uri": uri,
        "firmware_version": firmware,
        "context_attrs": attrs,
    }


def _preflight(
    context: Any,
    phy: Any,
    tx: Any,
    tandem: Any,
    *,
    serial: str,
    uri: str,
    firmware_pattern: str,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started_ns = time.monotonic_ns()
    identity_record = (
        dict(identity)
        if identity is not None
        else _attest_identity(
            context,
            serial=serial,
            uri=uri,
            firmware_pattern=firmware_pattern,
        )
    )
    mute = _read_mute(phy, tx)
    if not mute["verified"]:
        raise QualificationError(
            "read-only preflight refuses to touch a radio not already muted: "
            + "; ".join(mute["failures"])
        )
    status = _require_idle(_status(tandem), label="read-only preflight")
    rx_state = _read_rx_state(phy)
    rf_state = _read_rf_state(phy)
    _validate_boot_rx_record(rx_state, name="live preflight RX")
    _validate_rf_state(rf_state, name="live preflight RF", normalized=False)
    completed_ns = time.monotonic_ns()
    return {
        "verdict": "GO",
        **identity_record,
        "mute": mute,
        "rx_state": rx_state,
        "rf_state": rf_state,
        "tandem_status": status,
        "started_monotonic_ns": started_ns,
        "completed_monotonic_ns": completed_ns,
        "configuration_write_count": 0,
        "metadata_buffer_open_count": 0,
    }


def _resolve_uri(iio_module: Any, serial: str) -> str:
    contexts = iio_module.scan_contexts()
    matches = [
        uri
        for uri, description in contexts.items()
        if uri.startswith("usb:") and serial in str(description)
    ]
    if len(matches) != 1:
        raise QualificationError(
            f"expected exactly one local USB context for {serial}; got {matches}"
        )
    return matches[0]


def _lock_path(serial: str) -> pathlib.Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    return pathlib.Path(f"/tmp/plutosdr-fw-radio-{safe}.lock")


def _open_lock(serial: str) -> Any:
    path = _lock_path(serial)
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as error:
        raise QualificationError(f"R18 lock cannot be opened safely: {path}") from error
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        os.close(descriptor)
        raise QualificationError("R18 lock is not an owned regular file")
    if stat.S_IMODE(info.st_mode) != 0o600:
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.close(descriptor)
            raise QualificationError("R18 lock could not be made private mode 0600")
    return os.fdopen(descriptor, "r+", encoding="utf-8")


def _required_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QualificationError(f"durable {name} is not an object")
    return value


def _required_list(value: Any, *, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise QualificationError(f"durable {name} is not a list")
    return value


def _required_int(
    value: Any,
    *,
    name: str,
    minimum: int | None = None,
    maximum: int = MAXIMUM_UNSIGNED_64,
) -> int:
    if (
        type(value) is not int
        or (minimum is not None and value < minimum)
        or value < -MAXIMUM_SIGNED_64 - 1
        or value > maximum
    ):
        raise QualificationError(f"durable {name} is not an exact bounded integer")
    return value


def _required_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualificationError(f"durable {name} is not numeric")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise QualificationError(f"durable {name} is not bounded") from error
    if not math.isfinite(result):
        raise QualificationError(f"durable {name} is not finite")
    return result


def _required_float(value: Any, *, name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise QualificationError(f"durable {name} is not an exact finite float")
    return value


def _json_identical(observed: Any, expected: Any) -> bool:
    if type(observed) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(observed) == set(expected) and all(
            _json_identical(observed[key], item) for key, item in expected.items()
        )
    if isinstance(expected, list):
        return len(observed) == len(expected) and all(
            _json_identical(left, right)
            for left, right in zip(observed, expected, strict=True)
        )
    return observed == expected


def _validate_strict_json_domain(value: Any) -> None:
    """Bound the public validator input before traversing report-controlled data."""

    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAXIMUM_JSON_NODES or depth > MAXIMUM_JSON_DEPTH:
            raise QualificationError("durable report JSON structure is unbounded")
        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if not -MAXIMUM_SIGNED_64 - 1 <= current <= MAXIMUM_UNSIGNED_64:
                raise QualificationError("durable report integer is unbounded")
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise QualificationError("durable report number is nonfinite")
            continue
        if type(current) is str:
            if "\0" in current:
                raise QualificationError("durable report string contains NUL")
            try:
                encoded = current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise QualificationError(
                    "durable report string is not valid Unicode"
                ) from error
            if len(encoded) > MAXIMUM_JSON_STRING_BYTES:
                raise QualificationError("durable report string is unbounded")
            continue
        if type(current) is list:
            stack.extend((item, depth + 1) for item in current)
            continue
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str:
                    raise QualificationError("durable report object key is not text")
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
            continue
        raise QualificationError("durable report contains a non-JSON value")


def _validate_mute_record(
    value: Any,
    *,
    name: str,
    allowed_extra_fields: Sequence[str] = (),
    require_forced_mute: bool = False,
) -> None:
    record = _required_mapping(value, name=name)
    expected_fields = {
        "verified",
        "tx1_gain_db",
        "tx2_gain_db",
        "selectors",
        "dds",
        "failures",
        *allowed_extra_fields,
    }
    if set(record) != expected_fields:
        raise QualificationError(f"durable {name} fields changed")
    if record.get("verified") is not True or record.get("failures") != []:
        raise QualificationError(f"durable {name} is not verified")
    for gain_name in ("tx1_gain_db", "tx2_gain_db"):
        gain = _required_float(record.get(gain_name), name=f"{name} {gain_name}")
        if gain > -80 or (require_forced_mute and abs(gain - TX_MUTE_DB) > 0.26):
            raise QualificationError(f"durable {name} {gain_name} is not muted")
    if not _json_identical(record.get("selectors"), [DAC_SELECT_ZERO] * 4):
        raise QualificationError(f"durable {name} selectors are not ZERO")
    dds = _required_mapping(record.get("dds"), name=f"{name} DDS")
    if set(dds) != {f"altvoltage{i}" for i in range(8)}:
        raise QualificationError(f"durable {name} DDS coverage changed")
    for channel_name, channel_value in dds.items():
        channel = _required_mapping(channel_value, name=f"{name} {channel_name}")
        if set(channel) != {"present", "raw", "scale"}:
            raise QualificationError(f"durable {name} {channel_name} fields changed")
        if channel.get("present") is not True:
            raise QualificationError(f"durable {name} {channel_name} is absent")
        for attribute in ("raw", "scale"):
            if (
                abs(
                    _required_float(
                        channel.get(attribute),
                        name=f"{name} {channel_name} {attribute}",
                    )
                )
                > 1e-9
            ):
                raise QualificationError(
                    f"durable {name} {channel_name} {attribute} is nonzero"
                )


def _validate_rx_record(value: Any, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if set(record) != {"modes", "gains_db"}:
        raise QualificationError(f"durable {name} fields changed")
    if record.get("modes") != ["manual", "manual"]:
        raise QualificationError(f"durable {name} modes are not manual/manual")
    gains = _required_list(record.get("gains_db"), name=f"{name} gains")
    if len(gains) != 2 or any(
        abs(_required_float(gain, name=f"{name} gain") - HOLD_GAIN_DB) > 0.1
        for gain in gains
    ):
        raise QualificationError(f"durable {name} gains are not 40/40")


def _validate_boot_rx_record(value: Any, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if set(record) != {"modes", "gains_db"}:
        raise QualificationError(f"durable {name} fields changed")
    modes = _required_list(record.get("modes"), name=f"{name} modes")
    gains = _required_list(record.get("gains_db"), name=f"{name} gains")
    allowed_modes = {"manual", "fast_attack", "slow_attack", "hybrid"}
    if len(modes) != 2 or any(type(mode) is not str for mode in modes):
        raise QualificationError(f"durable {name} modes are malformed")
    if any(mode not in allowed_modes for mode in modes):
        raise QualificationError(f"durable {name} mode is unknown")
    if len(gains) != 2 or any(
        not -3.0 <= _required_float(gain, name=f"{name} gain") <= 71.0 for gain in gains
    ):
        raise QualificationError(f"durable {name} gain is outside AD9361 bounds")


def _validate_rf_state(value: Any, *, name: str, normalized: bool) -> None:
    record = _required_mapping(value, name=name)
    if set(record) != {"rx_lo_hz", "tx_lo_hz", "channels"}:
        raise QualificationError(f"durable {name} fields changed")
    rx_lo = _required_int(record.get("rx_lo_hz"), name=f"{name} RX LO", minimum=1)
    tx_lo = _required_int(record.get("tx_lo_hz"), name=f"{name} TX LO", minimum=1)
    channels = _required_mapping(record.get("channels"), name=f"{name} channels")
    if set(channels) != {role for role, _, _ in RF_CHANNELS}:
        raise QualificationError(f"durable {name} channel coverage changed")
    observed: list[tuple[int, int]] = []
    for role, _, _ in RF_CHANNELS:
        channel = _required_mapping(channels.get(role), name=f"{name} {role}")
        if set(channel) != {"sampling_frequency_hz", "rf_bandwidth_hz"}:
            raise QualificationError(f"durable {name} {role} fields changed")
        rate = _required_int(
            channel.get("sampling_frequency_hz"),
            name=f"{name} {role} sampling frequency",
            minimum=1,
        )
        bandwidth = _required_int(
            channel.get("rf_bandwidth_hz"),
            name=f"{name} {role} RF bandwidth",
            minimum=1,
        )
        observed.append((rate, bandwidth))
    if not normalized:
        return
    if (
        abs(rx_lo - CENTER_FREQUENCY_HZ) > LO_READBACK_TOLERANCE_HZ
        or abs(tx_lo - CENTER_FREQUENCY_HZ) > LO_READBACK_TOLERANCE_HZ
    ):
        raise QualificationError(f"durable {name} LO normalization changed")
    for rate, bandwidth in observed:
        if (
            abs(rate - SAMPLE_RATE_HZ) > SAMPLE_RATE_READBACK_TOLERANCE_HZ
            or abs(bandwidth - RF_BANDWIDTH_HZ) > RF_BANDWIDTH_READBACK_TOLERANCE_HZ
        ):
            raise QualificationError(f"durable {name} rate/bandwidth changed")


def _normalization_operation_contract() -> list[tuple[str, str, Any, Any]]:
    result: list[tuple[str, str, Any, Any]] = [
        ("rx_lo", "frequency", CENTER_FREQUENCY_HZ, LO_READBACK_TOLERANCE_HZ),
        ("tx_lo", "frequency", CENTER_FREQUENCY_HZ, LO_READBACK_TOLERANCE_HZ),
    ]
    for role, _, _ in RF_CHANNELS:
        result.extend(
            [
                (
                    role,
                    "sampling_frequency",
                    SAMPLE_RATE_HZ,
                    SAMPLE_RATE_READBACK_TOLERANCE_HZ,
                ),
                (
                    role,
                    "rf_bandwidth",
                    RF_BANDWIDTH_HZ,
                    RF_BANDWIDTH_READBACK_TOLERANCE_HZ,
                ),
            ]
        )
    result.extend(
        [
            ("rx0", "gain_control_mode", "manual", None),
            ("rx1", "gain_control_mode", "manual", None),
            ("rx0", "hardwaregain", HOLD_GAIN_DB, 0.1),
            ("rx1", "hardwaregain", HOLD_GAIN_DB, 0.1),
        ]
    )
    return result


def _validate_normalization(value: Any) -> None:
    record = _required_mapping(value, name="normalization")
    expected_fields = {
        "verified",
        "policy",
        "started_monotonic_ns",
        "mute_barrier_completed_monotonic_ns",
        "completed_monotonic_ns",
        "metadata_buffer_open_count_before",
        "metadata_buffer_open_count_after",
        "mute_barrier",
        "tandem_status_before",
        "operations",
        "rf_state_after",
        "rx_state_after",
        "mute_after",
        "tandem_status_after",
        "expected_gain_table",
    }
    if set(record) != expected_fields or record.get("verified") is not True:
        raise QualificationError("durable normalization fields/verdict changed")
    if record.get("policy") != (
        "safe preflight, complete mute barrier, then RF/RX normalization; "
        "zero metadata buffers until every readback passes"
    ):
        raise QualificationError("durable normalization policy changed")
    started = _required_int(
        record.get("started_monotonic_ns"),
        name="normalization start",
        minimum=1,
        maximum=MAXIMUM_SIGNED_64,
    )
    muted = _required_int(
        record.get("mute_barrier_completed_monotonic_ns"),
        name="normalization mute completion",
        minimum=started,
        maximum=MAXIMUM_SIGNED_64,
    )
    completed = _required_int(
        record.get("completed_monotonic_ns"),
        name="normalization completion",
        minimum=muted,
        maximum=MAXIMUM_SIGNED_64,
    )
    if (
        _required_int(
            record.get("metadata_buffer_open_count_before"),
            name="normalization buffer count before",
        )
        != 0
        or _required_int(
            record.get("metadata_buffer_open_count_after"),
            name="normalization buffer count after",
        )
        != 0
    ):
        raise QualificationError("durable normalization opened a metadata buffer")
    _validate_mute_record(
        record.get("mute_barrier"),
        name="normalization barrier",
        require_forced_mute=True,
    )
    _validate_mute_record(
        record.get("mute_after"),
        name="normalization post-mute",
        require_forced_mute=True,
    )
    if record.get("mute_after") != record.get("mute_barrier"):
        raise QualificationError("durable mute state changed during normalization")
    before_status = _require_idle(
        _required_mapping(
            record.get("tandem_status_before"), name="normalization before status"
        ),
        label="durable normalization before",
    )
    after_status = _require_idle(
        _required_mapping(
            record.get("tandem_status_after"), name="normalization after status"
        ),
        label="durable normalization after",
    )
    if before_status != after_status:
        raise QualificationError("durable tandem status changed during normalization")
    operations = _required_list(record.get("operations"), name="normalization ops")
    contract = _normalization_operation_contract()
    if len(operations) != len(contract):
        raise QualificationError("durable normalization operation count changed")
    previous_ns = muted
    for ordinal, (operation_value, expected) in enumerate(
        zip(operations, contract, strict=True)
    ):
        operation = _required_mapping(
            operation_value, name=f"normalization operation {ordinal}"
        )
        if set(operation) != {
            "ordinal",
            "target",
            "attribute",
            "requested",
            "readback",
            "tolerance",
            "host_before_ns",
            "host_after_ns",
        }:
            raise QualificationError(
                f"durable normalization operation {ordinal} fields changed"
            )
        target, attribute, requested, tolerance = expected
        if (
            _required_int(
                operation.get("ordinal"),
                name=f"normalization operation {ordinal} ordinal",
            )
            != ordinal
            or operation.get("target") != target
            or operation.get("attribute") != attribute
            or type(operation.get("requested")) is not type(requested)
            or operation.get("requested") != requested
            or type(operation.get("tolerance")) is not type(tolerance)
            or operation.get("tolerance") != tolerance
        ):
            raise QualificationError(
                f"durable normalization operation {ordinal} contract changed"
            )
        host_before = _required_int(
            operation.get("host_before_ns"),
            name=f"normalization operation {ordinal} before",
            minimum=previous_ns,
            maximum=MAXIMUM_SIGNED_64,
        )
        host_after = _required_int(
            operation.get("host_after_ns"),
            name=f"normalization operation {ordinal} after",
            minimum=host_before,
            maximum=MAXIMUM_SIGNED_64,
        )
        if host_before < previous_ns or host_after > completed:
            raise QualificationError(
                f"durable normalization operation {ordinal} chronology changed"
            )
        readback = operation.get("readback")
        if isinstance(requested, str):
            if type(readback) is not str or readback != requested:
                raise QualificationError(
                    f"durable normalization operation {ordinal} readback changed"
                )
        else:
            observed = _required_float(
                readback, name=f"normalization operation {ordinal} readback"
            )
            assert tolerance is not None
            if abs(observed - requested) > float(tolerance):
                raise QualificationError(
                    f"durable normalization operation {ordinal} readback changed"
                )
        previous_ns = host_after
    _validate_rf_state(
        record.get("rf_state_after"), name="normalization RF", normalized=True
    )
    _validate_rx_record(record.get("rx_state_after"), name="normalization RX")
    expected_table = _required_mapping(
        record.get("expected_gain_table"), name="normalization gain table"
    )
    if not _json_identical(
        expected_table,
        {
            "selection_basis": "common RX/TX LO at or below 1300000000 Hz",
            "center_frequency_hz": CENTER_FREQUENCY_HZ,
            "gain_table_id": int(EXPECTED_GAIN_TABLE),
            "gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
            "hold_frame_attestation_required": True,
        },
    ):
        raise QualificationError("durable expected gain table changed")


def _validate_post_full_drain_barrier(
    value: Any,
    *,
    full_close_completed_ns: int,
    full_close_status: Mapping[str, Any],
) -> None:
    record = _required_mapping(value, name="post-full barrier")
    if set(record) != {
        "verified",
        "policy",
        "started_monotonic_ns",
        "mute_completed_monotonic_ns",
        "idle_verified_monotonic_ns",
        "completed_monotonic_ns",
        "metadata_buffer_open_count",
        "operation_order",
        "mute",
        "tandem_status",
        "rx_state",
    }:
        raise QualificationError("durable post-full barrier fields changed")
    if (
        record.get("verified") is not True
        or record.get("policy")
        != "force mute, verify closed HOLD IDLE, then read RX without writes"
        or not _json_identical(
            record.get("operation_order"),
            ["force_mute", "verify_idle", "read_rx_state"],
        )
        or not _json_identical(record.get("metadata_buffer_open_count"), 0)
    ):
        raise QualificationError("durable post-full barrier policy changed")
    started = _required_int(
        record.get("started_monotonic_ns"),
        name="post-full barrier start",
        minimum=full_close_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    muted = _required_int(
        record.get("mute_completed_monotonic_ns"),
        name="post-full mute completion",
        minimum=started,
        maximum=MAXIMUM_SIGNED_64,
    )
    idle = _required_int(
        record.get("idle_verified_monotonic_ns"),
        name="post-full idle verification",
        minimum=muted,
        maximum=MAXIMUM_SIGNED_64,
    )
    _required_int(
        record.get("completed_monotonic_ns"),
        name="post-full RX readback completion",
        minimum=idle,
        maximum=MAXIMUM_SIGNED_64,
    )
    _validate_mute_record(
        record.get("mute"),
        name="post-full mute",
        require_forced_mute=True,
    )
    status = _require_post_hold_idle(
        _required_mapping(record.get("tandem_status"), name="post-full status"),
        label="durable post-full status",
    )
    if not _json_identical(status, full_close_status):
        raise QualificationError("durable post-full status changed after full close")
    _validate_rx_record(record.get("rx_state"), name="post-full RX")


def _validate_output_preflight(value: Any) -> pathlib.Path:
    record = _required_mapping(value, name="output preflight")
    if set(record) != {
        "verified",
        "absolute_report_path",
        "absolute_temporary_path",
        "absolute_raw_metadata_directory",
        "report_existed_before_context",
        "temporary_existed_before_context",
        "raw_metadata_directory_existed_before_context",
        "symlink_components",
    }:
        raise QualificationError("durable output preflight fields changed")
    if (
        record.get("verified") is not True
        or record.get("report_existed_before_context") is not False
        or record.get("temporary_existed_before_context") is not False
        or record.get("raw_metadata_directory_existed_before_context") is not False
        or _required_int(
            record.get("symlink_components"), name="output symlink component count"
        )
        != 0
    ):
        raise QualificationError("durable output was not fresh before context open")
    report_path = pathlib.Path(str(record.get("absolute_report_path", "")))
    temporary = pathlib.Path(str(record.get("absolute_temporary_path", "")))
    artifact_directory = pathlib.Path(
        str(record.get("absolute_raw_metadata_directory", ""))
    )
    if (
        not report_path.is_absolute()
        or report_path.suffix != ".json"
        or temporary != report_path.with_suffix(report_path.suffix + ".tmp")
        or artifact_directory != report_path.parent / RAW_METADATA_DIRECTORY
    ):
        raise QualificationError("durable output paths changed")
    try:
        _require_nonsymlink_path(report_path, include_leaf=True)
        _require_nonsymlink_path(temporary, include_leaf=True)
        _require_nonsymlink_path(artifact_directory, include_leaf=True)
        if temporary.exists():
            raise QualificationError("durable output temporary path remains")
    except QualificationError:
        raise
    except (OSError, ValueError) as error:
        raise QualificationError("durable output paths cannot be inspected") from error
    return report_path


def _validate_hold_observation_wire(
    payload: bytes, metadata: TandemFrameMetadata, *, name: str
) -> tuple[tuple[int, ...], ...]:
    if (
        len(payload) != RAW_METADATA_BYTES
        or metadata.observation_capacity != 64
        or not 1 <= metadata.observation_count <= 5
    ):
        raise QualificationError(f"durable {name} observation layout changed")
    try:
        (
            rx1_db_start,
            rx2_db_start,
            rx1_db_end,
            rx2_db_end,
            prefix_reserved,
            start_read_duration_ns,
            end_read_duration_ns,
            rx1_first_change_sample,
            rx2_first_change_sample,
            rx1_rssi_start_qdb,
            rx2_rssi_start_qdb,
            rx1_rssi_end_qdb,
            rx2_rssi_end_qdb,
            _rssi_start_read_duration_ns,
            _rssi_end_read_duration_ns,
            provider_interval,
        ) = struct.unpack_from("<bbbbBIIIIHHHHIII", payload, 55)
        prefix_reserved1, prefix_reserved2 = struct.unpack_from("<II", payload, 116)
    except struct.error as error:
        raise QualificationError(
            f"durable {name} observation prefix is truncated"
        ) from error
    if provider_interval != PROVIDER_OBSERVATION_INTERVAL_SAMPLES:
        raise QualificationError(f"durable {name} observation interval changed")
    observations: list[tuple[int, ...]] = []
    frame_start = metadata.first_sample_sequence
    frame_end = frame_start + metadata.samples_per_channel
    previous_before: int | None = None
    previous_after: int | None = None
    for slot in range(64):
        offset = V5_PREFIX_BYTES + slot * GAIN_OBSERVATION_BYTES
        raw_record = payload[offset : offset + GAIN_OBSERVATION_BYTES]
        if slot >= metadata.observation_count:
            if any(raw_record):
                raise QualificationError(
                    f"durable {name} unused observation {slot} is nonzero"
                )
            continue
        if len(raw_record) != GAIN_OBSERVATION_BYTES:
            raise QualificationError(f"durable {name} observation is truncated")
        record = GAIN_OBSERVATION.unpack(raw_record)
        (
            sample_before,
            sample_after,
            _read_duration_ns,
            flags,
            rx1_index,
            rx2_index,
            rx1_db,
            rx2_db,
            reserved0,
            reserved1,
        ) = record
        if (
            flags != GAIN_OBSERVATION_FLAGS
            or reserved0 != 0
            or reserved1 != 0
            or rx1_index != metadata.rx1_gain_index
            or rx2_index != metadata.rx2_gain_index
            or rx1_db != HOLD_GAIN_DB
            or rx2_db != HOLD_GAIN_DB
            or sample_before > sample_after
            or sample_after < frame_start
            or sample_before >= frame_end
            or (previous_after is not None and sample_before < previous_after)
            or (
                previous_before is not None
                and sample_before - previous_before
                < PROVIDER_OBSERVATION_INTERVAL_SAMPLES
            )
        ):
            raise QualificationError(
                f"durable {name} observation {slot} violates HOLD provenance"
            )
        previous_before = sample_before
        previous_after = sample_after
        observations.append(record)
    first = observations[0]
    last = observations[-1]
    if (
        prefix_reserved != 0
        or prefix_reserved1 != 0
        or prefix_reserved2 != 0
        or rx1_first_change_sample != (1 << 32) - 1
        or rx2_first_change_sample != (1 << 32) - 1
        or 0xFFFF
        in {
            rx1_rssi_start_qdb,
            rx2_rssi_start_qdb,
            rx1_rssi_end_qdb,
            rx2_rssi_end_qdb,
        }
        or (rx1_db_start, rx2_db_start, rx1_db_end, rx2_db_end) != (HOLD_GAIN_DB,) * 4
        or start_read_duration_ns != first[2]
        or end_read_duration_ns != last[2]
    ):
        raise QualificationError(f"durable {name} observation prefix changed")
    return tuple(observations)


def _validate_metadata_artifacts(
    report: Mapping[str, Any], *, report_path: pathlib.Path
) -> None:
    manifest = _required_mapping(
        report.get("metadata_artifacts"), name="metadata artifacts"
    )
    if set(manifest) != {
        "policy",
        "directory_relative",
        "expected_file_count",
        "completed_file_count",
        "total_bytes",
        "manifest_digest_method",
        "manifest_sha256",
        "inventory_state",
        "entries",
    }:
        raise QualificationError("durable metadata artifact fields changed")
    if (
        manifest.get("policy")
        != "retain, reread, hash, and reparse all 64 drain plus cancel-first metadata records"
        or manifest.get("directory_relative") != RAW_METADATA_DIRECTORY
        or _required_int(
            manifest.get("expected_file_count"), name="metadata expected file count"
        )
        != RAW_METADATA_FILE_COUNT
        or _required_int(
            manifest.get("completed_file_count"),
            name="metadata completed file count",
        )
        != RAW_METADATA_FILE_COUNT
        or _required_int(manifest.get("total_bytes"), name="metadata total bytes")
        != RAW_METADATA_FILE_COUNT * RAW_METADATA_BYTES
        or manifest.get("manifest_digest_method")
        != "sha256(path NUL bytes NUL sha256 LF) in entry order"
        or manifest.get("inventory_state") != "complete"
    ):
        raise QualificationError("durable metadata artifact policy/count changed")
    entries = _required_list(manifest.get("entries"), name="metadata entries")
    if len(entries) != RAW_METADATA_FILE_COUNT:
        raise QualificationError("durable metadata artifact inventory is incomplete")
    expected_identities = [
        *(("full_drain", index) for index in range(BATCH_FRAMES)),
        ("cancel_first", 0),
    ]
    artifact_directory = report_path.parent / RAW_METADATA_DIRECTORY
    try:
        inventory_valid = (
            artifact_directory.is_dir()
            and not artifact_directory.is_symlink()
            and {path.name for path in artifact_directory.iterdir()}
            == {
                _metadata_relative_path(role, ordinal).name
                for role, ordinal in expected_identities
            }
        )
    except (OSError, ValueError) as error:
        raise QualificationError(
            "durable metadata directory cannot be inspected"
        ) from error
    if not inventory_valid:
        raise QualificationError("durable metadata directory inventory changed")
    full = _required_mapping(report.get("full_drain"), name="full drain")
    if set(full) != {
        "kernel_buffers",
        "batch_frames",
        "metadata_capacity_bytes",
        "batch_cache_bound_bytes",
        "expected_batch_cache_bytes",
        "normalization_completed_monotonic_ns",
        "first_buffer_open_requested_monotonic_ns",
        "status_after_open",
        "status_before_close",
        "close_method",
        "close_completed_monotonic_ns",
        "frames",
        "continuity",
        "status_after_close",
    }:
        raise QualificationError("durable full-drain fields changed")
    full_frames = _required_list(full.get("frames"), name="full frames")
    cancel = _required_mapping(report.get("cancel_lifecycle"), name="cancel")
    cancel_frame = _required_mapping(
        cancel.get("first_returned_cached_frame"), name="cancel first frame"
    )
    previous_observations: tuple[tuple[int, ...], ...] | None = None
    seen_observations: set[tuple[int, ...]] = set()
    last_distinct_before: int | None = None
    for entry_value, (role, ordinal) in zip(entries, expected_identities, strict=True):
        entry = _required_mapping(
            entry_value, name=f"metadata artifact {role}/{ordinal}"
        )
        if set(entry) != {
            "role",
            "ordinal",
            "relative_path",
            "bytes",
            "sha256",
            "write_completed",
        }:
            raise QualificationError(
                f"durable metadata {role}/{ordinal} fields changed"
            )
        relative = _metadata_relative_path(role, ordinal)
        if (
            entry.get("role") != role
            or _required_int(
                entry.get("ordinal"), name=f"metadata {role}/{ordinal} ordinal"
            )
            != ordinal
            or entry.get("relative_path") != relative.as_posix()
            or _required_int(
                entry.get("bytes"), name=f"metadata {role}/{ordinal} bytes"
            )
            != RAW_METADATA_BYTES
            or entry.get("write_completed") is not True
            or re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))) is None
        ):
            raise QualificationError(
                f"durable metadata {role}/{ordinal} identity changed"
            )
        path = report_path.parent / pathlib.Path(*relative.parts)
        payload = _read_exact_owned_regular_file(
            path,
            expected_bytes=RAW_METADATA_BYTES,
            name=f"durable metadata {role}/{ordinal}",
        )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry.get("sha256"):
            raise QualificationError(
                f"durable metadata {role}/{ordinal} SHA-256 changed"
            )
        try:
            parsed = parse_tandem_frame_metadata(payload)
            observations = _validate_hold_observation_wire(
                payload, parsed, name=f"metadata {role}/{ordinal}"
            )
        except QualificationError:
            raise
        except (OverflowError, struct.error, ValueError) as error:
            raise QualificationError(
                f"durable metadata {role}/{ordinal} wire is invalid"
            ) from error
        if role == "full_drain":
            if previous_observations is not None:
                inherited = tuple(
                    item
                    for item in observations
                    if item[0] < parsed.first_sample_sequence
                )
                retained = tuple(
                    item
                    for item in previous_observations
                    if item[1] >= parsed.first_sample_sequence
                )
                if inherited != retained:
                    raise QualificationError(
                        f"durable metadata frame {ordinal} observation retention changed"
                    )
            for item in observations:
                if item in seen_observations:
                    continue
                if (
                    last_distinct_before is not None
                    and item[0] - last_distinct_before
                    < PROVIDER_OBSERVATION_INTERVAL_SAMPLES
                ):
                    raise QualificationError(
                        f"durable metadata frame {ordinal} observation cadence changed"
                    )
                seen_observations.add(item)
                last_distinct_before = item[0]
            previous_observations = observations
        expected_record = full_frames[ordinal] if role == "full_drain" else cancel_frame
        expected_record = _required_mapping(
            expected_record, name=f"metadata {role}/{ordinal} frame"
        )
        regenerated = _frame_evidence(
            ordinal,
            parsed,
            duration_ns=_required_int(
                expected_record.get("refill_duration_ns"),
                name=f"metadata {role}/{ordinal} refill duration",
                minimum=0,
                maximum=MAXIMUM_SIGNED_64,
            ),
            returned_iq_sha256_in_process=str(
                expected_record.get("returned_iq_sha256_in_process", "")
            ),
            metadata_sha256=digest,
        )
        if not _json_identical(dict(expected_record), regenerated):
            raise QualificationError(
                f"durable metadata {role}/{ordinal} does not reproduce its frame"
            )
    if manifest.get("manifest_sha256") != _metadata_manifest_digest(entries):
        raise QualificationError("durable metadata manifest digest changed")


def _validate_frame_json(
    value: Any,
    *,
    name: str,
    ordinal: int,
    status: Mapping[str, Any],
    expected_stream_id: int | None,
    expected_first_sample: int | None,
) -> tuple[int, int, int, int]:
    record = _required_mapping(value, name=name)
    exact = {
        "ordinal": ordinal,
        "buffer_sequence": ordinal,
        "version": 5,
        "header_bytes": 3_256,
        "samples_per_channel": FRAME_SAMPLES,
        "iq_payload_bytes": EXPECTED_IQ_BYTES,
        "returned_iq_bytes_in_process": EXPECTED_IQ_BYTES,
        "enabled_scan_mask": 0x0F,
        "sample_format": 1,
        "channel_count": 2,
        "observation_capacity": 64,
        "event_capacity": 64,
        "tandem_state": int(TandemState.ARMED_HOLD),
        "tandem_state_name": "armed_hold",
        "tandem_fault_flags": 0,
        "tandem_transition_count": 0,
        "gain_table_id": int(EXPECTED_GAIN_TABLE),
        "gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
        "minimum_gain_db": EXPECTED_MINIMUM_GAIN_DB,
        "maximum_gain_db": EXPECTED_MAXIMUM_GAIN_DB,
        "initial_gain_db": HOLD_GAIN_DB,
        "minimum_gain_index": EXPECTED_MINIMUM_GAIN_INDEX,
        "maximum_gain_index": EXPECTED_MAXIMUM_GAIN_INDEX,
        "event_count": 0,
        "observation_overflow_count": 0,
        "event_overflow_count": 0,
    }
    for field, expected in exact.items():
        if not _json_identical(record.get(field), expected):
            raise QualificationError(
                f"durable {name} {field} {record.get(field)!r} != {expected!r}"
            )
    features = _required_int(record.get("features"), name=f"{name} features")
    flags = _required_int(record.get("flags"), name=f"{name} flags")
    if features != EXACT_METADATA_FEATURES:
        raise QualificationError(f"durable {name} feature mask changed")
    if flags != EXACT_HOLD_METADATA_FLAGS or flags & TANDEM_UNSAFE_FLAGS:
        raise QualificationError(f"durable {name} validity/unsafe flags changed")
    _required_int(
        record.get("ad9361_temperature_mdeg_c"),
        name=f"{name} AD9361 temperature",
        minimum=-100_000,
        maximum=200_000,
    )
    stream_id = _required_int(record.get("stream_id"), name=f"{name} stream", minimum=1)
    epoch = _required_int(
        record.get("ownership_epoch"), name=f"{name} epoch", minimum=1
    )
    first_sample = _required_int(
        record.get("first_sample_sequence"), name=f"{name} first sample", minimum=0
    )
    rx1 = _required_int(record.get("rx1_gain_index"), name=f"{name} RX1 index")
    rx2 = _required_int(record.get("rx2_gain_index"), name=f"{name} RX2 index")
    if expected_stream_id is not None and stream_id != expected_stream_id:
        raise QualificationError(f"durable {name} stream changed")
    if expected_first_sample is not None and first_sample != expected_first_sample:
        raise QualificationError(f"durable {name} sample sequence is not contiguous")
    if (
        epoch != status["ownership_epoch"]
        or rx1 != status["rx1_gain_index"]
        or rx2 != status["rx2_gain_index"]
        or rx1 != rx2
        or rx1 != EXPECTED_HOLD_GAIN_INDEX
    ):
        raise QualificationError(f"durable {name} does not bind to owned HOLD")
    observations = _required_int(
        record.get("observation_count"), name=f"{name} observations", minimum=0
    )
    if not 1 <= observations <= 5:
        raise QualificationError(f"durable {name} observation count changed")
    if (
        _required_int(
            record.get("threshold_provenance"),
            name=f"{name} threshold provenance",
            minimum=1,
        )
        != EXPECTED_THRESHOLD_PROVENANCE
    ):
        raise QualificationError(f"durable {name} threshold provenance changed")
    _required_int(
        record.get("refill_duration_ns"),
        name=f"{name} duration",
        minimum=0,
        maximum=MAXIMUM_SIGNED_64,
    )
    if not _json_identical(record.get("metadata_bytes"), 3_256):
        raise QualificationError(f"durable {name} metadata length changed")
    for digest_name in ("returned_iq_sha256_in_process", "metadata_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(record.get(digest_name, ""))) is None:
            raise QualificationError(f"durable {name} {digest_name} is invalid")
    return stream_id, epoch, first_sample, rx1


def _validate_errno_record(value: Any, expected: int, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if (
        set(record) != {"type", "errno", "message"}
        or record.get("type") != "OSError"
        or _required_int(record.get("errno"), name=f"{name} errno") != expected
        or type(record.get("message")) is not str
    ):
        raise QualificationError(f"durable {name} does not prove errno {expected}")


def validate_durable_pass_report(value: Any) -> None:
    """Reject any durable artifact that could otherwise claim a false PASS."""

    _validate_strict_json_domain(value)
    report = _required_mapping(value, name="report")
    if set(report) != {
        "schema",
        "verdict",
        "release_claim",
        "release_pass_eligible",
        "hardware_qualified",
        "started_unix_ns",
        "completed_unix_ns",
        "host_libiio",
        "runner_provenance",
        "configuration",
        "output_preflight",
        "preflight",
        "normalization",
        "rx_scan",
        "full_drain",
        "post_full_drain_barrier",
        "cancel_lifecycle",
        "metadata_artifacts",
        "final_tandem_status",
        "final_rx_state",
        "final_rf_state",
        "cleanup",
    }:
        raise QualificationError("durable PASS top-level fields changed")
    if report.get("schema") != SCHEMA or report.get("verdict") != "PASS":
        raise QualificationError("durable report schema/verdict changed")
    if report.get("release_claim") != (
        "none; muted host-transport lifecycle qualification only"
    ):
        raise QualificationError("durable report overclaims release evidence")
    if (
        report.get("release_pass_eligible") is not False
        or report.get("hardware_qualified") is not False
    ):
        raise QualificationError("durable lifecycle evidence gained release authority")
    if "error" in report:
        raise QualificationError("durable PASS contains an error record")
    started = _required_int(
        report.get("started_unix_ns"),
        name="start time",
        minimum=1,
        maximum=MAXIMUM_SIGNED_64,
    )
    completed = _required_int(
        report.get("completed_unix_ns"),
        name="completion time",
        minimum=started,
        maximum=MAXIMUM_SIGNED_64,
    )
    if completed < started:
        raise QualificationError("durable report completion predates start")

    host = _required_mapping(report.get("host_libiio"), name="host libiio")
    if set(host) != {
        "source_commit",
        "protected_source_tag",
        "source_directory",
        "build_directory",
        "mapped_shared_objects",
        "mapped_shared_object",
        "mapped_shared_object_sha256",
        "runner_shared_object_sha256",
        "pylibiio_file",
    }:
        raise QualificationError("durable host libiio fields changed")
    if (
        host.get("source_commit") != EXACT_LIBIIO_COMMIT
        or host.get("protected_source_tag") != EXACT_LIBIIO_TAG
    ):
        raise QualificationError("durable host libiio source identity changed")
    mapped = _required_list(
        host.get("mapped_shared_objects"), name="mapped shared objects"
    )
    if mapped != [host.get("mapped_shared_object")]:
        raise QualificationError("durable mapped libiio identity is ambiguous")
    calculated_sha = str(host.get("mapped_shared_object_sha256", ""))
    if (
        re.fullmatch(r"[0-9a-f]{64}", calculated_sha) is None
        or host.get("runner_shared_object_sha256") != calculated_sha
    ):
        raise QualificationError("durable mapped libiio SHA binding failed")
    source = pathlib.Path(str(host.get("source_directory", "")))
    build = pathlib.Path(str(host.get("build_directory", "")))
    library = pathlib.Path(str(host.get("mapped_shared_object", "")))
    if not source.is_absolute() or not build.is_absolute() or not library.is_absolute():
        raise QualificationError("durable libiio paths are not absolute")
    if not library.is_relative_to(build):
        raise QualificationError("durable mapped libiio is outside its build")
    pylibiio = pathlib.Path(str(host.get("pylibiio_file", "")))
    if pylibiio != source / "bindings/python/iio.py":
        raise QualificationError("durable pylibiio is outside exact source tree")
    if (
        _git_bytes(source, "rev-parse", "HEAD").decode().strip() != EXACT_LIBIIO_COMMIT
        or _git_bytes(source, "rev-parse", f"refs/tags/{EXACT_LIBIIO_TAG}^{{commit}}")
        .decode()
        .strip()
        != EXACT_LIBIIO_COMMIT
        or _git_bytes(source, "status", "--porcelain", "--untracked-files=no").strip()
    ):
        raise QualificationError("durable libiio source graph changed")
    cache = build / "CMakeCache.txt"
    cmake_home = None
    try:
        cache_text = _read_bounded_owned_regular_file(
            cache,
            maximum_bytes=MAXIMUM_CMAKE_CACHE_BYTES,
            name="durable libiio CMake cache",
        ).decode("utf-8")
    except UnicodeDecodeError as error:
        raise QualificationError("durable libiio CMake cache is not UTF-8") from error
    for line in cache_text.splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
            cmake_home = pathlib.Path(line.split("=", 1)[1]).resolve()
            break
    if cmake_home != source:
        raise QualificationError("durable libiio build source changed")
    if (
        _sha256_bounded_owned_regular_file(
            library,
            maximum_bytes=MAXIMUM_LIBIIO_BYTES,
            name="durable mapped libiio",
        )
        != calculated_sha
    ):
        raise QualificationError("durable mapped libiio bytes changed")
    pylibiio_blob = hashlib.sha256(
        _git_bytes(
            source,
            "show",
            f"{EXACT_LIBIIO_COMMIT}:bindings/python/iio.py",
        )
    ).hexdigest()
    if (
        _sha256_bounded_owned_regular_file(
            pylibiio,
            maximum_bytes=MAXIMUM_PYLIBIIO_BYTES,
            name="durable pylibiio",
        )
        != pylibiio_blob
    ):
        raise QualificationError("durable pylibiio source changed")

    provenance = _required_mapping(
        report.get("runner_provenance"), name="runner provenance"
    )
    if set(provenance) != {
        "firmware_repo_commit",
        "firmware_repository",
        "python_module_path",
        "python_module_sha256",
        "python_module_head_blob_sha256",
        "shell_runner_path",
        "shell_runner_sha256",
        "shell_runner_head_blob_sha256",
        "metadata_abi_path",
        "metadata_abi_sha256",
        "metadata_abi_head_blob_sha256",
    }:
        raise QualificationError("durable runner provenance fields changed")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("firmware_repo_commit", "")))
        is None
    ):
        raise QualificationError("durable runner commit is invalid")
    for observed_name, head_name in (
        ("python_module_sha256", "python_module_head_blob_sha256"),
        ("shell_runner_sha256", "shell_runner_head_blob_sha256"),
        ("metadata_abi_sha256", "metadata_abi_head_blob_sha256"),
    ):
        observed = str(provenance.get(observed_name, ""))
        head = str(provenance.get(head_name, ""))
        if (
            re.fullmatch(r"[0-9a-f]{64}", observed) is None
            or re.fullmatch(r"[0-9a-f]{64}", head) is None
            or observed != head
        ):
            raise QualificationError(
                f"durable runner {observed_name} is not its exact HEAD blob"
            )
    module_path = pathlib.Path(str(provenance.get("python_module_path", "")))
    shell_path = pathlib.Path(str(provenance.get("shell_runner_path", "")))
    metadata_abi_path = pathlib.Path(str(provenance.get("metadata_abi_path", "")))
    repository = pathlib.Path(str(provenance.get("firmware_repository", "")))
    expected_repository = pathlib.Path(__file__).resolve().parents[2]
    if (
        not repository.is_absolute()
        or repository != expected_repository
        or not module_path.is_absolute()
        or not shell_path.is_absolute()
        or not metadata_abi_path.is_absolute()
        or module_path
        != repository / "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
        or shell_path
        != repository / "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
        or metadata_abi_path != module_path.parent / "metadata_abi.py"
    ):
        raise QualificationError("durable runner source paths are not absolute")
    commit = str(provenance.get("firmware_repo_commit", ""))
    if _git_bytes(repository, "cat-file", "-t", commit).decode().strip() != "commit":
        raise QualificationError("durable runner provenance is not a commit object")
    if _git_bytes(repository, "rev-parse", "HEAD").decode().strip() != commit:
        raise QualificationError("durable runner commit is not live HEAD")
    if _git_bytes(repository, "status", "--porcelain", "--untracked-files=no").strip():
        raise QualificationError("durable runner repository has tracked changes")
    for relative, digest_name, observed_name in (
        (
            "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
            "python_module_head_blob_sha256",
            "python_module_sha256",
        ),
        (
            "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
            "shell_runner_head_blob_sha256",
            "shell_runner_sha256",
        ),
        (
            "tests/radio_hardware/metadata_abi.py",
            "metadata_abi_head_blob_sha256",
            "metadata_abi_sha256",
        ),
    ):
        observed = hashlib.sha256(
            _git_bytes(repository, "show", f"{commit}:{relative}")
        ).hexdigest()
        if observed != provenance.get(digest_name):
            raise QualificationError(f"durable runner commit blob changed: {relative}")
        if _sha256_file(repository / relative) != provenance.get(observed_name):
            raise QualificationError(f"durable runner live file changed: {relative}")

    report_path = _validate_output_preflight(report.get("output_preflight"))

    configuration = _required_mapping(report.get("configuration"), name="configuration")
    exact_configuration = {
        "serial": DEFAULT_R18_SERIAL,
        "firmware_pattern": EXPECTED_FIRMWARE_PATTERN,
        "firmware_version": EXPECTED_FIRMWARE_VERSION,
        "kernel_version": EXPECTED_KERNEL_VERSION,
        "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
        "normalization_policy": (
            "under verified mute with zero buffers: common LO, all PHY rates and "
            "bandwidths, then RX manual 40"
        ),
        "iq_evidence_policy": IQ_EVIDENCE_POLICY,
        "center_frequency_hz": CENTER_FREQUENCY_HZ,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": RF_BANDWIDTH_HZ,
        "expected_gain_table_id": int(EXPECTED_GAIN_TABLE),
        "expected_gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
        "tandem_mode": "hold",
        "hold_gain_db": HOLD_GAIN_DB,
        "frame_samples_per_channel": FRAME_SAMPLES,
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "metadata_capacity_bytes": METADATA_CAPACITY,
        "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
    }
    for field, expected in exact_configuration.items():
        if not _json_identical(configuration.get(field), expected):
            raise QualificationError(f"durable configuration {field} changed")
    if set(configuration) != set(exact_configuration):
        raise QualificationError("durable configuration fields changed")
    serial = DEFAULT_R18_SERIAL
    firmware_pattern = EXPECTED_FIRMWARE_PATTERN

    preflight = _required_mapping(report.get("preflight"), name="preflight")
    if set(preflight) != {
        "verdict",
        "serial",
        "uri",
        "firmware_version",
        "context_attrs",
        "mute",
        "rx_state",
        "rf_state",
        "tandem_status",
        "started_monotonic_ns",
        "completed_monotonic_ns",
        "configuration_write_count",
        "metadata_buffer_open_count",
    }:
        raise QualificationError("durable preflight fields changed")
    if (
        preflight.get("verdict") != "GO"
        or preflight.get("serial") != serial
        or not str(preflight.get("uri", "")).startswith("usb:")
        or preflight.get("firmware_version") != EXPECTED_FIRMWARE_VERSION
        or re.fullmatch(firmware_pattern, str(preflight.get("firmware_version", "")))
        is None
        or _required_int(
            preflight.get("configuration_write_count"),
            name="preflight configuration write count",
        )
        != 0
        or _required_int(
            preflight.get("metadata_buffer_open_count"),
            name="preflight metadata buffer count",
        )
        != 0
    ):
        raise QualificationError("durable read-only preflight is not exact GO")
    context_attrs = _required_mapping(
        preflight.get("context_attrs"), name="preflight context attrs"
    )
    if (
        any(
            type(name) is not str or type(attribute) is not str
            for name, attribute in context_attrs.items()
        )
        or context_attrs.get("hw_serial") != serial
        or context_attrs.get("fw_version") != preflight.get("firmware_version")
        or context_attrs.get("iio,buffer-metadata") != "2"
        or context_attrs.get("local,kernel") != EXPECTED_KERNEL_VERSION
        or context_attrs.get("hw_model") != EXPECTED_HARDWARE_MODEL
        or context_attrs.get("ad9361-phy,model") != "ad9361"
        or context_attrs.get("uri", preflight.get("uri")) != preflight.get("uri")
    ):
        raise QualificationError("durable preflight identity/capability changed")
    _validate_mute_record(preflight.get("mute"), name="preflight mute")
    _validate_boot_rx_record(preflight.get("rx_state"), name="preflight RX")
    _validate_rf_state(preflight.get("rf_state"), name="preflight RF", normalized=False)
    _require_idle(
        _required_mapping(preflight.get("tandem_status"), name="preflight tandem"),
        label="durable preflight tandem",
    )
    preflight_started = _required_int(
        preflight.get("started_monotonic_ns"),
        name="preflight start",
        minimum=1,
        maximum=MAXIMUM_SIGNED_64,
    )
    preflight_completed = _required_int(
        preflight.get("completed_monotonic_ns"),
        name="preflight completion",
        minimum=preflight_started,
        maximum=MAXIMUM_SIGNED_64,
    )
    _validate_normalization(report.get("normalization"))
    normalization = _required_mapping(report.get("normalization"), name="normalization")
    if normalization["started_monotonic_ns"] < preflight_completed:
        raise QualificationError("durable normalization predates safe preflight")
    scan = _required_mapping(report.get("rx_scan"), name="RX scan")
    if set(scan) != {
        "enabled_channel_ids",
        "enabled_scan_mask",
        "sample_size_bytes",
        "layout",
    }:
        raise QualificationError("durable RX scan evidence fields changed")
    enabled_channel_ids = _required_list(
        scan.get("enabled_channel_ids"), name="RX enabled channel IDs"
    )
    if (
        any(type(channel_id) is not str for channel_id in enabled_channel_ids)
        or enabled_channel_ids != list(RX_SCAN_IDS)
        or _required_int(scan.get("enabled_scan_mask"), name="RX enabled scan mask")
        != RX_SCAN_MASK
        or _required_int(scan.get("sample_size_bytes"), name="RX sample size")
        != RX_SCAN_SAMPLE_BYTES
    ):
        raise QualificationError("durable RX scan selection/mask/size changed")
    layout = _required_list(scan.get("layout"), name="RX scan layout")
    if len(layout) != len(RX_SCAN_IDS):
        raise QualificationError("durable RX scan layout is not four scalar lanes")
    for expected_index, (channel_id, channel_value) in enumerate(
        zip(RX_SCAN_IDS, layout, strict=True)
    ):
        channel = _required_mapping(channel_value, name=f"RX scan layout {channel_id}")
        if set(channel) != {"id", "index", "format"}:
            raise QualificationError(
                f"durable RX scan lane {channel_id} fields changed"
            )
        if type(channel.get("id")) is not str or channel.get("id") != channel_id:
            raise QualificationError(f"durable RX scan lane {channel_id} ID changed")
        if (
            _required_int(channel.get("index"), name=f"RX scan lane {channel_id} index")
            != expected_index
        ):
            raise QualificationError(
                f"durable RX scan lane {channel_id} index/format changed"
            )
        scan_format = _required_mapping(
            channel.get("format"), name=f"RX scan lane {channel_id} format"
        )
        if set(scan_format) != set(RX_SCAN_FORMAT):
            raise QualificationError(
                f"durable RX scan lane {channel_id} format fields changed"
            )
        for field in ("length", "bits", "shift", "repeat"):
            if (
                _required_int(
                    scan_format.get(field),
                    name=f"RX scan lane {channel_id} format {field}",
                )
                != RX_SCAN_FORMAT[field]
            ):
                raise QualificationError(
                    f"durable RX scan lane {channel_id} format {field} changed"
                )
        for field in ("is_signed", "is_be"):
            value = scan_format.get(field)
            if type(value) is not bool or value is not RX_SCAN_FORMAT[field]:
                raise QualificationError(
                    f"durable RX scan lane {channel_id} format {field} changed"
                )

    full = _required_mapping(report.get("full_drain"), name="full drain")
    if (
        not _json_identical(full.get("kernel_buffers"), KERNEL_BUFFERS)
        or not _json_identical(full.get("batch_frames"), BATCH_FRAMES)
        or not _json_identical(full.get("metadata_capacity_bytes"), METADATA_CAPACITY)
        or not _json_identical(
            full.get("batch_cache_bound_bytes"), EXPECTED_BATCH_CACHE_BYTES
        )
        or not _json_identical(
            full.get("expected_batch_cache_bytes"), EXPECTED_BATCH_CACHE_BYTES
        )
        or full.get("close_method") != "explicit_normal_close"
        or not _json_identical(
            full.get("normalization_completed_monotonic_ns"),
            normalization["completed_monotonic_ns"],
        )
    ):
        raise QualificationError("durable full-drain configuration changed")
    first_open_ns = _required_int(
        full.get("first_buffer_open_requested_monotonic_ns"),
        name="first metadata buffer open request",
        minimum=normalization["completed_monotonic_ns"],
        maximum=MAXIMUM_SIGNED_64,
    )
    if first_open_ns < normalization["completed_monotonic_ns"]:
        raise QualificationError("durable first buffer open predates normalization")
    status_open = _require_hold(
        _required_mapping(full.get("status_after_open"), name="full open status"),
        label="durable full open",
    )
    status_before_close = _require_hold(
        _required_mapping(
            full.get("status_before_close"), name="full before-close status"
        ),
        label="durable full before close",
    )
    if status_open != status_before_close:
        raise QualificationError("durable full-drain status changed while open")
    frames = _required_list(full.get("frames"), name="full frames")
    if len(frames) != BATCH_FRAMES:
        raise QualificationError("durable full drain is not exactly 64 frames")
    first_sample = None
    stream_id = None
    threshold = None
    endpoint = None
    for ordinal, frame in enumerate(frames):
        expected_sample = (
            None if first_sample is None else first_sample + ordinal * FRAME_SAMPLES
        )
        current_stream, current_epoch, current_sample, current_endpoint = (
            _validate_frame_json(
                frame,
                name=f"full frame {ordinal}",
                ordinal=ordinal,
                status=status_open,
                expected_stream_id=stream_id,
                expected_first_sample=expected_sample,
            )
        )
        if first_sample is None:
            first_sample = current_sample
            stream_id = current_stream
            endpoint = current_endpoint
            threshold = frame["threshold_provenance"]
        elif (
            current_epoch != status_open["ownership_epoch"]
            or current_endpoint != endpoint
        ):
            raise QualificationError("durable full frame epoch/endpoint changed")
        if frame["threshold_provenance"] != threshold:
            raise QualificationError("durable full frame threshold provenance changed")
    assert first_sample is not None and stream_id is not None
    expected_continuity = {
        "verified": True,
        "frame_count": BATCH_FRAMES,
        "stream_id": stream_id,
        "ownership_epoch": status_open["ownership_epoch"],
        "buffer_sequence_range": [0, BATCH_FRAMES - 1],
        "sample_sequence_range": [
            first_sample,
            first_sample + BATCH_FRAMES * FRAME_SAMPLES,
        ],
        "sample_gaps": 0,
        "gain_events": 0,
        "faults": 0,
        "overflows": 0,
    }
    if not _json_identical(full.get("continuity"), expected_continuity):
        raise QualificationError("durable continuity summary is not frame-derived")
    full_close_status = _require_post_hold_idle(
        _required_mapping(full.get("status_after_close"), name="full close status"),
        label="durable full close",
    )
    full_close_completed_ns = _required_int(
        full.get("close_completed_monotonic_ns"),
        name="full close completion",
        minimum=first_open_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    _validate_post_full_drain_barrier(
        report.get("post_full_drain_barrier"),
        full_close_completed_ns=full_close_completed_ns,
        full_close_status=full_close_status,
    )
    post_full_barrier = _required_mapping(
        report.get("post_full_drain_barrier"), name="post-full barrier"
    )
    post_full_completed_ns = _required_int(
        post_full_barrier.get("completed_monotonic_ns"),
        name="post-full barrier completion",
        minimum=full_close_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )

    cancel = _required_mapping(report.get("cancel_lifecycle"), name="cancel lifecycle")
    if set(cancel) != {
        "verified",
        "kernel_buffers",
        "batch_frames",
        "old_buffer_open_requested_monotonic_ns",
        "operation_order",
        "status_after_old_open",
        "first_returned_cached_frame",
        "second_open_error",
        "poison_refill_error",
        "old_buffer_close_completed_monotonic_ns",
        "mute_after_old_close_started_monotonic_ns",
        "mute_after_old_close",
        "mute_after_old_close_completed_monotonic_ns",
        "old_close_idle_verified_monotonic_ns",
        "status_after_old_close",
        "fresh_buffer_open_requested_monotonic_ns",
        "status_after_fresh_open",
        "status_after_fresh_close",
        "fresh_buffer_close_completed_monotonic_ns",
    }:
        raise QualificationError("durable cancel lifecycle fields changed")
    if (
        cancel.get("verified") is not True
        or not _json_identical(cancel.get("kernel_buffers"), KERNEL_BUFFERS)
        or not _json_identical(cancel.get("batch_frames"), BATCH_FRAMES)
        or cancel.get("operation_order")
        != [
            "first_cached_frame_returned",
            "old_buffer_cancel",
            "second_open_ebusy",
            "old_refill_ebadf",
            "old_buffer_close",
            "mute_after_old_close",
            "verify_old_close_idle",
            "fresh_buffer_open",
            "fresh_buffer_close",
        ]
    ):
        raise QualificationError("durable cancel lifecycle order/config changed")
    old_open_requested_ns = _required_int(
        cancel.get("old_buffer_open_requested_monotonic_ns"),
        name="cancel old buffer open request",
        minimum=post_full_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    old_status = _require_hold(
        _required_mapping(
            cancel.get("status_after_old_open"), name="cancel old open status"
        ),
        label="durable cancel old open",
    )
    cancel_stream_id, _cancel_epoch, cancel_first_sample, _cancel_endpoint = (
        _validate_frame_json(
            cancel.get("first_returned_cached_frame"),
            name="cancel first cached frame",
            ordinal=0,
            status=old_status,
            expected_stream_id=None,
            expected_first_sample=None,
        )
    )
    full_sample_end = first_sample + BATCH_FRAMES * FRAME_SAMPLES
    if cancel_stream_id == stream_id or cancel_first_sample < full_sample_end:
        raise QualificationError(
            "durable cancel session does not follow the completed full-drain stream"
        )
    _validate_errno_record(
        cancel.get("second_open_error"), errno.EBUSY, name="second open"
    )
    _validate_errno_record(
        cancel.get("poison_refill_error"), errno.EBADF, name="poison refill"
    )
    old_close_completed_ns = _required_int(
        cancel.get("old_buffer_close_completed_monotonic_ns"),
        name="cancel old buffer close completion",
        minimum=old_open_requested_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    mute_started_ns = _required_int(
        cancel.get("mute_after_old_close_started_monotonic_ns"),
        name="cancel post-close mute start",
        minimum=old_close_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    mute_completed_ns = _required_int(
        cancel.get("mute_after_old_close_completed_monotonic_ns"),
        name="cancel post-close mute completion",
        minimum=mute_started_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    _validate_mute_record(
        cancel.get("mute_after_old_close"),
        name="cancel post-close mute",
        require_forced_mute=True,
    )
    old_close_idle_ns = _required_int(
        cancel.get("old_close_idle_verified_monotonic_ns"),
        name="cancel old close idle verification",
        minimum=mute_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    _require_post_hold_idle(
        _required_mapping(
            cancel.get("status_after_old_close"), name="cancel old close status"
        ),
        label="durable cancel old close",
    )
    fresh_open_requested_ns = _required_int(
        cancel.get("fresh_buffer_open_requested_monotonic_ns"),
        name="cancel fresh buffer open request",
        minimum=old_close_idle_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    fresh_status = _require_hold(
        _required_mapping(
            cancel.get("status_after_fresh_open"), name="fresh open status"
        ),
        label="durable fresh open",
    )
    expected_old_epoch = (status_open["ownership_epoch"] + 1) & 0xFFFFFFFF
    if expected_old_epoch == 0:
        expected_old_epoch = 1
    expected_fresh_epoch = (expected_old_epoch + 1) & 0xFFFFFFFF
    if expected_fresh_epoch == 0:
        expected_fresh_epoch = 1
    if (
        old_status["ownership_epoch"] != expected_old_epoch
        or fresh_status["ownership_epoch"] != expected_fresh_epoch
    ):
        raise QualificationError("durable session epochs are not exact successors")
    fresh_close = _require_post_hold_idle(
        _required_mapping(
            cancel.get("status_after_fresh_close"), name="fresh close status"
        ),
        label="durable fresh close",
    )
    fresh_close_completed_ns = _required_int(
        cancel.get("fresh_buffer_close_completed_monotonic_ns"),
        name="cancel fresh buffer close completion",
        minimum=fresh_open_requested_ns,
        maximum=MAXIMUM_SIGNED_64,
    )

    final_status = _require_post_hold_idle(
        _required_mapping(report.get("final_tandem_status"), name="final status"),
        label="durable final status",
    )
    if final_status != fresh_close:
        raise QualificationError("durable final status changed after recovery close")
    _validate_rx_record(report.get("final_rx_state"), name="final RX")
    _validate_rf_state(report.get("final_rf_state"), name="final RF", normalized=True)
    cleanup = _required_mapping(report.get("cleanup"), name="cleanup")
    _validate_mute_record(
        cleanup,
        name="cleanup mute",
        allowed_extra_fields=(
            "tandem_status",
            "rx_state",
            "rf_state",
            "errors",
            "started_monotonic_ns",
            "mute_completed_monotonic_ns",
            "idle_verified_monotonic_ns",
            "rx_completed_monotonic_ns",
            "final_idle_verified_monotonic_ns",
            "rf_readback_completed_monotonic_ns",
            "operation_order",
        ),
        require_forced_mute=True,
    )
    if cleanup.get("errors") != []:
        raise QualificationError("durable cleanup contains errors")
    if not _json_identical(cleanup.get("tandem_status"), final_status):
        raise QualificationError("durable cleanup tandem status is not final")
    if not _json_identical(cleanup.get("rx_state"), report.get("final_rx_state")):
        raise QualificationError("durable cleanup RX state is not final")
    if not _json_identical(cleanup.get("rf_state"), report.get("final_rf_state")):
        raise QualificationError("durable cleanup RF state is not final")
    if not _json_identical(
        cleanup.get("operation_order"),
        [
            "force_mute",
            "verify_idle",
            "configure_manual40",
            "verify_final_idle",
            "read_final_rf",
        ],
    ):
        raise QualificationError("durable cleanup operation order changed")
    cleanup_started_ns = _required_int(
        cleanup.get("started_monotonic_ns"),
        name="cleanup start",
        minimum=fresh_close_completed_ns,
        maximum=MAXIMUM_SIGNED_64,
    )
    previous_cleanup_ns = cleanup_started_ns
    for field, label in (
        ("mute_completed_monotonic_ns", "cleanup mute completion"),
        ("idle_verified_monotonic_ns", "cleanup idle verification"),
        ("rx_completed_monotonic_ns", "cleanup RX completion"),
        ("final_idle_verified_monotonic_ns", "cleanup final idle verification"),
        ("rf_readback_completed_monotonic_ns", "cleanup RF readback completion"),
    ):
        previous_cleanup_ns = _required_int(
            cleanup.get(field),
            name=label,
            minimum=previous_cleanup_ns,
            maximum=MAXIMUM_SIGNED_64,
        )
    _validate_metadata_artifacts(report, report_path=report_path)


def _reread_exact_report(
    path: pathlib.Path, expected: Mapping[str, Any]
) -> dict[str, Any]:
    expected_payload = _json_payload(expected)
    observed_payload = _read_exact_owned_regular_file(
        path,
        expected_bytes=len(expected_payload),
        name="atomic durable report",
    )
    if observed_payload != expected_payload:
        raise QualificationError("atomic report bytes differ from in-memory evidence")
    try:
        parsed = json.loads(observed_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationError("atomic report JSON is invalid") from error
    if parsed.get("verdict") == "PASS":
        validate_durable_pass_report(parsed)
    return parsed


def _close_resources_and_persist(
    report: dict[str, Any],
    *,
    output_path: pathlib.Path,
    context: Any,
    lock: Any,
    lock_acquired: bool,
    cleanup_errors: list[dict[str, Any]],
    primary_error: BaseException | None,
) -> tuple[dict[str, Any], BaseException | None]:
    """Close the context, persist while locked, then unlock unconditionally."""

    if context is not None:
        try:
            close_iio_object(context)
        except BaseException as error:
            cleanup_errors.append(_error_record(error))
        finally:
            context = None
            gc.collect()
    cleanup_record = report.setdefault("cleanup", {})
    cleanup_record["rx_state"] = report.get("final_rx_state")
    cleanup_record["rf_state"] = report.get("final_rf_state")
    cleanup_record["tandem_status"] = report.get("final_tandem_status")
    cleanup_record["errors"] = cleanup_errors
    cleanup_record["verified"] = bool(
        cleanup_record.get("verified") and not cleanup_errors
    )
    report["completed_unix_ns"] = time.time_ns()
    if cleanup_errors:
        report["verdict"] = "FAIL"
        cleanup_failure = QualificationError(
            f"durable cleanup failed: {cleanup_errors}"
        )
        if primary_error is None:
            primary_error = cleanup_failure
            report["error"] = _error_record(cleanup_failure)
    if report.get("verdict") == "PASS":
        try:
            validate_durable_pass_report(report)
        except BaseException as error:
            report["verdict"] = "FAIL"
            report["error"] = _error_record(error)
            if primary_error is None:
                primary_error = error

    durable_report = report
    persistence_error: BaseException | None = None
    owned_report_identity: tuple[int, int] | None = None
    lock_error_count_before = len(cleanup_errors)
    try:
        try:
            owned_report_identity = _atomic_json(output_path, report)
            durable_report = _reread_exact_report(output_path, report)
        except BaseException as error:
            if isinstance(error, _AtomicPromotionError):
                owned_report_identity = error.target_identity
            persistence_error = error
            report["verdict"] = "FAIL"
            report["error"] = _error_record(error)
            if primary_error is None:
                primary_error = error
            if _path_matches_owned_identity(output_path, owned_report_identity):
                try:
                    owned_report_identity = _atomic_json(
                        output_path,
                        report,
                        replace_existing=True,
                        expected_existing_identity=owned_report_identity,
                    )
                    durable_report = _reread_exact_report(output_path, report)
                    persistence_error = None
                except BaseException as demotion_error:
                    persistence_error = demotion_error
    finally:
        if lock is not None:
            if lock_acquired:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                except BaseException as error:
                    cleanup_errors.append(_error_record(error))
            try:
                lock.close()
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
    if len(cleanup_errors) != lock_error_count_before:
        cleanup_record["errors"] = cleanup_errors
        cleanup_record["verified"] = False
        report["verdict"] = "FAIL"
        cleanup_failure = QualificationError(
            f"durable lock cleanup failed: {cleanup_errors}"
        )
        report["error"] = _error_record(cleanup_failure)
        if primary_error is None:
            primary_error = cleanup_failure
        if _path_matches_owned_identity(output_path, owned_report_identity):
            try:
                owned_report_identity = _atomic_json(
                    output_path,
                    report,
                    replace_existing=True,
                    expected_existing_identity=owned_report_identity,
                )
                durable_report = _reread_exact_report(output_path, report)
                persistence_error = None
            except BaseException as error:
                persistence_error = error
    if persistence_error is not None and primary_error is None:
        primary_error = persistence_error
    return durable_report, primary_error


def _close_without_persisting_unowned_output(
    *,
    context: Any,
    lock: Any,
    lock_acquired: bool,
    cleanup_errors: list[dict[str, Any]],
) -> None:
    """Release resources after a pre-ownership failure without touching evidence."""

    if context is not None:
        try:
            close_iio_object(context)
        except BaseException as error:
            cleanup_errors.append(_error_record(error))
    if lock is not None:
        if lock_acquired:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
        try:
            lock.close()
        except BaseException as error:
            cleanup_errors.append(_error_record(error))
    gc.collect()


def _cleanup_live_state(
    report: dict[str, Any],
    *,
    phy: Any,
    tx: Any,
    tandem: Any,
    identity_verified: bool,
    safe_preflight_completed: bool,
    cleanup_errors: list[dict[str, Any]],
) -> None:
    if not identity_verified:
        # Unknown identity is closed read-only. Exact identity is the minimum
        # authority for a best-effort mute write.
        report.setdefault("cleanup", {"verified": False})[
            "preflight_failed_without_writes"
        ] = True
        return
    cleanup_mute_verified = False
    cleanup_idle_verified = False
    cleanup_started_ns = time.monotonic_ns()
    operation_order: list[str] = []
    try:
        report["cleanup"] = _force_mute(phy, tx)
        report["cleanup"].update(
            {
                "started_monotonic_ns": cleanup_started_ns,
                "mute_completed_monotonic_ns": time.monotonic_ns(),
                "operation_order": operation_order,
            }
        )
        operation_order.append("force_mute")
        cleanup_mute_verified = True
    except BaseException as error:
        cleanup_errors.append(_error_record(error))
    try:
        cleanup_idle = _wait_idle(tandem, label="durable cleanup before RX")
        report["final_tandem_status"] = (
            _require_post_hold_idle(
                cleanup_idle, label="durable cleanup before RX endpoint"
            )
            if "full_drain" in report
            else cleanup_idle
        )
        report["cleanup"]["idle_verified_monotonic_ns"] = time.monotonic_ns()
        operation_order.append("verify_idle")
        cleanup_idle_verified = True
    except BaseException as error:
        cleanup_errors.append(_error_record(error))
    if safe_preflight_completed and cleanup_mute_verified and cleanup_idle_verified:
        try:
            report["final_rx_state"] = _configure_manual_40(phy)
            report["cleanup"]["rx_completed_monotonic_ns"] = time.monotonic_ns()
            operation_order.append("configure_manual40")
        except BaseException as error:
            cleanup_errors.append(_error_record(error))
    try:
        cleanup_final = _wait_idle(tandem, label="durable cleanup final")
        report["final_tandem_status"] = (
            _require_post_hold_idle(
                cleanup_final, label="durable cleanup final endpoint"
            )
            if "full_drain" in report
            else cleanup_final
        )
        report["cleanup"]["final_idle_verified_monotonic_ns"] = time.monotonic_ns()
        operation_order.append("verify_final_idle")
    except BaseException as error:
        cleanup_errors.append(_error_record(error))
    try:
        report["final_rf_state"] = _read_rf_state(phy)
        report["cleanup"]["rf_readback_completed_monotonic_ns"] = time.monotonic_ns()
        operation_order.append("read_final_rf")
    except BaseException as error:
        cleanup_errors.append(_error_record(error))


def run_hardware(
    iio_module: Any,
    *,
    serial: str,
    firmware_pattern: str,
    output_path: pathlib.Path,
) -> dict[str, Any]:
    output_path = output_path.absolute()
    output_preflight = _prepare_fresh_output_path(output_path)
    if serial != DEFAULT_R18_SERIAL or firmware_pattern != EXPECTED_FIRMWARE_PATTERN:
        raise QualificationError("lifecycle runner is frozen to exact R18/RC3")
    expected_commit = os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", "")
    if expected_commit != EXACT_LIBIIO_COMMIT:
        raise QualificationError(
            f"host libiio attestation {expected_commit!r} is not exact "
            f"{EXACT_LIBIIO_COMMIT}"
        )
    runner_library_sha = os.environ.get("PLUTOSDR_FW_LIBIIO_SHA256", "")
    if re.fullmatch(r"[0-9a-f]{64}", runner_library_sha) is None:
        raise QualificationError("runner did not attest the mapped libiio SHA-256")
    host_libiio = _attest_host_libiio(iio_module)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "running",
        "release_claim": "none; muted host-transport lifecycle qualification only",
        "release_pass_eligible": False,
        "hardware_qualified": False,
        "started_unix_ns": time.time_ns(),
        "host_libiio": host_libiio,
        "runner_provenance": _attest_runner_provenance(),
        "output_preflight": output_preflight,
        "configuration": {
            "serial": serial,
            "firmware_pattern": firmware_pattern,
            "firmware_version": EXPECTED_FIRMWARE_VERSION,
            "kernel_version": EXPECTED_KERNEL_VERSION,
            "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
            "normalization_policy": (
                "under verified mute with zero buffers: common LO, all PHY rates "
                "and bandwidths, then RX manual 40"
            ),
            "iq_evidence_policy": IQ_EVIDENCE_POLICY,
            "center_frequency_hz": CENTER_FREQUENCY_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "rf_bandwidth_hz": RF_BANDWIDTH_HZ,
            "expected_gain_table_id": int(EXPECTED_GAIN_TABLE),
            "expected_gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
            "tandem_mode": "hold",
            "hold_gain_db": HOLD_GAIN_DB,
            "frame_samples_per_channel": FRAME_SAMPLES,
            "kernel_buffers": KERNEL_BUFFERS,
            "batch_frames": BATCH_FRAMES,
            "metadata_capacity_bytes": METADATA_CAPACITY,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        },
        "cleanup": {"verified": False},
    }
    lock: Any = None
    lock_acquired = False
    context: Any = None
    primary_error: BaseException | None = None
    cleanup_errors: list[dict[str, Any]] = []
    identity_verified = False
    safe_preflight_completed = False
    evidence_path_claimed = False
    raw_metadata: list[tuple[str, int, bytes]] = []
    try:
        lock = _open_lock(serial)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_acquired = True
        except BlockingIOError as error:
            lock.seek(0)
            raise QualificationError(
                f"R18 process lock is held: {lock.read().strip()}"
            ) from error
        locked_output_preflight = _prepare_fresh_output_path(output_path)
        if not _json_identical(locked_output_preflight, output_preflight):
            raise QualificationError("fresh output identity changed after R18 lock")
        evidence_path_claimed = True
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()} suite=muted-metadata-batch-lifecycle\n")
        lock.flush()
        uri = _resolve_uri(iio_module, serial)
        context = iio_module.Context(uri)
        context.set_timeout(10_000)
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        tx = context.find_device("cf-ad9361-dds-core-lpc")
        tandem = context.find_device("tandem-agc")
        if any(value is None for value in (phy, rx, tx, tandem)):
            raise QualificationError("required PHY/RX/TX/tandem device is absent")
        identity = _attest_identity(
            context,
            serial=serial,
            uri=uri,
            firmware_pattern=firmware_pattern,
        )
        identity_verified = True
        report["preflight"] = _preflight(
            context,
            phy,
            tx,
            tandem,
            serial=serial,
            uri=uri,
            firmware_pattern=firmware_pattern,
            identity=identity,
        )
        safe_preflight_completed = True
        report["normalization"] = _normalize_before_hold(
            phy, tx, tandem, preflight=report["preflight"]
        )
        report["rx_scan"] = _configure_dual_complex_rx_scan(rx)
        report["full_drain"] = _full_drain(
            iio_module,
            rx,
            tandem,
            raw_metadata_sink=raw_metadata,
            normalization_completed_ns=report["normalization"][
                "completed_monotonic_ns"
            ],
        )
        report["post_full_drain_barrier"] = _post_full_drain_barrier(phy, tx, tandem)
        report["cancel_lifecycle"] = _cancel_lifecycle(
            iio_module, rx, phy, tx, tandem, raw_metadata_sink=raw_metadata
        )
        final_freshness = _prepare_fresh_output_path(output_path)
        if not _json_identical(final_freshness, output_preflight):
            raise QualificationError("fresh output identity changed before persistence")
        metadata_manifest = _new_metadata_artifact_manifest(raw_metadata)
        report["metadata_artifacts"] = metadata_manifest
        _write_metadata_artifacts(output_path, raw_metadata, metadata_manifest)
        report["verdict"] = "PASS"
    except BaseException as error:
        primary_error = error
        report["verdict"] = "FAIL"
        report["error"] = _error_record(error)
    finally:
        if context is not None:
            try:
                phy = context.find_device("ad9361-phy")
                tx = context.find_device("cf-ad9361-dds-core-lpc")
                tandem = context.find_device("tandem-agc")
                _cleanup_live_state(
                    report,
                    phy=phy,
                    tx=tx,
                    tandem=tandem,
                    identity_verified=identity_verified,
                    safe_preflight_completed=safe_preflight_completed,
                    cleanup_errors=cleanup_errors,
                )
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
        if evidence_path_claimed:
            durable_report, primary_error = _close_resources_and_persist(
                report,
                output_path=output_path,
                context=context,
                lock=lock,
                lock_acquired=lock_acquired,
                cleanup_errors=cleanup_errors,
                primary_error=primary_error,
            )
        else:
            _close_without_persisting_unowned_output(
                context=context,
                lock=lock,
                lock_acquired=lock_acquired,
                cleanup_errors=cleanup_errors,
            )
            durable_report = report
        context = None
        lock = None
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)
    validate_durable_pass_report(durable_report)
    return durable_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--serial", default=DEFAULT_R18_SERIAL)
    parser.add_argument("--firmware-pattern", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.hardware:
        raise SystemExit("refusing hardware access without explicit --hardware")
    import iio

    try:
        report = run_hardware(
            iio,
            serial=args.serial,
            firmware_pattern=args.firmware_pattern,
            output_path=args.output.absolute(),
        )
    except BaseException as error:
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    artifact = args.output.absolute()
    digest = _sha256_file(artifact)
    print(f"PASS: {artifact}")
    print(f"SHA256: {digest}")
    print(
        "full drain: "
        f"{report['full_drain']['continuity']['frame_count']} exact frames; "
        "cancel/EBUSY/EBADF/reopen lifecycle verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
