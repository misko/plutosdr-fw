#!/usr/bin/env python3
"""Frozen standalone CLI; vendor execution is never performed by this program."""
import argparse
import json
from pathlib import Path
import sys
import types

if sys.flags.optimize:
    raise SystemExit("unoptimized frozen interpreter required")
if sys.version_info[:3] != (3, 11, 16):
    raise SystemExit("tested Python3.11.16 required")
root = Path(__file__).resolve().parents[1]
# This CLI's actual helper graph is stdlib-only. Do not execute the unchanged
# test package __init__, whose unrelated numerical APIs eagerly import NumPy.
# Only these two fixed namespaces are installed; relative modules still load
# from their exact frozen files, with original46 sources checked unchanged.
for name, path in (("tests", root / "tests"), ("tests.starlink_oracle", root / "tests/starlink_oracle")):
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    package.__package__ = name
    sys.modules[name] = package
from tests.starlink_oracle import retained_output_actual_bundle as b

p = argparse.ArgumentParser()
p.add_argument("action", choices=("prepare", "verify", "stage", "after", "results"))
p.add_argument("path", type=Path)
p.add_argument("--output", type=Path)
p.add_argument("--expected")
p.add_argument("--live", action="store_true")
p.add_argument("--authorize-actual", action="store_true")
args = p.parse_args()
if args.action == "prepare":
    result = b.prepare(args.path)
elif not args.expected:
    p.error("external --expected digest required")
elif args.action == "verify":
    result = b.verify(args.path, args.expected, live=args.live)
elif args.action == "results":
    result = b.results(args.path, args.expected)
elif args.output is None:
    p.error("explicit --output required")
elif args.action == "stage":
    result = b.stage(args.path, args.output, args.expected, authorize=args.authorize_actual)
else:
    result = b.after(args.path, args.output, args.expected)
print(json.dumps(result, sort_keys=True))
