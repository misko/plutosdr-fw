from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m3-cabled-dnm-v2-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m3_executor_manifest_is_cabled_only_fail_closed_and_dnm() -> None:
    values = _values()
    assert values["schema"] == "plutosdr-fw.starlink-pss-m3-cabled-source"
    assert values["schema_version"] == "2"
    for field in (
        "do_not_merge",
        "do_not_release",
        "cabled_only",
        "requires_explicit_confirmation",
        "requires_shared_ppu_serial_lock",
        "rejects_existing_usb_openers",
        "final_tx_mute_unconditional",
        "deterministic_iio_context_close",
    ):
        assert values[field] == "true"
    for field in (
        "persistent_flash_eligible",
        "persistent_write",
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
    assert values["allocated_receiver_serial"] == ("104000bac4950008230026001b440a003a")
    assert values["allocated_transmitter_serial"] == (
        "1040007c4a94000211000b009186843ef2"
    )
    assert values["allocated_transmitter_topology"] == "3-11"
    assert values["fixture_confirmation_state"] == "pending-operator-attestation"
    assert values["minimum_effective_attenuation_db"] == "30"
    assert values["recommended_effective_attenuation_db"] == "40"
    assert values["stimulus_sequence"] == (
        "positive-a,muted-negative,positive-b,final-mute"
    )


def test_m3_executor_manifest_binds_all_new_and_inherited_sources() -> None:
    values = _values()
    prefixes = (
        "transmitter_primitive",
        "transmitter_primitive_test",
        "execution_orchestrator",
        "execution_orchestrator_test",
        "executor_manifest_test",
        "inherited_m3_source_manifest",
        "inherited_campaign",
        "inherited_monitor_v2",
    )
    for prefix in prefixes:
        path = ROOT / values[f"{prefix}_path"]
        assert path.is_file()
        assert _sha256(path) == values[f"{prefix}_sha256"]
