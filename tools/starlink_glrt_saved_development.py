#!/usr/bin/env python3
"""Replay every record of a frozen saved LPP1 pack through blind host GLRT.

These already-examined recordings are development data, never a fresh holdout.
Only CI16 and the recorded edge reach acquisition; prior candidate labels are
retained as provenance and are not used to select records or supply seeds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
from types import SimpleNamespace

from starlink_glrt_host import analyze, digest, document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--leo-source", type=Path, required=True)
    parser.add_argument("--minimum-exact", type=float, required=True)
    parser.add_argument("--minimum-margin", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest["schema"] != "org.leo.research.presence-worker-pack/v1" or manifest["rate_hz"] != 2_500_000:
        raise ValueError("requires a 2.5 MS/s saved worker pack")
    if digest(args.pack) != manifest["pack_sha256"]:
        raise ValueError("saved pack identity differs")
    data = args.pack.read_bytes()
    magic, rate, count = struct.unpack_from("<4sII", data)
    record_bytes = 24 + 50_000 * 4
    if (magic, rate, count) != (b"LPP1", 2_500_000, len(manifest["records"])) or len(data) != 12 + count * record_bytes:
        raise ValueError("saved pack geometry differs")
    args.output.mkdir(parents=True, exist_ok=False)
    document(args.output / "protocol.json", {
        "schema": "starlink-glrt-saved-development/v1",
        "scope": "all 20 ms saved records, already examined development corpus; not a fresh holdout or GLR1 transport test",
        "pack_sha256": digest(args.pack), "source_manifest_sha256": digest(args.manifest),
        "records": count, "selection": "every record, in original order",
        "minimum_exact": args.minimum_exact, "minimum_margin": args.minimum_margin,
        "reference": str(args.leo_source.resolve()), "script_sha256": digest(Path(__file__)),
    })
    results = []
    for number, record in enumerate(manifest["records"]):
        offset = 12 + number * record_bytes
        counter, visit, edge, channel = struct.unpack_from("<QQII", data, offset)
        if (str(counter) != record["device_counter"] or visit != record["provenance"]["visit"]
                or edge != int(record["edge"] == "upper") or channel != record["provenance"]["channel"]
                or record["provenance"]["rx"] != 1):
            raise ValueError("saved record differs from its provenance")
        directory = args.output / f"record-{number:03}"
        directory.mkdir()
        iq = directory / "iq.ci16"
        with iq.open("xb") as stream:
            stream.write(data[offset+24:offset+record_bytes])
        document(directory / "provenance.json", record)
        summary = analyze(SimpleNamespace(
            leo_source=args.leo_source, iq=iq, edge=record["edge"],
            minimum_exact=args.minimum_exact, minimum_margin=args.minimum_margin,
            output=directory / "blind"))
        results.append({"record": number, "probe": record["file"], "edge": record["edge"],
                        "iq_sha256": summary["iq_sha256"],
                        "windows": summary["windows"],
                        "windows_with_engineering_positive": summary["windows_with_engineering_positive"],
                        "windows_with_in_band_engineering_positive": summary["windows_with_in_band_engineering_positive"],
                        "summary_sha256": digest(directory / "blind/summary.json")})
        document(directory / "result.json", results[-1])
    if digest(args.pack) != manifest["pack_sha256"]:
        raise ValueError("saved pack changed during execution")
    document(args.output / "summary.json", {"status": "complete", "records": results,
                                            "fresh_holdout": False, "hardware_qualified": False})


if __name__ == "__main__":
    main()
