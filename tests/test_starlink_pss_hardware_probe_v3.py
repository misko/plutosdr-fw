from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_hardware_probe_v3 as probe


def _target(*, serial: str = "radio", device: int = 10, topology: str = "5-2") -> object:
    return SimpleNamespace(
        serial=serial,
        topology=topology,
        sysfs_path=Path("/sys/bus/usb/devices") / topology,
        vendor_id="0456",
        product_id="b673",
        bus_number=5,
        device_number=device,
        network_interface="enxradio",
        source_ipv4="192.168.2.10",
    )


class _Backend:
    def __init__(self, *targets: object) -> None:
        self.targets = targets

    def _runtime_targets(self) -> tuple[object, ...]:
        return self.targets


def test_post_ram_resolution_accepts_only_transient_device_number_change() -> None:
    planned = _target(device=10)
    live = _target(device=12)
    assert probe._resolve_live_target(_Backend(live), planned) is live


@pytest.mark.parametrize(
    "other",
    [
        _target(serial="other", device=12),
        _target(device=12, topology="5-3"),
    ],
)
def test_post_ram_resolution_rejects_wrong_stable_identity(other: object) -> None:
    with pytest.raises(probe.ProbeError, match="not one unique match"):
        probe._resolve_live_target(_Backend(other), _target())


def test_post_ram_resolution_rejects_ambiguous_matches() -> None:
    planned = _target()
    with pytest.raises(probe.ProbeError, match="not one unique match"):
        probe._resolve_live_target(_Backend(_target(device=11), _target(device=12)), planned)


def test_post_ram_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v3-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "3"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["allocated_radio_serial"] == probe.probe_v1.ALLOCATED_SERIAL
    assert values["post_ram_usb_reenumeration"] == "exact-stable-identity-only"
    source_ref = values["firmware_source_ref"]
    for prefix in (
        "candidate_source",
        "probe_script",
        "probe_test",
        "inherited_v2_probe_script",
        "inherited_v2_probe_test",
        "inherited_v2_manifest",
        "controller_readme",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        frozen = subprocess.run(
            ["git", "show", f"{source_ref}:{member.relative_to(root)}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(frozen).hexdigest() == values[
            f"{prefix}_sha256"
        ]
