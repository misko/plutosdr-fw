#!/usr/bin/env python3
"""Frozen new synthetic trials through actual RTL and independent blind host.

These generated trials are distinct from saved/live RF holdouts. All seeds,
signal levels, CFOs and gates are fixed before evaluating any detector output.
Truth is used for assessment only after both autonomous implementations finish.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_glrt.ddc import RATES
from tests.starlink_glrt.pilot import frame, waveforms
from tools.starlink_glrt_replay import compare, digest, save
from tools.starlink_glrt_profile import add_arguments, profile, HOST_GATES


def cases(seed_offset=0, vary_epochs=False):
    result = []
    for rate in RATES:
        specifications = [("strong", cfo) for cfo in (-100_000, 0, 100_000)]
        specifications += [(kind, 42_000) for kind in ("weak", "short32", "short8", "noise", "tone", "scrambled", "rolled")]
        for kind, cfo in specifications:
            seed = 207892153+seed_offset+len(result)
            ratio = rate//2_500_000
            epoch = 513*ratio+ratio//3
            if vary_epochs:
                geometry = np.random.default_rng(seed ^ 0x74ca208d)
                epoch = int(geometry.integers(350, 901))*ratio+int(geometry.integers(ratio))
            result.append({"case": len(result), "rate": rate, "kind": kind, "cfo_hz": cfo,
                           "seed": seed, "count": rate//250,
                           "noise_sigma_per_component": 500*(rate/2_500_000)**.5,
                           "pilot_scale": 200 if kind == "weak" else 2000,
                           "epoch": epoch})
    return result


def stimulus(case):
    rate, count = case["rate"], case["count"]
    rng = np.random.default_rng(case["seed"])
    values = case["noise_sigma_per_component"]*(rng.normal(size=count)+1j*rng.normal(size=count))
    pilot = frame(rate, "upper", roll=17 if case["kind"] == "rolled" else 0).copy()
    n = 11*(rate//2_500_000)
    if case["kind"] == "scrambled":
        pilot[2*n:302*n] = waveforms(rate, "upper")[rng.permutation(300)].reshape(-1)
    if case["kind"].startswith("short"):
        pilot[(2+int(case["kind"][5:]))*n:] = 0
    epochs = []
    if case["kind"] not in ("noise", "tone"):
        for number in range(4):
            start = case["epoch"]+round(number*rate/750)
            if start >= count:
                break
            stop = min(count, start+len(pilot))
            values[start:stop] += case["pilot_scale"]*pilot[:stop-start]
            epochs.append(start)
    elif case["kind"] == "tone":
        values += 6000*np.exp(2j*np.pi*350_000*np.arange(count)/rate)
    values *= np.exp(2j*np.pi*case["cfo_hz"]*np.arange(count)/rate)
    raw = np.rint(np.column_stack((values.real, values.imag)))
    clipped = int(np.count_nonzero((raw < -32768) | (raw > 32767)))
    return np.clip(raw, -32768, 32767).astype("<i2"), epochs, clipped


def assess(case, epochs, events, *, unmatched_host_positives=0):
    """Assess unique complete truth frames only after both blind detectors finish."""
    ratio = case["rate"]//2_500_000
    truth = [epoch+(187*ratio if case["kind"] == "rolled" else 0) for epoch in epochs]
    truth = [epoch for epoch in truth if 0 <= epoch+22*ratio and epoch+726*ratio <= case["count"]]
    positives = [event for event in events if event["detected"]]
    # Maximum one-to-one assignment: duplicate detections never inflate recovery.
    eligible = [[index for index, epoch in enumerate(truth)
                 if abs(event["epoch"]-epoch) <= 2*ratio and abs(event["cfo_hz"]-case["cfo_hz"]) <= 2000]
                for event in positives]
    owners = {}
    def assign(event_index, seen):
        for truth_index in eligible[event_index]:
            if truth_index in seen:
                continue
            seen.add(truth_index)
            if truth_index not in owners or assign(owners[truth_index], seen):
                owners[truth_index] = event_index
                return True
        return False
    for index in range(len(positives)):
        assign(index, set())
    unmatched = sorted(set(range(len(positives)))-set(owners.values()))
    missed = [epoch for index, epoch in enumerate(truth) if index not in owners]
    criterion = "reported_limit"
    if case["kind"] == "strong":
        criterion = ("pass" if truth and not missed and not unmatched and not unmatched_host_positives
                     else "failed_frame_recovery_or_agreement")
    elif case["kind"] in ("noise", "tone", "scrambled"):
        criterion = "pass" if not positives else "false_positive"
    return {"criterion": criterion, "detections": len(positives), "truth_matches": len(owners),
            "complete_truth_epochs": truth, "missed_complete_truth_epochs": missed,
            "unmatched_positive_indexes": unmatched,
            "truth_assignments": [{"truth_epoch": truth[t], "positive_index": e} for t, e in sorted(owners.items())]}


def summarize(results, unchanged, selected_cases):
    complete = unchanged and all(result["status"] == "complete" for result in results)
    gated = [result for result in results if result["kind"] in ("strong", "noise", "tone", "scrambled")]
    passed = all(result.get("criterion") == "pass" for result in gated) if gated else None
    return {"schema": "starlink-glrt-synthetic-qualification/v2",
            "status": "complete" if complete else "disqualified", "source_unchanged": unchanged,
            "cases": results, "selected_case_ids": selected_cases, "full_five_rate_matrix": selected_cases == list(range(50)),
            "hardware_accessed": False, "qualification_passed": passed if complete else False,
            "gated_cases": len(gated), "all_strong_and_control_criteria_pass": passed if complete else False}


def exit_status(summary):
    return int(summary["status"] != "complete" or summary["qualification_passed"] is False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leo-source", type=Path, required=True)
    add_arguments(parser)
    parser.add_argument("--source-rate", type=int, choices=RATES, action="append",
                        help="evaluate only this rate; repeat to select more rates")
    parser.add_argument("--case", type=int, choices=range(50), action="append",
                        help="evaluate only this case ID; repeat to select more cases")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--vary-epochs", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        detector_profile = profile((args.acquisition_q16, args.exact_q16, args.margin_q16), requested=args.profile)
    except ValueError as error:
        parser.error(str(error))
    if not 0 <= args.seed_offset < 1 << 32:
        parser.error("seed offset must be an unsigned 32-bit integer")
    specifications = cases(args.seed_offset, args.vary_epochs)
    specifications = [case for case in specifications
                      if (args.source_rate is None or case["rate"] in args.source_rate)
                      and (args.case is None or case["case"] in args.case)]
    if not specifications:
        parser.error("case and rate selection has no cases")
    selected_cases = [case["case"] for case in specifications]
    sources = [Path(__file__), ROOT/"tools/starlink_glrt_replay.py", ROOT/"tools/starlink_glrt_host.py",
               ROOT/"tools/starlink_glrt_profile.py", ROOT/"tests/starlink_glrt/pilot.py", ROOT/"tests/starlink_glrt/ddc.py"]
    hashes = {str(p): digest(p) for p in sources}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output/"protocol.json", {"schema": "starlink-glrt-synthetic-trials/v2", "cases": specifications,
         "source_sha256": hashes, "fpga_gates_q16": detector_profile["fpga_gates_q16"], "detector_profile": detector_profile,
         "selected_case_ids": selected_cases, "full_five_rate_matrix": selected_cases == list(range(50)),
         "host_gates": HOST_GATES, "timing_tolerance_output_samples": 2, "cfo_tolerance_hz": 2000,
         "randomness": "fixed reproducible seeds; whether these cases were previously examined must be established from study provenance",
         "noise_model": "white complex noise, variance proportional to native sample rate for constant spectral density",
         "weak_nominal_2p5m_sample_snr_db": -10.9691001301,
         "signal_model": "published upper-edge pilot; integer native epochs with deterministic output-grid fractional offsets",
         "seed_offset": args.seed_offset, "vary_epochs": args.vary_epochs,
         "expected": "strong must recover every complete frame one-to-one, with no unmatched FPGA positives or host disagreements; noise/tone/scrambled must have no positives; weak/short/rolled are reported without a forced pass",
         "hardware_accessed": False, "fresh_saved_or_live_holdout": False})

    def run(case):
        output = args.output/f"case-{case['case']:03d}"
        output.mkdir()
        result = {**case, "status": "failed"}
        try:
            raw, epochs, clipped = stimulus(case)
            iq = output/"native.ci16"
            raw.tofile(iq)
            save(output/"stimulus.json", {**case, "epochs": epochs, "clipped_components": clipped, "sha256": digest(iq)})
            commands = [
                [sys.executable, str(ROOT/"tools/starlink_glrt_replay.py"), "--iq", str(iq),
                 "--source-rate", str(case["rate"]), "--edge", "upper", "--acquisition-q16", str(args.acquisition_q16),
                 "--exact-q16", str(args.exact_q16), "--margin-q16", str(args.margin_q16),
                 "--output", str(output/"rtl")],
                [str(args.leo_source/".venv/bin/python"), str(ROOT/"tools/starlink_glrt_host.py"),
                 "--leo-source", str(args.leo_source), "--iq", str(output/"rtl/exported.ci16"),
                 "--edge", "upper", "--minimum-exact", str(HOST_GATES[0]), "--minimum-margin", str(HOST_GATES[1]), "--output", str(output/"host")]]
            save(output/"commands.json", commands)
            for kind, command in zip(("rtl", "host"), commands):
                with (output/f"{kind}.log").open("x") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
            rtl = json.loads((output/"rtl/summary.json").read_text())
            ratio = case["rate"]//2_500_000
            comparison = compare(output/"host", output/"rtl/exported.ci16", rtl["events"], rtl["first_center_native_index"], ratio)
            save(output/"comparison.json", comparison)
            assessment = assess(case, epochs, rtl["events"], unmatched_host_positives=comparison["unmatched_fpga_positives"])
            result.update(status="complete", **assessment, clipped_components=clipped,
                          events=len(rtl["events"]),
                          status_counters=rtl["status_counters"],
                          unmatched_fpga_positives=comparison["unmatched_fpga_positives"],
                          rtl_summary_sha256=digest(output/"rtl/summary.json"), host_summary_sha256=digest(output/"host/summary.json"))
        except Exception as error:
            result["error"] = str(error)
        save(output/"result.json", result)
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, specifications))
    unchanged = all(digest(Path(p)) == h for p, h in hashes.items())
    summary = summarize(results, unchanged, selected_cases)
    save(args.output/"summary.json", summary)
    raise SystemExit(exit_status(summary))


if __name__ == "__main__":
    main()
