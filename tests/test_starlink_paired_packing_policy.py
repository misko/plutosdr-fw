"""Evaluate the real pre-synthesis Tcl policy without launching Vivado."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("profile,threshold,expected", [
    ("paired-pilot", None, 4), ("paired-pilot", "4", 4),
    ("paired-pilot", "8", 8), ("paired-pilot", "16", 16),
    ("detector-only", None, 4), (None, None, 4),
    ("paired-pilot", "32", None), ("paired-pilot", "0", None),
    ("paired-pilot", "16.0", None), ("detector-only", "16", None),
    (None, "16", None), ("pss-only", "8", None),
])
def test_control_set_override_is_explicit_bounded_and_paired_only(profile, threshold, expected):
    assert shutil.which("tclsh"), "Tcl is required for the build-policy test"
    root = Path(__file__).resolve().parents[1]
    source = (root / "hdl/projects/pluto/system_project.tcl").read_text()
    policy = source[source.index("set control_set_threshold 4"):
                    source.index("set_property strategy Flow_AreaOptimized_high")]
    environment = {key: value for key, value in os.environ.items() if key not in (
        "STARLINK_PSS_PROFILE", "STARLINK_PSS_CONTROL_SET_THRESHOLD")}
    if profile is not None:
        environment["STARLINK_PSS_PROFILE"] = profile
    if threshold is not None:
        environment["STARLINK_PSS_CONTROL_SET_THRESHOLD"] = threshold
    script = f"if {{[catch {{\n{policy}\n}} message]}} {{puts stderr $message; exit 2}}\n"
    script += "puts $control_set_threshold\n"
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                            env=environment, timeout=10)
    if expected is None:
        assert result.returncode == 2 and "control-set" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(expected)
