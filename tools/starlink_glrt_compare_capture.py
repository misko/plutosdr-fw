#!/usr/bin/env python3
"""Compare retained GLR1 capture events with independently finalized host GLRT.

Read-only inputs. This neither opens a radio nor acquires the host detector.
Counter validation and file hashes are not substitutes for hardware/RF evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.starlink_glrt_abi import Event, Snapshot, require
from tools.starlink_glrt_replay import compare, digest, save

EVIDENCE = ("protocol.json", "identity.json", "initial_snapshot.txt", "baseline_snapshot.txt",
            "final_snapshot.txt", "blocks.json", "iq.ci16", "events.raw")


def compare_capture(capture: Path, host: Path):
    paths = [capture/name for name in (*EVIDENCE, "summary.json")]
    paths += [host/name for name in ("protocol.json", "summary.json", "blind-windows.jsonl")]
    before = {str(path): digest(path) for path in paths}
    summary = json.loads((capture/"summary.json").read_text())
    protocol = json.loads((capture/"protocol.json").read_text())
    evidence = EVIDENCE
    if protocol.get("prefill", False):
        evidence += ("prefill_snapshot.txt",)
        before[str(capture/"prefill_snapshot.txt")] = digest(capture/"prefill_snapshot.txt")
    require(summary["schema"] == protocol["schema"] == "starlink-glrt-iio-capture/v1",
            "unsupported capture schema")
    require(summary["status"] == "complete" and not summary["failures"] and
            summary["iq_prefix_attested"] and summary["event_transport_attested"],
            "capture is not completely attested")
    for name in evidence:
        require(summary.get("evidence_sha256", {}).get(name) == before[str(capture/name)],
                "capture evidence missing or changed: " + name)
    require(summary["iq_sha256"] == before[str(capture/"iq.ci16")] and
            summary["events_sha256"] == before[str(capture/"events.raw")], "raw capture hash mismatch")
    identity = json.loads((capture/"identity.json").read_text())
    for name in ("iq_context", "event_context"):
        require(identity[name]["hw_serial"] == protocol["serial"] and
                identity[name]["fw_version"] == protocol["firmware_version"],
                "capture identity differs from its request")
    radio = summary["radio_before"]
    require(radio == summary["radio_after"] and radio["tx_powerdown"] == 1 and
            radio["sample_rate_hz"] == protocol["source_rate"] and
            radio["rx_lo_hz"] == protocol["lo_hz"] and
            radio["rf_bandwidth_hz"] == protocol["bandwidth_hz"], "RF state is not the attested request")
    baseline = Snapshot.decode((capture/"baseline_snapshot.txt").read_text())
    final = Snapshot.decode((capture/"final_snapshot.txt").read_text())
    byte_count = (capture/"iq.ci16").stat().st_size
    final.require_iq_prefix(expected_visit=protocol["visit"], expected_rate=protocol["source_rate"],
                            received_bytes=byte_count, expected_samples=protocol["samples"])
    if protocol.get("prefill", False):
        prefill = Snapshot.decode((capture/"prefill_snapshot.txt").read_text())
        prefill.require_stopped_iq(expected_visit=protocol["visit"], expected_rate=protocol["source_rate"],
                                   expected_samples=protocol["samples"])
        require(prefill.words[:8] == final.words[:8], "prefill and final IQ endpoints/counts differ")
        require(protocol["samples"] <= 4*protocol["chunk_samples"], "prefill exceeds requested kernel buffers")
    require(summary["received_bytes"] == byte_count, "capture byte count differs from payload")
    require(list(final.words[57:61]) == [protocol["acquisition_q16"], protocol["threshold_q16"],
            protocol["margin_q16"], int(not protocol["decisions_off"])], "capture gates differ from request")
    blocks = json.loads((capture/"blocks.json").read_text())
    require(sum(block["bytes"] for block in blocks) == byte_count and
            all(block["bytes"] == 4*protocol["chunk_samples"] for block in blocks),
            "refill records differ from complete capture buffers")
    raw = (capture/"events.raw").read_bytes()
    require(len(raw) % 64 == 0, "partial event record")
    decoded = [Event.decode(raw[offset:offset+64]) for offset in range(0, len(raw), 64)]
    events = [event for event in decoded if event.visit == protocol["visit"]]
    require(len(events) == summary["event_records"] and
            len(decoded)-len(events) == summary["other_visit_event_records"], "event inventory differs")
    final.require_events(events, baseline=baseline)
    host_protocol = json.loads((host/"protocol.json").read_text())
    host_summary = json.loads((host/"summary.json").read_text())
    require(host_protocol["schema"] == "starlink-glrt-blind-host/v1" and
            host_summary["schema"] == host_protocol["schema"] and host_summary["samples"] == final.samples and
            host_protocol["fpga_seed_inputs"] == [] and
            host_protocol["edge"] == protocol["edge"] == "upper" and
            host_protocol["sample_rate_hz"] == 2500000 and
            host_protocol["calibration"]["center_hz"] == 0 and
            host_protocol["cfo_comparison_band_hz"] == [-100000, 100000],
            "host result is not the independently acquired comparison protocol")
    eligible, excluded = [], []
    for event in events:
        if not event.detected:
            continue
        support = event.observable_interval(final)
        reasons = []
        if support is None:
            reasons.append("complete GLRT time support is outside exported IQ")
        if abs(event.cfo_hz()) > 100000:
            reasons.append("FPGA CFO is outside the host acquisition comparison band")
        row = {"sequence": event.sequence, "epoch": event.epoch, "detected": True,
               "cfo_hz": float(event.cfo_hz()), "exact_q16": event.words[5], "control_q16": event.words[6]}
        if reasons:
            excluded.append({**row, "reasons": reasons})
        else:
            eligible.append(row)
    comparison = compare(host, capture/"iq.ci16", eligible, final.source_center(0), final.ratio)
    require(all(digest(Path(path)) == value for path, value in before.items()),
            "comparison input changed during evaluation")
    return {"schema": "starlink-glrt-capture-comparison/v1", "status": "complete",
            "input_sha256": before, "capture_serial": protocol["serial"],
            "firmware_version": protocol["firmware_version"], "source_rate_hz": final.source_rate,
            "output_rate_hz": 2500000, "visit": protocol["visit"], "samples": final.samples,
            "first_output_center_native_index": final.source_center(0),
            "fpga_event_records": len(events), "other_visit_event_records": len(decoded)-len(events),
            "comparable_fpga_positive_events": eligible, "unobservable_fpga_positive_events": excluded,
            "comparison": comparison,
            "agreement_observed": any(row["matches"] for row in comparison["fpga_positive_comparisons"]),
            "busy_rejections": final.u64(36), "pending_bits": final.words[61],
            "ddc_clipping_count": final.words[16], "hardware_accessed_by_comparator": False,
            "live_detector_qualified": False,
            "limitations": ["Engineering comparison tolerances: five 0.4 us output samples and 2 kHz circular CFO.",
                            "Unobservable events are retained separately from unmatched comparable positives.",
                            "Host supports overlap and are not independent false-alarm trials.",
                            "Capture-file attestation does not supply deployment, calibrated I/O, headroom or RF truth."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--host-blind", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_capture(args.capture, args.host_blind)
    save(args.output, result)
    print(json.dumps({"status": result["status"], "agreement_observed": result["agreement_observed"],
                      "unmatched_comparable_positives": result["comparison"]["unmatched_fpga_positives"],
                      "unobservable_positives": len(result["unobservable_fpga_positive_events"])}))


if __name__ == "__main__":
    main()
