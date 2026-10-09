#!/usr/bin/env python3
"""Package the continuous scanner over the exact published v0.61 parent.

Only installed iiOD, its matching libiio, and /opt/VERSIONS change. Kernel,
FPGA, DTBs, FIT configurations, rootfs inventory and metadata are preserved.
This is component replacement, not a full Buildroot rebuild.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import stat
import subprocess
from pathlib import Path

from fit import Fit

ROOT = Path(__file__).resolve().parents[2]
PARENT_SHA = "ad5e6a350f65e11d4cd68013a3de4b2a62d7a6bec15bba210b5ccad65b727362"
VERSION = "v0.62-plutoplus-spf-continuous-fast-scan"
EPOCH = 1791504000
spec = importlib.util.spec_from_file_location("cpio", ROOT / "scripts/feature103/package_candidate.py")
cpio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpio)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*command):
    return subprocess.check_output(command, text=True).strip()


def archive(entries):
    """Keep inode, permissions, owners, times, devices and order exactly."""
    output = bytearray()
    for name, (metadata, payload) in list(entries.items()) + [("TRAILER!!!", ([0] * 13, b""))]:
        fields = list(metadata)
        fields[6], fields[11] = len(payload), len(name.encode()) + 1
        output.extend(b"070701" + b"".join(f"{v:08x}".encode() for v in fields))
        output.extend(name.encode() + b"\0")
        output.extend(bytes(-len(output) % 4))
        output.extend(payload)
        output.extend(bytes(-len(output) % 4))
    output.extend(bytes(-len(output) % 512))
    expected = {n: (m[:6] + [len(p)] + m[7:], p) for n, (m, p) in entries.items()}
    parsed = cpio.read_newc(output)
    require(parsed == expected and list(parsed) == list(entries), "rootfs round-trip changed metadata or order")
    return bytes(output)


def rootfs(base, replacements, source):
    entries = cpio.read_newc(gzip.decompress(base))
    original = dict(entries)
    require(set(replacements) == {"usr/sbin/iiod", "usr/lib/libiio.so.0.25"}, "unexpected executable inventory")
    for name, payload in replacements.items():
        require(name in entries and stat.S_ISREG(entries[name][0][1]), "missing regular file " + name)
        entries[name] = (entries[name][0], payload)
    name = "opt/VERSIONS"
    lines = entries[name][1].decode().splitlines()
    require("device-fw v0.61-plutoplus-spf-fastlock-timeout-fix" in lines, "parent version mismatch")
    lines = cpio.replace_version(lines, "device-fw", VERSION)
    lines = cpio.replace_version(lines, "libiio", source)
    entries[name] = (entries[name][0], ("\n".join(lines) + "\n").encode())
    changed = {n: {"before": sha(original[n][1]), "after": sha(p)} for n, (_, p) in entries.items() if p != original[n][1]}
    require(set(changed) == set(replacements) | {name}, "replacement did not change exactly approved files")
    return gzip.compress(archive(entries), compresslevel=9, mtime=EPOCH), changed


def replace_ramdisk(body, replacement):
    fit = Fit(body, len(body) + len(replacement) + 4096)
    before = fit.nodes()
    path = "/images/ramdisk@1"
    require(before[path].get("compression") == b"gzip\0", "unexpected rootfs compression")
    require(not any("signature" in n for n in before), "signed FIT is not supported")
    changes = {(path, "data"): replacement}
    unchanged = {}
    for node, props in before.items():
        if node.startswith("/images/") and node.count("/") == 2:
            require(props.get("data") and not {"data-offset", "data-position", "data-size"} & props.keys(), "expected inline FIT component")
            if node != path:
                unchanged[node] = sha(props["data"])
        if node.startswith("/images/") and node.count("/") == 3:
            algo = props.get("algo", b"").removesuffix(b"\0").decode()
            require(algo in {"md5", "sha1", "sha256"}, "unsupported FIT hash")
            parent = node.rsplit("/", 1)[0]
            require(props.get("value") == hashlib.new(algo, before[parent]["data"]).digest(), "parent FIT hash mismatch")
            if parent == path:
                changes[(node, "value")] = hashlib.new(algo, replacement).digest()
    require(len(changes) >= 2, "missing ramdisk integrity hash")
    expected = {n: dict(p) for n, p in before.items()}
    for (node, prop), value in changes.items():
        fit.replace(node, prop, value)
        expected[node][prop] = value
    packed = fit.packed()
    require(Fit(packed).nodes() == expected, "protected FIT property changed")
    return packed, unchanged


def check_elf(path, library=False):
    header = run("readelf", "-h", str(path))
    require("ARM" in header and "ELF32" in header, "expected 32-bit ARM executable")
    dynamic = run("readelf", "-d", str(path))
    require("RPATH" not in dynamic and "RUNPATH" not in dynamic, "installed ELF contains RPATH")
    if library:
        require("Library soname: [libiio.so.0]" in dynamic, "unexpected library SONAME")
    else:
        require("Shared library: [libiio.so.0]" in dynamic, "daemon does not use matching libiio")
    return dynamic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--iiod", type=Path, required=True)
    p.add_argument("--iiod-sha256", required=True)
    p.add_argument("--libiio", type=Path, required=True)
    p.add_argument("--libiio-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    parent = args.parent.read_bytes()
    require(sha(parent) == PARENT_SHA, "parent differs from published v0.61 DFU")
    require(run("git", "-C", str(args.source), "rev-parse", "HEAD") == args.source_commit, "source commit mismatch")
    require(not run("git", "-C", str(args.source), "status", "--porcelain", "--untracked-files=no"), "dirty tracked source")
    require(not (args.source / "power-scanner").exists(), "FPGA power controller must not enter this release")
    daemon, library = args.iiod.read_bytes(), args.libiio.read_bytes()
    require(sha(daemon) == args.iiod_sha256 and sha(library) == args.libiio_sha256, "installed binary hash mismatch")
    dependencies = {"iiod": check_elf(args.iiod), "libiio": check_elf(args.libiio, library=True)}
    parent_fit = cpio.fit_body(parent)
    original = Fit(parent_fit).nodes()["/images/ramdisk@1"]["data"]
    compressed, changes = rootfs(original, {"usr/sbin/iiod": daemon, "usr/lib/libiio.so.0.25": library}, args.source_commit)
    fit, unchanged = replace_ramdisk(parent_fit, compressed)
    dfu = cpio.add_dfu_suffix(fit)
    frm = fit + hashlib.md5(fit).hexdigest().encode() + b"\n"
    require(cpio.fit_body(dfu) == fit and frm[:-33] == fit, "container body mismatch")
    result = {
        "schema": "plutosdr-fw.continuous-scan-artifact/v1", "firmware": VERSION,
        "packaging": "installed-userspace-replacement-over-v061",
        "parent_dfu_sha256": PARENT_SHA, "parent_fit_sha256": sha(parent_fit),
        "libiio_source": args.source_commit, "iiod_sha256": sha(daemon), "libiio_sha256": sha(library),
        "changed_rootfs_files": changes, "rootfs_metadata_and_inventory_preserved": True,
        "unchanged_components": unchanged, "all_other_fit_properties_preserved": True,
        "fit_sha256": sha(fit), "fit_bytes": len(fit), "dfu_sha256": sha(dfu), "dfu_bytes": len(dfu),
        "frm_sha256": sha(frm), "frm_bytes": len(frm), "elf_dependencies": dependencies,
        "hardware_qualified": False,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    for suffix, data in (("itb", fit), ("dfu", dfu), ("frm", frm)):
        (args.output / ("plutoplus-spf-continuous-fast-scan-v062-pluto." + suffix)).write_bytes(data)
    (args.output / "artifact.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
