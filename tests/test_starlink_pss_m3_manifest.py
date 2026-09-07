from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m3-cabled-dnm-v1-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m3_source_manifest_is_offline_cabled_only_and_fail_closed() -> None:
    values = _values()
    assert values["schema"] == "plutosdr-fw.starlink-pss-m3-cabled-source"
    assert values["schema_version"] == "1"
    for field in (
        "do_not_merge",
        "do_not_release",
        "cabled_only",
        "qualifier_recomputes_all_metrics",
        "qualifier_requires_final_tx_shutdown",
    ):
        assert values[field] == "true"
    for field in (
        "persistent_flash_eligible",
        "hardware_accessed",
        "hardware_qualified",
        "transmitter_accessed",
        "receiver_accessed",
        "antenna_permitted",
        "over_the_air_authorized",
        "cabled_pss_detected_by_this_revision",
        "sss_detected",
        "frame_lock_claim",
    ):
        assert values[field] == "false"
    assert values["allocated_receiver_serial"] == (
        "104000bac4950008230026001b440a003a"
    )
    assert values["transmitter_serial"] == "unresolved-physical-fixture-input"
    assert values["supported_candidate_revision"] == "v7"
    assert values["minimum_effective_attenuation_db"] == "30"
    assert values["stimulus_sequence"] == (
        "positive-a,muted-negative,positive-b,final-mute"
    )
    assert values["waveform_sha256"] == (
        "00a3f70878d48ed0f3d60967c41b6c280954270bc69e7af4754439a05afa5829"
    )


def test_m3_source_manifest_binds_every_implementation_member() -> None:
    values = _values()
    prefixes = (
        "waveform_generator",
        "waveform_test",
        "monitor_v2",
        "monitor_v2_test",
        "campaign",
        "campaign_test",
        "manifest_test",
        "inherited_monitor_v1",
        "inherited_v7_probe",
        "candidate_source_manifest",
    )
    for prefix in prefixes:
        path = ROOT / values[f"{prefix}_path"]
        assert path.is_file()
        assert _sha256(path) == values[f"{prefix}_sha256"]
