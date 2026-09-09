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


def cases():
    result = []
    for rate in RATES:
        specifications = [("strong", cfo) for cfo in (-100_000, 0, 100_000)]
        specifications += [(kind, 42_000) for kind in ("weak", "short32", "short8", "noise", "tone", "scrambled", "rolled")]
        for kind, cfo in specifications:
            result.append({"case": len(result), "rate": rate, "kind": kind, "cfo_hz": cfo,
                           "seed": 207892153+len(result), "count": rate//250,
                           "noise_sigma_per_component": 500*(rate/2_500_000)**.5,
                           "pilot_scale": 200 if kind == "weak" else 2000,
                           "epoch": 513*(rate//2_500_000)+(rate//2_500_000)//3})
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leo-source", type=Path, required=True)
    parser.add_argument("--acquisition-q16", type=int, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.acquisition_q16 <= 65536:
        parser.error("acquisition gate must lie in [0, 65536]")
    specifications = cases()
    sources = [Path(__file__), ROOT/"tools/starlink_glrt_replay.py", ROOT/"tools/starlink_glrt_host.py",
               ROOT/"tests/starlink_glrt/pilot.py", ROOT/"tests/starlink_glrt/ddc.py"]
    hashes = {str(p): digest(p) for p in sources}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output/"protocol.json", {"schema": "starlink-glrt-synthetic-trials/v1", "cases": specifications,
         "source_sha256": hashes, "fpga_gates_q16": [args.acquisition_q16, 19661, 9831],
         "host_gates": [.175, .025], "timing_tolerance_output_samples": 2, "cfo_tolerance_hz": 2000,
         "randomness": "fixed reproducible seeds; whether these cases were previously examined must be established from study provenance",
         "noise_model": "white complex noise, variance proportional to native sample rate for constant spectral density",
         "weak_nominal_2p5m_sample_snr_db": -10.9691001301,
         "signal_model": "published upper-edge pilot; integer native epochs with deterministic output-grid fractional offsets",
         "expected": "strong must recover at least one complete frame; noise/tone/scrambled must have no positives; weak/short/rolled are reported without a forced pass",
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
                 "--output", str(output/"rtl")],
                [str(args.leo_source/".venv/bin/python"), str(ROOT/"tools/starlink_glrt_host.py"),
                 "--leo-source", str(args.leo_source), "--iq", str(output/"rtl/exported.ci16"),
                 "--edge", "upper", "--minimum-exact", ".175", "--minimum-margin", ".025", "--output", str(output/"host")]]
            save(output/"commands.json", commands)
            for kind, command in zip(("rtl", "host"), commands):
                with (output/f"{kind}.log").open("x") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
            rtl = json.loads((output/"rtl/summary.json").read_text())
            ratio = case["rate"]//2_500_000
            comparison = compare(output/"host", output/"rtl/exported.ci16", rtl["events"], rtl["first_center_native_index"], ratio)
            save(output/"comparison.json", comparison)
            positives = [e for e in rtl["events"] if e["detected"]]
            expected_epochs = [e+(187*ratio if case["kind"] == "rolled" else 0) for e in epochs]
            matched = [e for e in positives if any(abs(e["epoch"]-t) <= 2*ratio for t in expected_epochs)
                       and abs(e["cfo_hz"]-case["cfo_hz"]) <= 2000]
            criterion = "reported_limit"
            if case["kind"] == "strong":
                criterion = "pass" if matched else "miss"
            elif case["kind"] in ("noise", "tone", "scrambled"):
                criterion = "pass" if not positives else "false_positive"
            result.update(status="complete", criterion=criterion, clipped_components=clipped,
                          events=len(rtl["events"]), detections=len(positives), truth_matches=len(matched),
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
    summary = {"status": "complete" if unchanged and all(r["status"] == "complete" for r in results) else "disqualified",
         "source_unchanged": unchanged, "cases": results, "hardware_accessed": False,
         "all_strong_and_control_criteria_pass": all(r.get("criterion") in ("pass", "reported_limit") for r in results)}
    save(args.output/"summary.json", summary)
    if summary["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
