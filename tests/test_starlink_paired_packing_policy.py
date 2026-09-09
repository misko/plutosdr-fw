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


@pytest.mark.parametrize("shared,profile,rate,expected", [
    (None, None, None, "unchanged"), ("0", "paired-pilot", "15", "unchanged"),
    ("0", "detector-only", "60", "unchanged"),
    ("1", "paired-pilot", "15", "spread"),
    ("1", "paired-pilot", "30", "reject"),
    ("1", "paired-pilot", "60", "reject"),
    ("1", "detector-only", "15", "reject"),
    ("1", None, "15", "reject"), ("1", "paired-pilot", None, "reject"),
])
def test_spread_implementation_is_only_for_explicit_shared_receiver(shared, profile, rate, expected):
    root = Path(__file__).resolve().parents[1]
    source = (root / "hdl/projects/pluto/system_project.tcl").read_text()
    policy = source[source.index("if {[info exists ::env(STARLINK_PSS_SHARED_XFFT)]"):
                    source.index("adi_project_run pluto")]
    names = ("STARLINK_PSS_SHARED_XFFT", "STARLINK_PSS_PROFILE", "STARLINK_PSS_RATE_MSPS")
    environment = {key: value for key, value in os.environ.items() if key not in names}
    for name, value in zip(names, (shared, profile, rate)):
        if value is not None:
            environment[name] = value
    # Execute the actual Tcl policy, recording only its Vivado API boundary.
    script = "proc get_runs {name} {return $name}\n"
    script += "proc set_property {name value object} {puts [list $name $value $object]}\n"
    script += f"if {{[catch {{\n{policy}\n}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                            env=environment, timeout=10)
    if expected == "reject":
        assert result.returncode == 2 and "shared-XFFT implementation policy" in result.stderr
        assert not result.stdout
    else:
        assert result.returncode == 0, result.stderr
        if expected == "unchanged":
            assert not result.stdout
        else:
            lines = result.stdout.splitlines()
            assert lines[:4] == [
                "strategy Congestion_SpreadLogic_high impl_1",
                "STEPS.PLACE_DESIGN.ARGS.DIRECTIVE AltSpreadLogic_medium impl_1",
                "STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true impl_1",
                "STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE Explore impl_1",
            ]
            assert len(lines) == 5 and "shared_xfft_impl_gate.tcl" in lines[4]
