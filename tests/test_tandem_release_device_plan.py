"""Behavioral oracles for the utility release-candidate plan producer."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

import pytest

from scripts import tandem_release_device_plan as device_plan
from scripts.tandem_release_device_plan import DevicePlanError, build_plan, main
from tests.radio_hardware.candidate_binding import (
    REQUIRED_EVIDENCE_ROLES,
    validate_artifact_index,
)
from tests.radio_hardware.pluto_plus_candidate import (
    PLUTO_IIO_BUFFER_METADATA_ABI,
    PLUTO_PLUS_UTILS_SOURCE_COMMIT,
    validate_release_candidate_plan,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _index(dfu: bytes) -> dict[str, Any]:
    return {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": "candidate-pre-hardware",
        "release": {
            "firmware_version": "v0.41-plutoplus-spf-tandem-agc-v8-rc21",
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": "1" * 40,
            "manifest_path": "source/tandem-agc-v8-rc21-source.yaml",
            "manifest_sha256": "2" * 64,
        },
        "build": {"run_id": 1, "run_attempt": 1},
        "artifact": {
            "dfu_path": "artifact/firmware.dfu",
            "dfu_bytes": len(dfu),
            "dfu_sha256": hashlib.sha256(dfu).hexdigest(),
            "fit_bytes": len(dfu) - 16,
            "fit_sha256": hashlib.sha256(dfu[:-16]).hexdigest(),
        },
        "harness": {
            "files": [
                {"path": "scripts/tandem_release_device_plan.py", "sha256": "4" * 64}
            ]
        },
        "evidence": {
            "members": [
                {
                    "role": role,
                    "path": f"evidence/{role}.txt",
                    "bytes": position + 1,
                    "sha256": f"{(position + 5) % 16:x}" * 64,
                }
                for position, role in enumerate(REQUIRED_EVIDENCE_ROLES)
            ]
        },
    }


@pytest.fixture(autouse=True)
def _semantic_artifact_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(path: Path, *, expected_stage: str) -> dict[str, Any]:
        normalized = validate_artifact_index(json.loads(path.read_bytes()))
        assert normalized["stage"] == expected_stage
        return normalized

    monkeypatch.setattr(device_plan, "verify_artifact_index_semantics", verify)


def _archive(tmp_path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    tmp_path.chmod(0o700)
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    dfu = b"candidate-fit" + b"\x00" * 20
    dfu_path = artifact / "firmware.dfu"
    dfu_path.write_bytes(dfu)
    dfu_path.chmod(0o600)
    index = _index(dfu)
    index_path = tmp_path / "candidate-index.json"
    index_path.write_bytes(_canonical(index))
    return index_path, dfu, index


def test_plan_builder_binds_exact_artifact_and_pushed_utility(tmp_path: Path) -> None:
    index_path, _dfu, index = _archive(tmp_path)
    plan = build_plan(index_path, created_at="2026-08-26T18:00:00Z")
    index_payload = index_path.read_bytes()

    assert plan["device_tool_source_commit"] == PLUTO_PLUS_UTILS_SOURCE_COMMIT
    assert plan["allowed_operation"] == "ram-only"
    assert plan["expected_runtime"]["metadata_abi"] == PLUTO_IIO_BUFFER_METADATA_ABI
    assert index["release"]["metadata_abi"] == "frame-metadata-v5"
    assert plan["dfu_identity"]["selector"] == "0456:b673,0456:b674"
    assert plan["artifact_index"]["sha256"] == hashlib.sha256(index_payload).hexdigest()
    validate_release_candidate_plan(
        plan,
        artifact_index=index,
        artifact_index_bytes=len(index_payload),
        artifact_index_sha256=hashlib.sha256(index_payload).hexdigest(),
    )


def test_cli_publishes_absent_mode_private_canonical_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    index_path, _dfu, _index_value = _archive(tmp_path)
    deploy = tmp_path / "hardware" / "deploy" / "serial"
    deploy.mkdir(parents=True, mode=0o700)
    output = deploy / "release-candidate-plan.json"

    assert (
        main(
            [
                "--artifact-index",
                str(index_path),
                "--output",
                str(output),
                "--created-at",
                "2026-08-26T18:00:00Z",
            ]
        )
        == 0
    )

    report = json.loads(capsys.readouterr().out)
    assert report["hardware_accessed"] is False
    assert report["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_bytes() == _canonical(json.loads(output.read_bytes()))
    with pytest.raises(SystemExit):
        main(
            [
                "--artifact-index",
                str(index_path),
                "--output",
                str(output),
            ]
        )


def test_builder_rejects_substituted_dfu(tmp_path: Path) -> None:
    index_path, _dfu, _index_value = _archive(tmp_path)
    dfu_path = tmp_path / "artifact" / "firmware.dfu"
    dfu_path.write_bytes(b"x" * dfu_path.stat().st_size)
    dfu_path.chmod(0o600)

    with pytest.raises(DevicePlanError, match="DFU/FIT bytes differ"):
        build_plan(index_path, created_at="2026-08-26T18:00:00Z")


def test_builder_accepts_exact_final_pre_confirmation_index(tmp_path: Path) -> None:
    candidate_path, _dfu, index = _archive(tmp_path)
    index["stage"] = "final-pre-confirmation"
    final_path = tmp_path / "final-artifact-index.json"
    final_path.write_bytes(_canonical(index))
    candidate_path.unlink()

    plan = build_plan(final_path, created_at="2026-08-26T18:00:00Z")

    assert Path(plan["artifact_index"]["path"]).name == "final-artifact-index.json"


def test_builder_rejects_semantically_unauthorizing_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_path, _dfu, _index_value = _archive(tmp_path)

    def reject(_path: Path, *, expected_stage: str) -> dict[str, Any]:
        del expected_stage
        raise device_plan.EvidenceError("planted semantic rejection")

    monkeypatch.setattr(device_plan, "verify_artifact_index_semantics", reject)
    with pytest.raises(DevicePlanError, match="not semantically authorizing"):
        build_plan(index_path, created_at="2026-08-26T18:00:00Z")
