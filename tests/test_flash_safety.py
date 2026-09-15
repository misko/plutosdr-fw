"""Physical range checks and real BusyBox updater execution with fake devices."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "buildroot/board/pluto"
PROFILE = ROOT / "manifests/pluto-legacy-flash-layout.json"


def test_current_flash_safety_source_graph():
    manifest = dict(line.split(": ", 1) for line in
                    (ROOT / "manifests/flash-safety-v1-source.yaml").read_text().splitlines()
                    if ": " in line and not line.startswith("#"))
    assert manifest["release_state"] == "candidate"
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        pin = subprocess.check_output(["git", "ls-files", "--stage", component], cwd=ROOT, text=True).split()[1]
        assert manifest["submodule_" + component.replace("-", "_")] == pin


@pytest.mark.parametrize("size,allowed", [(12935447, True), (14680063, True),
    (14680064, True), (14680065, False), (14744943, False)])
def test_exact_incident_ranges(size, allowed):
    run = subprocess.run(["busybox", "sh", str(BOARD / "pluto-flash-range"),
        "2097152", "31457280", "65536", str(size), "16777216"], capture_output=True)
    assert (run.returncode == 0) == allowed


@pytest.mark.parametrize("args", [
    ["2097153", "31457280", "65536", "1", "16777216"],
    ["2097152", "65536", "65536", "65537", "16777216"],
    ["2097152", "31457280", "0", "1", "16777216"],
    ["2097152", "31457280", "65536", "-1", "16777216"],
    ["2097152", "31457280", "65536", "18446744073709551616", "16777216"],
    ["02097152", "31457280", "65536", "1", "16777216"],
    ["2097152", "31457280", "65536", "0", "16777216"],
    ["2097152", "31457280", "65536", "1", "2097153"],
])
def test_invalid_or_erase_crossing_ranges(args):
    assert subprocess.run(["busybox", "sh", str(BOARD / "pluto-flash-range"), *args],
                          capture_output=True).returncode != 0


@pytest.fixture
def fit(tmp_path):
    dt = tmp_path / "board.dts"
    dt.write_text('''/dts-v1/; / { #address-cells=<1>; #size-cells=<1>;
        amba { #address-cells=<1>; #size-cells=<1>;
        spi@e000d000 { #address-cells=<1>; #size-cells=<0>; reg=<0xe000d000 0x1000>;
        ps7-qspi@0 { #address-cells=<1>; #size-cells=<1>; reg=<0>;
        partition@qspi-linux { label="qspi-linux"; reg=<0x200000 0x1e00000>; }; }; }; }; };''')
    subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(tmp_path / "board.dtb"), str(dt)], check=True)
    its = tmp_path / "image.its"
    its.write_text('''/dts-v1/; / { description="flash test"; timestamp=<0>;
        magic="ITB PlutoSDR (ADALM-PLUTO)"; #address-cells=<1>;
        images { fdt@1 { description="dt"; type="flat_dt"; arch="arm";
        compression="none"; data=/incbin/("board.dtb"); };
        payload { description="data"; type="kernel"; arch="arm";
        os="linux"; compression="none"; load=<0>; entry=<0>; data=[01020304]; };
        ram { type="ramdisk"; arch="arm"; compression="none"; data=[05060708]; };
        fpga { type="fpga"; arch="arm"; compression="none"; data=[090a0b0c]; }; };
        configurations { default="config@0"; config@0 { kernel="payload";
        ramdisk="ram"; fpga="fpga"; fdt="fdt@1"; }; }; };''')
    target = tmp_path / "image.itb"
    subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(target), str(its)], check=True)
    return target


def frm_bytes(payload):
    return payload + hashlib.md5(payload).hexdigest().encode() + b"\n"


def test_artifact_matches_packaged_dt(fit, tmp_path):
    script = ROOT / "scripts/validate_flash_artifact.py"
    frm = tmp_path / "image.frm"
    frm.write_bytes(frm_bytes(fit.read_bytes()))
    result = subprocess.run(["python3", str(script), "--frm", str(frm), "--profile", str(PROFILE),
                             "--target", "pluto"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["fit_bytes"] == fit.stat().st_size
    bad = json.loads(PROFILE.read_text())
    bad["firmware_start"] += 65536
    bad["firmware_bytes"] -= 65536
    profile = tmp_path / "wrong.json"
    profile.write_text(json.dumps(bad))
    result = subprocess.run(["python3", str(script), "--fit", str(fit), "--profile", str(profile),
                             "--target", "pluto"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "packaged DT" in result.stderr


def test_artifact_validator_supports_pinned_buildroot_dumpimage(tmp_path, monkeypatch):
    script = ROOT / "scripts/validate_flash_artifact.py"
    spec = importlib.util.spec_from_file_location("validate_flash_artifact", script)
    assert spec is not None and spec.loader is not None
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    fit = tmp_path / "image.itb"
    fit.write_bytes(b"fit")
    destination = tmp_path / "board.dtb"
    calls = []

    def legacy_dumpimage(*args):
        calls.append(args)
        if "-i" not in args:
            destination.write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, args)
        assert args == (
            "dumpimage", "-i", str(fit), "-T", "flat_dt", "-p", "2", str(destination)
        )
        assert not destination.exists()
        destination.write_bytes(b"complete device tree")
        return ""

    monkeypatch.setattr(validator, "output", legacy_dumpimage)
    validator.extract_flat_dt(fit, 2, destination)

    assert destination.read_bytes() == b"complete device tree"
    assert calls[0] == (
        "dumpimage", "-T", "flat_dt", "-p", "2", "-o", str(destination), str(fit)
    )
    assert len(calls) == 2


@pytest.fixture
def updater(tmp_path, fit):
    root = tmp_path / "device"
    for p in ("bin", "etc", "run", "tmp", "dev", "media", "sys/class/mtd", "sys/devices/spi/mtd", "sys/devices/spi/spi-nor"):
        (root / p).mkdir(parents=True)
    (root / "sys/devices/spi/spi-nor/size").write_text("33554432\n")
    # Deliberately use different partition numbers from the production layout.
    for number, name, start, size in [(7, "qspi-fsbl-uboot", 0, 1048576),
                                    (4, "qspi-uboot-env", 1048576, 131072),
                                    (8, "qspi-nvmfs", 1179648, 917504),
                                    (9, "qspi-linux", 2097152, 31457280)]:
        node = root / f"sys/devices/spi/mtd/mtd{number}"
        node.mkdir()
        for attr, value in dict(name=name, offset=start, size=size, erasesize=65536, type="nor").items():
            (node / attr).write_text(str(value) + "\n")
        (root / f"sys/class/mtd/mtd{number}").symlink_to(node)
        # Character-device identity without ever opening real flash hardware.
        (root / f"dev/mtd{number}").symlink_to("/dev/null")
        (root / f"media/mtd{number}").write_bytes(b"original synthetic protected bytes")
    (root / "etc/device_config").write_text('FRM_MAGIC="ITB PlutoSDR (ADALM-PLUTO)"\n')
    (root / "environment").write_text("fit_size=1234\nhostname=test\n")
    mock = root / "bin/mock"
    mock.write_text('''#!/usr/bin/python3
import os, pathlib, sys, subprocess, shutil
root=pathlib.Path(__file__).resolve().parents[1]
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
if name=="sha256sum":
    args=[str(root/"media"/pathlib.Path(a).name) if a.startswith(str(root/"dev")) else a for a in args]
    raise SystemExit(subprocess.call(["/usr/bin/sha256sum",*args]))
if name=="fw_printenv":
    text=(root/"environment").read_text()
    print(dict(line.split("=",1) for line in text.splitlines())[args[-1]] if "-n" in args else text,end="\\n" if "-n" in args else "")
    raise SystemExit(0)
with (root/"mutations").open("a") as log: log.write(name+"\\n")
if (root/("fail-"+name)).exists(): raise SystemExit(1)
if name=="flashcp":
    shutil.copyfile(args[0],root/"media"/pathlib.Path(args[1]).name)
    if (root/"corrupt-boot").exists(): (root/"media/mtd7").write_bytes(b"corrupt")
elif name=="fw_setenv":
    text=(root/"environment").read_text()
    text="\\n".join(line for line in text.splitlines() if not line.startswith("fit_size="))+"\\nfit_size="+args[-1]+"\\n"
    (root/"environment").write_text(text)
''')
    mock.chmod(0o755)
    for command in ("flashcp", "fw_printenv", "fw_setenv", "sha256sum"):
        (root / f"bin/{command}").symlink_to(mock)
    shutil.copy(BOARD / "pluto-flash-range", root / "bin/pluto-flash-range")
    source = (BOARD / "pluto-fw-update").read_text()
    # Remap absolute filesystem roots only; execute the real transaction logic.
    source = re.sub(r"/(?:etc|sys|dev|run|tmp)/", lambda m: str(root) + m.group(), source)
    source = source.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={root}/bin:/usr/bin:/bin")
    # BusyBox may resolve its sha256sum applet before PATH; dispatch the fake explicitly.
    source = source.replace("sha256sum ", f"{root}/bin/sha256sum ")
    script = root / "updater"
    script.write_text(source)
    frm = root / "input.frm"
    frm.write_bytes(frm_bytes(fit.read_bytes()))
    return root, script, frm


def run_updater(updater):
    root, script, frm = updater
    result = subprocess.run(["busybox", "sh", str(script), str(frm)], capture_output=True, text=True)
    assert not (root / "run/pluto-fw-update.lock").exists()
    return result


def test_updater_success_discovers_devices(updater):
    root, _, _ = updater
    result = run_updater(updater)
    assert result.returncode == 0, result.stderr
    assert (root / "mutations").read_text() == "flashcp\nfw_setenv\n"
    assert "Done" in result.stdout


@pytest.mark.parametrize("problem", ["checksum", "truncated", "missing-offset", "missing-capacity",
    "oversized", "partition-end", "invalid-fit", "wrong-target"])
def test_updater_refuses_before_any_mutation(updater, problem):
    root, _, frm = updater
    if problem == "checksum":
        frm.write_bytes(frm.read_bytes()[:-1] + b"X")
    elif problem == "truncated":
        frm.write_bytes(b"short")
    elif problem == "missing-offset":
        (root / "sys/devices/spi/mtd/mtd9/offset").unlink()
    elif problem == "missing-capacity":
        (root / "sys/devices/spi/spi-nor/size").unlink()
    elif problem in ("oversized", "partition-end"):
        # A tiny structurally valid candidate on a boundary-crossing layout.
        (root / "sys/devices/spi/mtd/mtd9/offset").write_text("16777216\n")
        (root / "sys/devices/spi/mtd/mtd9/size").write_text("16777216\n" if problem == "oversized" else "0\n")
    elif problem == "invalid-fit":
        frm.write_bytes(frm_bytes(b"ITB PlutoSDR (ADALM-PLUTO)" + b"x" * 100))
    elif problem == "wrong-target":
        (root / "etc/device_config").write_text('FRM_MAGIC="other board"\n')
    result = run_updater(updater)
    assert result.returncode == 1, result.stderr
    assert "Failed:" in result.stderr
    assert not (root / "mutations").exists()
    assert "Done" not in result.stdout


@pytest.mark.parametrize("failure,expected", [("fail-flashcp", "flashcp\n"),
    ("corrupt-boot", "flashcp\n"), ("fail-fw_setenv", "flashcp\nfw_setenv\n")])
def test_updater_stops_after_failure(updater, failure, expected):
    root, _, _ = updater
    (root / failure).touch()
    result = run_updater(updater)
    assert result.returncode != 0
    assert (root / "mutations").read_text() == expected
    assert "Done" not in result.stdout


@pytest.mark.parametrize("size,allowed", [(12935447, True), (14680064, True), (14744943, False)])
def test_actual_large_frm_is_gated(updater, size, allowed):
    import struct
    root, _, frm = updater
    payload = bytearray(frm.read_bytes()[:-33])
    payload.extend(bytes(size - len(payload)))
    struct.pack_into(">I", payload, 4, size)
    frm.write_bytes(frm_bytes(payload))
    result = run_updater(updater)
    assert (result.returncode == 0) == allowed, result.stderr
    if not allowed:
        assert "image exceeds qualified flash range" in result.stderr
        assert not (root / "mutations").exists()


def test_ssh_wrapper_propagates_failure(updater):
    root, script, frm = updater
    wrapper = root / "update_frm.sh"
    wrapper.write_text((BOARD / "update_frm.sh").read_text().replace(
        'exec /usr/sbin/pluto-fw-update', f'exec /usr/bin/busybox sh {script}'))
    frm.write_bytes(b"bad")
    result = subprocess.run(["busybox", "sh", str(wrapper), str(frm)], capture_output=True)
    assert result.returncode == 1
    assert not (root / "mutations").exists()


@pytest.mark.parametrize("boot_present", [False, True])
def test_mass_storage_refusal_stops_entire_batch(updater, boot_present):
    root, script, frm = updater
    for name in ("mnt/msd", "opt", "sys/kernel/config/usb_gadget/composite_gadget/functions/mass_storage.0/lun.0",
                 "sys/class/leds/led0:green"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "sys/kernel/config/usb_gadget/composite_gadget/functions/mass_storage.0/lun.0/file").touch()
    (root / "mnt/msd/pluto.frm").write_bytes(b"invalid incoming firmware")
    if boot_present:
        (root / "mnt/msd/boot.frm").write_bytes(b"also present")
    with (root / "etc/device_config").open("a") as f:
        f.write(f'TARGET=plutosdr\nFIRMWARE="{root}/mnt/msd/pluto.frm"\n')
    for command in ("losetup", "mount", "umount", "sleep"):
        target = root / f"bin/{command}"
        target.write_text("#!/bin/sh\nexit 0\n")
        target.chmod(0o755)
    source = (BOARD / "update.sh").read_text()
    source = re.sub(r"/(?:etc|sys|dev|run|tmp|mnt|opt)/", lambda m: str(root) + m.group(), source)
    source = source.replace("/usr/sbin/pluto-fw-update", f"/usr/bin/busybox sh {script}")
    source = source.replace("while [ 1 ]", "for test_iteration in 1")
    source = source.replace('handle_boot_frm "${bootimage}"', f'echo boot-handler >> {root}/mutations')
    source = source.replace('process_ini $conf', f'echo env-handler >> {root}/mutations')
    for command in ("losetup", "mount", "umount", "sleep"):
        source = re.sub(r"(?m)^(\s*)" + command + " ", rf"\1{root}/bin/{command} ", source)
    batch = root / "update.sh"
    batch.write_text(source)
    result = subprocess.run(["busybox", "sh", str(batch)], capture_output=True, text=True, timeout=10)
    assert (root / "mnt/msd/FAILED").exists(), result.stderr
    reason = "separate verified transactions" if boot_present else "truncated FRM"
    assert reason in (root / "mnt/msd/UPDATE_RESULT").read_text()
    assert not (root / "mutations").exists()
    assert not (root / "mnt/msd/SUCCESS").exists()
