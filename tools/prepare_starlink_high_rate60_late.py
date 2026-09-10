#!/usr/bin/env python3
"""Offline late60 preparation/result verifier; never launches simulation."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tests.starlink_oracle.high_rate60_late import verify_results
from tests.starlink_oracle.high_rate60_late_bundle import freeze, verify_bundle

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode",required=True)
    f = sub.add_parser("freeze")
    f.add_argument("output",type=Path)
    f.add_argument("--healthy",required=True,type=Path)
    for mode in ["verify","result"]:
        q = sub.add_parser(mode)
        if mode == "result":
            q.add_argument("simulation",type=Path)
        q.add_argument("bundle",type=Path)
        q.add_argument("--expected-bundle-sha",required=True)
    a = p.parse_args()
    if a.mode == "freeze":
        receipt = freeze(a.healthy.absolute(),a.output.absolute())
        result = {"result":"PAIRED60_LATE_PREPARED_NOT_EXECUTED"}
    else:
        receipt = verify_bundle(a.bundle.absolute(),a.expected_bundle_sha)
        result = {"result":"PAIRED60_LATE_BUNDLE_VERIFIED"}
        if a.mode == "result":
            result = verify_results(a.simulation.absolute(),a.bundle.absolute())
    result["source_signature"] = receipt["source_signature"]
    print(json.dumps(result,sort_keys=True))
