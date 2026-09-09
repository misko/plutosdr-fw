#!/usr/bin/env python3
"""Replay saved native CI16 through autonomous FPGA RTL alongside IQ export.

Offline core simulation, not ADC/AXI/DMA/hardware qualification. An optional
already-frozen blind host result is opened only after RTL finishes and IQ hashes
match. It never supplies an acquisition seed to either implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_glrt.ddc import BANK_ROOT, Ddc, RATES, group_delay
from tests.starlink_glrt.pilot import fixed_score, symbol_correlations
from tools.starlink_glrt_profile import add_arguments, profile
from tests.starlink_glrt.test_ddc_rtl import records
from tests.starlink_glrt.test_receiver_rtl import BENCH


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def terminal_state(status, trace, samples, ratio):
    reading, next_index, newest_index, native_epoch, score_state, expected_symbol, score_epoch = trace
    partial = bool(status[13])
    if partial:
        if not (reading and next_index == samples and newest_index == samples-1
                and native_epoch+726*ratio > samples and score_state in (0, 1)):
            raise ValueError("pending native work is not solely waiting for samples beyond the observation")
        if score_state == 1 and (not 1 <= expected_symbol <= 63 or score_epoch != native_epoch):
            raise ValueError("partial scorer does not belong to the incomplete native frame")
    elif score_state != 0 or status[14]:
        raise ValueError("complete scorer work is still pending after drain")
    if bool(status[14]) != bool(score_state):
        raise ValueError("scorer state and busy flag disagree")
    return {"native_waiting_for_future_input": partial,
            "native_epoch": native_epoch if partial else None,
            "required_support_end_native": native_epoch+726*ratio if partial else None,
            "received_support_end_native": samples,
            "scorer_state": score_state, "collected_symbols": expected_symbol if score_state == 1 else None}


def compare(host, iq_path, events, first_center, ratio):
    # Call only after the exported bytes and their observation have been verified.
    summary = json.loads((host / "summary.json").read_text())
    if summary["status"] != "complete" or summary["iq_sha256"] != digest(iq_path):
        raise ValueError("blind host result did not analyze these exact exported bytes")
    if summary["windows_sha256"] != digest(host / "blind-windows.jsonl"):
        raise ValueError("blind host windows changed after finalization")
    if summary["protocol_sha256"] != digest(host / "protocol.json"):
        raise ValueError("blind host protocol changed after finalization")
    positives = []
    evidence_scopes = set()
    for line in (host / "blind-windows.jsonl").read_text().splitlines():
        window = json.loads(line)
        for candidate in window["candidates"]:
            if "frame_glrt64" in candidate:
                evidence_scopes.add("individually scored frames at blind host acquisition coordinates")
                for frame in candidate["frame_glrt64"]:
                    cfo = frame["glrt64"]["tracking_cfo_hz"]
                    if frame["engineering_positive"] and abs(cfo) <= 100_000:
                        positives.append({"window_start": window["start"], "rank": candidate["acquisition"]["rank"],
                                          "support": frame["support_output_samples"], "cfo_hz": cfo})
                continue
            evidence_scopes.add("legacy multi-frame crossing supports; individual frame positivity is unknown")
            cfo = candidate["glrt64"]["tracking_cfo_hz"]
            if not candidate["engineering_positive"] or abs(cfo) > 100_000:
                continue
            for support in candidate["score_support_output_samples"]:
                positives.append({"window_start": window["start"], "rank": candidate["acquisition"]["rank"],
                                  "support": support, "cfo_hz": cfo})
    comparisons, matched_supports = [], set()
    period = 5_000_000/22
    for event in events:
        if not event["detected"]:
            continue
        begin = (event["epoch"] + 22*ratio - first_center)/ratio
        end = (event["epoch"] + 726*ratio - first_center)/ratio
        matches = []
        for index, positive in enumerate(positives):
            dt = begin-positive["support"][0]
            df = (event["cfo_hz"]-positive["cfo_hz"]+period/2) % period-period/2
            if abs(dt) <= 5 and abs(df) <= 2000:
                matches.append({"host_support": index, "epoch_error_output_samples": dt, "cfo_error_hz": df})
                matched_supports.add(index)
        comparisons.append({"fpga_event": event["sequence"], "support": [begin, end], "matches": matches})
    return {"host_summary_sha256": digest(host / "summary.json"),
            "host_evidence_scopes": sorted(evidence_scopes),
            "host_positive_supports": positives, "fpga_positive_comparisons": comparisons,
            "unmatched_fpga_positives": sum(not row["matches"] for row in comparisons),
            "unmatched_host_support_indexes": sorted(set(range(len(positives)))-matched_supports),
            "support_count_note": "host supports overlap across windows/candidate basins; not independent trials",
            "interpretation": "engineering agreement/unmatched supports, not calibrated false-positive/false-negative or RF-truth labels"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iq", type=Path, required=True)
    parser.add_argument("--source-rate", type=int, choices=RATES, required=True)
    parser.add_argument("--edge", choices=("upper", "lower"), required=True)
    parser.add_argument("--host-blind", type=Path)
    add_arguments(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gates = (args.acquisition_q16, args.exact_q16, args.margin_q16)
    try:
        detector_profile = profile(gates, requested=args.profile)
    except ValueError as error:
        parser.error(str(error))
    raw_bytes = args.iq.read_bytes()
    if not raw_bytes or len(raw_bytes) % 4 or len(raw_bytes)//4 > args.source_rate//50:
        parser.error("requires a nonempty complete CI16 observation of at most 20 ms")
    raw = np.frombuffer(raw_bytes, dtype="<i2").reshape(-1, 2)
    source_files = [Path(__file__), ROOT / "tools/starlink_glrt_profile.py", ROOT / "tests/starlink_glrt/test_receiver_rtl.py",
                    ROOT / "tests/starlink_glrt/test_ddc_rtl.py", ROOT / "tests/starlink_glrt/pilot.py",
                    ROOT / "tests/starlink_glrt/ddc.py", *sorted(BANK_ROOT.glob("*.*"))]
    source_files = [p for p in source_files if p.is_file() and p.suffix in (".py", ".v", ".mem", ".json")]
    source_hashes = {str(path): digest(path) for path in source_files}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "protocol.json", {"schema": "starlink-glrt-saved-rtl/v2", "source_rate_hz": args.source_rate,
         "edge": args.edge, "samples": len(raw), "input_sha256": hashlib.sha256(raw_bytes).hexdigest(),
         "source_sha256": source_hashes, "replay_first_source_index": 0,
         "index_note": "replay ordinal, not the original radio counter",
         "fpga_gates_q16": gates, "detector_profile": detector_profile, "host_seed_inputs": [],
         "comparison_epoch_tolerance_output_samples": 5, "comparison_cfo_tolerance_hz": 2000,
         "tolerance_note": "engineering window of five 0.4 us cells and about 4.5 FPGA CFO bins; misses are retained",
         "hardware_accessed": False})
    source = BENCH.replace("(RATE)", f"({args.source_rate})")
    source = source.replace("$finish;", '$display("T %d %d %d %d %d %d %d", dut.native.reading, dut.native.next_index, '
                            'dut.native.newest_index, dut.native.job_epoch, dut.scorer.state, '
                            'dut.scorer.expected_symbol, dut.scorer.job_epoch);\n $finish;')
    source = source.replace("acquisition_threshold_q16=15729,glrt_threshold_q16=19661,glrt_margin_q16=9831",
                            f"acquisition_threshold_q16={gates[0]},glrt_threshold_q16={gates[1]},glrt_margin_q16={gates[2]}")
    for token, filename in {"NATIVE": f"pilot_{args.source_rate}_{args.edge}_q7.mem",
                           "ACQUISITION": f"pilot_2500000_{args.edge}_q7.mem",
                           "FIRST": f"ddc_{args.source_rate}_q17.mem", "FINAL": "ddc_5000000_q17.mem",
                           "TWIDDLE": "glrt_dft512_q15.mem"}.items():
        source = source.replace(f'"{token}"', f'"{BANK_ROOT / filename}"')
    bench, executable = args.output / "bench.sv", args.output / "sim"
    bench.write_text(source)
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                    *map(str, sorted(BANK_ROOT.glob("*.v")))], check=True)
    stimulus = args.output / "input.txt"
    stimulus.write_text("\n".join(records(raw, args.source_rate) + ["0 0 0 0 0 0 0"]*75_000)+"\n")
    started = time.monotonic()
    print(f"RTL replay {args.source_rate} samples/s, {len(raw)} samples; no timing/CFO seed", flush=True)
    process = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"], capture_output=True, text=True, timeout=900)
    (args.output / "rtl_trace.txt").write_text(process.stdout + process.stderr)
    if process.returncode:
        raise RuntimeError("RTL replay failed; inspect retained trace")
    streams = {name: [] for name in ("O", "P", "C", "G", "S", "T")}
    for line in process.stdout.splitlines():
        words = line.split()
        if words[0] in streams:
            streams[words[0]].append(tuple(int(word, 16 if j == 0 and words[0] not in ("S", "T") else 10)
                                                for j, word in enumerate(words[1:])))
        elif "$finish called at" not in line:
            raise ValueError("unexpected RTL output: " + line)
    reference = Ddc(args.source_rate).process(raw, 0)
    expected = [(int(index), int(i), int(q), int(support)) for index, (i, q), support in
                zip(reference.indexes, reference.iq, reference.supported)]
    if streams["O"] != expected or len(streams["S"]) != 1 or len(streams["T"]) != 1:
        raise ValueError("RTL IQ differs from independent integer convolution")
    status = streams["S"][0]
    if status[:5] != (len(raw), len(expected), reference.clips, 0, 0) or any(status[j] for j in (11, 12)):
        raise ValueError("RTL export or detector fault/pending complete work")
    terminal = terminal_state(status, streams["T"][0], len(raw), args.source_rate//2_500_000)
    if status[5:8] != (len(expected), max(0, int(reference.supported.sum())-175), len(streams["P"])):
        raise ValueError("acquisition window/proposal counts do not reconcile")
    if status[8:11] != (sum(row[1] for row in streams["C"]), sum(row[2] for row in streams["C"]), len(streams["G"])):
        raise ValueError("candidate admission/busy/result counts do not reconcile")
    if (status[15] != len(streams["C"]) or status[7] != status[15]+status[16]+status[17]
            or status[15] != status[8]+status[9] or status[8] != status[10]+status[13]):
        raise ValueError("proposal selection or incomplete native work is unaccounted")
    admitted = [row[0] for row in streams["C"] if row[1]]
    if [row[0] for row in streams["G"]] != admitted[:len(streams["G"])]:
        raise ValueError("result epochs do not match admitted candidate order")
    events = []
    for sequence, row in enumerate(streams["G"]):
        epoch, detected, exact, control, ebin, cbin, ee, ce, ep, cp, shift, zero, clamp = row
        oracle = fixed_score(symbol_correlations(raw, args.source_rate, args.edge, epoch),
                             symbol_correlations(raw, args.source_rate, args.edge, epoch, 17))
        e, c = oracle["exact"], oracle["control"]
        wanted = (e["score"], c["score"], e["bin"], c["bin"], e["energy"], c["energy"],
                  e["peak"], c["peak"], oracle["block_shift"], e["zero"]+2*c["zero"], e["clamped"]+2*c["clamped"])
        if row[2:] != wanted or bool(detected) != (not e["zero"] and exact >= gates[1] and exact >= control+gates[2]):
            raise ValueError("RTL native GLRT raw statistic differs from frozen integer oracle")
        events.append({"sequence": sequence, "epoch": epoch, "detected": bool(detected),
                       "exact_q16": exact, "control_q16": control, "raw_event": row,
                       "cfo_hz": (ebin if ebin < 256 else ebin-512)*5_000_000/(512*22)})
    supported = [row for row in streams["O"] if row[3]]
    iq_path = args.output / "exported.ci16"
    np.asarray([(row[1], row[2]) for row in supported], dtype="<i2").tofile(iq_path)
    first_center = supported[0][0]-group_delay(args.source_rate) if supported else None
    result = {"status": "complete", "elapsed_seconds": time.monotonic()-started,
              "source_rate_hz": args.source_rate, "output_rate_hz": 2_500_000, "supported_samples": len(supported),
              "first_center_native_index": first_center, "group_delay_native_samples": group_delay(args.source_rate),
              "exported_sha256": digest(iq_path), "status_counters": status, "events": events,
              "proposal_epochs": [row[0] for row in streams["P"]],
              "selected_candidates": [{"epoch": row[0], "admitted": bool(row[1]), "busy_rejected": bool(row[2])}
                                      for row in streams["C"]],
              "incomplete_native_candidate": bool(status[13]), "selection_pending": bool(status[17]),
              "terminal_state": terminal,
              "hardware_accessed": False, "transport_qualified": False, "live_detector_qualified": False}
    if args.host_blind is not None:
        result["comparison"] = compare(args.host_blind, iq_path, events, first_center, args.source_rate//2_500_000)
    if digest(args.iq) != hashlib.sha256(raw_bytes).hexdigest() or any(digest(Path(p)) != h for p, h in source_hashes.items()):
        raise ValueError("replay input/source changed; evidence is disqualified")
    save(args.output / "summary.json", result)
    print(json.dumps({"events": len(events), "detections": sum(e["detected"] for e in events),
                      "supported_samples": len(supported), "output": str(args.output)}))


if __name__ == "__main__":
    main()
