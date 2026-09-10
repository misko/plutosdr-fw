#!/usr/bin/env python3
"""Install a pinned finite native controller into a copy of the radio rootfs.

This creates an input for package_glrt_ram.py without changing its published
manifest. It does not enable RX or install an automatic startup service.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

from scripts.package_glrt_ram import Entry, read_newc, write_newc

MEMBER = "usr/sbin/glrt_native_radio"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_static_arm(data):
    """Reject a host binary or an executable requiring an absent interpreter."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("controller must be a complete little-endian ELF32 executable")
    kind, machine, version = struct.unpack_from("<HHI", data, 16)
    phoff, = struct.unpack_from("<I", data, 28)
    flags, = struct.unpack_from("<I", data, 36)
    ehsize, phsize, count = struct.unpack_from("<HHH", data, 40)
    if (kind != 2 or machine != 40 or version != 1 or ehsize != 52
            or flags & 0xff000000 != 0x05000000 or not flags & 0x400
            or flags & 0x200 or phsize != 32 or not count
            or phoff < 52 or phoff + count * phsize > len(data)):
        raise ValueError("controller must be an ARM EABI5 hard-float executable")
    load = False
    for index in range(count):
        ptype, offset, _, _, size, memory, _, _ = struct.unpack_from("<8I", data, phoff + index * phsize)
        if ptype in (2, 3):
            raise ValueError("controller must be statically linked")
        if offset + size > len(data) or (ptype == 1 and size > memory):
            raise ValueError("controller has a truncated or invalid segment")
        load |= ptype == 1
    if not load:
        raise ValueError("controller has no load segment")


def install(compressed, binary):
    require_static_arm(binary)
    entries = read_newc(gzip.decompress(compressed))
    by_name = {entry.name.removeprefix("./"): entry for entry in entries}
    if len(by_name) != len(entries):
        raise ValueError("duplicate rootfs member")
    if MEMBER in by_name:
        raise ValueError("rootfs already contains a native controller")
    for parent in ("usr", "usr/sbin"):
        if parent not in by_name or by_name[parent].fields[1] & 0o170000 != 0o040000:
            raise ValueError("controller parent is not a directory: " + parent)
    fields = [0] * 13
    fields[0] = max(entry.fields[0] for entry in entries) + 1
    fields[1], fields[4] = 0o100755, 1
    entries.insert(-1, Entry(MEMBER, fields, binary))
    return gzip.compress(write_newc(entries), mtime=0)


def stage(rootfs, binary, build_receipt, output):
    original, executable, receipt_bytes = rootfs.read_bytes(), binary.read_bytes(), build_receipt.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("scope") != "native_controller_arm_build" or sha(executable) != receipt.get("binary_sha256"):
        raise ValueError("controller differs from its build receipt")
    if not receipt.get("source_sha256"):
        raise ValueError("build receipt has no source evidence")
    for path, expected in receipt["source_sha256"].items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError("controller source differs from its build receipt: " + path)
    result = install(original, executable)
    output.mkdir(parents=True, exist_ok=False)
    (output / "rootfs.cpio.gz").write_bytes(result)
    manifest = {"schema": "glrt-native-controller-rootfs/v1", "controller_member": MEMBER,
                "controller_mode": "0755", "controller_sha256": sha(executable),
                "build_receipt_sha256": sha(receipt_bytes),
                "firmware_commit": receipt["firmware_commit"],
                "input_rootfs_sha256": sha(original), "output_rootfs_sha256": sha(result),
                "script_sha256": sha(Path(__file__).read_bytes()),
                "automatic_start_installed": False, "hardware_accessed": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rootfs", "binary", "build-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.rootfs, args.binary, args.build_receipt, args.output)))


if __name__ == "__main__":
    main()
