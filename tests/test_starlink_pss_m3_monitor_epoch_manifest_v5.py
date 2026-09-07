from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m3-cabled-dnm-v5-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m3_v5_manifest_keeps_the_two_radio_cabled_scope() -> None:
    values = _values()
    assert values["schema"] == "plutosdr-fw.starlink-pss-m3-cabled-source"
    assert values["schema_version"] == "5"
    for field in (
        "do_not_merge",
        "do_not_release",
        "experimental_receiver_rx_only",
        "separate_bench_transmitter",
        "cabled_only",
        "antenna_absent",
        "over_the_air_transmission",
        "strict_in_observation_fault_deltas",
        "transmitter_final_mute_verified",
        "receiver_recovery_verified",
        "cabled_pss_detected",
    ):
        expected = "false" if field in {"over_the_air_transmission"} else "true"
        assert values[field] == expected
    assert values["allocated_receiver_serial"] == (
        "104000bac4950008230026001b440a003a"
    )
    assert values["separate_bench_transmitter_serial"] == (
        "1040007c4a94000211000b009186843ef2"
    )
    assert values["sss_detected"] == "false"
    assert values["frame_lock_claim"] == "false"


def test_m3_v5_manifest_binds_the_versioned_monitor_sources() -> None:
    values = _values()
    for prefix in (
        "monitor_v2_source",
        "monitor_v2_native_test",
        "monitor_makefile",
        "manifest_test",
        "inherited_m3_v4_manifest",
    ):
        path = ROOT / values[f"{prefix}_path"]
        assert path.is_file()
        assert _sha256(path) == values[f"{prefix}_sha256"]
    assert values["native_monitor_v2_test_verdict"] == "PASS"
    assert values["hardware_campaign_verdict"] == (
        "PASS_M3_CABLED_PSS_ACQUISITION_ONLY"
    )
