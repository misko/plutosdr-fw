from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.starlink_pss_progress_probe_v3 as probe


def test_v3_execute_scopes_measurement_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    original = probe.probe_v2.probe_v1._execute_measurement
    observed: list[object] = []

    def fake(_args: object) -> dict[str, bool]:
        observed.append(probe.probe_v2.probe_v1._execute_measurement)
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v2, "execute_plan", fake)
    assert probe.execute_plan(object()) == {"ok": True}
    assert observed == [probe._execute_measurement]
    assert probe.probe_v2.probe_v1._execute_measurement is original


def test_v3_execute_restores_measurement_extension_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = probe.probe_v2.probe_v1._execute_measurement

    def fail(_args: object) -> dict[str, bool]:
        raise RuntimeError("test")

    monkeypatch.setattr(probe.probe_v2, "execute_plan", fail)
    with pytest.raises(RuntimeError, match="test"):
        probe.execute_plan(object())
    assert probe.probe_v2.probe_v1._execute_measurement is original


def test_v3_source_requests_complete_snapshot_under_existing_route() -> None:
    source = Path(probe.__file__).read_text()
    assert 'measurement["controller_snapshot_after_diagnostic"]' in source
    assert "snapshot --timeout-ms {base['controller_timeout_ms']}" in source
    assert "_remote_json(" in source


def test_v3_progress_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-progress-diagnostic-dnm-v3-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-progress-diagnostic-source"
    assert values["schema_version"] == "3"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["supported_candidate_revision"] == "v6"
    assert values["full_snapshot_appended"] == "true"
    for prefix in (
        "host_probe",
        "host_test",
        "inherited_progress_probe",
        "inherited_progress_manifest",
        "candidate_source_manifest",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
