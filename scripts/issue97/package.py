#!/usr/bin/env python3
"""Build a reviewable candidate from the verified v0.49 FIT and rebuilt ARM parts.

Preserve cpio device nodes, ownership, permissions, and unmodified payload bytes.
The input baseline is deliberately immutable; this is not a full Buildroot build.
"""

import gzip
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build"
VERSION = "v0.49-plutoplus-spf-counter-rx-v1-rc1"
EPOCH = 1789257600
BASE = "77f899610548d486aab2c83c4dc7170532d470b115d2bd0e8fc43e72b3bfca67"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_cpio(data):
    offset = 0
    result = {}
    while True:
        assert data[offset : offset + 6] == b"070701"
        fields = [
            int(data[offset + 6 + i * 8 : offset + 14 + i * 8], 16) for i in range(13)
        ]
        size, name_size = fields[6], fields[11]
        start = offset + 110
        name = data[start : start + name_size - 1].decode()
        start = (start + name_size + 3) & ~3
        payload = data[start : start + size]
        assert len(payload) == size
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            return result
        assert name not in result
        result[name] = (fields, payload)


def write_cpio(entries):
    out = bytearray()
    for inode, (name, (original, data)) in enumerate(entries.items(), 1):
        fields = list(original)
        fields[0], fields[6], fields[11] = inode, len(data), len(name.encode()) + 1
        out.extend(b"070701" + b"".join(f"{v:08x}".encode() for v in fields))
        out.extend(name.encode() + b"\0")
        out.extend(bytes(-len(out) % 4))
        out.extend(data)
        out.extend(bytes(-len(out) % 4))
    out.extend(bytes(-len(out) % 512))
    return bytes(out)


def main():
    baseline = (B / "baseline.itb").read_bytes()
    assert sha(baseline) == BASE
    entries = read_cpio(gzip.decompress((B / "baseline-rootfs.cpio.gz").read_bytes()))
    original = dict(entries)
    for target, source in {
        "usr/sbin/iiod": B / "libiio-arm/iiod/iiod",
        "usr/lib/libiio.so.0.25": B / "libiio-arm/libiio.so.0.25",
    }.items():
        fields, _ = entries[target]
        assert stat.S_ISREG(fields[1])
        entries[target] = (fields, source.read_bytes())
    versions = entries["opt/VERSIONS"][1].decode().splitlines()
    versions = [
        "device-fw " + VERSION
        if l.startswith("device-fw ")
        else "linux 4683cd2e3556448295e03a216a3a7fc6e8bbc474"
        if l.startswith("linux ")
        else l
        for l in versions
    ]
    versions.append("libiio 47a75cbc5e7d24a063b8b54eb531fdba6602b85c")
    entries["opt/VERSIONS"] = (
        entries["opt/VERSIONS"][0],
        ("\n".join(versions) + "\n").encode(),
    )
    assert not any(n.startswith("lib/modules/") for n in entries), (
        "unexpected baseline modules"
    )
    module_root = B / "modules"
    for path in sorted((module_root / "lib/modules").rglob("*")):
        if path.is_symlink():
            assert path.name in {"source", "build"}
            continue
        name = str(path.relative_to(module_root))
        fields = [0, path.stat().st_mode, 0, 0, 1, EPOCH, 0, 0, 0, 0, 0, 0, 0]
        entries[name] = (fields, path.read_bytes() if path.is_file() else b"")
    if "lib/modules" not in entries:
        entries["lib/modules"] = (
            [0, stat.S_IFDIR | 0o755, 0, 0, 2, EPOCH, 0, 0, 0, 0, 0, 0, 0],
            b"",
        )
    changed = {
        n: {"before": sha(original[n][1]), "after": sha(v[1])}
        for n, v in entries.items()
        if n in original and v[1] != original[n][1]
    }
    assert set(changed) == {"usr/sbin/iiod", "usr/lib/libiio.so.0.25", "opt/VERSIONS"}
    entries = dict(sorted(entries.items()))
    entries["TRAILER!!!"] = ([0] * 13, b"")
    archive = write_cpio(entries)
    reread = read_cpio(archive)
    assert {n: v[1] for n, v in reread.items()} == {
        n: v[1] for n, v in entries.items() if n != "TRAILER!!!"
    }
    (B / "rootfs.cpio.gz").write_bytes(
        gzip.compress(archive, compresslevel=9, mtime=EPOCH)
    )
    shutil.copyfile(B / "linux/arch/arm/boot/zImage", B / "zImage")
    image = B / "counter-rx-v1-rc1.itb"
    subprocess.run(
        ["mkimage", "-f", "scripts/pluto.its", str(image)],
        cwd=ROOT,
        env=os.environ | {"SOURCE_DATE_EPOCH": str(EPOCH)},
        check=True,
    )
    fit = image.read_bytes()
    # DFU suffix: same bcdDevice/product/vendor/DFU version as the baseline.
    suffix = struct.pack("<HHHH3sB", 0xFFFF, 0xB673, 0x0456, 0x0100, b"UFD", 16)
    body = fit + suffix
    dfu = body + struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF)
    output = B / "counter-rx-v1-rc1.dfu"
    output.write_bytes(dfu)
    manifest = {
        "firmware": VERSION,
        "serial": "1040007c4a94000211000b009186843ef2",
        "baseline_fit_sha256": BASE,
        "fit_sha256": sha(fit),
        "fit_size": len(fit),
        "asset_sha256": sha(dfu),
        "asset_path": str(output),
        "changed_rootfs_files": changed,
        "components": {
            p: sha((B / p).read_bytes())
            for p in (
                "zImage",
                "system_top.bit",
                "rootfs.cpio.gz",
                "zynq-pluto-sdr.dtb",
                "zynq-pluto-sdr-revb.dtb",
                "zynq-pluto-sdr-revc.dtb",
            )
        },
        "sources": {
            "firmware_base": "bc00edb8c340dd4f9b04361398cbd2c8edcc9cae",
            "linux": "4683cd2e3556448295e03a216a3a7fc6e8bbc474",
            "libiio": "47a75cbc5e7d24a063b8b54eb531fdba6602b85c",
            "metadata": "3294365ff44da26b261be4a2ccb241b7896d23ad",
        },
    }
    (B / "counter-rx-v1-rc1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
