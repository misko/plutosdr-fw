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
