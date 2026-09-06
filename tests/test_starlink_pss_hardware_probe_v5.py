from __future__ import annotations

import hashlib
from pathlib import Path

import scripts.starlink_pss_hardware_probe_v5 as probe


class _Attribute:
    def __init__(self, value: int) -> None:
        self.value = str(value)


class _Channel:
    def __init__(self, **values: int) -> None:
        self.attrs = {name: _Attribute(value) for name, value in values.items()}


def test_dependency_graph_is_snapshotted_before_parent_clock_write(monkeypatch) -> None:
    phy = _Channel(sampling_frequency=30_000_000, rf_bandwidth=18_000_000)
    capture = _Channel(sampling_frequency=3_750_000)

    def write(channel, name, requested, tolerance, *, label):
        del tolerance, label
        channel.attrs[name].value = str(requested)
        if channel is phy and name == "sampling_frequency":
            capture.attrs["sampling_frequency"].value = str(requested // 8)
        return requested

    monkeypatch.setattr(probe.probe_v1, "_write_numeric", write)
    before, originals, selected = probe._snapshot_and_apply(
        (
            (phy, "sampling_frequency", 15_000_000, "PHY RX"),
            (capture, "sampling_frequency", 15_000_000, "capture RX"),
            (phy, "rf_bandwidth", 15_000_000, "PHY RX"),
        )
    )
    assert before == {
        "phy_rx_sampling_frequency": "30000000",
        "capture_rx_sampling_frequency": "3750000",
        "phy_rx_rf_bandwidth": "18000000",
    }
    assert originals[1][2] == "3750000"
    assert selected["capture_rx_sampling_frequency"] == 15_000_000


def test_dependency_safe_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v5-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "5"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["dependent_attribute_snapshot"] == "before-any-write"
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
