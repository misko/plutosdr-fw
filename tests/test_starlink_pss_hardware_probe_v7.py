from __future__ import annotations

import hashlib
from pathlib import Path

import scripts.starlink_pss_hardware_probe_v7 as probe


def test_v7_admits_v6_without_dropping_earlier_supported_candidates() -> None:
    original = probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
    with probe._v6_candidate_identity():
        assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == (
            "v2",
            "v3",
            "v4",
            "v5",
            "v6",
        )
        assert probe.probe_v2._expected_versions(15) == {
            "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v2",
            "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v3",
            "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v4",
            "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v5",
            "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v6",
        }
    assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == original


def test_v7_restores_identity_gate_after_exception() -> None:
    original = probe.probe_v2.SUPPORTED_SOURCE_REVISIONS
    try:
        with probe._v6_candidate_identity():
            raise RuntimeError("test")
    except RuntimeError:
        pass
    assert probe.probe_v2.SUPPORTED_SOURCE_REVISIONS == original


def test_v7_reuses_dependency_safe_measurement_path() -> None:
    assert probe.probe_v5.execute_plan is not probe.execute_plan
    assert "dependency-safe v5 measurement" in (probe.execute_plan.__doc__ or "")


def test_v7_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v7-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "7"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["supported_candidate_revisions"] == "v2,v3,v4,v5,v6"
    assert values["candidate_profile"] == "acquisition-only"
    for prefix in (
        "candidate_source",
        "probe_script",
        "probe_test",
        "inherited_v5_probe_script",
        "inherited_v5_probe_test",
        "inherited_v6_manifest",
        "controller_readme",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
