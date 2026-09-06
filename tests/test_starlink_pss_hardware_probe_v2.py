from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

import scripts.starlink_pss_hardware_probe_v2 as probe


def _identity(path: Path, digit: str) -> dict[str, object]:
    return {"path": str(path.absolute()), "bytes": 100, "sha256": digit * 64}


def _plan(root: Path, revision: str) -> dict[str, object]:
    serial = probe.probe_v1.ALLOCATED_SERIAL
    return {
        "schema": probe.probe_v1.PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": "1" * 32,
        "created_at": "2026-09-06T20:00:00Z",
        "do_not_merge": True,
        "allowed_operation": "rx-only-candidate-measurement",
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": serial,
        "rate_msps": 15,
        "sample_rate_hz": 15_000_000,
        "rf_bandwidth_hz": 15_000_000,
        "runtime_target": "ad9363a-1r1t",
        "expected_firmware": (
            f"v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-{revision}"
        ),
        "ppu_repository": str((root / "ppu").absolute()),
        "ppu_source_commit": "2" * 40,
        "candidate_plan": _identity(root / "candidate.json", "3"),
        "operation_plan": _identity(root / "operation.json", "4"),
        "ram_receipt": _identity(root / "ram-receipt.json", "5"),
        "controller_timeout_ms": 5000,
        "confirmation_phrase": f"RUN STARLINK PSS CANDIDATE {serial} 15 MSPS",
        "receipt_path": str((root / "probe-receipt.json").absolute()),
    }


@pytest.mark.parametrize("revision", ["v2", "v3"])
def test_revision_aware_plan_gate_accepts_locked_candidates(
    tmp_path: Path, revision: str
) -> None:
    probe._validate_plan(_plan(tmp_path, revision))


def test_revision_aware_plan_gate_rejects_unlocked_revision(tmp_path: Path) -> None:
    with pytest.raises(probe.ProbeError, match="firmware revision"):
        probe._validate_plan(_plan(tmp_path, "v4"))


def test_revision_aware_probe_manifest_is_offline_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v2-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "2"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["allocated_radio_serial"] == probe.probe_v1.ALLOCATED_SERIAL
    assert values["supported_candidate_revisions"] == "v2,v3"
    source_ref = values["firmware_source_ref"]
    for prefix in (
        "candidate_source",
        "probe_script",
        "probe_test",
        "inherited_probe_script",
        "inherited_probe_test",
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
