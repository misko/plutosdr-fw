from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m3-cabled-dnm-v3-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m3_runner_manifest_preserves_rx_only_and_separate_bench_tx() -> None:
    values = _values()
    assert values["schema"] == "plutosdr-fw.starlink-pss-m3-cabled-source"
    assert values["schema_version"] == "3"
    for field in (
        "do_not_merge",
        "do_not_release",
        "experimental_receiver_rx_only",
        "bench_transmitter_is_separate_radio",
        "cabled_only",
        "deterministic_receiver_context_close_required",
        "suppressed_context_close_failure_is_fatal",
        "runner_receipt_required",
    ):
        assert values[field] == "true"
    for field in (
        "persistent_flash_eligible",
        "persistent_write",
        "hardware_accessed",
        "hardware_qualified",
        "antenna_permitted",
        "over_the_air_authorized",
        "cabled_pss_detected_by_this_revision",
        "sss_detected",
        "frame_lock_claim",
    ):
        assert values[field] == "false"
    assert values["allocated_receiver_serial"] == ("104000bac4950008230026001b440a003a")
    assert values["separate_bench_transmitter_serial"] == (
        "1040007c4a94000211000b009186843ef2"
    )
    assert values["receiver_operational_entrypoint"] == (
        "scripts/starlink_pss_monitor_probe_v3.py"
    )
    assert values["campaign_operational_entrypoint"] == (
        "scripts/starlink_pss_m3_execute_v2.py"
    )


def test_m3_runner_manifest_binds_all_versioned_sources() -> None:
    values = _values()
    prefixes = (
        "receiver_monitor_v3",
        "receiver_monitor_v3_test",
        "campaign_runner_v2",
        "campaign_runner_v2_test",
        "runner_manifest_test",
        "inherited_m3_v2_manifest",
    )
    for prefix in prefixes:
        path = ROOT / values[f"{prefix}_path"]
        assert path.is_file()
        assert _sha256(path) == values[f"{prefix}_sha256"]
