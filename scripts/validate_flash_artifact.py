#!/usr/bin/env python3
"""Validate persistent FIT/FRM geometry against an explicit packaged-DT profile."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def extract_flat_dt(fit: Path, index: int, destination: Path) -> None:
    """Extract one FIT component with current or pinned-Buildroot dumpimage."""
    try:
        output(
            "dumpimage",
            "-T",
            "flat_dt",
            "-p",
            str(index),
            "-o",
            str(destination),
            str(fit),
        )
        return
    except subprocess.CalledProcessError as modern_error:
        destination.unlink(missing_ok=True)
        try:
            # U-Boot 2017's dumpimage uses -i for the input and the final
            # positional argument for the output. The protected source graph's
            # Buildroot host tool still has that interface.
            output(
                "dumpimage",
                "-i",
                str(fit),
                "-T",
                "flat_dt",
                "-p",
                str(index),
                str(destination),
            )
            return
        except subprocess.CalledProcessError as legacy_error:
            raise ValueError(
                "dumpimage could not extract FIT component "
                f"{index} with modern or legacy syntax "
                f"(modern={modern_error.returncode}, legacy={legacy_error.returncode})"
            ) from legacy_error


def validate(path: Path, profile_path: Path, target: str, *, frm: bool) -> dict:
    profile = json.loads(profile_path.read_text())
    if profile.get("schema") != "plutosdr-fw.flash-layout.v1" or profile.get("target") != target:
        raise ValueError("missing or mismatched layout profile")
    if profile.get("profile") != "legacy-update":
        raise ValueError("no extended persistent qualification is enabled")
    fields = ("flash_bytes", "address_limit", "firmware_start", "firmware_bytes", "erase_bytes")
    if any(type(profile.get(k)) is not int or not 0 <= profile[k] <= 0xFFFFFFFF for k in fields):
        raise ValueError("invalid layout byte counts")
    if profile["address_limit"] > min(profile["flash_bytes"], 0x1000000):
        raise ValueError("legacy profile exceeds conservative physical limit")
    if profile["firmware_start"] + profile["firmware_bytes"] > profile["flash_bytes"]:
        raise ValueError("partition exceeds flash capacity")
    payload = path.read_bytes()
    if frm:
        if len(payload) <= 33 or payload[-33:] != hashlib.md5(payload[:-33]).hexdigest().encode() + b"\n":
            raise ValueError("invalid FRM checksum/trailer")
        payload = payload[:-33]
    if len(payload) < 40:
        raise ValueError("truncated FIT")
    magic, total = struct.unpack_from(">II", payload)
    if magic != 0xD00DFEED or total != len(payload):
        raise ValueError("FIT header length/magic mismatch")
    result = output("sh", str(ROOT / "buildroot/board/pluto/pluto-flash-range"),
                    str(profile["firmware_start"]), str(profile["firmware_bytes"]),
                    str(profile["erase_bytes"]), str(len(payload)), str(profile["address_limit"]))
    with tempfile.TemporaryDirectory(prefix="pluto-flash-artifact-") as scratch:
        fit = Path(scratch) / "image.itb"
        fit.write_bytes(payload)
        output("dumpimage", "-l", str(fit))
        images = output("fdtget", "-l", str(fit), "/images").splitlines()
        checked = 0
        for index, name in enumerate(images):
            if output("fdtget", "-t", "s", str(fit), f"/images/{name}", "type") != "flat_dt":
                continue
            dtb = Path(scratch) / f"{index}.dtb"
            extract_flat_dt(fit, index, dtb)
            node = profile["firmware_node"]
            if output("fdtget", "-t", "s", str(dtb), node, "label") != "qspi-linux":
                raise ValueError("packaged DT firmware partition role mismatch")
            reg = [int(v) for v in output("fdtget", "-t", "u", str(dtb), node, "reg").split()]
            if reg != [profile["firmware_start"], profile["firmware_bytes"]]:
                raise ValueError("packaged DT does not match flash layout profile")
            checked += 1
        if not checked:
            raise ValueError("FIT has no device trees to verify against layout")
    return {"schema": "plutosdr-fw.flash-artifact-check.v1", "profile": profile,
            "fit_bytes": len(payload), "fit_sha256": hashlib.sha256(payload).hexdigest(),
            "device_trees_checked": checked, "ranges": dict(line.split("=", 1) for line in result.splitlines())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fit", type=Path)
    group.add_argument("--frm", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    try:
        result = validate(args.frm or args.fit, args.profile, args.target, frm=args.frm is not None)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Persistent artifact refused: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
