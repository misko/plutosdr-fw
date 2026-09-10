#!/usr/bin/env python3
"""Bounded portable prelaunch proof; never changes inputs or runs simulators."""

import argparse
import io
import json
import tarfile
from pathlib import Path

from prepare_starlink_high_rate_cases import verify

ROOT = Path(__file__).resolve().parents[1]


def package(output):
    from tests.starlink_oracle.high_rate_harness import sha
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("refusing to overwrite portable proof")
    selected = {Path(__file__).resolve(), ROOT / "docs/starlink-high-rate30-cases-prelaunch-20260910.md"}
    for case in ["healthy343", "late447"]:
        bundle = ROOT / f"build/high-rate-cases-{case}-prelaunch-v1"
        verify(bundle)
        selected.update(path for path in bundle.rglob("*") if path.is_file())
    for name in ["high-rate-cases-offline-v1", "high-rate-cases-offline-v2", "high-rate-cases-offline-v3",
                 "high-rate-cases-offline-v4", "high-rate-cases-regression-v1"]:
        run = ROOT / "build" / name
        for path in run.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(run)
            if set(relative.parts) & {"prepared", "inputs", "base", "native_only_late_evidence", "PARSER_ONLY", "parser_only"}:
                continue  # Full originals are already present in both bundles.
            native_probe = "test_actual_late_native_only_z0" in relative.parts
            if ((native_probe and path.suffix != ".vvp") or path.suffix in {".log", ".xml"} or path.name in {
                "source-before.json", "source-after.json", "source-after-compile.json", "source-after-simulation.json",
                "fixtures-before.json", "fixtures-after.json", "contract-before.json", "after_integrity.txt",
                "run_status.txt", "prelaunch_receipt.txt",
            }):
                selected.add(path)
    payloads = {}
    for path in sorted(selected):
        if path.is_symlink() or not path.is_relative_to(ROOT):
            raise ValueError("unsafe member")
        data = path.read_bytes()
        if len(data) > 4_000_000:
            raise ValueError("unbounded member")
        payloads[str(path.relative_to(ROOT))] = data
    if sum(map(len, payloads.values())) > 32_000_000:
        raise ValueError("proof exceeds32MB uncompressed")
    receipt = {"schema": "starlink-high-rate30-cases-prelaunch-v1", "actual_fft_run": False,
               "source_signature": "b9d4d306fd9665133e36dc21e24125bce9ac7a6b3b34ed335b45fd5e2ba9ab09",
               "files": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in payloads.items()},
               "excluded": "duplicate transient policy bundles, synthetic parser logs and compiled bytecode; all raw local attempts retained"}
    payloads["portable_receipt.json"] = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, data in payloads.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        if {m.name for m in members} != payloads.keys() or any(
            not m.isfile() or m.name.startswith("/") or ".." in Path(m.name).parts for m in members
        ):
            raise ValueError("unsafe/incomplete archive")
        for member in members:
            if archive.extractfile(member).read() != payloads[member.name]:
                raise ValueError("archive readback mismatch")
    for path in selected:
        if path.read_bytes() != payloads[str(path.relative_to(ROOT))]:
            raise ValueError("proof changed during packaging")
    result = {"archive_sha256": sha(output.read_bytes()), "archive_bytes": output.stat().st_size,
              "receipt_files": len(receipt["files"]), "regular_members": len(payloads),
              "uncompressed_bytes": sum(map(len, payloads.values())), "source_signature": receipt["source_signature"]}
    output.with_suffix(".json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(package(parser.parse_args().output.absolute()), sort_keys=True))
