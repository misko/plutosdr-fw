#!/usr/bin/env python3
"""Build the conservative recovery candidate as an audited v0.50 rootfs overlay.

This preserves the released FPGA, DTs and radio userspace. It does not claim a
full Buildroot rebuild or hardware qualification. Run build_tools.sh and build
the kernel from the baseline embedded config with the LOCALVERSION below first.
"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build/issue99"
OUT = WORK / "candidate"
VERSION = "v0.50-counter-rx-v1-flash-safety-rc1"
LOCALVERSION = "-counter-rx-v1-flash-safety-rc1"
EPOCH = 1789257600
BASE_DFU_SHA = "435a26369018e86ee66262b79c32895dbaaacef510a1efb71c566d6409555344"
BASE_FIT_SHA = "a53efc46f3c65d1a15e5063374551d2daa3cb9d0df51257de53b6af80be39493"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, **kw):
    return subprocess.check_output([str(a) for a in args], **kw)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = (WORK / "baseline/pluto.dfu").read_bytes()
    assert sha(baseline) == BASE_DFU_SHA
    assert sha(baseline[:-16]) == BASE_FIT_SHA
    fit_path = OUT / "baseline.itb"
    fit_path.write_bytes(baseline[:-16])
    names = ("zynq-pluto-sdr.dtb", "zynq-pluto-sdr-revb.dtb", "zynq-pluto-sdr-revc.dtb",
             "system_top.bit", "baseline-zImage", "baseline-rootfs.cpio.gz")
    for index, name in enumerate(names):
        run("dumpimage", "-T", "flat_dt", "-p", index, "-o", OUT / name, fit_path)
    spec = importlib.util.spec_from_file_location("cpio", ROOT / "scripts/issue97/package.py")
    cpio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpio)
    entries = cpio.read_cpio(gzip.decompress((OUT / names[-1]).read_bytes()))
    original = dict(entries)
    assert not any(n.startswith("lib/modules/") for n in entries)
    # Check the candidate retains the exact released configuration except its name.
    base_config = run(ROOT / "linux/scripts/extract-ikconfig", OUT / "baseline-zImage").decode()
    config = (ROOT / "build/linux/.config").read_text()
    assert config == base_config.replace('CONFIG_LOCALVERSION="-counter-rx-v1"',
                                         f'CONFIG_LOCALVERSION="{LOCALVERSION}"')
    sources = {}
    for repo in ("linux", "buildroot", "u-boot-xlnx"):
        assert not run("git", "-C", ROOT / repo, "status", "--porcelain").strip(), repo
        sources[repo] = run("git", "-C", ROOT / repo, "rev-parse", "HEAD").decode().strip()

    def add(name, data, mode=stat.S_IFREG | 0o755):
        parent = str(Path(name).parent)
        if parent != "." and parent not in entries:
            add(parent, b"", stat.S_IFDIR | 0o755)
        fields = [0, mode, 0, 0, 1, EPOCH, 0, 0, 0, 0, 0, 0, 0]
        entries[name] = (fields, data)

    module_root = WORK / "modules"
    release = (ROOT / "build/linux/include/config/kernel.release").read_text().strip()
    installed = module_root / "lib/modules" / release
    assert installed.is_dir(), "run modules_install with INSTALL_MOD_PATH=build/issue99/modules"
    assert len(list(installed.rglob("*.ko"))) == len(list((ROOT / "build/linux").rglob("*.ko")))
    for path in sorted(installed.rglob("*")):
        if path.is_symlink():
            assert path.name in {"source", "build"}
            continue
        if path.is_file():
            add(str(path.relative_to(module_root)), path.read_bytes(), stat.S_IFREG | 0o644)

    board = ROOT / "buildroot/board/pluto"
    for name in ("update.sh", "update_frm.sh", "update_from_github.sh"):
        add("sbin/" + name, (board / name).read_bytes())
    for name in ("pluto-fw-update", "pluto-flash-range"):
        add("usr/sbin/" + name, (board / name).read_bytes())
    add("usr/bin/fdtget", (WORK / "tools/dtc-1.6.1/fdtget").read_bytes())
    add("usr/sbin/dumpimage", (WORK / "tools/u-boot-2021.07/tools/dumpimage").read_bytes())
    add("usr/lib/libfdt-1.6.1.so", (WORK / "tools/dtc-1.6.1/libfdt/libfdt-1.6.1.so").read_bytes())
    add("usr/lib/libfdt.so.1", b"libfdt-1.6.1.so", stat.S_IFLNK | 0o777)
    versions = entries["opt/VERSIONS"][1].decode().splitlines()
    versions = ["device-fw " + VERSION if line.startswith("device-fw ") else
                "linux " + sources["linux"] if line.startswith("linux ") else line
                for line in versions]
    versions += ["flash-updater " + sources["buildroot"], "flash-qualification none"]
    add("opt/VERSIONS", ("\n".join(versions) + "\n").encode(), stat.S_IFREG | 0o644)
    overlay = {n: {"before": sha(original[n][1]) if n in original else None,
                   "after": sha(v[1]), "mode": oct(v[0][1])}
               for n, v in entries.items() if n not in original or v != original[n]}
    for name in original.keys() - overlay.keys():
        assert entries[name] == original[name], name
    ordered = dict(sorted(entries.items()))
    ordered["TRAILER!!!"] = ([0] * 13, b"")
    archive = cpio.write_cpio(ordered)
    assert {n: v[1] for n, v in cpio.read_cpio(archive).items()} == {n: v[1] for n, v in entries.items()}
    (OUT / "rootfs.cpio.gz").write_bytes(gzip.compress(archive, compresslevel=9, mtime=EPOCH))
    shutil.copyfile(ROOT / "build/linux/arch/arm/boot/zImage", OUT / "zImage")
    shutil.copyfile(ROOT / "build/linux/.config", OUT / "kernel.config")
    its = (ROOT / "scripts/pluto.its").read_text().replace("../build/", "")
    (OUT / "pluto.its").write_text(its)
    fit = OUT / "pluto.itb"
    run("mkimage", "-f", "pluto.its", "pluto.itb", cwd=OUT,
        env=os.environ | {"SOURCE_DATE_EPOCH": str(EPOCH)})
    payload = fit.read_bytes()
    frm = OUT / "pluto.frm"
    frm.write_bytes(payload + hashlib.md5(payload).hexdigest().encode() + b"\n")
    verdict = json.loads(run("python3", ROOT / "scripts/validate_flash_artifact.py", "--frm", frm,
                             "--profile", ROOT / "manifests/pluto-legacy-flash-layout.json", "--target", "pluto"))
    # The suffix identifies the image format, not whether a DFU target is RAM.
    body = payload + baseline[-16:-4]
    (OUT / "pluto.dfu").write_bytes(body + struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF))
    manifest = {"schema": "plutosdr-fw.flash-safety-candidate.v1", "version": VERSION,
        "status": "unqualified-recovery-candidate", "qualification": None,
        "baseline_dfu_sha256": BASE_DFU_SHA, "baseline_fit_sha256": BASE_FIT_SHA,
        "sources": sources, "rootfs_overlay": overlay, "persistent_range": verdict,
        "installed_bootloader_changed": False,
        "files": {name: {"sha256": sha((OUT / name).read_bytes()), "bytes": (OUT / name).stat().st_size}
                  for name in ("pluto.itb", "pluto.frm", "pluto.dfu", "zImage", "kernel.config",
                               "rootfs.cpio.gz", *names[:4])}}
    (OUT / "candidate.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate": str(OUT), "fit_bytes": len(payload), "sources": sources}, indent=2))


if __name__ == "__main__":
    main()
