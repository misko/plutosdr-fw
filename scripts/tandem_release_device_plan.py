#!/usr/bin/env python3
"""Build and verify the pluto-plus-utils RAM-only release-candidate plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tandem_release_evidence import (
    EvidenceError,
    verify_artifact_index_semantics,
)
from tests.radio_hardware.candidate_binding import (
    CandidateBindingError,
    validate_artifact_index,
)
from tests.radio_hardware.pluto_plus_candidate import (
    CANDIDATE_PLAN_SCHEMA,
    PLUTO_IIO_BUFFER_METADATA_ABI,
    PLUTO_PLUS_UTILS_REPOSITORY,
    PLUTO_PLUS_UTILS_SOURCE_COMMIT,
    PLUTO_PLUS_UTILS_VERSION,
    validate_release_candidate_plan,
)

MAX_JSON_BYTES = 4 * 1024 * 1024


class DevicePlanError(RuntimeError):
    """The retained artifact cannot produce an exact utility candidate plan."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
    except OSError as error:
        raise DevicePlanError(f"{label} cannot be opened safely: {error}") from error
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or opened.st_size <= 0
            or opened.st_size > maximum
            or identity
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            raise DevicePlanError(f"{label} is not one stable owned regular file")
        payload = bytearray()
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            if not chunk:
                raise DevicePlanError(f"{label} was truncated during read")
            payload.extend(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise DevicePlanError(f"{label} grew during read")
        after = os.fstat(descriptor)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise DevicePlanError(f"{label} changed during read")
    finally:
        os.close(descriptor)
    return bytes(payload)


def _decode_json(payload: bytes, *, label: str) -> object:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise DevicePlanError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    def no_nonfinite(value: str) -> None:
        raise DevicePlanError(f"{label} contains non-finite number {value}")

    try:
        return json.loads(
            payload.decode(),
            object_pairs_hook=no_duplicates,
            parse_constant=no_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevicePlanError(f"{label} is not UTF-8 JSON") from error


def _created_at(value: str | None) -> str:
    if value is None:
        selected = datetime.now(UTC).replace(microsecond=0)
    else:
        if not value.endswith("Z"):
            raise DevicePlanError(
                "--created-at must be an ISO-8601 UTC timestamp ending in Z"
            )
        try:
            selected = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise DevicePlanError(
                "--created-at is not an ISO-8601 timestamp"
            ) from error
        if selected.utcoffset() != UTC.utcoffset(selected):
            raise DevicePlanError("--created-at must be UTC")
    return selected.isoformat(timespec="seconds").replace("+00:00", "Z")


def build_plan(index_path: Path, *, created_at: str | None = None) -> dict[str, Any]:
    """Build one canonical utility plan from an exact candidate artifact index."""

    selected_index = index_path.absolute()
    index_payload = _read_regular(
        selected_index, maximum=MAX_JSON_BYTES, label="candidate artifact index"
    )
    index_sha256 = hashlib.sha256(index_payload).hexdigest()
    try:
        index = validate_artifact_index(
            _decode_json(index_payload, label="candidate artifact index")
        )
    except CandidateBindingError as error:
        raise DevicePlanError(
            f"candidate artifact index is invalid: {error}"
        ) from error
    if index["stage"] not in {"candidate-pre-hardware", "final-pre-confirmation"}:
        raise DevicePlanError(
            "device candidate plan requires a hardware-authorizing artifact index"
        )
    try:
        semantic_index = verify_artifact_index_semantics(
            selected_index, expected_stage=index["stage"]
        )
    except (EvidenceError, OSError) as error:
        raise DevicePlanError(
            f"candidate artifact index is not semantically authorizing: {error}"
        ) from error
    if semantic_index != index:
        raise DevicePlanError(
            "semantic release verifier returned a different artifact index"
        )
    root = selected_index.parent
    dfu_path = root / index["artifact"]["dfu_path"]
    dfu_payload = _read_regular(
        dfu_path,
        maximum=index["artifact"]["dfu_bytes"],
        label="candidate DFU",
    )
    if (
        len(dfu_payload) != index["artifact"]["dfu_bytes"]
        or hashlib.sha256(dfu_payload).hexdigest() != index["artifact"]["dfu_sha256"]
        or len(dfu_payload) != index["artifact"]["fit_bytes"] + 16
        or hashlib.sha256(dfu_payload[: index["artifact"]["fit_bytes"]]).hexdigest()
        != index["artifact"]["fit_sha256"]
    ):
        raise DevicePlanError("candidate DFU/FIT bytes differ from the artifact index")
    identifier = hashlib.sha256(
        b"pluto-plus-utils.release-candidate-plan.v1\0"
        + index_sha256.encode()
        + PLUTO_PLUS_UTILS_SOURCE_COMMIT.encode()
    ).hexdigest()[:32]
    plan: dict[str, Any] = {
        "schema": CANDIDATE_PLAN_SCHEMA,
        "schema_version": 1,
        "candidate_id": identifier,
        "created_at": _created_at(created_at),
        "source_repository": "misko/plutosdr-fw",
        "source_commit": index["source"]["commit"],
        "device_tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
        "device_tool_version": PLUTO_PLUS_UTILS_VERSION,
        "device_tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
        "artifact_index": {
            "path": str(selected_index),
            "bytes": len(index_payload),
            "sha256": index_sha256,
        },
        "dfu": {
            "path": str(dfu_path),
            "bytes": len(dfu_payload),
            "sha256": hashlib.sha256(dfu_payload).hexdigest(),
        },
        "fit": {
            "bytes": index["artifact"]["fit_bytes"],
            "sha256": index["artifact"]["fit_sha256"],
        },
        "expected_runtime": {
            "firmware_version": index["release"]["firmware_version"],
            "hardware_model": index["release"]["hardware_model"],
            # The release index names the v5 durable frame/report schema.  The
            # live IIO context independently selects authoritative buffer ABI 4;
            # they are intentionally different contracts.
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
    try:
        return validate_release_candidate_plan(
            plan,
            artifact_index=index,
            artifact_index_bytes=len(index_payload),
            artifact_index_sha256=index_sha256,
        )
    except CandidateBindingError as error:
        raise DevicePlanError(
            f"generated candidate plan is invalid: {error}"
        ) from error


def _write_absent_private(path: Path, payload: bytes) -> None:
    selected = path.absolute()
    parent = selected.parent
    state = parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != 0o700
    ):
        raise DevicePlanError(
            "candidate-plan parent must be an owned mode-0700 directory"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(selected, flags, 0o600)
    except FileExistsError as error:
        raise DevicePlanError(
            "refusing to replace an existing candidate plan"
        ) from error
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    except BaseException:
        selected.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.artifact_index, created_at=args.created_at)
        payload = _canonical(plan)
        _write_absent_private(args.output, payload)
    except (OSError, ValueError, DevicePlanError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "verdict": "pass",
                "output": str(args.output.absolute()),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "device_tool_repository": PLUTO_PLUS_UTILS_REPOSITORY,
                "device_tool_version": PLUTO_PLUS_UTILS_VERSION,
                "device_tool_source_commit": PLUTO_PLUS_UTILS_SOURCE_COMMIT,
                "hardware_accessed": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
