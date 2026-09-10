#!/usr/bin/env python3
"""Portable source/prelaunch/log receipt, excluding duplicate policy bundles.

Packaging only: does not change the reviewed simulation source signature,
launch a simulator, regenerate goldens, or delete any retained local attempt.
"""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build/high-rate-harness-prelaunch-v1"
REPORT = ROOT / "docs/starlink-high-rate-harness-prelaunch-20260910.md"
RUNS = [ROOT / "build" / name for name in [
    "high-rate-harness-offline-v1", "high-rate-harness-offline-v2", "high-rate-harness-offline-v3",
    "high-rate-harness-offline-v4", "high-rate-harness-offline-v5",
    "high-rate-harness-regression-v1", "high-rate-harness-freeze-attempt-v1",
]]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(output):
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("refusing to overwrite portable receipts")
    selected = {path for path in BUNDLE.rglob("*") if path.is_file()}
    selected.update([REPORT, Path(__file__).resolve()])
    for run in RUNS:
        for path in run.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix in {".log", ".xml"} or path.name in {
                "source-before.json", "source-after-compile.json", "source-after-simulation.json",
                "sources-before.json", "sources-after.json", "fixture-before.json", "fixture-after.json",
                "budget-before-evaluation.json", "run_status.txt", "after_integrity.txt", "prelaunch_receipt.txt",
            }:
                selected.add(path)
            # Retain actual numeric probe outputs; parser-only specimens are
            # already clearly labeled in their simulate.log, not actual data.
            if path.parent.name in {"test_real_native30_and_conditi0", "test_actual_native30_bound_and0", "test_actual_native30_bound_and1"} and path.name in {
                "native30_actual_raw_tuples.txt", "paired_pilot_actual.ci16",
            }:
                selected.add(path)
    payloads = {}
    for path in sorted(selected):
        if path.is_symlink() or not path.is_relative_to(ROOT):
            raise ValueError("unsafe archive source")
        payload = path.read_bytes()
        if len(payload) > 4_000_000:
            raise ValueError("unbounded portable member")
        payloads[str(path.relative_to(ROOT))] = payload
    if sum(map(len, payloads.values())) > 32_000_000:
        raise ValueError("portable receipt exceeds32MB uncompressed")
    receipt = {
        "schema": "starlink-high-rate-prelaunch-portable-v1",
        "source_signature": "413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31",
        "files": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in payloads.items()},
        "excluded": "duplicate pytest prepared/input bundles and policy vectors, generated pytest current symlinks and non-bundle vvp bytecode; all original local attempts retained",
        "actual_fft_launched": False,
    }
    payloads["portable_receipt.json"] = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, payload in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        if {member.name for member in members} != set(payloads) or any(
            not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts for member in members
        ):
            raise ValueError("unsafe/incomplete portable archive")
        for member in members:
            if archive.extractfile(member).read() != payloads[member.name]:
                raise ValueError("portable archive readback mismatch")
    for path in selected:
        if path.read_bytes() != payloads[str(path.relative_to(ROOT))]:
            raise ValueError("source/evidence changed during packaging")
    result = {"archive_sha256": sha(output.read_bytes()), "archive_bytes": output.stat().st_size,
              "regular_members": len(payloads), "receipt_files": len(receipt["files"]),
              "uncompressed_bytes": sum(map(len, payloads.values())), "source_signature": receipt["source_signature"]}
    output.with_suffix(".json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(package(parser.parse_args().output.absolute()), sort_keys=True))
