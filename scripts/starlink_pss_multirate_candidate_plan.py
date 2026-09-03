#!/usr/bin/env python3
"""Prepare one verified Starlink PSS package for PPU's RX-only RAM lifecycle.

This command is deliberately offline.  It reads a retained CI package, verifies
the archive sidecar and every internally indexed member, extracts only the DFU
and source manifest, and emits a canonical candidate-plan.v2.  It never
enumerates USB, opens IIO, invokes DFU, or writes persistent radio storage.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

SUPPORTED_RATES = (15, 30, 60)
ALLOCATED_SERIAL = "104000bac4950008230026001b440a003a"
SOURCE_MANIFEST_REVISIONS = {
    "starlink-pss-multirate-rx-only-dnm-v1-source.yaml": "v1",
    "starlink-pss-multirate-rx-only-dnm-v2-source.yaml": "v2",
}
SOURCE_MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v2-source.yaml"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUALIFICATION_MANIFEST = ROOT / "manifests" / SOURCE_MANIFEST_NAME
PPU_REPOSITORY = "misko/pluto-plus-utils"
PPU_VERSION = "0.1.0"
FIRMWARE_REPOSITORY = "misko/plutosdr-fw"
HARDWARE_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9363A)"
METADATA_ABI = "frame-metadata-v3"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_SMALL_MEMBER_BYTES = 4 * 1024 * 1024
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class CandidatePlanError(RuntimeError):
    """The retained package cannot produce an exact RAM-only candidate plan."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash_stream(stream: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1 << 20):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _stable_owned_file(path: Path, *, maximum: int, label: str) -> tuple[int, str]:
    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
    except OSError as error:
        raise CandidatePlanError(f"{label} cannot be opened safely: {error}") from error
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
            raise CandidatePlanError(f"{label} is not one stable owned regular file")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            size, digest = _hash_stream(stream)
        after = os.fstat(descriptor)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise CandidatePlanError(f"{label} changed during read")
    finally:
        os.close(descriptor)
    return size, digest


