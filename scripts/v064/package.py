"""Build a bound v0.64 image from the published v0.63 and installed ARM components."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import stat
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/v063"))
from fit import Fit

spec = importlib.util.spec_from_file_location("v063_package", ROOT / "scripts/v063/package.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
sys.path.pop(0)

VERSION = "v0.64-plutoplus-spf-position-scan"
PARENT_SHA = "3715beff0ab6d2060437729e1ec82fd672fd475989e4295943715147c39db04b"
EPOCH = 1795737600
require, sha = legacy.require, legacy.sha


def replace_rootfs(compressed, replacements, linux_source, libiio_source):
    entries = legacy.cpio.read_newc(gzip.decompress(compressed))
    original = dict(entries)
    require(set(replacements) == {"usr/sbin/iiod", "usr/lib/libiio.so.0.25"},
            "unexpected executable inventory")
    for name, payload in replacements.items():
        require(name in entries and stat.S_ISREG(entries[name][0][1]), "missing regular file " + name)
        entries[name] = (entries[name][0], payload)
    name = "opt/VERSIONS"
    lines = entries[name][1].decode().splitlines()
    require("device-fw v0.63-plutoplus-spf-continuous-fast-scan" in lines, "parent version mismatch")
    for field, value in (("device-fw", VERSION), ("linux", linux_source), ("libiio", libiio_source)):
        require(sum(line.startswith(field + " ") for line in lines) == 1, "ambiguous version " + field)
        lines = legacy.cpio.replace_version(lines, field, value)
    entries[name] = (entries[name][0], ("\n".join(lines) + "\n").encode())
    changed = {name: {"before": sha(original[name][1]), "after": sha(payload)}
               for name, (_, payload) in entries.items() if payload != original[name][1]}
    require(set(changed) == set(replacements) | {"opt/VERSIONS"}, "replacement inventory mismatch")
    return gzip.compress(legacy.archive(entries), compresslevel=9, mtime=EPOCH), changed


def replace_components(body, replacements):
    require(set(replacements) == {"/images/linux_kernel@1", "/images/ramdisk@1"},
            "unexpected FIT replacement inventory")
    fit = Fit(body, len(body) + sum(map(len, replacements.values())) + 4096)
    before = fit.nodes()
    require(not any("signature" in path for path in before), "signed FIT is not supported")
    require(before.get("/images/ramdisk@1", {}).get("compression") == b"gzip\0", "unexpected ramdisk compression")
    expected = {path: dict(props) for path, props in before.items()}
    hashes = {path: 0 for path in replacements}
    for path, props in before.items():
        if path.startswith("/images/") and path.count("/") == 2:
            require(props.get("data") and not {"data-offset", "data-position", "data-size"} & props.keys(),
                    "expected inline FIT component")
        if path.startswith("/images/") and path.count("/") == 3:
            algo = props.get("algo", b"").removesuffix(b"\0").decode()
            require(algo in {"md5", "sha1", "sha256"}, "unsupported FIT hash")
            parent = path.rsplit("/", 1)[0]
            require(props.get("value") == hashlib.new(algo, before[parent]["data"]).digest(),
                    "parent FIT hash mismatch")
            if parent in replacements:
                expected[path]["value"] = hashlib.new(algo, replacements[parent]).digest()
                fit.replace(path, "value", expected[path]["value"])
                hashes[parent] += 1
    for path, payload in replacements.items():
        require(path in before and hashes[path] > 0, "missing protected component or hash " + path)
        expected[path]["data"] = payload
        fit.replace(path, "data", payload)
    packed = fit.packed()
    require(Fit(packed).nodes() == expected, "protected FIT property changed")
    unchanged = {path: sha(props["data"]) for path, props in before.items()
                 if path.startswith("/images/") and path.count("/") == 2 and path not in replacements}
    return packed, unchanged


def checked_source(path, expected):
    require(len(expected) == 40 and all(char in "0123456789abcdef" for char in expected), "invalid source commit")
    require(legacy.run("git", "-C", str(path), "rev-parse", "HEAD") == expected, "source commit mismatch")
    require(not legacy.run("git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"),
            "dirty tracked source " + str(path))


def checked_manifest(manifest, linux_source, libiio_source, kernel, config):
    expected = {
        "submodule_linux": linux_source,
        "libiio_0_25_source": libiio_source,
        "kernel_zimage_sha256": sha(kernel),
        "kernel_config_sha256": sha(config),
    }
    for field, value in expected.items():
        require(manifest.get(field) == value, "source manifest mismatch: " + field)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "linux", "source", "kernel", "kernel-config", "iiod", "libiio", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("linux-commit", "source-commit", "kernel-sha256", "iiod-sha256", "libiio-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    checked_source(args.linux, args.linux_commit)
    checked_source(args.source, args.source_commit)
    parent = args.parent.read_bytes()
    require(sha(parent) == PARENT_SHA, "parent differs from published v0.63 DFU")
    kernel, daemon, library = args.kernel.read_bytes(), args.iiod.read_bytes(), args.libiio.read_bytes()
    require(sha(kernel) == args.kernel_sha256 and sha(daemon) == args.iiod_sha256
            and sha(library) == args.libiio_sha256, "component hash mismatch")
    manifest = dict(line.split(": ", 1) for line in
        (ROOT / "manifests/position-scan-v064-source.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#"))
    checked_manifest(manifest, args.linux_commit, args.source_commit, kernel, args.kernel_config.read_bytes())
    require(len(kernel) >= 48 and struct.unpack_from("<I", kernel, 36)[0] == 0x016F2818, "expected ARM zImage")
    dependencies = {"iiod": legacy.check_elf(args.iiod), "libiio": legacy.check_elf(args.libiio, library=True)}
    original = legacy.cpio.fit_body(parent)
    ramdisk, changes = replace_rootfs(Fit(original).nodes()["/images/ramdisk@1"]["data"],
        {"usr/sbin/iiod": daemon, "usr/lib/libiio.so.0.25": library}, args.linux_commit, args.source_commit)
    fit, unchanged = replace_components(original,
        {"/images/linux_kernel@1": kernel, "/images/ramdisk@1": ramdisk})
    # Reopen the finished container and independently compare both installed components.
    dfu = legacy.cpio.add_dfu_suffix(fit)
    frm = fit + hashlib.md5(fit).hexdigest().encode() + b"\n"
    nodes = Fit(legacy.cpio.fit_body(dfu)).nodes()
    require(nodes["/images/linux_kernel@1"]["data"] == kernel, "packed kernel mismatch")
    unpacked = legacy.cpio.read_newc(gzip.decompress(nodes["/images/ramdisk@1"]["data"]))
    require(unpacked["usr/sbin/iiod"][1] == daemon and unpacked["usr/lib/libiio.so.0.25"][1] == library,
            "packed userspace mismatch")
    require(frm[:-33] == fit, "FRM container mismatch")
    binding = {"schema": "plutosdr-fw.position-scan-artifact/v1", "firmware": VERSION,
        "packaging": "installed-kernel-userspace-replacement-over-v063", "parent_dfu_sha256": PARENT_SHA,
        "firmware_source": legacy.run("git", "-C", str(ROOT), "rev-parse", "HEAD"),
        "linux_source": args.linux_commit, "libiio_source": args.source_commit,
        "kernel_sha256": sha(kernel), "kernel_config_sha256": sha(args.kernel_config.read_bytes()),
        "iiod_sha256": sha(daemon), "libiio_sha256": sha(library), "changed_rootfs_files": changes,
        "unchanged_components": unchanged, "elf_dependencies": dependencies,
        "fit_sha256": sha(fit), "fit_bytes": len(fit), "dfu_sha256": sha(dfu), "dfu_bytes": len(dfu),
        "frm_sha256": sha(frm), "frm_bytes": len(frm), "hardware_qualified": False}
    args.output.mkdir(parents=True, exist_ok=False)
    for suffix, payload in (("itb", fit), ("dfu", dfu), ("frm", frm)):
        (args.output / ("plutoplus-spf-position-scan-v064-pluto." + suffix)).write_bytes(payload)
    (args.output / "artifact.json").write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    print(json.dumps(binding, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
