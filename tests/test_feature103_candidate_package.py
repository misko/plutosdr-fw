"""Provenance and archive invariants for feature-103 candidate packaging."""

import gzip
import importlib.util
import stat
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/feature103/package_candidate.py"
SPEC = importlib.util.spec_from_file_location("feature103_package", SCRIPT)
assert SPEC and SPEC.loader
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


def _entry(mode: int, payload: bytes):
    return ([0, mode, 0, 0, 1, 0, len(payload), 0, 0, 0, 0, 0, 0], payload)


def test_newc_round_trip_preserves_inventory_and_payloads():
    entries = OrderedDict(
        (
            ("opt", _entry(stat.S_IFDIR | 0o755, b"")),
            ("opt/VERSIONS", _entry(stat.S_IFREG | 0o644, b"device-fw old\n")),
            ("usr/sbin/iiod", _entry(stat.S_IFREG | 0o755, b"old-iiod")),
        )
    )
    encoded = PACKAGE.write_newc(entries)
    decoded = PACKAGE.read_newc(encoded)
    assert tuple(decoded) == tuple(entries)
    assert {name: value[1] for name, value in decoded.items()} == {
        name: value[1] for name, value in entries.items()
    }


def test_feature_rootfs_changes_only_explicit_files(tmp_path):
    entries = OrderedDict(
        (
            ("opt/VERSIONS", _entry(stat.S_IFREG | 0o644, b"device-fw old\nlinux old\n")),
            ("usr/sbin/iiod", _entry(stat.S_IFREG | 0o755, b"old-iiod")),
            ("usr/lib/libiio.so.0.25", _entry(stat.S_IFREG | 0o755, b"old-lib")),
            ("etc/sentinel", _entry(stat.S_IFREG | 0o644, b"unchanged")),
        )
    )
    base = gzip.compress(PACKAGE.write_newc(entries), mtime=0)
    iiod = tmp_path / "iiod"
    libiio = tmp_path / "libiio"
    iiod.write_bytes(b"new-iiod")
    libiio.write_bytes(b"new-lib")
    rebuilt, changes = PACKAGE.feature_rootfs(base, iiod, libiio)
    decoded = PACKAGE.read_newc(gzip.decompress(rebuilt))
    assert tuple(decoded) == tuple(entries)
    assert decoded["etc/sentinel"][1] == b"unchanged"
    assert set(changes) == {
        "opt/VERSIONS",
        "usr/sbin/iiod",
        "usr/lib/libiio.so.0.25",
    }


def test_release_parent_and_fpga_are_hard_pinned():
    release = dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/counter-rx-v1.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )
    assert PACKAGE.BASE_DFU_SHA256 == release["image_sha256"]
    assert PACKAGE.BASE_FIT_SHA256 == release["fit_body_sha256"]
    assert PACKAGE.BASE_COMPONENT_SHA256["fpga"] == release["fpga_bitstream_sha256"]
    assert PACKAGE.BASE_COMPONENT_SHA256["rootfs"] == release["rootfs_sha256"]


def test_staged_bisection_is_fixed_and_ram_only():
    source = SCRIPT.read_text()
    assert PACKAGE.STAGES == ("parent", "repack", "kernel", "rx0", "full")
    assert '"persistent_write_allowed": False' in source
    assert 'default = "config@0"' in source
    assert 'config@9 {{ description = "Linux with fpga RevC"' in source
    assert 'fdt@1 {{ description = "zynq-pluto-sdr"' in source
    assert 'fdt@2 {{ description = "zynq-pluto-sdr-revb"' in source
    assert 'fdt@3 {{ description = "zynq-pluto-sdr-revc"' in source
    assert "algo = \"md5\"" in source


def test_device_trees_have_no_noncanonical_hash_nodes():
    rendered = PACKAGE.its_text(
        "repack",
        "parent-reva.dtb",
        "parent-revb.dtb",
        "parent-revc.dtb",
        "parent-zImage",
        "parent-rootfs.cpio.gz",
    )
    images = rendered.split("configurations", 1)[0]
    for node in ("fdt@1", "fdt@2", "fdt@3"):
        body = images.split(node, 1)[1].split("};", 1)[0]
        assert "hash@" not in body


def test_rx0_stages_transform_every_fit_device_tree_slot():
    source = SCRIPT.read_text()
    assert 'work / f"rx0-{revision}.dtb"' in source
    for revision in ("reva", "revb", "revc"):
        assert f'"rx0-{revision}.dtb"' in source
