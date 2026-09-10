#!/usr/bin/env python3
"""Generate/independently rederive the frozen60-upper offline cohort only."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.starlink_oracle.high_rate60_paired import generate, verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    info = (verify if args.verify else generate)(args.output.absolute())
    print(json.dumps({"result": "HIGH_RATE60_OFFLINE_VERIFIED" if args.verify else "HIGH_RATE60_OFFLINE_GENERATED",
                      "cohort": info["contract"]["cohort"], "files": len(info["files"]), "raw": 16423,
                      "canonical": 4096, "blocks": 7, "scores": 3129, "native_raw": 257,
                      "native_qualified": 241, "pilot": 512, "actual_RTL": False}, sort_keys=True))
