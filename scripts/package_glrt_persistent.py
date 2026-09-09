#!/usr/bin/env python3
"""Produce canonical pluto.frm from an independently verified GLRT FIT.

Only local files are read/written. A new immutable receipt binds the persistent
payload to its RAM package/extraction evidence; it grants no hardware status.
The FRM encoding is the existing firmware Makefile's FIT + md5sum + newline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package(source: Path, verification: Path, output: Path) -> dict:
    source, verification, output = source.resolve(), verification.resolve(), output.resolve()
    manifest_path, fit_path = source / "manifest.json", source / "pluto.itb"
    inputs = (manifest_path, fit_path, verification, Path(__file__).resolve())
    before = {str(path): digest(path) for path in inputs}
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads(verification.read_text())
    if manifest.get("schema") != "starlink-glrt-ram-package/v1":
        raise ValueError("unsupported RAM package schema")
    if (receipt.get("schema") != "starlink-glrt-independent-package-verification/v1"
            or receipt.get("status") != "pass"
            or receipt.get("manifest_sha256") != before[str(manifest_path)]
            or receipt.get("outputs_sha256") != manifest.get("outputs_sha256")):
        raise ValueError("independent extraction does not attest this RAM package")
    if manifest.get("outputs_sha256", {}).get("pluto.itb") != before[str(fit_path)]:
        raise ValueError("FIT differs from verified package")
    fit = fit_path.read_bytes()
    # FDT total size excludes any appended DFU suffix, FRM checksum or garbage.
    if len(fit) < 40 or struct.unpack_from(">II", fit) != (0xD00DFEED, len(fit)):
        raise ValueError("FIT is not exactly one complete FDT payload")
    checksum = hashlib.md5(fit, usedforsecurity=False).hexdigest().encode() + b"\n"
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise ValueError("package evidence changed during persistent assembly")
    output.mkdir(parents=True, exist_ok=False)
    frm_path = output / "pluto.frm"
    with frm_path.open("xb") as stream:
        stream.write(fit + checksum)
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise ValueError("package evidence changed during persistent assembly")
    result = {
        "schema": "starlink-glrt-persistent-package/v1",
        "firmware_label": manifest["firmware_label"],
        "source_rate_hz": manifest["source_rate_hz"],
        "output_rate_hz": manifest["output_rate_hz"],
        "edge": manifest["edge"], "source_commits": manifest["source_commits"],
        "input_sha256": before, "fit_sha256": before[str(fit_path)],
        "fit_bytes": len(fit), "frm_bytes": frm_path.stat().st_size,
        "frm_sha256": digest(frm_path),
        "encoding": "exact verified FIT followed by lowercase ASCII MD5 and newline (33 bytes)",
        "hardware_accessed": False, "hardware_qualified": False,
        "deployment_approved": False,
    }
    with (output / "manifest.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True,
                        help="receipt.json from verify_glrt_ram.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = package(args.package, args.verification, args.output)
    print(json.dumps({key: result[key] for key in
                      ("firmware_label", "fit_sha256", "frm_sha256", "hardware_qualified")}))


if __name__ == "__main__":
    main()
