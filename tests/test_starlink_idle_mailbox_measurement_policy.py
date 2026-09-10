"""Executed Tcl admission/snapshot checks; synthesis and netlist replay separate."""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[1] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
SCRIPT = ACQ / "measure_idle_mailbox_guard.tcl"


def invoke(arguments, version="2022.2"):
    source = "proc version {args} {return {" + version + "}}\n"
    source += 'proc set_param {args} {error "SYNTHESIS_BOUNDARY_STUB"}\n'
    source += "set argv [list " + " ".join(f"{{{argument}}}" for argument in arguments) + "]\n"
    source += "set argc [llength $argv]\n"
    source += f"if {{[catch {{source {{{SCRIPT}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=source, text=True, capture_output=True,
                          check=False, timeout=10)


@pytest.mark.parametrize("count", [0, 2])
def test_wrong_arity_creates_no_evidence(tmp_path, count):
    output = tmp_path / "new evidence"
    result = invoke([output, "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT_DIRECTORY" in result.stderr
    assert not output.exists()


def test_wrong_version_creates_no_evidence(tmp_path):
    output = tmp_path / "new evidence"
    result = invoke([output], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_evidence_is_preserved(tmp_path, kind):
    output = tmp_path / "evidence"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "scope.txt"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_bytes(b"original evidence")
    result = invoke([output])
    assert result.returncode == 2 and "output directory must be new" in result.stderr
    assert retained.read_bytes() == b"original evidence"


def test_snapshots_exact_guard_and_runner_before_synthesis(tmp_path):
    output = tmp_path / "new evidence"
    before = (ACQ / "starlink_pss_realtime_result_guard.v").read_bytes()
    result = invoke([output])
    assert result.returncode == 2 and "SYNTHESIS_BOUNDARY_STUB" in result.stderr
    assert (output / "guard.v").read_bytes() == before
    assert (ACQ / "starlink_pss_realtime_result_guard.v").read_bytes() == before
    assert (output / "measurement_source.tcl").read_bytes() == SCRIPT.read_bytes()
    scope = (output / "scope.txt").read_text()
    assert f"source_sha256={hashlib.sha256(before).hexdigest()}\n" in scope
    assert "caller_contract_and_full_receiver_qualified=false" in scope
    assert "IDLE_MAILBOX_DEPENDENCY_MEASURED" not in scope
