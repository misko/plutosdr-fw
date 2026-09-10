#!/usr/bin/env python3
"""Bounded offline60 source/numeric proof; no simulator or receiver operation."""

import argparse
import io
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle.high_rate60_paired import source_hashes, verify
from tests.starlink_oracle.high_rate_paired import digest, json_bytes


def package(output):
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("refusing to overwrite offline proof")
    final = ROOT / "build/high-rate60-offline-v2/cohort"
    info = verify(final)
    first = ROOT / "build/high-rate60-offline-v1/cohort"
    original = json.loads((first / "cohort.json").read_bytes())
    if original["files"] != info["files"] or source_hashes() != info["source_sha256"]:
        raise ValueError("numeric69 or final live sources changed")
    selected = {Path(__file__).resolve(), ROOT / "docs/starlink-high-rate60-offline-cohort-20260910.md"}
    for cohort in [first, final]:
        selected.update(p for p in cohort.rglob("*") if p.is_file())
        selected.update(p for p in cohort.parent.iterdir() if p.is_file() and p.suffix in {".log", ".xml"})
    payloads = {}
    for path in sorted(selected):
        if path.is_symlink() or not path.is_relative_to(ROOT) or path.stat().st_size > 4_000_000:
            raise ValueError("unsafe/unbounded member")
        payloads[str(path.relative_to(ROOT))] = path.read_bytes()
    if sum(map(len, payloads.values())) > 16_000_000:
        raise ValueError("offline proof exceeds16MB")
    receipt = {"schema": "starlink-high-rate60-offline-portable-v1", "actual_RTL": False,
               "source_signature": digest(json_bytes(info["source_sha256"])), "numeric69_v1_v2_equal": True,
               "files": {name: {"bytes": len(data), "sha256": digest(data)} for name, data in payloads.items()},
               "excluded": "intentionally corrupted pytest fixture copies and third-party binaries; all original local attempts retained"}
    payloads["portable_receipt.json"] = json_bytes(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, data in payloads.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(data), 0o644, 0
            archive.addfile(member, io.BytesIO(data))
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
    result = {"archive_sha256": digest(output.read_bytes()), "archive_bytes": output.stat().st_size,
              "regular_members": len(payloads), "receipt_files": len(receipt["files"]),
              "source_signature": receipt["source_signature"], "cohort_sha256": digest((final / "cohort.json").read_bytes())}
    output.with_suffix(".json").write_bytes(json_bytes(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(package(parser.parse_args().output.absolute()), sort_keys=True))
