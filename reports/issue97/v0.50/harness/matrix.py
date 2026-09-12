#!/usr/bin/env python3
"""Serial-bound finite qualification matrices for the exact final image."""

import argparse
import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

from maintain import ROOT, SERIAL

parser = argparse.ArgumentParser()
parser.add_argument("--paired", action="store_true")
parser.add_argument("--persistent", action="store_true")
args = parser.parse_args()
manifest = json.loads((ROOT.parent / "build/counter-rx-v1.json").read_text())
assert manifest["serial"] == SERIAL
if args.paired:
    cases = [
        (f"paired-{channels}-{mode}", [5000000], 5, 100000, 4, list(channels), mode, 0)
        for channels in ("0", "1", "01")
        for mode in ("hold", "auto")
    ]
else:
    cases = [
        (
            "candidate-1r1t-low-lan",
            [2500000, 5000000],
            5,
            1000000,
            50,
            ["0"],
            "counter",
            0,
        ),
        (
            "candidate-1r1t-high",
            [30000000, 60000000],
            30,
            1000000,
            50,
            ["0"],
            "counter",
            0,
        ),
        ("candidate-1r1t-loss", [60000000], 100, 1000000, 50, ["0"], "counter", 2),
    ]
for name, rates, count, samples, buffers, channels, mode, delay in cases:
    output = ROOT / (("persistent-" if args.persistent else "") + name + ".json")
    assert not output.exists(), output
    command = [
        sys.executable,
        str(Path(__file__).with_name("capture.py")),
        "--library",
        "/home/mouse9911/gits/pluto-plus-utils-issue-97/.venv/lib/libiio.so.0.25",
        "--binding-directory",
        "/home/mouse9911/gits/libiio-issue-97/bindings/python",
        "--output",
        str(output),
        "--rates",
        *map(str, rates),
        "--frames",
        str(count),
        "--samples",
        str(samples),
        "--kernel-buffers",
        str(buffers),
        "--channels",
        *channels,
        "--delay",
        str(delay),
    ]
    command += ["--counter-only"] if mode == "counter" else ["--ordinary"]
    if mode == "auto":
        command += ["--auto"]
    subprocess.run(command, check=True)
    result = json.loads(output.read_text())
    assert result["serial"] == SERIAL and result["firmware"] == manifest["firmware"]
    assert result["restored"] and result["restored_gain"] and result["restored_queue"]
    for cell in result["cells"]:
        frames = cell["frames"]
        assert cell["outcome"] == "completed" and len(frames) == count
        assert all(f["end"] - f["first"] == samples for f in frames)
        assert all(b["first"] - a["end"] == b["missing"] for a, b in pairwise(frames))
        assert frames[0]["missing"] == 0
        missing = sum(f["missing"] for f in frames)
        assert (missing > 0) if delay else (missing == 0)
        if mode == "counter":
            assert cell["allocated_kernel_buffers"] == buffers
    print("PASS:", name, flush=True)
