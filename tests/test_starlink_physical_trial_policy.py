"""Execute diagnostic-runner admission without pretending to run implementation."""

from pathlib import Path
import subprocess

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/explore_shared_receiver_checkpoint.tcl"


@pytest.mark.parametrize("mode", ["spread-high", "spread-medium", "post-route"])
def test_named_trial_requires_fresh_evidence_directory(tmp_path, mode):
    checkpoint = tmp_path / "saved.dcp"
    checkpoint.touch()
    existing = tmp_path / "existing"
    existing.mkdir()
    result = subprocess.run(["tclsh", str(RUNNER), str(checkpoint), str(existing), mode],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "refusing to overwrite experiment evidence" in result.stderr
    assert not list(existing.iterdir())


@pytest.mark.parametrize("mode", ["default", "spread-low", "spread-medium; exit 0", ""])
def test_unknown_trial_is_rejected_before_creating_output(tmp_path, mode):
    checkpoint = tmp_path / "saved.dcp"
    checkpoint.touch()
    output = tmp_path / "new"
    result = subprocess.run(["tclsh", str(RUNNER), str(checkpoint), str(output), mode],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "unsupported implementation experiment" in result.stderr
    assert not output.exists()


def test_missing_checkpoint_does_not_create_output(tmp_path):
    output = tmp_path / "new"
    result = subprocess.run(["tclsh", str(RUNNER), str(tmp_path / "missing.dcp"),
                             str(output), "spread-medium"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "missing input checkpoint" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("clock,mode,existing,error", [
    ("200", "actual-synth", True, "requires a fresh output directory"),
    ("150", "actual-synth", False, "restricted to 100/200 MHz"),
    ("200", "unknown", False, "only optional synthesis-clock probe"),
    ("200", "actual-synth; exit 0", False, "only optional synthesis-clock probe"),
])
def test_actual_synthesis_probe_admission(tmp_path, clock, mode, existing, error):
    runner = RUNNER.parents[2] / "library/starlink_pss_acquisition/measure_shared_xfft_clock.tcl"
    output = tmp_path / "evidence"
    if existing:
        output.mkdir()
    # The actual runner exits before any Vivado design command. Only emulate
    # its version query, not synthesis, implementation, clocks or timing.
    script = "proc version {args} {return 2022.2}\nset argc 3\n"
    script += f"set argv [list {{{output}}} {{{clock}}} {{{mode}}}]\n"
    script += f"if {{[catch {{source {{{runner}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and error in result.stderr
    assert output.exists() == existing
    if existing:
        assert not list(output.iterdir())
