from __future__ import annotations

import binascii
import hashlib
import io
import json
import stat
import struct
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.starlink_pss_multirate_candidate_plan import (
    ALLOCATED_SERIAL,
    ROOT,
    CandidatePlanError,
    _verify_clean_source_repository,
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
    revision: str = "v1",
    source_commit: str = SOURCE_COMMIT,
    actual_bit: bytes = b"bit",
    manifest_payload: bytes | None = None,
) -> tuple[Path, Path]:
    assert revision in {"v1", "v2"}
    dfu_name = (
        f"plutoplus-starlink-pss-{rate}m-rx-only-dnm-{revision}-source-pluto.dfu"
    )
    manifest_name = f"starlink-pss-multirate-rx-only-dnm-{revision}-source.yaml"
    buildroot_version = (
        "starlink-rx-only-dnm-v1-source/buildroot-pss15-abi12-v1"
        if revision == "v1"
        else "starlink-rx-only-dnm-v1-source/buildroot-pss-acqctl-v1"
    )
    members: dict[str, bytes] = {
        "packed-VERSIONS.txt": (
            f"device-fw v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-{revision}\n"
            "hdl starlink-rx-only-dnm-v1-source/hdl-pss15-30-60-acquisition-v2\n"
            f"buildroot {buildroot_version}\n"
            "linux starlink-rx-only-dnm-v1-source/linux-v2\n"
            "u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx\n"
        ).encode(),
        manifest_name: manifest_payload
        or (
            "do_not_merge: true\n"
            "persistent_flash_eligible: false\n"
            f"allocated_radio_serial: {ALLOCATED_SERIAL}\n"
            "starlink_pss_supported_rates_msps: 15,30,60\n"
            f"route_{rate}_firmware_source: {source_commit}\n"
            f"route_{rate}_bit_sha256: {hashlib.sha256(b'bit').hexdigest()}\n"
            "versions_hdl: starlink-rx-only-dnm-v1-source/hdl-pss15-30-60-acquisition-v2\n"
            f"versions_buildroot: {buildroot_version}\n"
            "versions_linux: starlink-rx-only-dnm-v1-source/linux-v2\n"
            "versions_u_boot_xlnx: gain-series-v4-rc2-source/u-boot-xlnx\n"
        ).encode(),
        f"plutoplus-starlink-pss-{rate}m-rx-only-dnm-{revision}-source-provenance.txt": (
            "release_state=candidate\n"
            "hardware_accessed=false\n"
            f"firmware_source={source_commit}\n"
            "build_utc=2026-09-03T12:34:56Z\n"
            f"starlink_pss_rate_msps={rate}\n"
            "do_not_merge=true\n"
            "persistent_flash_eligible=false\n"
        ).encode(),
        dfu_name: _dfu(),
        "system_top.bit": actual_bit,
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


def _manifest_from_archive(archive: Path, *, revision: str = "v2") -> bytes:
    name = f"starlink-pss-multirate-rx-only-dnm-{revision}-source.yaml"
    with tarfile.open(archive, mode="r:gz") as bundle:
        stream = bundle.extractfile(name)
        assert stream is not None
        return stream.read()


def _generator_repository(
    root: Path, manifest_payload: bytes
) -> tuple[Path, str, str]:
    repository = root / "generator"
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.name", "Candidate Test")
    git("config", "user.email", "candidate@example.invalid")
    git("remote", "add", "origin", "git@github.com:misko/plutosdr-fw.git")
    manifests = repository / "manifests"
    manifests.mkdir()
    (manifests / "starlink-pss-multirate-rx-only-dnm-v2-source.yaml").write_bytes(
        manifest_payload
    )
    git("add", "manifests")
    git("commit", "-m", "package source")
    package_commit = git("rev-parse", "HEAD")
    (repository / "README").write_text("generator descendant\n")
    git("add", "README")
    git("commit", "-m", "generator fix")
    generator_commit = git("rev-parse", "HEAD")
    return repository, package_commit, generator_commit


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


def test_prepares_controller_v2_only_from_identical_source_checkout(
    tmp_path: Path,
) -> None:
    provisional, _ = _package(
        tmp_path, revision="v2", actual_bit=b"fresh-vivado-route"
    )
    packaged_manifest = _manifest_from_archive(provisional)
    repository, package_commit, generator_commit = _generator_repository(
        tmp_path, packaged_manifest
    )
    archive, sidecar = _package(
        tmp_path,
        revision="v2",
        source_commit=package_commit,
        actual_bit=b"fresh-vivado-route",
        manifest_payload=packaged_manifest,
    )
    manifest_name = "starlink-pss-multirate-rx-only-dnm-v2-source.yaml"
    qualification = tmp_path / manifest_name
    qualification.write_bytes(packaged_manifest)
    output = _output_parent(tmp_path) / "15-v2"

    result = prepare_candidate(
        archive,
        sidecar,
        output,
        rate=15,
        ppu_commit=PPU_COMMIT,
        generator_commit=generator_commit,
        generator_repository=repository,
        qualification_manifest_path=qualification,
    )

    plan = json.loads((output / "candidate-plan-v2.json").read_bytes())
    index = json.loads((output / "candidate-artifact-index.json").read_bytes())
    assert result["verdict"] == "PASS_OFFLINE"
    assert plan["source_commit"] == package_commit
    assert plan["expected_runtime"]["firmware_version"].endswith("dnm-v2")
    assert index["source_manifest_name"] == manifest_name
    assert index["source_manifest_revision"] == "v2"
    assert index["package_source_attestation"] == (
        "clean-generator-descendant-identical-manifest-v1"
    )


def test_rejects_v2_package_source_outside_generator_history(tmp_path: Path) -> None:
    provisional, _ = _package(tmp_path, revision="v2")
    packaged_manifest = _manifest_from_archive(provisional)
    repository, _, generator_commit = _generator_repository(
        tmp_path, packaged_manifest
    )
    archive, sidecar = _package(
        tmp_path,
        revision="v2",
        source_commit="7" * 40,
        manifest_payload=packaged_manifest,
    )
    qualification = tmp_path / "starlink-pss-multirate-rx-only-dnm-v2-source.yaml"
    qualification.write_bytes(packaged_manifest)
    output = _output_parent(tmp_path) / "outside-history"

    with pytest.raises(CandidatePlanError, match="not an ancestor"):
        prepare_candidate(
            archive,
            sidecar,
            output,
            rate=15,
            ppu_commit=PPU_COMMIT,
            generator_commit=generator_commit,
            generator_repository=repository,
            qualification_manifest_path=qualification,
        )

    assert not output.exists()


def test_rejects_v2_manifest_not_present_at_package_source(tmp_path: Path) -> None:
    provisional, _ = _package(tmp_path, revision="v2")
    source_manifest = _manifest_from_archive(provisional)
    repository, package_commit, generator_commit = _generator_repository(
        tmp_path, source_manifest
    )
    packaged_manifest = source_manifest + b"# post-source divergence\n"
    archive, sidecar = _package(
        tmp_path,
        revision="v2",
        source_commit=package_commit,
        manifest_payload=packaged_manifest,
    )
    qualification = tmp_path / "starlink-pss-multirate-rx-only-dnm-v2-source.yaml"
    qualification.write_bytes(packaged_manifest)
    output = _output_parent(tmp_path) / "manifest-divergence"

    with pytest.raises(CandidatePlanError, match="not byte-identical"):
        prepare_candidate(
            archive,
            sidecar,
            output,
            rate=15,
            ppu_commit=PPU_COMMIT,
            generator_commit=generator_commit,
            generator_repository=repository,
            qualification_manifest_path=qualification,
        )

    assert not output.exists()


def test_v1_still_rejects_non_reference_bitstream(tmp_path: Path) -> None:
    archive, sidecar = _package(tmp_path, actual_bit=b"fresh-vivado-route")
    qualification = _qualification_manifest(tmp_path)
    output = _output_parent(tmp_path) / "v1-bit-mismatch"

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


def test_source_repository_attestor_requires_exact_clean_head(tmp_path: Path) -> None:
    repository = tmp_path / "ppu"
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.name", "Candidate Test")
    git("config", "user.email", "candidate@example.invalid")
    (repository / "README").write_text("clean\n")
    git("add", "README")
    git("commit", "-m", "fixture")
    git("remote", "add", "origin", "git@github.com:misko/pluto-plus-utils.git")
    commit = git("rev-parse", "HEAD")

    assert (
        _verify_clean_source_repository(
            repository,
            commit=commit,
            expected_slug="misko/pluto-plus-utils",
            label="PPU",
        )
        == repository.absolute()
    )
    (repository / "dirty").write_text("reject\n")
    with pytest.raises(CandidatePlanError, match="exact clean expected"):
        _verify_clean_source_repository(
            repository,
            commit=commit,
            expected_slug="misko/pluto-plus-utils",
            label="PPU",
        )


def test_retained_offline_candidate_evidence_is_sealed_and_non_authorizing() -> None:
    name = "starlink-pss-multirate-ram-candidates-dnm-v1-offline.yaml"
    manifest = ROOT / "manifests" / name
    sidecar = ROOT / "manifests" / f"{name.removesuffix('.yaml')}-SHA256SUMS"
    payload = manifest.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    assert sidecar.read_text() == f"{digest}  {name}\n"
    text = payload.decode()
    assert "do_not_merge: true" in text
    assert "persistent_flash_eligible: false" in text
    assert "hardware_accessed: false" in text
    assert "operation_plans_created: false" in text
    assert f"allocated_radio_serial: {ALLOCATED_SERIAL}" in text
    assert "generator_source_commit: 0a2ccd2f8c7826742541112eac9b5842965a1544" in text
    assert "ppu_main_commit: 5790a39705e9e598ef048ec773e0227cf9ac1808" in text
    assert "rate_15_candidate_plan_sha256: 8fe7e216" in text
    assert "rate_30_candidate_plan_sha256: d4dfcc02" in text
    assert "rate_60_candidate_plan_sha256: 561249fe" in text
    assert "explicit_operator_authorization_required: true" in text


def test_controller_candidate_evidence_is_sealed_and_non_authorizing() -> None:
    name = "starlink-pss-multirate-ram-candidates-dnm-v2-offline.yaml"
    manifest = ROOT / "manifests" / name
    sidecar = ROOT / "manifests" / f"{name.removesuffix('.yaml')}-SHA256SUMS"
    payload = manifest.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()

    assert sidecar.read_text() == f"{digest}  {name}\n"
    text = payload.decode()
    assert "do_not_merge: true" in text
    assert "persistent_flash_eligible: false" in text
    assert "hardware_accessed: false" in text
    assert "operation_plans_created: false" in text
    assert f"allocated_radio_serial: {ALLOCATED_SERIAL}" in text
    assert "package_firmware_source: 205884182c2e" in text
    assert "generator_source_commit: ee8fe286d136" in text
    assert "ppu_main_commit: 5790a39705e9" in text
    assert "rate_15_github_run: 33790840756" in text
    assert "rate_30_github_run: 33792849042" in text
    assert "rate_60_github_run: 33795030770" in text
    assert "rate_15_candidate_plan_sha256: 773e12ae" in text
    assert "rate_30_candidate_plan_sha256: d671c254" in text
    assert "rate_60_candidate_plan_sha256: d467eb2e" in text
    assert "controller_present_all_rates: true" in text
    assert "all_package_checksums_verified: true" in text
    assert "ppu_offline_schema_dfu_builder_verdict: PASS_ALL_RATES" in text
    assert "ppu_offline_builder_operation_written: false" in text
    assert "ppu_offline_builder_hardware_accessed: false" in text
    assert "explicit_operator_authorization_required: true" in text
