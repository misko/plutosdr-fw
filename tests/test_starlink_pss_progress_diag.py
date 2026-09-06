from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import scripts.starlink_pss_progress_probe_v1 as probe

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/starlink_pssctl"


def test_progress_diagnostic_builds_and_is_explicitly_non_authorizing() -> None:
    subprocess.run(
        ["make", "-C", str(SOURCE), "build/starlink_pss_acqctl-host"],
        check=True,
    )
    help_text = subprocess.run(
        [str(SOURCE / "build/starlink_pss_acqctl-host"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    source = (SOURCE / "starlink_pss_acqctl.c").read_text()
    assert "progress [--timeout-ms N]" in help_text
    assert "datapath_progress_diagnostic_only" in source
    assert '\\"pss_detected\\": false' in source
    assert '\\"frame_lock_claim\\": false' in source
    assert "AD9361_ADC_GPIO_IN_OFFSET 0x00b8U" in source
    assert "pss_map_set_enabled(io, false, true" in source


def test_progress_probe_accepts_only_the_static_arm_binary() -> None:
    subprocess.run(
        ["make", "-C", str(SOURCE), "build/starlink_pss_progress_diag"],
        check=True,
    )
    binary = SOURCE / "build/starlink_pss_progress_diag"
    identity, payload = probe._binary_identity(binary)
    assert identity["path"] == str(binary.absolute())
    assert identity["bytes"] == len(payload)
    assert identity["bytes"] < probe.MAXIMUM_BINARY_BYTES
    assert len(identity["sha256"]) == 64


def test_progress_probe_is_ephemeral_and_receipt_bound() -> None:
    source = (ROOT / "scripts/starlink_pss_progress_probe_v1.py").read_text()
    assert 'REMOTE_PREFIX = "/tmp/starlink_pss_progress_diag"' in source
    assert "test ! -e {remote}" in source
    assert 'remote_command=f"rm -f {remote} && test ! -e {remote}"' in source
    assert '"persistent_write": False' in source
    assert '"recovery_required": True' in source


def test_progress_diagnostic_manifest_is_offline_and_byte_exact() -> None:
    manifest = ROOT / "manifests/starlink-pss-progress-diagnostic-dnm-v1-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-progress-diagnostic-source"
    assert values["schema_version"] == "1"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    for prefix in (
        "controller",
        "acquisition_library",
        "acquisition_header",
        "controller_readme",
        "controller_makefile",
        "host_probe",
        "host_test",
        "inherited_probe_manifest",
        "candidate_source_manifest",
    ):
        member = ROOT / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
