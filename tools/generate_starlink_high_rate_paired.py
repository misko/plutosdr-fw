#!/usr/bin/env python3
"""Generate/independently rederive the frozen 30-upper offline paired cohort."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.starlink_oracle.high_rate_paired import generate, verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = (verify if args.verify else generate)(args.output.absolute())
    print(
        json.dumps(
            {
                "result": "HIGH_RATE_OFFLINE_VERIFIED"
                if args.verify
                else "HIGH_RATE_OFFLINE_GENERATED",
                "cohort": result["contract"]["cohort"],
                "files": len(result["files"]),
                "raw": 8205,
                "canonical": 4096,
                "blocks": 7,
                "scores": 3129,
                "native_tuples": 121,
                "pilot": 512,
                "RTL_executed": False,
            },
            sort_keys=True,
        )
    )
