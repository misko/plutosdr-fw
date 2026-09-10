#!/usr/bin/env python3
"""Offline paired60 preparation/result gate; never invokes a simulator."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.starlink_oracle.high_rate60_bundle import freeze, verify_bundle
from tests.starlink_oracle.high_rate60_harness_result import verify_results

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("output", type=Path)
    f.add_argument("--cohort", required=True, type=Path)
    v = sub.add_parser("verify")
    v.add_argument("bundle", type=Path)
    v.add_argument("--expected-bundle-sha", required=True)
    r = sub.add_parser("result")
    r.add_argument("simulation", type=Path)
    r.add_argument("bundle", type=Path)
    r.add_argument("--expected-bundle-sha", required=True)
    a = p.parse_args()
    if a.mode == "freeze":
        receipt = freeze(a.cohort.absolute(), a.output.absolute())
        result = {"result": "PAIRED60_PREPARED_NOT_EXECUTED", "source_signature": receipt["source_signature"]}
    else:
        receipt = verify_bundle(a.bundle.absolute(), a.expected_bundle_sha)
        result = {"result": "PAIRED60_BUNDLE_VERIFIED", "source_signature": receipt["source_signature"]}
        if a.mode == "result":
            result = verify_results(a.simulation.absolute(), a.bundle.absolute() / "cohort")
            result["source_signature"] = receipt["source_signature"]
    print(json.dumps(result, sort_keys=True))
