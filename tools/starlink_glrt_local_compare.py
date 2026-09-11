"""Read-only GLA1 capture attestation and independent same-window comparison.

Prepare an IQ-only host plan before running the separate numerical oracle.
No radio, host acquisition implementation or FPGA timing/CFO seeds are imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .starlink_glrt_abi import require
from .starlink_glrt_local_abi import (
    PERIOD,
    RATE,
    WINDOW,
    LocalEvent,
    LocalIQSnapshot,
    LocalSearchSnapshot,
    LocalSourceClosure,
    attest_capture,
)

CONFIG_SHA256 = "5babe61f9fed681854a90fdcc3f1c7baff784265529220f04190bd5e73b47146"
LOCAL_PROFILE = {"name": "gla1-upper-local-v1", "period_samples": PERIOD,
                 "window_samples": WINDOW, "epochs": 3333, "coarse_cfo_bins": 11,
                 "verify_minimum_q16": 5243, "margin_minimum_q16": 2622,
                 "minimum_frame_support": 2, "alias_separation_q16": 656,
                 "cfo_unit_hz": 100, "thresholds": "fixed in pinned FPGA image"}
POLICY = {"maximum_epoch_distance_samples": 2, "maximum_cfo_distance_hz": 80000,
          "minimum_supported_window_recovery": .95, "minimum_positive_windows": 20,
          "minimum_positive_episodes": 3, "episode_gap_samples": 10*RATE,
          "additional_local_detections_require_review": True}
EVIDENCE = ("protocol.json", "identity.json", "initial_snapshot.txt", "baseline_snapshot.txt",
            "final_snapshot.txt", "blocks.json", "iq.ci16", "events.raw", "extension_abi.txt",
            "baseline_extension_snapshot.txt", "final_extension_snapshot.txt",
            "baseline_local_search_snapshot.txt", "final_local_search_snapshot.txt")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def load_capture(capture):
    capture = Path(capture)
    hashes = {name: digest(capture/name) for name in (*EVIDENCE, "summary.json")}
    summary, protocol = load(capture/"summary.json"), load(capture/"protocol.json")
    require(summary["schema"] == protocol["schema"] == "starlink-glrt-local-iio-capture/v1",
            "not a GLA1 capture")
    require(summary["status"] == "complete" and not summary["failures"] and
            summary["iq_prefix_attested"] and summary["event_transport_attested"] and
            summary["finite_detector_closure_attested"], "capture was not completely attested")
    require(all(summary["evidence_sha256"].get(name) == hashes[name] for name in EVIDENCE),
            "capture evidence changed or missing")
    require(summary["iq_sha256"] == hashes["iq.ci16"] and summary["events_sha256"] == hashes["events.raw"],
            "raw capture digest differs")
    require((capture/"extension_abi.txt").read_text().strip() == summary["extension_abi"] == "GLA1-1.0",
            "GLA1 extension differs")
    require(protocol["source_rate"] == RATE and protocol["edge"] == "upper" and
            protocol["local_search"] is True and protocol["closure_extension_required"] is True and
            protocol["detector_profile"] == LOCAL_PROFILE, "local profile differs")
    identity = load(capture/"identity.json")
    for key in ("iq_context", "event_context"):
        require(identity[key]["hw_serial"] == protocol["serial"] and
                identity[key]["fw_version"] == protocol["firmware_version"], "receiver identity differs")
    radio = summary["radio_before"]
    require(radio == summary["radio_after"] and radio["sample_rate_hz"] == RATE and
            radio["rx_lo_hz"] == protocol["lo_hz"] and radio["rf_bandwidth_hz"] == protocol["bandwidth_hz"]
            and radio["tx_powerdown"] == 1, "radio configuration differs")
    final = LocalIQSnapshot.decode((capture/"final_snapshot.txt").read_text())
    baseline = LocalIQSnapshot.decode((capture/"baseline_snapshot.txt").read_text())
    raw = (capture/"events.raw").read_bytes()
    require(len(raw) % 64 == 0, "partial local record")
    decoded = [LocalEvent.decode(raw[n:n+64]) for n in range(0, len(raw), 64)]
    events = [event for event in decoded if event.visit == protocol["visit"]]
    require(len(events) == summary["event_records"] and
            len(decoded)-len(events) == summary["other_visit_event_records"], "record inventory differs")
    byte_count = (capture/"iq.ci16").stat().st_size
    final.require_iq_prefix(expected_visit=protocol["visit"], expected_rate=RATE,
                            expected_samples=protocol["samples"], received_bytes=byte_count)
    require(summary["received_bytes"] == byte_count, "received byte count differs")
    blocks = load(capture/"blocks.json")
    require(sum(b["bytes"] for b in blocks) == byte_count and
            all(b["bytes"] == 4*protocol["chunk_samples"] for b in blocks), "IQ block inventory differs")
    kwargs = {}
    for name, filename, cls in (
        ("source", "final_extension_snapshot.txt", LocalSourceClosure),
        ("source_baseline", "baseline_extension_snapshot.txt", LocalSourceClosure),
        ("search", "final_local_search_snapshot.txt", LocalSearchSnapshot),
        ("search_baseline", "baseline_local_search_snapshot.txt", LocalSearchSnapshot),
    ):
        kwargs[name] = cls.decode((capture/filename).read_text())
    accounting = attest_capture(final=final, baseline=baseline, events=events, received_bytes=byte_count, **kwargs)
    require(accounting == summary["finite_detector_closure"], "closure summary differs from raw evidence")
    require(all(digest(capture/name) == sha for name, sha in hashes.items()), "capture changed while reading")
    return {"protocol": protocol, "hashes": hashes, "accounting": accounting, "events": events}


def plan_for(capture):
    """Every complete cadence window, without inspecting local detections."""
    return _plan_for_data(load_capture(capture))


def _plan_for_data(data):
    accounting = data["accounting"]
    return {"schema": "gla1-independent-host-plan/v1", "capture_summary_sha256": data["hashes"]["summary.json"],
            "iq_sha256": data["hashes"]["iq.ci16"], "samples": accounting["samples"], "sample_rate_hz": RATE,
            "edge": "upper", "window_samples": WINDOW, "period_samples": PERIOD,
            "source_first_index": accounting["first_source_index"], "fpga_seed_inputs": [],
            "window_offsets": list(range(0, max(0, accounting["samples"]-WINDOW+1), PERIOD)),
            "host_config_sha256": CONFIG_SHA256, "comparison_policy": POLICY}


def compare_capture(capture, plan_path, host):
    capture, host = Path(capture), Path(host)
    plan = load(plan_path)
    data = load_capture(capture)
    require(plan == _plan_for_data(data), "plan does not match the complete capture and frozen policy")
    inputs = {str(Path(plan_path)): digest(plan_path)}
    inputs.update({str(host/name): digest(host/name) for name in ("protocol.json", "summary.json", "windows.jsonl")})
    protocol, summary = load(host/"protocol.json"), load(host/"summary.json")
    require(protocol["schema"] == summary["schema"] == "gla1-independent-host-replay/v1" and
            summary["status"] == "complete" and protocol["fpga_seed_inputs"] == [], "host replay incomplete or seeded")
    require(protocol["plan_sha256"] == inputs[str(Path(plan_path))] and
            summary["protocol_sha256"] == inputs[str(host/"protocol.json")] and
            summary["records_sha256"] == inputs[str(host/"windows.jsonl")] and
            protocol["iq_sha256"] == summary["iq_sha256"] == plan["iq_sha256"], "host input/output digest differs")
    require(canonical_digest(protocol["config"]) == plan["host_config_sha256"] and
            protocol["frequency_center_hz"] == 0, "host configuration differs")
    rows = [json.loads(line) for line in (host/"windows.jsonl").read_text().splitlines()]
    require(len(rows) == summary["window_count"] == len(plan["window_offsets"]), "host window count differs")
    decisions = {event.first: event for event in data["events"] if event.decision}
    comparisons, outside = [], []
    host_positive_offsets = []
    with (capture/"iq.ci16").open("rb") as stream:
        for offset, row in zip(plan["window_offsets"], rows, strict=True):
            require(type(row["sample_offset"]) is int and row["sample_offset"] == offset and
                    row["sample_count"] == WINDOW and type(row["supported"]) is bool,
                    "host window reordered or invalid")
            stream.seek(offset*4)
            raw = stream.read(WINDOW*4)
            require(hashlib.sha256(raw).hexdigest() == row["iq_sha256"], "host searched different IQ")
            candidates = row["candidates"]
            require(isinstance(candidates, list) and len(candidates) <= 8 and
                    row["supported"] == bool(candidates and not row["reasons"]), "host verdict inconsistent")
            for c in candidates:
                require(type(c["refined_epoch_sample"]) is int and 0 <= c["refined_epoch_sample"] < 3333 and
                        type(c["absolute_cfo_hz"]) in (int, float) and math.isfinite(c["absolute_cfo_hz"])
                        and abs(c["absolute_cfo_hz"]) <= 400000, "invalid host candidate")
            decision = decisions.get(plan["source_first_index"]+offset)
            if decision is None:
                outside.append({"sample_offset": offset, "host_supported": row["supported"],
                                "reason": "no completed FPGA decision; not a detector miss"})
                continue
            winner = candidates[0] if candidates else None
            local_supported = decision.reasons == 0
            phase_error = cfo_error = None
            if winner is not None and not decision.reasons & 1:
                phase = (3*(decision.epoch-winner["refined_epoch_sample"])) % 10000
                phase_error = min(phase, 10000-phase)/3
                cfo_error = decision.cfo_hz-winner["absolute_cfo_hz"]
            matched = bool(row["supported"] and local_supported and phase_error is not None and
                           phase_error <= POLICY["maximum_epoch_distance_samples"] and
                           abs(cfo_error) <= POLICY["maximum_cfo_distance_hz"])
            if row["supported"]:
                host_positive_offsets.append(offset)
            comparisons.append({"sample_offset": offset, "host_supported": row["supported"],
                                "fpga_supported": local_supported, "matched": matched,
                                "epoch_distance_samples": phase_error, "cfo_difference_hz": cfo_error,
                                "host_reasons": row["reasons"], "fpga_reasons": decision.reasons})
    positives = len(host_positive_offsets)
    recovered = sum(r["matched"] for r in comparisons)
    extras = [r for r in comparisons if r["fpga_supported"] and not r["matched"]]
    episodes = sum(i == 0 or offset-host_positive_offsets[i-1] > POLICY["episode_gap_samples"]
                   for i, offset in enumerate(host_positive_offsets))
    enough = positives >= POLICY["minimum_positive_windows"] and episodes >= POLICY["minimum_positive_episodes"]
    recovery = recovered/positives if positives else None
    gate = ("inconclusive" if not enough else "pass"
            if recovery >= POLICY["minimum_supported_window_recovery"] and not extras else "fail")
    require(all(digest(path) == sha for path, sha in inputs.items()), "host replay changed during comparison")
    require(all(digest(capture/name) == sha for name, sha in data["hashes"].items()),
            "capture changed during comparison")
    return {"schema": "gla1-same-window-comparison/v1", "status": "complete", "detection_gate": gate,
            "policy": POLICY, "capture_sha256": data["hashes"], "host_input_sha256": inputs,
            "comparable_windows": len(comparisons), "host_supported_windows": positives,
            "host_positive_episodes": episodes, "recovered_windows": recovered, "recovery": recovery,
            "fpga_additional_or_mismatched": extras, "windows": comparisons,
            "host_windows_without_fpga_completion": outside, "coverage": data["accounting"],
            "hardware_accessed_by_comparator": False, "live_detector_qualified": False,
            "limitations": ["Matching tests acquisition neighborhoods, not fine CFO/timing accuracy.",
                "Host rejection is not proof of noise; extra local detections require review.",
                "Only the fixed cadence windows are searched; intervening samples remain unsearched.",
                "Matched-window recovery excludes skipped/aborted windows, reported separately.",
                "Deployment, calibration, RTL arithmetic and real-time reliability have separate release gates."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--host", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.host is None:
        require(args.output is None, "plan creation writes only --plan")
        save(args.plan, plan_for(args.capture))
    else:
        require(args.output is not None, "comparison requires --output")
        save(args.output, compare_capture(args.capture, args.plan, args.host))


if __name__ == "__main__":
    main()
