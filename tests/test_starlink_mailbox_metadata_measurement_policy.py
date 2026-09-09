"""Run real measurement admission with synthesis deliberately stubbed out.

These tests establish evidence isolation/provenance, not synthesized behavior,
receiver timing, or hardware qualification. Actual netlist replay is separate.
"""
import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[1] / "hdl"))
RELATIVE = Path("library/starlink_pss_acquisition")
SCRIPT = HDL / RELATIVE / "measure_mailbox_metadata_tree.tcl"


def git(repo, *arguments):
    return subprocess.run(["git", "-C", str(repo), *arguments], capture_output=True,
                          text=True, check=True, timeout=10).stdout.strip()


@pytest.fixture
def admission(tmp_path):
    repo = tmp_path / "repo"
    directory = repo / RELATIVE
    directory.mkdir(parents=True)
    mailbox = directory / "starlink_pss_block_mailbox.v"
    mailbox.write_text("// immutable baseline fixture, not RTL\n")
    git(repo, "init", "--quiet")
    git(repo, "add", str(mailbox))
    git(repo, "-c", "user.name=Mailbox Fixture", "-c",
        "user.email=mailbox-fixture@example.invalid", "commit", "--quiet", "-m", "baseline")
    revision = git(repo, "rev-parse", "HEAD")
    mailbox.write_text("// current candidate fixture, not RTL\n")
    script = directory / SCRIPT.name
    script.write_bytes(SCRIPT.read_bytes())
    harness = tmp_path / "harness.tcl"
    harness.write_text('''
set target [lindex $argv 0]
set tool_version [lindex $argv 1]
set argv [lrange $argv 2 end]
set argc [llength $argv]
proc version {args} {return $::tool_version}
proc set_param {args} {error "SYNTHESIS_BOUNDARY_STUB"}
if {[catch {source $target} message]} {puts stderr $message; exit 2}
exit 3
''')
    return {"repo": repo, "revision": revision, "output": tmp_path / "new output",
            "mailbox": mailbox, "script": script, "harness": harness}


def invoke(fixture, *, version="2022.2", arguments=None):
    if arguments is None:
        arguments = [fixture["output"], fixture["revision"]]
    return subprocess.run(["tclsh", str(fixture["harness"]), str(fixture["script"]),
                           version, *map(str, arguments)], capture_output=True,
                          text=True, check=False, timeout=10)


@pytest.mark.parametrize("arguments", [[], ["one"], ["one", "two", "three"]])
def test_wrong_argument_count_creates_no_evidence(admission, arguments):
    result = invoke(admission, arguments=arguments)
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not admission["output"].exists()


@pytest.mark.parametrize("version", ["2022.1", "2023.1"])
def test_wrong_tool_creates_no_evidence(admission, version):
    result = invoke(admission, version=version)
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not admission["output"].exists()


@pytest.mark.parametrize("revision", ["HEAD", "a" * 39, "G" * 40, "0" * 40])
def test_nonimmutable_or_missing_baseline_creates_no_evidence(admission, revision):
    admission["revision"] = revision
    result = invoke(admission)
    assert result.returncode == 2 and "SYNTHESIS_BOUNDARY_STUB" not in result.stderr
    assert not admission["output"].exists()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_evidence_is_not_overwritten(admission, kind):
    output = admission["output"]
    if kind == "directory":
        output.mkdir()
        marker = output / "scope.txt"
    else:
        marker = output
    marker.write_bytes(b"original evidence")
    result = invoke(admission)
    assert result.returncode == 2 and "output directory must be new" in result.stderr
    assert marker.read_bytes() == b"original evidence"


def test_valid_admission_freezes_distinct_baseline_candidate_and_runner(admission):
    result = invoke(admission)
    assert result.returncode == 2 and "SYNTHESIS_BOUNDARY_STUB" in result.stderr
    output = admission["output"]
    assert (output / "baseline.v").read_text() == "// immutable baseline fixture, not RTL\n"
    assert (output / "candidate.v").read_bytes() == admission["mailbox"].read_bytes()
    assert (output / "measurement_source.tcl").read_bytes() == SCRIPT.read_bytes()
    scope = (output / "scope.txt").read_text()
    assert f"baseline_commit={admission['revision']}\n" in scope
    assert "not_receiver_timing_or_CDC_qualification" in scope
    assert "MAILBOX_METADATA_TREE_MEASURED" not in scope
