"""Read-only physical-inspection admission tests; no simulated timing evidence."""

import hashlib
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
SCRIPT = HDL / "projects/pluto/inspect_pss_physical_pressure.tcl"
REVISION = "653a3205bc7bd158a7267a9288beba63aebe12cf"


@pytest.mark.parametrize("case,error", [
    ("valid", "MOCK_REACHED_OPEN"),
    ("version", "requires Vivado 2022.2"),
    ("missing", "existing checkpoint and new output required"),
    ("existing", "existing checkpoint and new output required"),
    ("hash", "checkpoint SHA256 mismatch"),
    ("short_hash", "full revision and checkpoint hash required"),
    ("short_revision", "full revision and checkpoint hash required"),
])
def test_pressure_inspection_admits_only_new_output_and_pinned_checkpoint(tmp_path, case, error):
    checkpoint = tmp_path / "mock.dcp"
    contents = b"MOCK CHECKPOINT NOT PHYSICAL EVIDENCE"
    checkpoint.write_bytes(contents)
    digest = hashlib.sha256(contents).hexdigest()
    output = tmp_path / "output"
    if case == "missing":
        checkpoint.unlink()
    if case == "existing":
        output.mkdir()
        (output / "preserve").write_text("unchanged")
    version = "2020.2" if case == "version" else "2022.2"
    revision = "653a" if case == "short_revision" else REVISION
    if case == "hash":
        digest = "0" * 64
    if case == "short_hash":
        digest = "1234"
    script = f"""
proc version {{args}} {{ return {version} }}
proc open_checkpoint {{args}} {{ error MOCK_REACHED_OPEN }}
set argc 4
set argv [list {{{checkpoint}}} {{{output}}} {revision} {digest}]
if {{[catch [list source {{{SCRIPT}}}] message]}} {{ puts stderr $message; exit 2 }}
"""
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            check=False, timeout=10)
    assert result.returncode == 2 and error in result.stderr, result
    assert "PHYSICAL_PRESSURE_INSPECTED" not in result.stdout
    if case == "valid":
        assert (output / "inspection_source.tcl").read_bytes() == SCRIPT.read_bytes()
    elif case == "existing":
        assert list(output.iterdir()) == [output / "preserve"]
        assert (output / "preserve").read_text() == "unchanged"
    else:
        assert not output.exists()
    if case != "missing":
        assert checkpoint.read_bytes() == contents
