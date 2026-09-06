from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.starlink_pss_progress_probe_v2 as probe


def test_v2_identity_context_is_scoped_and_exception_safe() -> None:
    original_revisions = probe.hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS
    original_identity = probe.probe_v1.probe_v6._v4_candidate_identity
    original_validate = probe.probe_v1._validate_plan
    with pytest.raises(RuntimeError, match="test"):
        with probe._v6_candidate_identity():
            assert probe.hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS[-1] == "v6"
            assert probe.probe_v1.probe_v6._v4_candidate_identity is (
                probe._identity_passthrough
            )
            assert probe.probe_v1._validate_plan is probe._validate_plan
            raise RuntimeError("test")
    assert probe.hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS == original_revisions
    assert probe.probe_v1.probe_v6._v4_candidate_identity is original_identity
    assert probe.probe_v1._validate_plan is original_validate


def test_v2_delegates_all_operations_inside_v6_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[tuple[str, ...]] = []

    def fake(_args: object) -> dict[str, object]:
        observed.append(probe.hardware_probe_v2.SUPPORTED_SOURCE_REVISIONS)
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v1, "build_plan", fake)
    monkeypatch.setattr(probe.probe_v1, "execute_plan", fake)
    monkeypatch.setattr(probe.probe_v1, "verify_receipt", fake)
    assert probe.build_plan(object()) == {"ok": True}
    assert probe.execute_plan(object()) == {"ok": True}
    assert probe.verify_receipt(object()) == {"ok": True}
    assert observed == [("v2", "v3", "v4", "v5", "v6")] * 3


def test_v2_progress_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-progress-diagnostic-dnm-v2-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-progress-diagnostic-source"
    assert values["schema_version"] == "2"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["supported_candidate_revision"] == "v6"
    for prefix in (
        "host_probe",
        "host_test",
        "inherited_progress_probe",
        "inherited_progress_manifest",
        "hardware_probe_manifest",
        "candidate_source_manifest",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