def _verify_clean_source_repository(
    repository: Path, *, commit: str, expected_slug: str, label: str
) -> Path:
    selected = repository.absolute()

    def git(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ("git", "-C", str(selected), *arguments),
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise CandidatePlanError(
                f"{label} repository cannot be attested"
            ) from error
        return result.stdout.strip()

    root = Path(git("rev-parse", "--show-toplevel")).absolute()
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    remote = git("remote", "get-url", "origin")
    remote_path = remote.removesuffix(".git").replace(":", "/")
    if (
        root != selected
        or head != commit
        or status
        or not remote_path.endswith(f"/{expected_slug}")
    ):
        raise CandidatePlanError(
            f"{label} repository is not the exact clean expected source checkout"
        )
    return selected


def _parse_sums(payload: bytes, *, label: str) -> dict[str, str]:
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise CandidatePlanError(f"{label} is not ASCII") from error
    result: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
        if match is None:
            raise CandidatePlanError(f"{label} contains a malformed checksum row")
        digest, name = match.groups()
        if name in result:
            raise CandidatePlanError(f"{label} contains duplicate member {name!r}")
        result[name] = digest
    if not result:
        raise CandidatePlanError(f"{label} is empty")
    return result


def _parse_key_values(payload: bytes, *, label: str) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise CandidatePlanError(f"{label} is not UTF-8") from error
    result: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith(("#", "[")):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key, value = (item.strip() for item in line.split(separator, 1))
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", key):
            continue
        if key in result:
            raise CandidatePlanError(f"{label} contains duplicate key {key!r}")
        result[key] = value
    return result


def _parse_versions(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise CandidatePlanError("packed VERSIONS is not UTF-8") from error
    result: dict[str, str] = {}
    for line in lines:
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not fields[0] or not fields[1]:
            raise CandidatePlanError("packed VERSIONS contains a malformed row")
        key, value = fields
        if key in result:
            raise CandidatePlanError(f"packed VERSIONS contains duplicate key {key!r}")
        result[key] = value
    return result


def _member_payload(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    if member.size > MAX_MEMBER_BYTES:
        raise CandidatePlanError(f"archive member {member.name!r} is too large")
    stream = archive.extractfile(member)
    if stream is None:
        raise CandidatePlanError(f"archive member {member.name!r} cannot be read")
    payload = stream.read(MAX_MEMBER_BYTES + 1)
    if len(payload) != member.size:
        raise CandidatePlanError(
            f"archive member {member.name!r} changed size while reading"
        )
    return payload


def _verified_members(path: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    try:
        archive = tarfile.open(path, mode="r:gz")  # noqa: SIM115
    except (OSError, tarfile.TarError) as error:
        raise CandidatePlanError(f"candidate archive is invalid: {error}") from error
    with archive:
        infos: dict[str, tarfile.TarInfo] = {}
        for member in archive.getmembers():
            pure = PurePosixPath(member.name)
            if (
                not member.isfile()
                or pure.name != member.name
                or member.name in infos
                or member.size <= 0
                or member.size > MAX_MEMBER_BYTES
            ):
                raise CandidatePlanError(
                    "archive must contain unique, non-empty regular basename members only"
                )
            infos[member.name] = member
        manifest_names = set(infos).intersection(SOURCE_MANIFEST_REVISIONS)
        if len(manifest_names) != 1:
            raise CandidatePlanError(
                "archive must contain exactly one supported multirate source manifest"
            )
        required = {
            "SHA256SUMS",
            "PAYLOAD_SHA256SUMS",
            "packed-VERSIONS.txt",
            next(iter(manifest_names)),
        }
        if not required.issubset(infos):
            missing = sorted(required - infos.keys())
            raise CandidatePlanError(f"archive is missing required members: {missing}")
        small: dict[str, bytes] = {}
        for name in required:
            if infos[name].size > MAX_SMALL_MEMBER_BYTES:
                raise CandidatePlanError(f"small archive member {name!r} is too large")
            small[name] = _member_payload(archive, infos[name])
        checksums = _parse_sums(small["SHA256SUMS"], label="SHA256SUMS")
        expected_names = set(infos) - {"SHA256SUMS"}
        if set(checksums) != expected_names:
            raise CandidatePlanError(
                "SHA256SUMS does not index every other archive member exactly"
            )
        payload_checksums = _parse_sums(
            small["PAYLOAD_SHA256SUMS"], label="PAYLOAD_SHA256SUMS"
        )
        if not set(payload_checksums).issubset(checksums):
            raise CandidatePlanError(
                "PAYLOAD_SHA256SUMS names a member outside SHA256SUMS"
            )
        retained = dict(small)
        for name, member in infos.items():
            if name == "SHA256SUMS":
                continue
            payload = retained.get(name)
            if payload is None:
                payload = _member_payload(archive, member)
            digest = hashlib.sha256(payload).hexdigest()
            if digest != checksums[name] or (
                name in payload_checksums and digest != payload_checksums[name]
            ):
                raise CandidatePlanError(
                    f"archive member {name!r} fails SHA-256 verification"
                )
            if (
                name.endswith(("-pluto.dfu", "-provenance.txt"))
                or name in SOURCE_MANIFEST_REVISIONS
            ):
                retained[name] = payload
        return retained, checksums


def _verify_sidecar(archive: Path, sidecar: Path) -> tuple[int, str]:
    archive_size, archive_digest = _stable_owned_file(
        archive, maximum=MAX_ARCHIVE_BYTES, label="candidate archive"
    )
    _sidecar_size, _sidecar_digest = _stable_owned_file(
        sidecar, maximum=1024, label="candidate archive sidecar"
    )
    try:
        payload = sidecar.read_bytes()
    except OSError as error:
        raise CandidatePlanError(
            f"candidate archive sidecar cannot be read: {error}"
        ) from error
    values = _parse_sums(payload, label="candidate archive sidecar")
    if values != {archive.name: archive_digest}:
        raise CandidatePlanError("candidate archive SHA-256 sidecar does not match")
    return archive_size, archive_digest


def _verify_dfu(payload: bytes) -> tuple[int, str]:
    if len(payload) <= 16:
        raise CandidatePlanError("candidate DFU is too small")
    device, product, vendor, dfu_version, signature, length, stored_crc = struct.unpack(
        "<HHHH3sBI", payload[-16:]
    )
    computed_crc = binascii.crc32(payload[:-4]) ^ 0xFFFFFFFF
    if (
        device != 0xFFFF
        or product != 0xB673
        or vendor != 0x0456
        or dfu_version != 0x0100
        or signature != b"UFD"
        or length != 16
        or stored_crc != computed_crc
    ):
        raise CandidatePlanError("candidate DFU suffix or CRC is invalid")
    fit = payload[:-16]
    return len(fit), hashlib.sha256(fit).hexdigest()


def _write_new(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _new_private_directory(path: Path) -> Path:
    selected = path.absolute()
    parent = selected.parent
    state = parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != 0o700
    ):
        raise CandidatePlanError("output parent must be an owned mode-0700 directory")
    try:
        selected.mkdir(mode=0o700)
    except FileExistsError as error:
        raise CandidatePlanError(
            "refusing to reuse an existing output directory"
        ) from error
    return selected


def prepare_candidate(
    archive_path: Path,
    sidecar_path: Path,
    output_directory: Path,
    *,
    rate: int,
    ppu_commit: str,
    generator_commit: str,
    qualification_manifest_path: Path = DEFAULT_QUALIFICATION_MANIFEST,
) -> dict[str, Any]:
    """Verify and prepare one archive without performing any hardware access."""

    if rate not in SUPPORTED_RATES:
        raise CandidatePlanError("rate must be exactly one of 15, 30, or 60 MS/s")
    if HEX_40.fullmatch(ppu_commit) is None:
        raise CandidatePlanError(
            "PPU commit must be one lowercase 40-hex source identity"
        )
    if HEX_40.fullmatch(generator_commit) is None:
        raise CandidatePlanError(
            "generator commit must be one lowercase 40-hex source identity"
        )
    archive = archive_path.absolute()
    sidecar = sidecar_path.absolute()
    archive_bytes, archive_sha256 = _verify_sidecar(archive, sidecar)
    retained, member_sums = _verified_members(archive)
    final_archive_bytes, final_archive_sha256 = _stable_owned_file(
        archive, maximum=MAX_ARCHIVE_BYTES, label="candidate archive"
    )
    if (final_archive_bytes, final_archive_sha256) != (
        archive_bytes,
        archive_sha256,
    ):
        raise CandidatePlanError("candidate archive changed during verification")

    dfu_names = sorted(name for name in retained if name.endswith("-pluto.dfu"))
    provenance_names = sorted(
        name for name in retained if name.endswith("-provenance.txt")
    )
    if len(dfu_names) != 1 or len(provenance_names) != 1:
        raise CandidatePlanError(
            "archive must contain exactly one candidate DFU and provenance"
        )
    dfu_name = dfu_names[0]
    source_manifest_names = [
        name for name in SOURCE_MANIFEST_REVISIONS if name in retained
    ]
    if len(source_manifest_names) != 1:
        raise CandidatePlanError("verified archive lost its source-manifest identity")
    source_manifest_name = source_manifest_names[0]
    source_revision = SOURCE_MANIFEST_REVISIONS[source_manifest_name]
    if f"-{rate}m-rx-only-dnm-{source_revision}-" not in dfu_name:
        raise CandidatePlanError(
            "candidate DFU identity does not match the requested rate"
        )
    dfu_payload = retained[dfu_name]
    fit_bytes, fit_sha256 = _verify_dfu(dfu_payload)

    provenance = _parse_key_values(retained[provenance_names[0]], label="provenance")
    packaged_manifest_payload = retained[source_manifest_name]
    packaged_manifest = _parse_key_values(
        packaged_manifest_payload, label="packaged source manifest"
    )
    qualification_path = qualification_manifest_path.absolute()
    qualification_bytes, qualification_sha256 = _stable_owned_file(
        qualification_path,
        maximum=MAX_SMALL_MEMBER_BYTES,
        label="qualification source manifest",
    )
    qualification_manifest_payload = qualification_path.read_bytes()
    if (
        len(qualification_manifest_payload) != qualification_bytes
        or hashlib.sha256(qualification_manifest_payload).hexdigest()
        != qualification_sha256
    ):
        raise CandidatePlanError("qualification source manifest changed during read")
    qualification_manifest = _parse_key_values(
        qualification_manifest_payload, label="qualification source manifest"
    )
    versions = _parse_versions(retained["packed-VERSIONS.txt"])
    source_commit = provenance.get("firmware_source", "")
    expected_source = qualification_manifest.get(f"route_{rate}_firmware_source")
    expected_bit = qualification_manifest.get(f"route_{rate}_bit_sha256")
    firmware_version = versions.get("device-fw", "")
    source_identity_matches = (
        source_commit == expected_source
        if source_revision == "v1"
        else source_commit == generator_commit
        and qualification_path.name == source_manifest_name
        and packaged_manifest_payload == qualification_manifest_payload
    )
    if (
        HEX_40.fullmatch(source_commit) is None
        or not source_identity_matches
        or provenance.get("starlink_pss_rate_msps") != str(rate)
        or provenance.get("do_not_merge") != "true"
        or provenance.get("persistent_flash_eligible") != "false"
        or packaged_manifest.get("do_not_merge") != "true"
        or packaged_manifest.get("persistent_flash_eligible") != "false"
        or packaged_manifest.get("allocated_radio_serial") != ALLOCATED_SERIAL
        or packaged_manifest.get("starlink_pss_supported_rates_msps") != "15,30,60"
        or qualification_manifest.get("do_not_merge") != "true"
        or qualification_manifest.get("persistent_flash_eligible") != "false"
        or qualification_manifest.get("allocated_radio_serial") != ALLOCATED_SERIAL
        or qualification_manifest.get("starlink_pss_supported_rates_msps") != "15,30,60"
        or expected_bit != member_sums.get("system_top.bit")
        or firmware_version
        != f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-{source_revision}"
        or versions.get("hdl") != packaged_manifest.get("versions_hdl")
        or versions.get("buildroot") != packaged_manifest.get("versions_buildroot")
        or versions.get("linux") != packaged_manifest.get("versions_linux")
        or versions.get("u-boot-xlnx") != packaged_manifest.get("versions_u_boot_xlnx")
    ):
        raise CandidatePlanError(
            "package provenance, manifest, rate, or runtime identity disagrees"
        )
    created_at = provenance.get("build_utc", "")
    if (
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", created_at
        )
        is None
    ):
        raise CandidatePlanError(
            "provenance build_utc is not a canonical UTC timestamp"
        )

    output = _new_private_directory(output_directory)
    try:
        dfu_path = output / dfu_name
        packaged_manifest_path = output / "packaged-source-manifest.yaml"
        qualification_manifest_copy = output / "qualification-source-manifest.yaml"
        index_path = output / "candidate-artifact-index.json"
        plan_path = output / "candidate-plan-v2.json"
        sums_path = output / "CANDIDATE_SHA256SUMS"
        _write_new(dfu_path, dfu_payload)
        _write_new(packaged_manifest_path, packaged_manifest_payload)
        _write_new(qualification_manifest_copy, qualification_manifest_payload)
        index: dict[str, Any] = {
            "schema": "plutosdr-fw.starlink-pss-multirate-candidate-index.v1",
            "schema_version": 1,
            "allowed_operation": "ram-only",
            "allocated_radio_serial": ALLOCATED_SERIAL,
            "archive": {
                "path": str(archive),
                "bytes": archive_bytes,
                "sha256": archive_sha256,
            },
            "dfu": {
                "path": str(dfu_path),
                "bytes": len(dfu_payload),
                "sha256": hashlib.sha256(dfu_payload).hexdigest(),
            },
            "fit": {"bytes": fit_bytes, "sha256": fit_sha256},
            "firmware_version": firmware_version,
            "hardware_accessed": False,
            "generator_source_commit": generator_commit,
            "persistent_flash_eligible": False,
            "ppu_source_commit": ppu_commit,
            "rate_msps": rate,
            "source_manifest_name": source_manifest_name,
            "source_manifest_revision": source_revision,
            "runtime_target": "ad9363a-1r1t",
            "source_commit": source_commit,
            "packaged_source_manifest": {
                "path": str(packaged_manifest_path),
                "bytes": len(packaged_manifest_payload),
                "sha256": hashlib.sha256(packaged_manifest_payload).hexdigest(),
            },
            "qualification_source_manifest": {
                "path": str(qualification_manifest_copy),
                "bytes": len(qualification_manifest_payload),
                "sha256": qualification_sha256,
            },
        }
        index_payload = _canonical(index)
        _write_new(index_path, index_payload)
        candidate_id = hashlib.sha256(
            b"pluto-plus-utils.release-candidate-plan.v2\0"
            + archive_sha256.encode()
            + ppu_commit.encode()
            + generator_commit.encode()
            + str(rate).encode()
        ).hexdigest()[:32]
        plan: dict[str, Any] = {
            "schema": "pluto-plus-utils.release-candidate-plan.v2",
            "schema_version": 2,
            "candidate_id": candidate_id,
            "created_at": created_at,
            "source_repository": FIRMWARE_REPOSITORY,
            "source_commit": source_commit,
            "device_tool_repository": PPU_REPOSITORY,
            "device_tool_version": PPU_VERSION,
            "device_tool_source_commit": ppu_commit,
            "artifact_index": {
                "path": str(index_path),
                "bytes": len(index_payload),
                "sha256": hashlib.sha256(index_payload).hexdigest(),
            },
            "dfu": index["dfu"],
            "fit": index["fit"],
            "expected_runtime": {
                "firmware_version": firmware_version,
                "hardware_model": HARDWARE_MODEL,
                "metadata_abi": METADATA_ABI,
                "capabilities": [],
            },
            "attestation_policy": {
                "profile": "rx-only-v1",
                "supported_runtime_targets": ["ad9361-1r1t", "ad9363a-1r1t"],
                "root_device_tree_marker": "misko,rx-only-fpga",
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
        plan_payload = _canonical(plan)
        _write_new(plan_path, plan_payload)
        digests = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                index_path,
                plan_path,
                dfu_path,
                packaged_manifest_path,
                qualification_manifest_copy,
            )
        }
        sums_payload = "".join(
            f"{digest}  {name}\n" for name, digest in sorted(digests.items())
        ).encode()
        _write_new(sums_path, sums_payload)
        directory = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # The directory is new and contains only files created by this invocation.
        for child in output.iterdir():
            child.unlink()
        output.rmdir()
        raise
    return {
        "verdict": "PASS_OFFLINE",
        "hardware_accessed": False,
        "will_write_qspi": False,
        "will_load_volatile_ram": False,
        "rate_msps": rate,
        "allocated_radio_serial": ALLOCATED_SERIAL,
        "runtime_target": "ad9363a-1r1t",
        "candidate_plan": str(plan_path),
        "candidate_plan_sha256": hashlib.sha256(plan_payload).hexdigest(),
        "candidate_artifact_index": str(index_path),
        "candidate_dfu": str(dfu_path),
        "generator_source_commit": generator_commit,
        "ppu_source_commit": ppu_commit,
        "next_gate": "fresh serial-scoped USB inventory and reviewed operation-plan.v2",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--rate", type=int, choices=SUPPORTED_RATES, required=True)
    parser.add_argument("--ppu-commit", required=True)
    parser.add_argument("--ppu-repository", type=Path, required=True)
    parser.add_argument("--generator-commit", required=True)
    parser.add_argument(
        "--qualification-manifest",
        type=Path,
        default=DEFAULT_QUALIFICATION_MANIFEST,
    )
    args = parser.parse_args(argv)
    sidecar = args.archive_sha256
    # Keep the inferred sidecar identity explicit in the result and validation.
    if sidecar is None:
        sidecar = Path(str(args.archive) + ".sha256")
    try:
        _verify_clean_source_repository(
            ROOT,
            commit=args.generator_commit,
            expected_slug=FIRMWARE_REPOSITORY,
            label="generator",
        )
        _verify_clean_source_repository(
            args.ppu_repository,
            commit=args.ppu_commit,
            expected_slug=PPU_REPOSITORY,
            label="PPU",
        )
        result = prepare_candidate(
            args.archive,
            sidecar,
            args.output_directory,
            rate=args.rate,
            ppu_commit=args.ppu_commit,
            generator_commit=args.generator_commit,
            qualification_manifest_path=args.qualification_manifest,
        )
    except (OSError, ValueError, CandidatePlanError, tarfile.TarError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
