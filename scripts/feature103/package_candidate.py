#!/usr/bin/env python3
"""Build provenance-closed feature-103 RAM candidates from qualified v0.50.

The qualified DFU is the only source for unchanged boot components.  Five
stages are emitted so hardware qualification can distinguish the known-good
transport from FIT reconstruction, then introduce one feature boundary at a
time: byte-exact parent, canonical repack, feature kernel, RX0 DTB, and
feature userspace.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import zlib
from collections import OrderedDict
from pathlib import Path

BASE_DFU_SHA256 = "435a26369018e86ee66262b79c32895dbaaacef510a1efb71c566d6409555344"
BASE_FIT_SHA256 = "a53efc46f3c65d1a15e5063374551d2daa3cb9d0df51257de53b6af80be39493"
BASE_COMPONENT_SHA256 = {
    "fpga": "b96891fa1bb4fe8053089dc3fa76812d3e046e624810b333808354958c26e93c",
    "rootfs": "b0b7e5c640d7274da6f93b4e755473184ce79db0cedd710f676563703c4aa498",
}
LINUX_SOURCE = "eeefe8c6228eede6206197e941aa7024d5ac60d2"
LIBIIO_SOURCE = "61fdcc844ef8c78b7c3d2b044295565eb8d01ce4"
EPOCH = 1789588800
STAGES = ("parent", "repack", "kernel", "rx0", "full")
CANDIDATE = "feature103-rc13"


class CandidateError(RuntimeError):
    """The candidate does not preserve the qualified-parent contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_sha(path: Path, expected: str, label: str) -> bytes:
    data = path.read_bytes()
    actual = sha256(data)
    if actual != expected:
        raise CandidateError(f"{label} SHA-256: expected {expected}, got {actual}")
    return data


def fit_body(dfu: bytes) -> bytes:
    if len(dfu) < 16 or dfu[-8:-5] != b"UFD" or dfu[-5] != 16:
        raise CandidateError("qualified parent lacks a 16-byte DFU suffix")
    if zlib.crc32(dfu[:-4]) ^ 0xFFFFFFFF != struct.unpack("<I", dfu[-4:])[0]:
        raise CandidateError("qualified parent DFU suffix CRC is invalid")
    return dfu[:-16]


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


def fit_indexes(parent: Path) -> dict[str, int]:
    listing = run("dumpimage", "-l", str(parent))
    found: dict[str, int] = {}
    for index, name in re.findall(r"^ Image (\d+) \(([^)]+)\)", listing, re.MULTILINE):
        found[name] = int(index)
    required = {
        "fdt@1",
        "fdt@2",
        "fdt@3",
        "fpga@1",
        "linux_kernel@1",
        "ramdisk@1",
    }
    if not required <= found.keys():
        raise CandidateError(f"qualified FIT lacks components: {sorted(required - found.keys())}")
    return found


def extract_component(parent: Path, index: int, destination: Path) -> bytes:
    run(
        "dumpimage",
        "-T",
        "flat_dt",
        "-p",
        str(index),
        "-o",
        str(destination),
        str(parent),
    )
    return destination.read_bytes()


def read_newc(data: bytes) -> OrderedDict[str, tuple[list[int], bytes]]:
    entries: OrderedDict[str, tuple[list[int], bytes]] = OrderedDict()
    offset = 0
    while True:
        if data[offset : offset + 6] != b"070701":
            raise CandidateError(f"rootfs is not newc at byte {offset}")
        fields = [
            int(data[offset + 6 + field * 8 : offset + 14 + field * 8], 16)
            for field in range(13)
        ]
        size, name_size = fields[6], fields[11]
        start = offset + 110
        name = data[start : start + name_size - 1].decode("utf-8")
        start = (start + name_size + 3) & ~3
        payload = data[start : start + size]
        if len(payload) != size:
            raise CandidateError(f"truncated rootfs entry {name}")
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            return entries
        if name in entries:
            raise CandidateError(f"duplicate rootfs entry {name}")
        entries[name] = (fields, payload)


def write_newc(entries: OrderedDict[str, tuple[list[int], bytes]]) -> bytes:
    output = bytearray()
    all_entries = list(entries.items()) + [("TRAILER!!!", ([0] * 13, b""))]
    for inode, (name, (original, payload)) in enumerate(all_entries, 1):
        fields = list(original)
        fields[0] = inode
        fields[6] = len(payload)
        fields[11] = len(name.encode("utf-8")) + 1
        output.extend(b"070701")
        output.extend(b"".join(f"{value:08x}".encode("ascii") for value in fields))
        output.extend(name.encode("utf-8") + b"\0")
        output.extend(bytes(-len(output) % 4))
        output.extend(payload)
        output.extend(bytes(-len(output) % 4))
    output.extend(bytes(-len(output) % 512))
    return bytes(output)


