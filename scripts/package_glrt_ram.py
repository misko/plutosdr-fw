#!/usr/bin/env python3
"""Assemble a reviewable GLR1 RAM FIT/DFU from audited local build artifacts.

No radio access, deployment, bootloader or flash update. Packaging is separate
from CDC/I/O review and hardware qualification. The input rootfs is preserved;
its copy receives exact component versions and, for GLF1, the profile-aware
boot inventory script. Both replacements are recorded.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root, *arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


@dataclass
class Entry:
    name: str
    fields: list[int]
    data: bytes


def read_newc(data: bytes) -> list[Entry]:
    entries, offset = [], 0
    while True:
        if data[offset:offset+6] != b"070701" or len(data) < offset+110:
            raise ValueError("rootfs must be a complete newc archive")
        fields = [int(data[offset+6+8*n:offset+14+8*n], 16) for n in range(13)]
        length, name_size = fields[6], fields[11]
        if name_size == 0:
            raise ValueError("newc entry has an empty name field")
        name_raw = data[offset+110:offset+110+name_size]
        if len(name_raw) != name_size or name_raw[-1:] != b"\0":
            raise ValueError("truncated newc name")
        name = name_raw[:-1].decode("utf-8", errors="surrogateescape")
        begin = (offset+110+name_size+3) & ~3
        if begin+length > len(data):
            raise ValueError("truncated newc payload")
        entries.append(Entry(name, fields, data[begin:begin+length]))
        offset = (begin+length+3) & ~3
        if name == "TRAILER!!!":
            if length or any(data[offset:]):
                raise ValueError("unexpected data after newc trailer")
            return entries


def write_newc(entries: list[Entry]) -> bytes:
    result = bytearray()
    if not entries or entries[-1].name != "TRAILER!!!":
        raise ValueError("newc trailer is missing")
    for entry in entries:
        name = entry.name.encode("utf-8", errors="surrogateescape") + b"\0"
        fields = list(entry.fields)
        fields[6], fields[11] = len(entry.data), len(name)
        result += b"070701" + "".join(f"{value:08x}" for value in fields).encode() + name
        result += b"\0" * (-len(result) % 4)
        result += entry.data
        result += b"\0" * (-len(result) % 4)
    result += b"\0" * (-len(result) % 512)
    return bytes(result)


def stamp_rootfs(compressed: bytes, versions: str, *, lean_init: bytes | None = None) -> bytes:
    entries = read_newc(gzip.decompress(compressed))
    by_name = {entry.name.removeprefix("./"): entry for entry in entries}
    if len(by_name) != len(entries):
        raise ValueError("duplicate rootfs member names")
    if any("starlink_pss" in name or "starlink-pss" in name for name in by_name):
        raise ValueError("rootfs retains a PSS tool, init or module path")
    for required in ("opt/VERSIONS", "etc/init.d/S22starlink_glrt_iio", "usr/sbin/iiod"):
        if required not in by_name:
            raise ValueError("GLRT rootfs member is missing: " + required)
    if by_name["opt/VERSIONS"].fields[1] & 0o170000 != 0o100000:
        raise ValueError("rootfs VERSIONS is not a regular file")
    by_name["opt/VERSIONS"].data = versions.encode()
    if lean_init is not None:
        if by_name["etc/init.d/S22starlink_glrt_iio"].fields[1] & 0o170000 != 0o100000:
            raise ValueError("rootfs GLRT init is not a regular file")
        by_name["etc/init.d/S22starlink_glrt_iio"].data = lean_init
    return gzip.compress(write_newc(entries), mtime=0)


def verify_native_selection(board: Path, audit: dict, rate: int) -> list[Path]:
    tracking_path = board / "tracking.txt"
    tracking = tracking_path.read_text().strip() if tracking_path.exists() else "0"
    if tracking not in ("0", "1"):
        raise ValueError("invalid tracking build selection")
    local_path = board / "local_search.txt"
    local = local_path.read_text().strip() if local_path.exists() else "0"
    if local not in ("0", "1"):
        raise ValueError("invalid local search build selection")
    for block in ("local_search_controls", "local_search_engines", "local_search_cadences"):
        count = audit.get(block, None if local_path.exists() else "0")
        if count != local:
            raise ValueError("implemented local search differs from build selection")
    selection = board / "native_refinement.txt"
    enabled = selection.read_text().strip() if selection.exists() else "0"
    if enabled not in ("0", "1"):
        raise ValueError("invalid native refinement build selection")
    # Old reference builds predate this field. An enabled image always needs
    # explicit implemented-netlist evidence; its source setting alone is not
    # proof that the native engine survived synthesis and routing.
    if audit.get("native_refinement_engines", "0") != ("1" if tracking == "1" else enabled):
        raise ValueError("implemented native engine differs from build selection")
    if enabled == "1" and rate != 60_000_000:
        raise ValueError("native refinement requires a 60 MS/s board")
    legacy_path = board / "legacy_scorer.txt"
    legacy = legacy_path.read_text().strip() if legacy_path.exists() else "1"
    if legacy not in ("0", "1"):
        raise ValueError("invalid legacy scorer build selection")
    if local == "1" and (rate != 2_500_000 or enabled != "0" or legacy != "0"):
        raise ValueError("local search requires direct 2.5 MS/s without native or legacy scoring")
    if legacy == "0" and enabled != "1" and local != "1" and tracking != "1":
        raise ValueError("lean profile requires native refinement or local search")
    # New selections require exact topology evidence. Reference artifacts
    # predating this selector remain valid under their original gates.
    if legacy_path.exists():
        for block in ("legacy_correlators", "legacy_scorers", "legacy_vector_stages"):
            if audit.get(block) != legacy:
                raise ValueError("implemented legacy blocks differ from build selection")
    schedule_path = board / "native_schedule.txt"
    scheduled = schedule_path.read_text().strip() if schedule_path.exists() else "0"
    if scheduled not in ("0", "1") or (scheduled == "1" and (enabled != "1" or legacy != "0")):
        raise ValueError("native scheduling requires the lean native profile")
    if tracking == "1":
        if enabled != "0" or legacy != "0" or scheduled != "0" or (
                rate != 2_500_000 if local == "1" else rate not in (30_000_000, 60_000_000)):
            raise ValueError("invalid integrated tracking profile")
        if audit.get("tracking_controls") != "1" or audit.get("acquisition_engines") != "0":
            raise ValueError("implemented tracking/acquisition topology differs")
    if rate == 30_000_000 and (tracking != "1" or local != "0"):
        raise ValueError("30-MS/s packaging requires GLI1")
    if schedule_path.exists():
        for block in ("native_schedule_controls", "native_result_queues"):
            if audit.get(block) != ("1" if tracking == "1" else scheduled):
                raise ValueError("implemented schedule/queue differs from build selection")
    return [path for path in (selection, legacy_path, schedule_path, local_path, tracking_path) if path.exists()]


def package(args):
    board, kernel = args.board.resolve(), args.kernel.resolve()
    host_bin = (getattr(args, "host_bin", None) or ROOT / "buildroot/output/host/bin").resolve()
    dtc, mkimage = host_bin / "dtc", host_bin / "mkimage"
    environment = dict(os.environ, PATH=str(host_bin) + os.pathsep + os.environ.get("PATH", ""))
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", args.label):
        raise ValueError("firmware label must be a plain filename-safe identifier")
    if (board / "build_exit_code.txt").read_text().strip() != "0":
        raise ValueError("board build did not pass")
    hdl = (board / "hdl_commit.txt").read_text().strip()
    if git(board / "hdl", "rev-parse", "HEAD") != hdl or git(board / "hdl", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("board HDL identity changed after its build")
    if (board / "source_validation.log").read_text().strip():
        raise ValueError("board source validation failed")
    audit_root = board / "full-audit"
    audit = dict(line.split("\t", 1) for line in (audit_root / "audit.tsv").read_text().splitlines())
    if (float(audit["setup_slack_ns"]) < 0 or float(audit["hold_slack_ns"]) < 0
            or any(audit[key] != value for key, value in
                   {"pss_cells": "0", "native_dma_cells": "0", "glrt_ip_cells": "1", "glrt_dma_cells": "1"}.items())):
        raise ValueError("implemented GLRT netlist or internal timing gate failed")
    if "VIOLATED" in (audit_root / "bus_skew.rpt").read_text():
        raise ValueError("implemented CDC bus skew failed")
    rate = int((board / "source_rate_hz.txt").read_text())
    if rate not in (2_500_000, 5_000_000, 10_000_000, 25_000_000, 30_000_000, 60_000_000):
        raise ValueError("unsupported board source rate")
    native_inputs = verify_native_selection(board, audit, rate)
    lean_profile = (board / "legacy_scorer.txt").exists() and (board / "legacy_scorer.txt").read_text().strip() == "0"
    bit = board / "hdl/projects/pluto/pluto.runs/impl_1/system_top.bit"
    xsa = board / "hdl/projects/pluto/pluto.sdk/system_top.xsa"
    frozen_outputs = dict(line.split(maxsplit=1)[::-1] for line in (board / "outputs.sha256").read_text().splitlines())
    for path in (bit, xsa):
        if frozen_outputs.get(str(path)) != digest(path):
            raise ValueError("board output differs from its build receipt")
    with zipfile.ZipFile(xsa) as archive:
        if archive.read("system_top.bit") != bit.read_bytes():
            raise ValueError("XSA and bitstream differ")
    source_commits = {name: git(ROOT / name, "rev-parse", "HEAD") for name in ("linux", "buildroot", "u-boot-xlnx")}
    for name in source_commits:
        if git(ROOT / name, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("component source is dirty: " + name)
    release = (kernel / "include/config/kernel.release").read_text().strip()
    if "-g" + source_commits["linux"][:12] not in release or "dirty" in release:
        raise ValueError("kernel release does not identify the clean Linux source")
    config = (kernel / ".config").read_text().splitlines()
    if "CONFIG_ADI_STARLINK_GLRT=y" not in config or any(
            line.startswith("CONFIG_ADI_STARLINK_PSS") for line in config):
        raise ValueError("kernel configuration is not GLRT-only")
    dtb = kernel / "arch/arm/boot/dts/zynq-pluto-sdr-glrt.dtb"
    dts = subprocess.check_output([str(dtc), "-q", "-I", "dtb", "-O", "dts", str(dtb)], text=True)
    if '"adi,starlink-glrt-1.00.a"' not in dts or "starlink-pss" in dts:
        raise ValueError("compiled device tree is not GLRT-only")
    source_commits.update(hdl=hdl, firmware=git(ROOT, "rev-parse", "HEAD"))
    versions = "device-fw " + args.label + "\n" + "".join(
        f"{name} {source_commits[name]}\n" for name in ("hdl", "linux", "buildroot", "u-boot-xlnx"))
    rootfs = args.rootfs.resolve()
    inputs = [bit, xsa, rootfs, dtb, kernel / "arch/arm/boot/zImage", kernel / ".config",
              ROOT / "scripts/pluto-glrt.its", Path(__file__), mkimage, dtc,
              audit_root / "audit.tsv", audit_root / "bus_skew.rpt", *native_inputs]
    lean_init = ROOT / "buildroot/board/pluto/S22starlink_glrt_iio"
    if lean_profile:
        inputs.append(lean_init)
    hashes = {str(path): digest(path) for path in inputs}
    stamped = stamp_rootfs(rootfs.read_bytes(), versions,
                          lean_init=lean_init.read_bytes() if lean_profile else None)
    args.output.mkdir(parents=True, exist_ok=False)
    build, scripts = args.output / "build", args.output / "scripts"
    build.mkdir()
    scripts.mkdir()
    shutil.copy2(bit, build / "system_top.bit")
    shutil.copy2(dtb, build / dtb.name)
    shutil.copy2(kernel / "arch/arm/boot/zImage", build / "zImage")
    shutil.copy2(ROOT / "scripts/pluto-glrt.its", scripts / "pluto-glrt.its")
    (build / "rootfs.cpio.gz").write_bytes(stamped)
    (args.output / "VERSIONS").write_text(versions)
    fit = args.output / "pluto.itb"
    commands = [[str(mkimage), "-f", str(scripts / "pluto-glrt.its"), str(fit)]]
    with (args.output / "package.log").open("x") as log:
        subprocess.run(commands[0], check=True, stdout=log, stderr=subprocess.STDOUT, env=environment)
        dfu = args.output / "pluto.dfu"
        shutil.copy2(fit, dfu)
        commands.append(["dfu-suffix", "-a", str(dfu), "-v", "0x0456", "-p", "0xb673"])
        subprocess.run(commands[1], check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(["dfu-suffix", "-c", str(dfu)], check=True, stdout=log, stderr=subprocess.STDOUT)
    if any(digest(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("package input changed during assembly")
    manifest = {"schema": "starlink-glrt-ram-package/v1", "firmware_label": args.label,
                "source_rate_hz": rate, "output_rate_hz": 2_500_000, "edge": "upper",
                "source_commits": source_commits, "kernel_release": release,
                "input_sha256": hashes, "rootfs_replaced_members": ["opt/VERSIONS"] +
                    (["etc/init.d/S22starlink_glrt_iio"] if lean_profile else []),
                "commands": commands, "outputs_sha256": {p.name: digest(p) for p in (fit, dfu)},
                "internal_setup_slack_ns": float(audit["setup_slack_ns"]),
                "internal_hold_slack_ns": float(audit["hold_slack_ns"]),
                "ready_for_deployment": False,
                "remaining_gates": ["manual timing/CDC/I/O review", "allocated bench window",
                                    "calibrated receive interface", "hardware transport and live qualification"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--host-bin", type=Path,
                        help="explicit existing read-only Buildroot host tools; recorded by hash")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = package(args)
    print(json.dumps({"output": str(args.output), "rate": result["source_rate_hz"],
                      "ready_for_deployment": False}))


if __name__ == "__main__":
    main()
