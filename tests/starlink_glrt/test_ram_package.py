"""Validate rootfs stamping against the independent system cpio implementation."""
import gzip
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts.package_glrt_ram import package, read_newc, stamp_rootfs


def rootfs(root, *, pss=False):
    files = {"opt/VERSIONS": b"device-fw old\nhdl old\n", "usr/sbin/iiod": b"\0BIN\xff\x10",
             "etc/init.d/S22starlink_glrt_iio": b"#!/bin/sh\nexit 0\n"}
    if pss:
        files["opt/starlink-pssctl"] = b"legacy"
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "usr/sbin/iiod-link").symlink_to("iiod")
    names = ["."] + sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    result = subprocess.run(["cpio", "--create", "--format=newc", "--quiet"],
                            input="\n".join(names).encode()+b"\n", cwd=root, capture_output=True, check=True)
    return gzip.compress(result.stdout)


def extract(archive, name):
    return subprocess.run(["cpio", "--extract", "--to-stdout", "--quiet", name],
                          input=gzip.decompress(archive), capture_output=True, check=True).stdout


def test_stamped_archive_preserves_binary_members_modes_and_links(tmp_path):
    original = rootfs(tmp_path)
    versions = "device-fw glrt-fixture\nhdl 123456789\n"
    stamped = stamp_rootfs(original, versions)
    assert extract(stamped, "opt/VERSIONS") == versions.encode()
    assert extract(original, "opt/VERSIONS") == b"device-fw old\nhdl old\n"
    assert extract(stamped, "usr/sbin/iiod") == b"\0BIN\xff\x10"
    before, after = read_newc(gzip.decompress(original)), read_newc(gzip.decompress(stamped))
    assert [e.name for e in before] == [e.name for e in after]
    for a, b in zip(before, after):
        assert a.fields[:6] == b.fields[:6] and a.fields[7:] == b.fields[7:]
        if a.name != "opt/VERSIONS":
            assert a.data == b.data
    assert stamp_rootfs(original, versions) == stamped  # Stable gzip header.


def test_legacy_pss_rootfs_and_truncated_archives_are_rejected(tmp_path):
    original = rootfs(tmp_path, pss=True)
    with pytest.raises(ValueError, match="PSS"):
        stamp_rootfs(original, "device-fw new\n")
    raw = gzip.decompress(original)
    for count in (0, 6, 109, len(raw)//2):
        with pytest.raises(ValueError):
            read_newc(raw[:count])


def test_failed_board_cannot_be_packaged(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    (board / "build_exit_code.txt").write_text("1\n")
    args = SimpleNamespace(board=board, kernel=tmp_path, label="glrt-fixture", output=tmp_path / "out")
    with pytest.raises(ValueError, match="board build did not pass"):
        package(args)
    assert not args.output.exists()
