from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.starlink_pss_hardware_probe_v4 as probe


class _Attribute:
    def __init__(self, value: str) -> None:
        self.stored = value
        self.writes: list[str] = []

    @property
    def value(self) -> str:
        return self.stored

    @value.setter
    def value(self, value: str) -> None:
        self.writes.append(value)
        self.stored = value


def test_equal_numeric_capture_rate_is_not_rewritten() -> None:
    raw = _Attribute("15000000")
    wrapped = probe._IdempotentNumericAttribute(raw)
    wrapped.value = "15000000.0"
    assert wrapped.value == "15000000"
    assert raw.writes == []


def test_different_capture_rate_is_written() -> None:
    raw = _Attribute("1875000")
    wrapped = probe._IdempotentNumericAttribute(raw)
    wrapped.value = "15000000"
    assert wrapped.value == "15000000"
    assert raw.writes == ["15000000"]


def test_non_numeric_capture_value_preserves_fail_closed_write() -> None:
    raw = _Attribute("unknown")
    wrapped = probe._IdempotentNumericAttribute(raw)
    wrapped.value = "15000000"
    assert raw.writes == ["15000000"]


def test_source_locked_attribute_wrap_is_narrow(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _Attribute("15000000")
    monkeypatch.setattr(probe, "_attribute_v1", lambda *args, **kwargs: raw)
    assert isinstance(
        probe._idempotent_source_locked_attribute(
            object(), "sampling_frequency", label="capture RX"
        ),
        probe._IdempotentNumericAttribute,
    )
    assert (
        probe._idempotent_source_locked_attribute(
            object(), "rf_bandwidth", label="PHY RX"
        )
        is raw
    )


def test_source_locked_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v4-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "4"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["idempotent_capture_rate_write"] == "exact-readback-only"
    for prefix in (
        "candidate_source",
        "probe_script",
        "probe_test",
        "inherited_v3_probe_script",
        "inherited_v3_probe_test",
        "inherited_v3_manifest",
        "controller_readme",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
