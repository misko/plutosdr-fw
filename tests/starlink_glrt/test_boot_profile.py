"""Execute the boot inventory check against synthetic sysfs, without hardware."""
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("abi,events,native,extension,iq_count,accepted", [
    ("GLR1-1.0-upper-only", 1, "none", "none", 1, True),
    ("GLF1-1.0-upper-only", 0, "GLN1-1.0", "GLF1-1.0", 1, True),
    ("GLF1-1.0-upper-only", 1, "GLN1-1.0", "GLF1-1.0", 1, False),
    ("GLR1-1.0-upper-only", 0, "GLN1-1.0", "GLX1-1.0", 1, False),
    ("GLF1-1.0-upper-only", 0, "none", "GLF1-1.0", 1, False),
    ("GLF1-1.0-upper-only", 0, "GLN1-1.0", "GLX1-1.0", 1, False),
    ("GLF1-2.0-upper-only", 0, "GLN1-1.0", "GLF1-1.0", 1, False),
    ("GLF1-1.0-upper-only", 0, "GLN1-1.0", "GLF1-1.0", 2, False),
    ("GLR1-1.0-upper-only", 2, "none", "none", 1, False),
    ("GLF1-1.0-upper-only", 0, "GLN1-1.0", "GLF1-1.0", 0, False),
    ("GLA1-1.0-upper-only", 1, "GLA1-1.0", "GLA1-1.0", 1, True),
    ("GLA1-1.0-upper-only", 0, "GLA1-1.0", "GLA1-1.0", 1, False),
    ("GLA1-1.0-upper-only", 2, "GLA1-1.0", "GLA1-1.0", 1, False),
    ("GLA1-1.0-upper-only", 1, "none", "GLA1-1.0", 1, False),
    ("GLA1-1.0-upper-only", 1, "GLA1-1.0", "GLX1-1.0", 1, False),
    ("GLA1-1.0-upper-only", 1, "GLA1-1.0", "GLA1-1.0", 2, False),
])
def test_boot_inventory_matches_profile(tmp_path, abi, events, native, extension, iq_count, accepted):
    root, run = tmp_path / "iio", tmp_path / "run"
    root.mkdir()
    for index in range(iq_count + events):
        device = root / f"iio:device{index}"
        device.mkdir()
        values = {"name": "starlink-glrt-iq" if index < iq_count else "starlink-glrt-events",
                  "capture_abi": abi, "native_capture_abi": native, "capture_extension_abi": extension,
                  "local_search_abi": native}
        for key, value in values.items():
            (device / key).write_text(value + "\n")
    script = Path(__file__).resolve().parents[2] / "buildroot/board/pluto/S22starlink_glrt_iio"
    result = subprocess.run(["sh", str(script), "start"],
        env=dict(os.environ, STARLINK_GLRT_IIO_ROOT=str(root), STARLINK_GLRT_RUN_DIR=str(run)),
        capture_output=True, text=True, timeout=5, check=False)
    assert (result.returncode == 0) == accepted, result.stderr
    assert (run / "starlink-glrt-iio-load").read_text() == ("overall=PASS\n" if accepted else "overall=FAIL\n")
