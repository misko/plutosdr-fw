from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_hardware_probe_v13 as probe


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
        "starlink_pss_profile_rate_gate_msps: 60\n"
        "starlink_pss_60_ddc_stages: 2\n"
        "starlink_pss_clean_start_scheduler_gaps: 0\n"
        "starlink_pss_cold_start_absolute_index_load: true\n"
        "starlink_pss_real_gap_fail_closed: true\n"
        "starlink_pss_abi_60: 1.4\n"
        "starlink_pss_60_ddc_observation_counter_bits: 64\n"
        "starlink_pss_60_ddc_counter_read_policy: high-low-high-coherent\n"
        "starlink_pss_group_delay_60_source_samples: 21\n"
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


def test_v13_profile_attestation_accepts_exact_v10_candidate(tmp_path: Path) -> None:
    probe._require_acquisition_only_profile(_profile_handoff(tmp_path))


def test_v13_profile_attestation_rejects_wrong_rate(tmp_path: Path) -> None:
    handoff = _profile_handoff(tmp_path)
    index = Path(handoff.candidate.artifact_index.path)
    value = json.loads(index.read_text())
    value["rate_msps"] = 30
    _write_private(index, value)
    handoff.candidate.artifact_index.bytes = index.stat().st_size
    handoff.candidate.artifact_index.sha256 = hashlib.sha256(index.read_bytes()).hexdigest()
    with pytest.raises(probe.ProbeError, match="60 MS/s v10 profile"):
        probe._require_acquisition_only_profile(handoff)


def test_v13_contract_scopes_identity_revision_and_loader(monkeypatch) -> None:
    original_identity = (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL)
    original_revisions = probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
    checked: list[object] = []
    fake_handoff = SimpleNamespace(candidate=object())
    monkeypatch.setattr(probe.probe_v1, "_load_handoff", lambda *a, **k: fake_handoff)
    monkeypatch.setattr(probe, "_require_acquisition_only_profile", checked.append)
    patched_original = probe.probe_v1._load_handoff
    with probe._ad9361_v10_acquisition_only_contract():
        assert probe.probe_v1.RUNTIME_TARGET == "ad9361-1r1t"
        assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS[-1] == "v10"
        assert probe.probe_v1._load_handoff() is fake_handoff
        assert checked == [fake_handoff]
    assert probe.probe_v1._load_handoff is patched_original
    assert (probe.probe_v1.RUNTIME_TARGET, probe.probe_v1.EXPECTED_MODEL) == original_identity
    assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == original_revisions


def test_v13_execute_scopes_cleanup_measurement(monkeypatch) -> None:
    original = probe.probe_v5._measure
    observed: list[object] = []
    monkeypatch.setattr(
        probe.probe_v5,
        "execute_plan",
        lambda _args: observed.append(probe.probe_v5._measure) or {"ok": True},
    )
    monkeypatch.setattr(probe, "_require_acquisition_only_profile", lambda _value: None)
    assert probe.execute_plan(object()) == {"ok": True}
    assert observed == [probe.probe_v12._measure]
    assert probe.probe_v5._measure is original


def test_v13_probe_manifest_is_offline_dnm_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v13-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema_version"] == "13"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["supported_candidate_revision"] == "v10"
    assert values["supported_sample_rates_msps"] == "60"
    assert values["required_psma_abi"] == "1.4"
    assert values["required_ddc_observation_counter_bits"] == "64"
    for prefix in (
        "probe_script",
        "probe_test",
        "inherited_v12_probe_script",
        "inherited_v12_manifest",
        "candidate_source",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
