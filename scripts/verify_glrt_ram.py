#!/usr/bin/env python3
"""Verify a local GLR1 RAM package with U-Boot and GNU cpio, without a radio.

This deliberately does not import the packager's FIT/newc implementation.
An independent extraction receipt is evidence of package contents only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_lean_init(archive, members, manifest, cpio):
    """Independently bind the embedded GLF1 init script to its frozen input."""
    selectors = [Path(path) for path in manifest["input_sha256"]
                 if Path(path).name == "legacy_scorer.txt"]
    if len(selectors) > 1:
        raise ValueError("ambiguous legacy scorer selection")
    lean = False
    if selectors:
        selection = selectors[0]
        if digest(selection) != manifest["input_sha256"][str(selection)]:
            raise ValueError("legacy scorer selection changed")
        value = selection.read_text().strip()
        if value not in ("0", "1"):
            raise ValueError("invalid legacy scorer selection")
        lean = value == "0"
    expected = ["opt/VERSIONS"] + (["etc/init.d/S22starlink_glrt_iio"] if lean else [])
    if manifest["rootfs_replaced_members"] != expected:
        raise ValueError("rootfs replacements differ from the selected profile")
    if not lean:
        return
    inputs = [value for path, value in manifest["input_sha256"].items()
              if Path(path).name == "S22starlink_glrt_iio"]
    names = [name for name in members if name.removeprefix("./") == "etc/init.d/S22starlink_glrt_iio"]
    if len(inputs) != 1 or len(names) != 1:
        raise ValueError("lean init input or archive member is ambiguous/missing")
    embedded = subprocess.run([str(cpio), "-i", "--to-stdout", "--quiet", names[0]],
                              input=archive, check=True, capture_output=True).stdout
    if hashlib.sha256(embedded).hexdigest() != inputs[0]:
        raise ValueError("embedded lean init differs from the frozen input")


def verify(package, output, *, dumpimage=None):
    package, output = package.resolve(), output.resolve()
    manifest_path = package / "manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema"] != "starlink-glrt-ram-package/v1":
        raise ValueError("unsupported package schema")
    fit, dfu = package / "pluto.itb", package / "pluto.dfu"
    for path in (fit, dfu):
        if digest(path) != manifest["outputs_sha256"][path.name]:
            raise ValueError("package output changed: " + path.name)
    dumpimage = (dumpimage or ROOT / "buildroot/output/host/bin/dumpimage").resolve()
    cpio = Path(shutil.which("cpio") or "/missing-cpio")
    suffix = Path(shutil.which("dfu-suffix") or "/missing-dfu-suffix")
    tools = {str(p): digest(p) for p in (dumpimage, cpio, suffix, Path(__file__))}
    output.mkdir(parents=True, exist_ok=False)
    payloads = ("zynq-pluto-sdr-glrt.dtb", "system_top.bit", "zImage", "rootfs.cpio.gz")
    embedded = {}
    with (output / "extraction.log").open("x") as log:
        for index, name in enumerate(payloads):
            extracted = output / name
            subprocess.run([str(dumpimage), "-T", "flat_dt", "-p", str(index),
                            "-o", str(extracted), str(fit)],
                           check=True, stdout=log, stderr=subprocess.STDOUT)
            if extracted.read_bytes() != (package / "build" / name).read_bytes():
                raise ValueError("embedded payload differs from assembled input: " + name)
            embedded[name] = digest(extracted)
        subprocess.run([str(suffix), "-c", str(dfu)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    fit_bytes, dfu_bytes = fit.read_bytes(), dfu.read_bytes()
    if len(dfu_bytes) != len(fit_bytes) + 16 or dfu_bytes[:-16] != fit_bytes:
        raise ValueError("DFU is not exactly FIT plus its 16-byte suffix")
    archive = gzip.decompress((output / "rootfs.cpio.gz").read_bytes())
    listing = subprocess.run([str(cpio), "-it", "--quiet"], input=archive,
                             check=True, capture_output=True)
    (output / "cpio-listing.txt").write_bytes(listing.stdout)
    members = listing.stdout.decode().splitlines()
    normalized = [name.removeprefix("./") for name in members]
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate rootfs member")
    if any("starlink_pss" in name or "starlink-pss" in name for name in normalized):
        raise ValueError("rootfs retains a PSS path")
    for required in ("opt/VERSIONS", "etc/init.d/S22starlink_glrt_iio", "usr/sbin/iiod"):
        if required not in normalized:
            raise ValueError("missing GLRT rootfs member: " + required)
    verify_lean_init(archive, members, manifest, cpio)
    versions_name = members[normalized.index("opt/VERSIONS")]
    versions = subprocess.run([str(cpio), "-i", "--to-stdout", "--quiet", versions_name],
                              input=archive, check=True, capture_output=True).stdout
    expected_versions = "device-fw " + manifest["firmware_label"] + "\n" + "".join(
        f"{name} {manifest['source_commits'][name]}\n"
        for name in ("hdl", "linux", "buildroot", "u-boot-xlnx"))
    if versions != expected_versions.encode() or versions != (package / "VERSIONS").read_bytes():
        raise ValueError("embedded VERSIONS does not identify the assembled components")
    (output / "VERSIONS").write_bytes(versions)
    if digest(manifest_path) != manifest_hash or any(digest(Path(p)) != h for p, h in tools.items()):
        raise ValueError("manifest or verification tool changed during extraction")
    for path in (fit, dfu):
        if digest(path) != manifest["outputs_sha256"][path.name]:
            raise ValueError("package changed during verification")
    receipt = {"schema": "starlink-glrt-independent-package-verification/v1", "status": "pass",
               "method": "U-Boot payload extraction and byte comparison; GNU cpio listing and VERSIONS extraction; dfu-suffix validation",
               "manifest_sha256": manifest_hash, "tools_sha256": tools,
               "outputs_sha256": manifest["outputs_sha256"], "embedded_sha256": embedded,
               "rootfs_members": len(members), "versions": versions.decode(),
               "dfu_prefix_matches_fit": True, "hardware_accessed": False,
               "deployment_approved": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dumpimage", type=Path,
                        help="explicit existing U-Boot extractor; recorded by hash")
    args = parser.parse_args()
    receipt = verify(args.package, args.output, dumpimage=args.dumpimage)
    print(json.dumps({"status": receipt["status"], "rootfs_members": receipt["rootfs_members"],
                      "receipt": str(args.output / "receipt.json"), "hardware_accessed": False}))


if __name__ == "__main__":
    main()