def replace_version(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + " "
    replaced = False
    result = []
    for line in lines:
        if line.startswith(prefix):
            if not replaced:
                result.append(prefix + value)
                replaced = True
        else:
            result.append(line)
    if not replaced:
        result.append(prefix + value)
    return result


def feature_rootfs(
    base: bytes, iiod: Path, libiio: Path
) -> tuple[bytes, dict[str, dict[str, str]]]:
    entries = read_newc(gzip.decompress(base))
    before_names = tuple(entries)
    replacements = {
        "usr/sbin/iiod": iiod.read_bytes(),
        "usr/lib/libiio.so.0.25": libiio.read_bytes(),
    }
    changes: dict[str, dict[str, str]] = {}
    for name, payload in replacements.items():
        if name not in entries or not stat.S_ISREG(entries[name][0][1]):
            raise CandidateError(f"qualified rootfs lacks regular file {name}")
        fields, original = entries[name]
        entries[name] = (fields, payload)
        changes[name] = {"before": sha256(original), "after": sha256(payload)}

    versions_name = "opt/VERSIONS"
    if versions_name not in entries:
        raise CandidateError("qualified rootfs lacks opt/VERSIONS")
    fields, original_versions = entries[versions_name]
    lines = original_versions.decode("utf-8").splitlines()
    lines = replace_version(lines, "device-fw", "v0.50-plutoplus-feature103-rc13")
    lines = replace_version(lines, "linux", LINUX_SOURCE)
    lines = replace_version(lines, "libiio", LIBIIO_SOURCE)
    new_versions = ("\n".join(lines) + "\n").encode("utf-8")
    entries[versions_name] = (fields, new_versions)
    changes[versions_name] = {
        "before": sha256(original_versions),
        "after": sha256(new_versions),
    }
    if tuple(entries) != before_names:
        raise CandidateError("feature rootfs changed the qualified archive inventory")
    archive = write_newc(entries)
    if tuple(read_newc(archive)) != before_names:
        raise CandidateError("rootfs round trip changed the qualified archive inventory")
    return gzip.compress(archive, compresslevel=9, mtime=EPOCH), changes


def rx0_dtb(base: Path, destination: Path) -> bytes:
    shutil.copyfile(base, destination)
    phy = "/amba/spi@e0006000/ad9361-phy@0"
    dds = "/fpga-axi@0/cf-ad9361-dds-core-lpc@79024000"
    properties = run("fdtget", "-p", str(destination), phy).splitlines()
    if "adi,2rx-2tx-mode-enable" in properties:
        run("fdtput", "-d", str(destination), phy, "adi,2rx-2tx-mode-enable")
    run("fdtput", "-t", "x", str(destination), phy, "adi,1rx-1tx-mode-use-rx-num", "1")
    run("fdtput", "-t", "x", str(destination), phy, "adi,1rx-1tx-mode-use-tx-num", "2")
    run("fdtput", "-t", "s", str(destination), dds, "compatible", "adi,axi-ad9364-dds-6.00.a")
    return destination.read_bytes()


def its_text(stage: str, fdt1: str, fdt2: str, fdt3: str, kernel: str, rootfs: str) -> str:
    return f"""/dts-v1/;

/ {{
	description = "Configuration to load fpga before Kernel";
	magic = "ITB PlutoSDR (ADALM-PLUTO)";
	#address-cells = <1>;
	images {{
		fdt@1 {{ description = "zynq-pluto-sdr"; data = /incbin/("{fdt1}"); type = "flat_dt"; arch = "arm"; compression = "none"; }};
		fdt@2 {{ description = "zynq-pluto-sdr-revb"; data = /incbin/("{fdt2}"); type = "flat_dt"; arch = "arm"; compression = "none"; }};
		fdt@3 {{ description = "zynq-pluto-sdr-revc"; data = /incbin/("{fdt3}"); type = "flat_dt"; arch = "arm"; compression = "none"; }};
		fpga@1 {{ description = "FPGA"; data = /incbin/("fpga.bit"); type = "fpga"; arch = "arm"; compression = "none"; load = <0x0f000000>; hash@1 {{ algo = "md5"; }}; }};
		linux_kernel@1 {{ description = "Linux"; data = /incbin/("{kernel}"); type = "kernel"; arch = "arm"; os = "linux"; compression = "none"; load = <0x00008000>; entry = <0x00008000>; hash@1 {{ algo = "md5"; }}; }};
		ramdisk@1 {{ description = "Ramdisk"; data = /incbin/("{rootfs}"); type = "ramdisk"; arch = "arm"; os = "linux"; compression = "gzip"; hash@1 {{ algo = "md5"; }}; }};
	}};
	configurations {{
		default = "config@0";
		config@0 {{ description = "Linux with fpga RevA"; fdt = "fdt@1"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@1 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@2 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@3 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@4 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@5 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@6 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@7 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@8 {{ description = "Linux with fpga RevC"; fdt = "fdt@3"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@9 {{ description = "Linux with fpga RevC"; fdt = "fdt@3"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
		config@10 {{ description = "Linux with fpga RevB"; fdt = "fdt@2"; kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1"; }};
	}};
}};
"""


def add_dfu_suffix(fit: bytes) -> bytes:
    suffix = struct.pack("<HHHH3sB", 0xFFFF, 0xB673, 0x0456, 0x0100, b"UFD", 16)
    body = fit + suffix
    return body + struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF)


