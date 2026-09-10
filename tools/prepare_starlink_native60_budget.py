#!/usr/bin/env python3
"""Native60 prelaunch/compile-only by default; actual service needs explicit approval."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True  # Snapshot verification must not create cache files.

from tests.starlink_oracle.native60_budget import prepare, run, verify, verify_result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("output", type=Path)
    p = sub.add_parser("verify")
    p.add_argument("bundle", type=Path)
    p.add_argument("--expected-bundle-sha", required=True)
    p = sub.add_parser("run")
    p.add_argument("bundle", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--expected-bundle-sha", required=True)
    p.add_argument("--authorize-native-service", action="store_true")
    p = sub.add_parser("result")
    p.add_argument("output", type=Path)
    p.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.output.absolute())
        result = {"result": "NATIVE60_PREPARED_NOT_MEASURED", "source_signature": result["source_signature"]}
    elif args.command == "verify":
        result = verify(args.bundle.absolute(), args.expected_bundle_sha)
        result = {"result": "NATIVE60_BUNDLE_VERIFIED", "source_signature": result["source_signature"]}
    elif args.command == "result":
        result = verify_result(args.output.absolute(), args.bundle.absolute())
    else:
        result = run(args.bundle.absolute(), args.output.absolute(), args.expected_bundle_sha,
                     authorize_native_service=args.authorize_native_service)
    print(json.dumps(result, sort_keys=True))
