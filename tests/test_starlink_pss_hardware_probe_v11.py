from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_hardware_probe_v11 as probe


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
        "starlink_pss_profile: acquisition-only\n"
        "starlink_pss_profile_rate_gate_msps: 30\n"
        "starlink_pss_30_ddc_stages: 1\n"
        "starlink_pss_clean_start_scheduler_gaps: 0\n"
        "starlink_pss_cold_start_absolute_index_load: true\n"
        "starlink_pss_real_gap_fail_closed: true\n"
        "starlink_pss_abi_30: 1.2\n"
        "starlink_pss_group_delay_30_source_samples: 7\n"
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
            "rate_msps": probe.RATE_MSPS,
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


def test_v11_profile_attestation_accepts_exact_v9_candidate(tmp_path: Path) -> None:
    probe._require_acquisition_only_profile(_profile_handoff(tmp_path))


def test_v11_profile_attestation_rejects_wrong_rate(tmp_path: Path) -> None:
    handoff = _profile_handoff(tmp_path)
    index = Path(handoff.candidate.artifact_index.path)
    value = json.loads(index.read_text())
    value["rate_msps"] = 15
    _write_private(index, value)
    handoff.candidate.artifact_index.bytes = index.stat().st_size
    handoff.candidate.artifact_index.sha256 = hashlib.sha256(index.read_bytes()).hexdigest()
    with pytest.raises(probe.ProbeError, match="30 MS/s v9 profile"):
        probe._require_acquisition_only_profile(handoff)


def test_v11_contract_scopes_identity_revision_and_loader(monkeypatch) -> None:
    original_identity = (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL)
    original_revisions = probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
    checked: list[object] = []
    fake_handoff = SimpleNamespace(candidate=object())

    monkeypatch.setattr(probe.probe_v1, "_load_handoff", lambda *a, **k: fake_handoff)
    monkeypatch.setattr(probe, "_require_acquisition_only_profile", checked.append)
    patched_original = probe.probe_v1._load_handoff
    with probe._ad9361_v9_acquisition_only_contract():
        assert probe.probe_v1.RUNTIME_TARGET == "ad9361-1r1t"
        assert probe.probe_v1.EXPECTED_MODEL == probe.EXPECTED_MODEL
        assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS[-1] == "v9"
        assert probe.probe_v1._load_handoff() is fake_handoff
        assert checked == [fake_handoff]
    assert probe.probe_v1._load_handoff is patched_original
    assert (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL) == original_identity
    assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == original_revisions


def test_v11_wraps_dependency_safe_probe_under_the_v9_contract(monkeypatch) -> None:
    observed: list[tuple[str, tuple[str, ...]]] = []

    def fake(_args: object) -> dict[str, bool]:
        observed.append((probe.probe_v1.RUNTIME_TARGET, probe.probe_v2.SUPPORTED_SOURCE_REVISIONS))
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v5, "build_plan", fake)
    assert probe.build_plan(object()) == {"ok": True}
    assert observed == [("ad9361-1r1t", ("v2", "v3", "v4", "v5", "v6", "v8", "v9"))]


def test_v11_probe_manifest_is_offline_dnm_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v11-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "11"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["candidate_profile"] == "acquisition-only"
    assert values["supported_candidate_revision"] == "v9"
    assert values["supported_sample_rates_msps"] == "30"
    for prefix in (
        "probe_script",
        "probe_test",
        "inherited_v10_probe_script",
        "inherited_v10_manifest",
        "candidate_source",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
