"""The persistent controller is executable, pinned, and cannot start RX at boot."""
import gzip
import hashlib
import json
import stat
import struct
import subprocess

import pytest

from scripts.stage_native_controller_rootfs import MEMBER, install, require_static_arm, stage
from .test_ram_package import rootfs


def executable():
    data = bytearray(128)
    data[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHI", data, 16, 2, 40, 1)
    struct.pack_into("<I", data, 28, 52)
    struct.pack_into("<I", data, 36, 0x05000400)
    struct.pack_into("<HHH", data, 40, 52, 32, 1)
    struct.pack_into("<8I", data, 52, 1, 0, 0, 0, 128, 128, 5, 4096)
    return bytes(data)


def test_independent_cpio_extraction_preserves_rootfs_and_installs_executable(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    original = rootfs(source)
    binary = executable()
    result = install(original, binary)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    subprocess.run(["cpio", "-id", "--quiet", "--no-absolute-filenames"],
                   input=gzip.decompress(result), cwd=extracted, capture_output=True, check=True)
    assert (extracted / MEMBER).read_bytes() == binary
    assert stat.S_IMODE((extracted / MEMBER).stat().st_mode) == 0o755
    for path in source.rglob("*"):
        other = extracted / path.relative_to(source)
        if path.is_symlink():
            assert other.readlink() == path.readlink()
        elif path.is_file():
            assert other.read_bytes() == path.read_bytes()
            assert stat.S_IMODE(other.stat().st_mode) == stat.S_IMODE(path.stat().st_mode)
    assert sorted(p.name for p in (extracted / "etc/init.d").iterdir()) == ["S22starlink_glrt_iio"]
    assert install(original, binary) == result
    with pytest.raises(ValueError, match="already contains"):
        install(result, binary)


@pytest.mark.parametrize("fault", ["host", "soft-float", "interpreter", "dynamic", "truncated", "segment", "no-load"])
def test_invalid_controller_rejected(fault):
    data = bytearray(executable())
    if fault == "host": struct.pack_into("<H", data, 18, 62)
    elif fault == "soft-float": struct.pack_into("<I", data, 36, 0x05000200)
    elif fault == "interpreter": struct.pack_into("<I", data, 52, 3)
    elif fault == "dynamic": struct.pack_into("<I", data, 52, 2)
    elif fault == "truncated": data = data[:70]
    elif fault == "segment": struct.pack_into("<I", data, 68, 129)
    elif fault == "no-load": struct.pack_into("<I", data, 52, 4)
    with pytest.raises(ValueError): require_static_arm(data)


@pytest.mark.parametrize("fault", [None, "binary", "source"])
def test_staging_requires_matching_build_evidence_before_creating_output(tmp_path, fault):
    source = tmp_path / "source"
    source.mkdir()
    archive, binary, build = (tmp_path / name for name in ("rootfs.gz", "controller", "build.json"))
    archive.write_bytes(rootfs(source))
    binary.write_bytes(executable())
    code = tmp_path / "controller.c"
    code.write_text("source revision\n")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    build.write_text(json.dumps({"scope": "native_controller_arm_build", "binary_sha256": sha(binary),
        "source_sha256": {str(code): sha(code)}, "firmware_commit": "fixture"}))
    if fault == "binary": binary.write_bytes(b"changed")
    elif fault == "source": code.write_text("changed")
    output = tmp_path / "output"
    if fault:
        with pytest.raises(ValueError, match="differs"):
            stage(archive, binary, build, output)
        assert not output.exists()
    else:
        manifest = stage(archive, binary, build, output)
        assert manifest["output_rootfs_sha256"] == sha(output / "rootfs.cpio.gz")
        assert not manifest["automatic_start_installed"]
