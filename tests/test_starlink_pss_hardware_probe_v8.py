from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.starlink_pss_hardware_probe_v8 as probe


def test_v8_scopes_ad9361_1r1t_identity_and_restores_it() -> None:
    probe_v1 = probe.probe_v7.probe_v5.probe_v1
    original = (probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL)

    with probe._ad9361_1r1t_identity():
        assert probe_v1.RUNTIME_TARGET == "ad9361-1r1t"
        assert probe_v1.EXPECTED_MODEL == (
            "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
        )

    assert (probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL) == original


def test_v8_restores_identity_after_exception() -> None:
    probe_v1 = probe.probe_v7.probe_v5.probe_v1
    original = (probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL)

    with pytest.raises(RuntimeError, match="test"), probe._ad9361_1r1t_identity():
        raise RuntimeError("test")

    assert (probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL) == original


def test_v8_wraps_v7_without_changing_v6_candidate_admission(monkeypatch) -> None:
    observed: list[tuple[str, str]] = []

    def fake(_args: object) -> dict[str, bool]:
        probe_v1 = probe.probe_v7.probe_v5.probe_v1
        observed.append((probe_v1.RUNTIME_TARGET, probe_v1.EXPECTED_MODEL))
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v7, "build_plan", fake)
    assert probe.build_plan(object()) == {"ok": True}
    assert observed == [
        ("ad9361-1r1t", "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)")
    ]


def test_v8_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v8-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "8"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["candidate_profile"] == "acquisition-only"
    for prefix in (
        "probe_script",
        "probe_test",
        "inherited_v7_probe_script",
        "inherited_v7_manifest",
        "candidate_source",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
