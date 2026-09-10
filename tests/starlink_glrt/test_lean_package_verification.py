"""Independent cpio extraction detects a stale/missing GLF1 boot script."""
import gzip
import hashlib
import subprocess

import pytest

from scripts.verify_glrt_ram import verify_lean_init

from .test_ram_package import rootfs


@pytest.mark.parametrize("fault", [None, "script", "selection", "missing-input", "replacement"])
def test_embedded_boot_script_is_bound_to_profile_and_input_hash(tmp_path, fault):
    archive = gzip.decompress(rootfs(tmp_path))
    members = subprocess.run(["cpio", "-it", "--quiet"], input=archive,
        capture_output=True, check=True).stdout.decode().splitlines()
    selector = tmp_path / "legacy_scorer.txt"
    selector.write_text("0\n")
    init = tmp_path / "etc/init.d/S22starlink_glrt_iio"
    inputs = {str(selector): hashlib.sha256(selector.read_bytes()).hexdigest(),
              str(init): hashlib.sha256(init.read_bytes()).hexdigest()}
    manifest = {"input_sha256": inputs,
                "rootfs_replaced_members": ["opt/VERSIONS", "etc/init.d/S22starlink_glrt_iio"]}
    if fault == "script":
        inputs[str(init)] = "0" * 64
    elif fault == "selection":
        selector.write_text("1\n")
    elif fault == "missing-input":
        del inputs[str(init)]
    elif fault == "replacement":
        manifest["rootfs_replaced_members"] = ["opt/VERSIONS"]
    if fault is None:
        verify_lean_init(archive, members, manifest, "cpio")
    else:
        with pytest.raises(ValueError):
            verify_lean_init(archive, members, manifest, "cpio")


def test_reference_package_does_not_require_a_new_selector_or_boot_script():
    verify_lean_init(b"", [], {"input_sha256": {}, "rootfs_replaced_members": ["opt/VERSIONS"]}, "cpio")