def build(args: argparse.Namespace) -> dict[str, object]:
    parent = args.parent.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    parent_bytes = require_sha(parent, BASE_DFU_SHA256, "qualified parent DFU")
    if sha256(fit_body(parent_bytes)) != BASE_FIT_SHA256:
        raise CandidateError("qualified parent FIT SHA-256 is not the release identity")

    with tempfile.TemporaryDirectory(prefix="feature103-package-") as temporary:
        work = Path(temporary)
        indexes = fit_indexes(parent)
        extracted = {}
        for key, fit_name, filename in (
            ("dtb_reva", "fdt@1", "parent-reva.dtb"),
            ("dtb_revb", "fdt@2", "parent-revb.dtb"),
            ("dtb", "fdt@3", "parent-revc.dtb"),
            ("fpga", "fpga@1", "fpga.bit"),
            ("kernel", "linux_kernel@1", "parent-zImage"),
            ("rootfs", "ramdisk@1", "parent-rootfs.cpio.gz"),
        ):
            path = work / filename
            extracted[key] = extract_component(parent, indexes[fit_name], path)
        for key, expected in BASE_COMPONENT_SHA256.items():
            if sha256(extracted[key]) != expected:
                raise CandidateError(f"qualified {key} component disagrees with release manifest")

        feature_kernel = require_sha(args.kernel.resolve(), args.kernel_sha256, "feature kernel")
        require_sha(args.iiod.resolve(), args.iiod_sha256, "feature iiOD")
        require_sha(args.libiio.resolve(), args.libiio_sha256, "feature libiio")
        (work / "feature-zImage").write_bytes(feature_kernel)
        shutil.copyfile(args.iiod.resolve(), work / "feature-iiod")
        shutil.copyfile(args.libiio.resolve(), work / "feature-libiio.so.0.25")
        rx0_dtbs = {}
        for revision in ("reva", "revb", "revc"):
            rx0_dtbs[revision] = rx0_dtb(
                work / f"parent-{revision}.dtb", work / f"rx0-{revision}.dtb"
            )
        full_rootfs, rootfs_changes = feature_rootfs(
            extracted["rootfs"], work / "feature-iiod", work / "feature-libiio.so.0.25"
        )
        (work / "feature-rootfs.cpio.gz").write_bytes(full_rootfs)

        stage_inputs = {
            "repack": (
                "parent-reva.dtb", "parent-revb.dtb", "parent-revc.dtb",
                "parent-zImage", "parent-rootfs.cpio.gz",
            ),
            "kernel": (
                "parent-reva.dtb", "parent-revb.dtb", "parent-revc.dtb",
                "feature-zImage", "parent-rootfs.cpio.gz",
            ),
            "rx0": (
                "rx0-reva.dtb", "rx0-revb.dtb", "rx0-revc.dtb",
                "feature-zImage", "parent-rootfs.cpio.gz",
            ),
            "full": (
                "rx0-reva.dtb", "rx0-revb.dtb", "rx0-revc.dtb",
                "feature-zImage", "feature-rootfs.cpio.gz",
            ),
        }
        stages = {}
        for stage in STAGES:
            stage_dir = output / stage
            stage_dir.mkdir(parents=True, exist_ok=True)
            if stage == "parent":
                dfu = stage_dir / f"{CANDIDATE}-parent.dfu"
                dfu.write_bytes(parent_bytes)
                stages[stage] = {
                    "dfu_path": str(dfu),
                    "dfu_bytes": len(parent_bytes),
                    "dfu_sha256": BASE_DFU_SHA256,
                    "fit_bytes": len(fit_body(parent_bytes)),
                    "fit_sha256": BASE_FIT_SHA256,
                    "components": {
                        name: sha256(extracted[name])
                        for name in ("dtb_reva", "dtb_revb", "dtb", "fpga", "kernel", "rootfs")
                    },
                    "changes_from_parent": [],
                    "container": "byte-exact-qualified-parent",
                }
                continue
            fdt1_name, fdt2_name, fdt3_name, kernel_name, rootfs_name = stage_inputs[stage]
            for filename in (
                fdt1_name,
                fdt2_name,
                fdt3_name,
                kernel_name,
                rootfs_name,
                "fpga.bit",
            ):
                shutil.copyfile(work / filename, stage_dir / filename)
            its = stage_dir / f"{CANDIDATE}.its"
            its.write_text(
                its_text(stage, fdt1_name, fdt2_name, fdt3_name, kernel_name, rootfs_name)
            )
            itb = stage_dir / f"{CANDIDATE}-{stage}.itb"
            run(
                "mkimage",
                "-f",
                its.name,
                itb.name,
                cwd=stage_dir,
                env=os.environ | {"SOURCE_DATE_EPOCH": str(EPOCH)},
            )
            fit = itb.read_bytes()
            dfu = stage_dir / f"{CANDIDATE}-{stage}.dfu"
            dfu.write_bytes(add_dfu_suffix(fit))
            stages[stage] = {
                "dfu_path": str(dfu),
                "dfu_bytes": dfu.stat().st_size,
                "dfu_sha256": sha256(dfu.read_bytes()),
                "fit_bytes": len(fit),
                "fit_sha256": sha256(fit),
                "components": {
                    "dtb_reva": sha256((stage_dir / fdt1_name).read_bytes()),
                    "dtb_revb": sha256((stage_dir / fdt2_name).read_bytes()),
                    "dtb": sha256((stage_dir / fdt3_name).read_bytes()),
                    "fpga": sha256((stage_dir / "fpga.bit").read_bytes()),
                    "kernel": sha256((stage_dir / kernel_name).read_bytes()),
                    "rootfs": sha256((stage_dir / rootfs_name).read_bytes()),
                },
                "changes_from_parent": [
                    name
                    for name in ("dtb", "kernel", "rootfs")
                    if sha256((stage_dir / {"dtb": fdt3_name, "kernel": kernel_name, "rootfs": rootfs_name}[name]).read_bytes())
                    != sha256(extracted[name])
                ],
                "container": "canonical-full-fit-layout",
            }

        manifest = {
            "schema": "plutosdr-fw.feature103-provenance-closed-candidate",
            "schema_version": 1,
            "candidate": CANDIDATE,
            "persistent_write_allowed": False,
            "qualified_parent": {
                "dfu_sha256": BASE_DFU_SHA256,
                "fit_sha256": BASE_FIT_SHA256,
                "component_sha256": {key: sha256(value) for key, value in extracted.items()},
            },
            "sources": {"linux": LINUX_SOURCE, "libiio": LIBIIO_SOURCE},
            "rx0_dtb": {
                "sha256_by_fit_slot": {
                    revision: sha256(data) for revision, data in rx0_dtbs.items()
                },
                "allowed_changes": [
                    "remove adi,2rx-2tx-mode-enable",
                    "select physical RX1 and TX2",
                    "select adi,axi-ad9364-dds-6.00.a",
                ],
            },
            "rootfs": {
                "inventory_preserved": True,
                "changed_files": rootfs_changes,
            },
            "stages": stages,
        }
        manifest_path = output / f"{CANDIDATE}-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--parent", required=True, type=Path)
    result.add_argument("--kernel", required=True, type=Path)
    result.add_argument("--kernel-sha256", required=True)
    result.add_argument("--iiod", required=True, type=Path)
    result.add_argument("--iiod-sha256", required=True)
    result.add_argument("--libiio", required=True, type=Path)
    result.add_argument("--libiio-sha256", required=True)
    result.add_argument("--output", required=True, type=Path)
    return result


def main() -> None:
    print(json.dumps(build(parser().parse_args()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
