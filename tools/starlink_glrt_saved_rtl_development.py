#!/usr/bin/env python3
"""Run all saved development records of one edge through blind host and RTL.

The corpus has already been examined. These are engineering threshold studies,
not holdouts, RF truth labels or hardware transport qualification.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from starlink_glrt_replay import digest, save

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", type=Path, required=True)
    parser.add_argument("--leo-source", type=Path, required=True)
    parser.add_argument("--edge", choices=("upper", "lower"), required=True)
    parser.add_argument("--acquisition-q16", type=int, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.acquisition_q16 <= 65536:
        parser.error("acquisition gate must lie in [0, 65536]")
    summary_path = args.saved / "summary.json"
    records = [row for row in json.loads(summary_path.read_text())["records"] if row["edge"] == args.edge]
    if not records or len({row["record"] for row in records}) != len(records):
        parser.error("no records or duplicate record indexes")
    for row in records:
        path = args.saved / f"record-{row['record']:03d}" / "iq.ci16"
        if digest(path) != row["iq_sha256"]:
            parser.error("saved IQ differs from the frozen corpus receipt")
    sources = [Path(__file__), ROOT/"tools/starlink_glrt_host.py", ROOT/"tools/starlink_glrt_replay.py"]
    hashes = {str(path): digest(path) for path in sources}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output/"protocol.json", {"schema": "starlink-glrt-saved-development-batch/v1",
         "selection": "every record of the requested edge in original corpus order; no score-based filtering",
         "source_sha256": hashes, "saved_summary_sha256": digest(summary_path), "records": records,
         "edge": args.edge, "fpga_gates_q16": [args.acquisition_q16, 19661, 9831],
         "host_gates": [.175, .025], "fresh_holdout": False, "hardware_accessed": False})

    def run(row):
        number = row["record"]
        output = args.output/f"record-{number:03d}"
        output.mkdir()
        iq = args.saved/f"record-{number:03d}"/"iq.ci16"
        commands = [
            [str(args.leo_source/".venv/bin/python"), str(ROOT/"tools/starlink_glrt_host.py"),
             "--leo-source", str(args.leo_source), "--iq", str(iq), "--edge", args.edge,
             "--minimum-exact", ".175", "--minimum-margin", ".025", "--output", str(output/"host")],
            [sys.executable, str(ROOT/"tools/starlink_glrt_replay.py"), "--iq", str(iq),
             "--source-rate", "2500000", "--edge", args.edge, "--host-blind", str(output/"host"),
             "--acquisition-q16", str(args.acquisition_q16), "--output", str(output/"rtl")]]
        result = {"record": number, "commands": commands, "status": "failed"}
        try:
            for kind, command in zip(("host", "rtl"), commands):
                with (output/f"{kind}.log").open("x") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
            rtl = json.loads((output/"rtl/summary.json").read_text())
            result.update(status="complete", rtl_summary_sha256=digest(output/"rtl/summary.json"),
                          status_counters=rtl["status_counters"], detections=sum(e["detected"] for e in rtl["events"]),
                          unmatched_fpga_positives=rtl["comparison"]["unmatched_fpga_positives"],
                          unmatched_host_supports=len(rtl["comparison"]["unmatched_host_support_indexes"]))
        except Exception as error:
            result["error"] = str(error)
        save(output/"result.json", result)
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, records))
    unchanged = all(digest(Path(path)) == value for path, value in hashes.items())
    final = {"status": "complete" if unchanged and all(r["status"] == "complete" for r in results) else "disqualified",
             "source_unchanged": unchanged, "records": results, "fresh_holdout": False, "hardware_accessed": False}
    save(args.output/"summary.json", final)
    if final["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
