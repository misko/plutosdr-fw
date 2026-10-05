"""Validate and compact issue-123 hardware receipts without opening a radio."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import zstandard


def compact(path):
    document = json.loads(path.read_text())
    return {k: document[k] for k in (
        "serial", "host", "boot_identity_verified", "dfu_sha256", "setup",
        "terminal", "settings_restored", "ordinary_capture_after", "elapsed_seconds"
    )}


def archive(summary):
    directory = Path(summary["iq_archive"])
    manifest = json.loads((directory / "manifest.json").read_text())
    terminal = manifest["terminal"]
    assert terminal["state"] == 1 and terminal["error"] == 0
    assert terminal["flags"] & 1
    assert terminal["planned"] == terminal["delivered"] == len(manifest["visits"])
    assert not any(terminal[k] for k in ("skipped", "invalid", "cancelled"))
    setup = manifest["setup"]
    assert setup == summary["setup"]
    assert setup["duration_ms"] == 300000 and setup["rx_mask"] == 3
    assert setup["protocol_version"] == 3
    rate = setup["source_rate_hz"]
    previous_end, total = None, 0
    for number, visit in enumerate(manifest["visits"]):
        record, iq = visit["record"], visit["iq"]
        assert record["visit"] == number and record["result"] == 1
        assert record["session"] == setup["session"]
        assert record["generation"] == setup["generation"]
        assert record["flags"] & 1 and record["profile_crc32"]
        assert record["source_rate_hz"] == record["analog_bandwidth_hz"] == rate
        assert record["frequency_hz"] in [t["frequency_hz"] for t in setup["targets"]]
        assert record["valid_end"] - record["valid_start"] == rate * 120 // 1000
        assert record["valid_start"] >= record["transition_after"]
        assert record["valid_start"] >= record["selection_counter"]
        if record["transition_before"] != record["transition_after"]:
            assert record["valid_start"] >= record["selection_counter"] + rate * 20 // 1000
        if previous_end is not None:
            assert record["transition_before"] >= previous_end
        previous_end = record["valid_end"]
        assert record["iq_bytes"] == iq["uncompressed_bytes"] == rate * 120 // 1000 * 8
        assert (directory / iq["relative_path"]).stat().st_size == iq["compressed_bytes"]
        total += record["iq_bytes"]
    assert total == terminal["iq_bytes"] == manifest["uncompressed_bytes"]
    checked = sorted({0, len(manifest["visits"]) // 2, len(manifest["visits"]) - 1})
    for number in checked:
        iq = manifest["visits"][number]["iq"]
        payload = (directory / iq["relative_path"]).read_bytes()
        assert "sha256:" + hashlib.sha256(payload).hexdigest() == iq["compressed_sha256"]
        raw = zstandard.ZstdDecompressor().decompress(payload)
        assert len(raw) == iq["uncompressed_bytes"]
        assert "sha256:" + hashlib.sha256(raw).hexdigest() == iq["uncompressed_sha256"]
    restoration = summary["restoration"]
    assert restoration["fastlock_inactive"]
    assert restoration["observed_kernel_buffers"] == restoration["expected_kernel_buffers"]
    # Automatic gain can change during readback; manual settings must match exactly.
    for key in ("sample_rate_hz", "bandwidth_hz", "center_frequency_hz", "channels", "gain_modes"):
        assert restoration["observed"][key] == restoration["expected"][key]
    assert summary["run"]["gate"]["passed"]
    return {
        "rate_hz": rate, "selected_edge": summary["selected_edge"], "setup": setup,
        "terminal": terminal, "metrics": summary["run"]["metrics"],
        "restoration": restoration, "gate": summary["run"]["gate"],
        "archive_manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(),
        "iq_bytes": total, "iq_sha256": manifest["uncompressed_sha256"],
        "all_visit_geometry_verified": True, "decoded_hash_checked_visits": checked,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    binding = json.loads((root / "fixed/artifact.json").read_text())
    cells = [archive(json.loads(p.read_text())) for p in sorted(
        (root / "production-fixed-evidence").glob("adaptive-seven*.json"))]
    assert len(cells) == 4
    assert sorted((c["rate_hz"], c["selected_edge"]) for c in cells) == [
        (2500000, "upper"), (10000000, "lower"), (10000000, "upper"), (10000000, "upper")]
    canaries = [compact(root / name / "report.json") for name in (
        "fixed-canary-10m", "fixed-canary-cancel", "fixed-canary-dma-fault")]
    for cell in canaries:
        assert cell["dfu_sha256"] == binding["dfu_sha256"]
        assert cell["boot_identity_verified"] and cell["settings_restored"]
        assert cell["ordinary_capture_after"]["bytes"] == 32768
    args.output.write_text(json.dumps({
        "schema": "plutosdr-fw.issue123-qualification/v1",
        "firmware": binding["firmware"], "dfu_sha256": binding["dfu_sha256"],
        "serial": "1040005e0b100007100010000bf33a5d4d", "host": "192.168.1.20",
        "production": cells, "canary": canaries,
    }, indent=2) + "\n")
    print(f"PASS: {len(cells)} five-minute production cells, three canary recovery cells")


if __name__ == "__main__":
    main()
