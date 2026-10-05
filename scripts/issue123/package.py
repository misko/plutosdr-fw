"""Package issue 123 kernel and iiOD into the verified v0.60 firmware parent.

This is a reproducible component replacement, not a full Buildroot rebuild.
The qualified Fast Lock kernel and integrated iiOD replace their v0.60 counterparts.
FPGA, device trees, libraries, device nodes and file metadata are preserved.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT_SHA = "521ab9d36ade7ff4f278e699be6c080a7e7af1b7353de7d62189300caea7fb20"
VERSION = "v0.61-plutoplus-spf-fastlock-timeout-fix"
SOURCE = "461722230e9d645d368eeb623dd7e80709c7ada9"
EPOCH = 1791212400


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--libiio", type=Path, required=True)
    p.add_argument("--kernel", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--linux", type=Path, required=True)
    p.add_argument("--version", default=VERSION)
    args = p.parse_args()
    version = args.version
    linux_source = run("git", "-C", str(args.linux), "rev-parse", "HEAD").strip()
    require(not run("git", "-C", str(args.linux), "diff", "HEAD"), "dirty kernel source")
    spec = importlib.util.spec_from_file_location(
        "pack", ROOT / "scripts/feature103/package_candidate.py"
    )
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    parent = args.parent.read_bytes()
    if sha(parent) != PARENT_SHA:
        raise ValueError("parent DFU differs from the qualified v0.60 artifact")
    source = run("git", "-C", str(args.libiio), "rev-parse", "HEAD").strip()
    if source != SOURCE or run(
        "git", "-C", str(args.libiio), "diff", "HEAD", "--", "iiod", "tests"
    ):
        raise ValueError("libiio source differs from reviewed issue-123 commit")
    binary = (args.libiio / "build-arm/iiod/iiod").read_bytes()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline = output / "parent.itb"
    baseline.write_bytes(pack.fit_body(parent))
    indexes = pack.fit_indexes(baseline)
    parts = {}
    for name, index in indexes.items():
        file = output / f"component-{index}.bin"
        parts[name] = (file, pack.extract_component(baseline, index, file))
    kernel = args.kernel.read_bytes()
    parts["linux_kernel@1"][0].write_bytes(kernel)
    entries = pack.read_newc(gzip.decompress(parts["ramdisk@1"][1]))
    original = dict(entries)
    entries["usr/sbin/iiod"] = (entries["usr/sbin/iiod"][0], binary)
    versions = entries["opt/VERSIONS"][1].decode().splitlines()
    versions = [
        "device-fw " + version if x.startswith("device-fw ") else x for x in versions
    ]
    versions = [
        "linux " + linux_source
        if x.startswith("linux ")
        else x
        for x in versions
    ]
    versions = [x for x in versions if not x.startswith("libiio ")]
    versions.append("libiio " + source)
    entries["opt/VERSIONS"] = (
        entries["opt/VERSIONS"][0],
        ("\n".join(versions) + "\n").encode(),
    )
    changed = {
        name: {"before": sha(original[name][1]), "after": sha(value[1])}
        for name, value in entries.items()
        if value[1] != original[name][1]
    }
    require(
        set(changed) == {"usr/sbin/iiod", "opt/VERSIONS"},
        "Validation failed: set(changed) == {'usr/sbin/iiod', 'opt/VERSIONS'}",
    )
    archive = bytearray()
    for name, (metadata, payload) in list(entries.items()) + [
        ("TRAILER!!!", ([0] * 13, b""))
    ]:
        fields = metadata.copy()
        fields[6], fields[11] = (len(payload), len(name.encode()) + 1)
        archive.extend(b"070701" + b"".join(f"{v:08x}".encode() for v in fields))
        archive.extend(name.encode() + b"\x00")
        archive.extend(bytes(-len(archive) % 4))
        archive.extend(payload)
        archive.extend(bytes(-len(archive) % 4))
    archive.extend(bytes(-len(archive) % 512))
    require(
        pack.read_newc(archive)
        == {
            name: (fields[:6] + [len(data)] + fields[7:], data)
            for name, (fields, data) in entries.items()
        },
        "Validation failed: pack.read_newc(archive) == {name: (fields[:6] + [len(data)] + fields[7:], data) for name, (fields, data) in entries.items()}",
    )
    parts["ramdisk@1"][0].write_bytes(
        gzip.compress(archive, compresslevel=9, mtime=EPOCH)
    )
    dts = run("dtc", "-I", "dtb", "-O", "dts", str(baseline), stderr=subprocess.DEVNULL)
    ordered = iter((file.name for file, _ in parts.values()))
    dts, count = re.subn(
        "\\bdata\\s*=\\s*.*?;",
        lambda _: 'data = /incbin/("' + next(ordered) + '");',
        dts,
        flags=re.DOTALL,
    )
    require(count == len(parts), "Validation failed: count == len(parts)")
    (output / "candidate.its").write_text(dts)
    image = output / "issue123.itb"
    subprocess.run(
        ["mkimage", "-f", "candidate.its", image.name],
        cwd=output,
        env=os.environ | {"SOURCE_DATE_EPOCH": str(EPOCH)},
        check=True,
        stdout=(output / "mkimage.log").open("w"),
        stderr=subprocess.STDOUT,
    )
    for name, index in pack.fit_indexes(image).items():
        data = pack.extract_component(image, index, output / f"verify-{index}.bin")
        require(
            data == parts[name][0].read_bytes(),
            "Validation failed: data == parts[name][0].read_bytes()",
        )
        if name not in ("ramdisk@1", "linux_kernel@1"):
            require(data == parts[name][1], "Validation failed: data == parts[name][1]")
    fit = image.read_bytes()
    dfu = pack.add_dfu_suffix(fit)
    (output / "issue123.dfu").write_bytes(dfu)
    (output / "issue123.frm").write_bytes(
        fit + hashlib.md5(fit).hexdigest().encode() + b"\n"
    )
    manifest = {
        "schema": "plutosdr-fw.issue123-artifact/v1",
        "firmware": version,
        "parent_dfu_sha256": PARENT_SHA,
        "libiio_source": source,
        "linux_source": linux_source,
        "kernel_sha256": sha(kernel),
        "iiod_sha256": sha(binary),
        "changed_rootfs_files": changed,
        "fit_sha256": sha(fit),
        "fit_bytes": len(fit),
        "dfu_sha256": sha(dfu),
        "dfu_bytes": len(dfu),
        "unchanged_components": {
            n: sha(data)
            for n, (_, data) in parts.items()
            if n not in ("ramdisk@1", "linux_kernel@1")
        },
    }
    (output / "artifact.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
