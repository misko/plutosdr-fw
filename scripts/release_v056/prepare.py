#!/usr/bin/env python3
"""Bind a v0.56 qualification plan to one source tree and exact DFU artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
V056_FIRMWARE = "v0.56-plutoplus-spf-adaptive-runtime-rates"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_candidate(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("candidate manifest must be a JSON object")
    return document


def _candidate_source(candidate: dict[str, object]) -> object:
    sources = candidate.get("sources")
    if isinstance(sources, dict) and isinstance(sources.get("firmware_base"), str):
        return sources["firmware_base"]
    return candidate.get("firmware_source_commit") or candidate.get("firmware_source")


def prepare(
    *, repo: Path, source_manifest: Path, candidate_path: Path, image: Path,
    expected_source: str,
) -> dict[str, object]:
    if not COMMIT.fullmatch(expected_source):
        raise ValueError("expected source must be a full lowercase Git commit")
    source_bytes = source_manifest.read_bytes()
    committed = subprocess.check_output(
        ["git", "show", f"{expected_source}:{source_manifest.relative_to(repo)}"], cwd=repo
    )
    if committed != source_bytes:
        raise ValueError("source manifest differs from the expected source commit")
    candidate = load_candidate(candidate_path)
    firmware = candidate.get("firmware") or candidate.get("device_fw")
    source = _candidate_source(candidate)
    if firmware != V056_FIRMWARE:
        raise ValueError(f"candidate must identify {V056_FIRMWARE}")
    if source != expected_source:
        raise ValueError("candidate firmware source differs from expected source")
    image_hash = candidate.get("asset_sha256") or candidate.get("image_sha256")
    if not isinstance(image_hash, str) or not SHA256.fullmatch(image_hash):
        raise ValueError("candidate has no valid DFU SHA-256")
    if digest(image) != image_hash:
        raise ValueError("DFU bytes differ from candidate manifest")
    expected_source_hash = candidate.get("source_manifest_sha256")
    if not isinstance(expected_source_hash, str) or not SHA256.fullmatch(expected_source_hash):
        raise ValueError("candidate has no valid source-manifest SHA-256")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if expected_source_hash != source_hash:
        raise ValueError("source manifest digest differs from candidate manifest")
    return {
        "schema": "plutosdr-fw.v056-qualification-binding/v1",
        "firmware": firmware,
        "source_commit": expected_source,
        "source_manifest": str(source_manifest.resolve()),
        "source_manifest_sha256": source_hash,
        "candidate_manifest": str(candidate_path.resolve()),
        "candidate_manifest_sha256": digest(candidate_path),
        "image": str(image.resolve()),
        "image_sha256": image_hash,
        "image_bytes": image.stat().st_size,
        "utc_accuracy_qualified": False,
    }


def write_new(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = prepare(
        repo=args.repo.resolve(), source_manifest=args.source_manifest.resolve(),
        candidate_path=args.candidate.resolve(), image=args.image.resolve(),
        expected_source=args.expected_source,
    )
    write_new(args.output, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
