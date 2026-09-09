"""Execute the real routed-audit admission against isolated fixture repositories.

These checks qualify provenance, fresh-output admission and read-only policy;
they do not simulate Vivado timing, CDC or physical endpoint completeness.
"""
import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_HDL = Path(os.environ.get("STARLINK_PSS_AUDIT_HDL", ROOT / "hdl"))
AUDIT = AUDIT_HDL / "projects/pluto/audit_shared_realtime_routed.tcl"
SOURCE_NAMES = (
    "starlink_pss_shared_realtime_xfft_service.v",
    "starlink_pss_realtime_input_guard.v",
    "starlink_pss_realtime_result_guard.v",
    "starlink_pss_block_mailbox.v",
)


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True, timeout=10,
    ).stdout.strip()


@pytest.fixture
def fixture_audit(tmp_path):
    if not shutil.which("tclsh"):
        pytest.skip("tclsh unavailable")
    repo = tmp_path / "hdl"
    source_dir = repo / "library/starlink_pss_acquisition"
    source_dir.mkdir(parents=True)
    for name in SOURCE_NAMES:
        (source_dir / name).write_text(f"// immutable fixture: {name}\n")
    run_git(repo, "init", "--quiet")
    run_git(repo, "add", "library")
    run_git(repo, "-c", "user.name=Audit Fixture", "-c",
            "user.email=audit-fixture@example.invalid", "commit", "--quiet", "-m", "fixture")
    revision = run_git(repo, "rev-parse", "HEAD")
    # Deliberately different dirty files: an admitted audit must use git show.
    for name in SOURCE_NAMES:
        (source_dir / name).write_text(f"// uncommitted and not the built source: {name}\n")
    script = repo / "projects/pluto/audit_shared_realtime_routed.tcl"
    script.parent.mkdir(parents=True)
    script.write_bytes(AUDIT.read_bytes())
    checkpoint = tmp_path / "completed.dcp"
    checkpoint.write_bytes(b"fixture checkpoint, not a real Vivado netlist\n")
    output = tmp_path / "new audit output"
    harness = tmp_path / "admission.tcl"
    harness.write_text(r'''
set target [lindex $argv 0]
set fixture_tool_version [lindex $argv 1]
set argv [lrange $argv 2 end]
set argc [llength $argv]
proc version {args} {return $::fixture_tool_version}
proc open_checkpoint {checkpoint} {
  puts "REACHED_OPEN_CHECKPOINT $checkpoint"
  error "INTENTIONAL_OPEN_CHECKPOINT_STUB"
}
if {[catch {source $target} message]} {
  puts stderr $message
  exit 2
}
puts stderr "UNEXPECTED_SCRIPT_COMPLETION"
exit 3
''')
    return {
        "repo": repo, "script": script, "checkpoint": checkpoint,
        "output": output, "revision": revision, "harness": harness,
        "sha": sha256(checkpoint.read_bytes()).hexdigest(),
    }


def invoke(fixture, *, version="2022.2", args=None):
    if args is None:
        args = [fixture["checkpoint"], fixture["output"],
                fixture["revision"], fixture["sha"]]
    return subprocess.run(
        ["tclsh", str(fixture["harness"]), str(fixture["script"]), version,
          *map(str, args)], capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.mark.parametrize("args", [[], ["only-one"], ["a", "b", "c"], ["a"] * 5])
def test_wrong_argument_count_cannot_create_output(fixture_audit, args):
    result = invoke(fixture_audit, args=args)
    assert result.returncode == 2 and "expected CHECKPOINT" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not fixture_audit["output"].exists()


@pytest.mark.parametrize("version", ["2022.1", "2023.1", "unknown"])
def test_wrong_tool_rejected_before_any_output(fixture_audit, version):
    result = invoke(fixture_audit, version=version)
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not fixture_audit["output"].exists()


@pytest.mark.parametrize("field,value,expected", [
    ("revision", "ff4229bb", "full immutable HDL commit required"),
    ("revision", "G" * 40, "full immutable HDL commit required"),
    ("revision", "a" * 41, "full immutable HDL commit required"),
    ("sha", "a" * 63, "checkpoint SHA256 required"),
    ("sha", "a" * 65, "checkpoint SHA256 required"),
    ("sha", "G" * 64, "checkpoint SHA256 required"),
    ("sha", "0" * 64, "checkpoint SHA256 mismatch"),
    ("revision", "0" * 40, "unknown revision"),
])
def test_invalid_provenance_rejected_without_output(fixture_audit, field, value, expected):
    fixture_audit[field] = value
    result = invoke(fixture_audit)
    assert result.returncode == 2 and expected in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not fixture_audit["output"].exists()


def test_missing_checkpoint_rejected_without_output(fixture_audit):
    fixture_audit["checkpoint"] = fixture_audit["repo"] / "missing.dcp"
    result = invoke(fixture_audit)
    assert result.returncode == 2 and "missing checkpoint" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not fixture_audit["output"].exists()


@pytest.mark.parametrize("kind", ["empty_directory", "nonempty_directory", "file"])
def test_existing_output_is_never_modified(fixture_audit, kind):
    output = fixture_audit["output"]
    if kind == "file":
        output.write_bytes(b"original evidence")
    else:
        output.mkdir()
        if kind == "nonempty_directory":
            (output / "summary.txt").write_bytes(b"original evidence")
    before = (output.read_bytes() if output.is_file() else
              {p.name: p.read_bytes() for p in output.iterdir()})
    result = invoke(fixture_audit)
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    after = (output.read_bytes() if output.is_file() else
             {p.name: p.read_bytes() for p in output.iterdir()})
    assert before == after


def test_valid_admission_freezes_immutable_source_not_dirty_worktree(fixture_audit):
    checkpoint_before = fixture_audit["checkpoint"].read_bytes()
    result = invoke(fixture_audit)
    assert result.returncode == 2 and "INTENTIONAL_OPEN_CHECKPOINT_STUB" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" in result.stdout
    assert fixture_audit["checkpoint"].read_bytes() == checkpoint_before
    output = fixture_audit["output"]
    assert (output / "audit_source.tcl").read_bytes() == AUDIT.read_bytes()
    for name in SOURCE_NAMES:
        frozen = (output / name).read_bytes()
        assert frozen == f"// immutable fixture: {name}\n".encode()
        dirty = fixture_audit["repo"] / "library/starlink_pss_acquisition" / name
        assert frozen != dirty.read_bytes()
    assert {p.name for p in output.iterdir()} == {*SOURCE_NAMES, "audit_source.tcl"}


def test_audit_never_mutates_saved_design_or_constraints():
    # This narrow guard supplements actual Tcl admission and the real retained
    # Vivado run. It is not a substitute for physical endpoint/path evidence.
    commands = "\n".join(line for line in AUDIT.read_text().splitlines()
                         if not line.lstrip().startswith("#"))
    forbidden = (
        "set_property", "create_clock", "create_generated_clock", "set_max_delay",
        "set_min_delay", "set_false_path", "set_multicycle_path", "set_bus_skew",
        "set_clock_groups", "reset_timing", "read_xdc", "write_checkpoint",
        "opt_design", "phys_opt_design", "place_design", "route_design", "write_bitstream",
    )
    for command in forbidden:
        assert not re.search(rf"\b{command}\b", commands), command
    assert "source_association=caller_attested_build_provenance_not_derived_from_checkpoint" in commands
    assert "checkpoint changed during the read-only audit" in commands
    assert "no timed paths for $label; do not infer a pass" in commands
    assert "sticky_fault_second_stage $fault_first $fault_second 5.0" in commands
