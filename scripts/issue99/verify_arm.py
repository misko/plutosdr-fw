#!/usr/bin/env python3
"""Run candidate ARM FIT inspectors and updater fixtures under qemu-user.

Run with a Python environment containing pytest. All MTD operations are synthetic.
This checks ARM userspace compatibility, not hardware addressing or bootability.
"""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "build/issue99/candidate"


def main():
    spec = importlib.util.spec_from_file_location("cpio", ROOT / "scripts/issue97/package.py")
    cpio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpio)
    entries = cpio.read_cpio(gzip.decompress((CANDIDATE / "rootfs.cpio.gz").read_bytes()))
    with tempfile.TemporaryDirectory(prefix="issue99-arm-") as scratch:
        root = Path(scratch) / "root"
        root.mkdir()
        # Extract files before symlinks; never materialize device nodes or follow
        # a rootfs symlink while writing into the temporary host directory.
        for name, (fields, data) in entries.items():
            path = Path(name)
            assert not path.is_absolute() and ".." not in path.parts
            path = root / path
            if stat.S_ISDIR(fields[1]):
                path.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISREG(fields[1]):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(fields[1] & 0o777)
        for name, (fields, data) in entries.items():
            if stat.S_ISLNK(fields[1]):
                (root / name).symlink_to(data.decode())
        qemu = ["qemu-arm", "-L", str(root)]
        def arm(binary, *args):
            return subprocess.check_output(qemu + [str(root / binary), *map(str, args)])
        assert arm("usr/bin/fdtget", "-t", "s", CANDIDATE / "pluto.itb", "/", "magic").strip() == b"ITB PlutoSDR (ADALM-PLUTO)"
        arm("usr/sbin/dumpimage", "-l", CANDIDATE / "pluto.itb")
        wrapper = Path(scratch) / "bin"
        wrapper.mkdir()
        busybox = wrapper / "busybox"
        busybox.write_text("#!/bin/sh\nexec " + shlex.join(qemu + [str(root / "bin/busybox")]) + ' "$@"\n')
        busybox.chmod(0o755)
        subprocess.run([sys.executable, "-m", "pytest", "tests/test_flash_safety.py",
                        "tests/test_flash_safety_candidate.py", "-q"], cwd=ROOT, check=True,
                       env=os.environ | {"PATH": str(wrapper) + ":" + os.environ["PATH"]})
    print(json.dumps({"arm_fit_inspectors": "passed", "arm_busybox_updater_fixtures": "passed",
                      "hardware_qualification": None}))


if __name__ == "__main__":
    main()
