from __future__ import annotations

import binascii
import hashlib
import io
import json
import stat
import struct
import tarfile
from pathlib import Path

import pytest

from scripts.starlink_pss_multirate_candidate_plan import (
    ALLOCATED_SERIAL,
    CandidatePlanError,
    prepare_candidate,
)

PPU_COMMIT = "5" * 40
SOURCE_COMMIT = "6" * 40
GENERATOR_COMMIT = "8" * 40


def _dfu() -> bytes:
    fit = b"valid-fit-body"
    prefix = struct.pack("<HHHH3sB", 0xFFFF, 0xB673, 0x0456, 0x0100, b"UFD", 16)
    crc = binascii.crc32(fit + prefix) ^ 0xFFFFFFFF
    return fit + prefix + struct.pack("<I", crc)


def _package(
    root: Path,
    *,
    rate: int = 15,
    unsafe_member: bool = False,
) -> tuple[Path, Path]:
    dfu_name = f"plutoplus-starlink-pss-{rate}m-rx-only-dnm-v1-source-pluto.dfu"
    members: dict[str, bytes] = {
        "packed-VERSIONS.txt": (
            f"device-fw v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v1\n"
            "hdl starlink-rx-only-dnm-v1-source/hdl-pss15-30-60-acquisition-v2\n"
            "buildroot starlink-rx-only-dnm-v1-source/buildroot-pss15-abi12-v1\n"
            "linux starlink-rx-only-dnm-v1-source/linux-v2\n"
            "u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx\n"
        ).encode(),
        "starlink-pss-multirate-rx-only-dnm-v1-source.yaml": (
            "do_not_merge: true\n"
            "persistent_flash_eligible: false\n"
            f"allocated_radio_serial: {ALLOCATED_SERIAL}\n"
            "starlink_pss_supported_rates_msps: 15,30,60\n"
            "versions_hdl: starlink-rx-only-dnm-v1-source/hdl-pss15-30-60-acquisition-v2\n"
            "versions_buildroot: starlink-rx-only-dnm-v1-source/buildroot-pss15-abi12-v1\n"
            "versions_linux: starlink-rx-only-dnm-v1-source/linux-v2\n"
            "versions_u_boot_xlnx: gain-series-v4-rc2-source/u-boot-xlnx\n"
        ).encode(),
        f"plutoplus-starlink-pss-{rate}m-rx-only-dnm-v1-source-provenance.txt": (
            "release_state=candidate\n"
            "hardware_accessed=false\n"
            f"firmware_source={SOURCE_COMMIT}\n"
            "build_utc=2026-09-03T12:34:56Z\n"
            f"starlink_pss_rate_msps={rate}\n"
            "do_not_merge=true\n"
            "persistent_flash_eligible=false\n"
        ).encode(),
        dfu_name: _dfu(),
        "system_top.bit": b"bit",
    }
    payload_names = (dfu_name, "system_top.bit")
    members["PAYLOAD_SHA256SUMS"] = "".join(
        f"{hashlib.sha256(members[name]).hexdigest()}  {name}\n"
        for name in payload_names
    ).encode()
    checksum_payload = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(members.items())
    ).encode()
    members["SHA256SUMS"] = checksum_payload
    if unsafe_member:
        members["../escape"] = b"bad"

    archive = root / f"candidate-{rate}.tar.gz"
    with tarfile.open(archive, mode="w:gz") as bundle:
        for name, payload in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mode = 0o600
            bundle.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar = Path(str(archive) + ".sha256")
    sidecar.write_text(f"{digest}  {archive.name}\n")
    return archive, sidecar


def _qualification_manifest(
    root: Path, *, rate: int = 15, source: str = SOURCE_COMMIT
) -> Path:
    path = root / "qualification.yaml"
    path.write_text(
        "do_not_merge: true\n"
        "persistent_flash_eligible: false\n"
        f"allocated_radio_serial: {ALLOCATED_SERIAL}\n"
        "starlink_pss_supported_rates_msps: 15,30,60\n"
        f"route_{rate}_firmware_source: {source}\n"
        f"route_{rate}_bit_sha256: {hashlib.sha256(b'bit').hexdigest()}\n"
    )
    return path


def _output_parent(root: Path) -> Path:
    parent = root / "private"
    parent.mkdir(mode=0o700)
    return parent


def test_prepares_canonical_ppu_v2_plan_without_hardware(tmp_path: Path) -> None:
    archive, sidecar = _package(tmp_path)
    qualification = _qualification_manifest(tmp_path)
    output = _output_parent(tmp_path) / "15"

    result = prepare_candidate(
        archive,
        sidecar,
        output,
        rate=15,
        ppu_commit=PPU_COMMIT,
        generator_commit=GENERATOR_COMMIT,
        qualification_manifest_path=qualification,
    )

    plan = json.loads((output / "candidate-plan-v2.json").read_bytes())
    index = json.loads((output / "candidate-artifact-index.json").read_bytes())
    assert result["verdict"] == "PASS_OFFLINE"
    assert result["hardware_accessed"] is False
    assert result["will_write_qspi"] is False
    assert result["will_load_volatile_ram"] is False
    assert result["allocated_radio_serial"] == ALLOCATED_SERIAL
    assert plan["schema"] == "pluto-plus-utils.release-candidate-plan.v2"
    assert plan["source_commit"] == SOURCE_COMMIT
    assert plan["device_tool_source_commit"] == PPU_COMMIT
    assert plan["allowed_operation"] == "ram-only"
    assert plan["expected_runtime"] == {
        "capabilities": [],
        "firmware_version": "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v1",
        "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9363A)",
        "metadata_abi": "frame-metadata-v3",
    }
    assert index["runtime_target"] == "ad9363a-1r1t"
    assert index["generator_source_commit"] == GENERATOR_COMMIT
    assert index["persistent_flash_eligible"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())


def test_rejects_archive_sidecar_mismatch_before_output(tmp_path: Path) -> None:
    archive, sidecar = _package(tmp_path)
    qualification = _qualification_manifest(tmp_path)
    sidecar.write_text(f"{'0' * 64}  {archive.name}\n")
    output = _output_parent(tmp_path) / "15"

    with pytest.raises(CandidatePlanError, match="sidecar does not match"):
        prepare_candidate(
            archive,
            sidecar,
            output,
            rate=15,
            ppu_commit=PPU_COMMIT,
            generator_commit=GENERATOR_COMMIT,
            qualification_manifest_path=qualification,
        )

    assert not output.exists()


def test_rejects_manifest_source_disagreement(tmp_path: Path) -> None:
    archive, sidecar = _package(tmp_path)
    qualification = _qualification_manifest(tmp_path, source="7" * 40)
    output = _output_parent(tmp_path) / "15"

    with pytest.raises(CandidatePlanError, match="provenance, manifest"):
        prepare_candidate(
            archive,
            sidecar,
            output,
            rate=15,
            ppu_commit=PPU_COMMIT,
            generator_commit=GENERATOR_COMMIT,
            qualification_manifest_path=qualification,
        )

    assert not output.exists()


def test_rejects_non_basename_archive_member(tmp_path: Path) -> None:
    archive, sidecar = _package(tmp_path, unsafe_member=True)
    qualification = _qualification_manifest(tmp_path)
    output = _output_parent(tmp_path) / "15"

    with pytest.raises(CandidatePlanError, match="basename members"):
        prepare_candidate(
            archive,
            sidecar,
            output,
            rate=15,
            ppu_commit=PPU_COMMIT,
            generator_commit=GENERATOR_COMMIT,
            qualification_manifest_path=qualification,
        )

    assert not output.exists()
