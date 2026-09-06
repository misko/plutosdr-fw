from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_hardware_probe_v9 as probe


def _write_private(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    path.chmod(0o600)


def _profile_handoff(tmp_path: Path) -> SimpleNamespace:
    tmp_path.chmod(0o700)
    manifest = tmp_path / probe.SOURCE_MANIFEST_NAME
    manifest.write_text(
        "schema: plutosdr-fw.source-manifest\n"
        "do_not_merge: true\n"
        "persistent_flash_eligible: false\n"
        f"allocated_radio_serial: {probe.probe_v1.ALLOCATED_SERIAL}\n"
        "starlink_pss_profile: acquisition-injection\n"
        "starlink_pss_profile_rate_gate_msps: 15\n"
        "m2_default_test_phases: 0,19999,7311\n"
    )
    manifest.chmod(0o600)
    qualification = tmp_path / "qualification-source-manifest.yaml"
    qualification.write_bytes(manifest.read_bytes())
    qualification.chmod(0o600)

    def identity(path: Path) -> dict[str, object]:
        payload = path.read_bytes()
        return {
            "path": str(path),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    index = tmp_path / "candidate-artifact-index.json"
    _write_private(
        index,
        {
            "schema": "plutosdr-fw.starlink-pss-multirate-candidate-index.v1",
            "schema_version": 1,
            "allowed_operation": "ram-only",
            "allocated_radio_serial": probe.probe_v1.ALLOCATED_SERIAL,
            "firmware_version": probe.EXPECTED_FIRMWARE,
            "persistent_flash_eligible": False,
            "rate_msps": 15,
            "runtime_target": probe.RUNTIME_TARGET,
            "source_manifest_name": probe.SOURCE_MANIFEST_NAME,
            "source_manifest_revision": probe.SOURCE_REVISION,
            "packaged_source_manifest": identity(manifest),
            "qualification_source_manifest": identity(qualification),
        },
    )
    return SimpleNamespace(
        candidate=SimpleNamespace(
            artifact_index=SimpleNamespace(
                path=index,
                bytes=index.stat().st_size,
                sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
            )
        )
    )


def test_v9_profile_attestation_accepts_exact_v7_candidate(tmp_path: Path) -> None:
    probe._require_acquisition_injection_profile(_profile_handoff(tmp_path))


def test_v9_profile_attestation_rejects_wrong_profile(tmp_path: Path) -> None:
    handoff = _profile_handoff(tmp_path)
    index = Path(handoff.candidate.artifact_index.path)
    value = json.loads(index.read_text())
    value["source_manifest_revision"] = "v6"
    _write_private(index, value)
    handoff.candidate.artifact_index.bytes = index.stat().st_size
    handoff.candidate.artifact_index.sha256 = hashlib.sha256(index.read_bytes()).hexdigest()
    with pytest.raises(probe.ProbeError, match="v7 profile"):
        probe._require_acquisition_injection_profile(handoff)


def test_v9_contract_scopes_identity_revision_and_loader(monkeypatch) -> None:
    original_identity = (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL)
    original_revisions = probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
    original_loader = probe.probe_v1._load_handoff
    checked: list[object] = []
    fake_handoff = SimpleNamespace(candidate=object())

    monkeypatch.setattr(probe.probe_v1, "_load_handoff", lambda *a, **k: fake_handoff)
    monkeypatch.setattr(
        probe, "_require_acquisition_injection_profile", checked.append
    )
    patched_original = probe.probe_v1._load_handoff
    with probe._ad9361_v7_acquisition_injection_contract():
        assert probe.probe_v1.RUNTIME_TARGET == "ad9361-1r1t"
        assert probe.probe_v1.EXPECTED_MODEL == probe.EXPECTED_MODEL
        assert "v7" in probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
        assert probe.probe_v1._load_handoff() is fake_handoff
        assert checked == [fake_handoff]
    assert probe.probe_v1._load_handoff is patched_original
    assert (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL) == original_identity
    assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == original_revisions
    monkeypatch.setattr(probe.probe_v1, "_load_handoff", original_loader)


def test_v9_wraps_dependency_safe_probe_under_the_v7_contract(monkeypatch) -> None:
    observed: list[tuple[str, tuple[str, ...]]] = []

    def fake(_args: object) -> dict[str, bool]:
        observed.append((probe.probe_v1.RUNTIME_TARGET, probe.probe_v2.SUPPORTED_SOURCE_REVISIONS))
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v5, "build_plan", fake)
    assert probe.build_plan(object()) == {"ok": True}
    assert observed[0][0] == "ad9361-1r1t"
    assert observed[0][1][-1] == "v7"


def test_v9_probe_manifest_is_offline_dnm_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v9-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "9"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["candidate_profile"] == "acquisition-injection"
    assert values["supported_candidate_revision"] == "v7"
    for prefix in (
        "probe_script",
        "probe_test",
        "inherited_v8_probe_script",
        "inherited_v8_manifest",
        "candidate_source",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
