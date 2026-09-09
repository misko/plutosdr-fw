"""Real Tcl admission and strict helper policy; not Vivado physical qualification."""
import re
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "hdl/projects/pluto/trial_shared_realtime_direction_replication.tcl"
SOURCES = (
    "starlink_pss_shared_realtime_xfft_service.v",
    "starlink_pss_realtime_input_guard.v",
    "starlink_pss_realtime_result_guard.v",
    "starlink_pss_block_mailbox.v",
)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, timeout=10).stdout.strip()


@pytest.fixture
def fixture_trial(tmp_path):
    repo = tmp_path / "hdl"
    library = repo / "library/starlink_pss_acquisition"
    library.mkdir(parents=True)
    for name in SOURCES:
        (library / name).write_text(f"// frozen {name}\n")
    git(repo, "init", "--quiet")
    git(repo, "add", "library")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "-m", "immutable fixture")
    revision = git(repo, "rev-parse", "HEAD")
    for name in SOURCES:
        (library / name).write_text("// dirty source must not be used\n")
    script = repo / "projects/pluto" / RUNNER.name
    script.parent.mkdir(parents=True)
    script.write_bytes(RUNNER.read_bytes())
    checkpoint = tmp_path / "complete.dcp"
    checkpoint.write_bytes(b"not a real DCP; admission-only fixture\n")
    output = tmp_path / "fresh evidence"
    harness = tmp_path / "admission.tcl"
    harness.write_text('''
set target [lindex $argv 0]
set fixture_version [lindex $argv 1]
set argv [lrange $argv 2 end]
set argc [llength $argv]
proc version {args} {return $::fixture_version}
proc open_checkpoint {path} {
  puts "REACHED_OPEN_CHECKPOINT $path"
  error INTENTIONAL_OPEN_STUB
}
proc phys_opt_design {args} {error UNAUTHORIZED_MUTATION_REACHED}
if {[catch {source $target} message]} {puts stderr $message; exit 2}
exit 3
''')
    return {"repo": repo, "script": script, "checkpoint": checkpoint, "output": output,
            "harness": harness, "revision": revision,
            "digest": sha256(checkpoint.read_bytes()).hexdigest()}


def invoke(fixture, *, version="2022.2", args=None):
    if args is None:
        args = [fixture["checkpoint"], fixture["output"], fixture["revision"],
                fixture["digest"], "inspect", "read-only-inspection"]
    return subprocess.run(["tclsh", str(fixture["harness"]), str(fixture["script"]),
                           version, *map(str, args)], capture_output=True,
                          text=True, timeout=10, check=False)


@pytest.mark.parametrize("args", [[], ["a"], ["a"] * 5, ["a"] * 7])
def test_wrong_arity_cannot_create_evidence(fixture_trial, args):
    result = invoke(fixture_trial, args=args)
    assert result.returncode == 2 and "expected CHECKPOINT" in result.stderr
    assert not fixture_trial["output"].exists()


@pytest.mark.parametrize("version", ["2022.1", "2023.1", "unknown"])
def test_wrong_tool_cannot_reach_checkpoint(fixture_trial, version):
    result = invoke(fixture_trial, version=version)
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not fixture_trial["output"].exists()


@pytest.mark.parametrize("index,value,message", [
    (2, "0463f887", "full immutable HDL commit"),
    (2, "G" * 40, "full immutable HDL commit"),
    (2, "0" * 40, "unknown revision"),
    (3, "a" * 63, "checkpoint SHA256 required"),
    (3, "G" * 64, "checkpoint SHA256 required"),
    (3, "0" * 64, "checkpoint SHA256 mismatch"),
    (4, "optimize", "mode must be"),
    (5, "not-attested", "inspect requires"),
])
def test_bad_admission_never_allocates_output(fixture_trial, index, value, message):
    f = fixture_trial
    args = [f["checkpoint"], f["output"], f["revision"], f["digest"],
            "inspect", "read-only-inspection"]
    args[index] = value
    result = invoke(f, args=args)
    assert result.returncode == 2 and message in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout
    assert not f["output"].exists()


@pytest.mark.parametrize("kind", ["empty", "nonempty", "file"])
def test_existing_output_is_immutable(fixture_trial, kind):
    output = fixture_trial["output"]
    if kind == "file":
        output.write_bytes(b"original")
    else:
        output.mkdir()
        if kind == "nonempty":
            (output / "summary.txt").write_bytes(b"original")
    before = output.read_bytes() if output.is_file() else {p.name: p.read_bytes() for p in output.iterdir()}
    result = invoke(fixture_trial)
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    after = output.read_bytes() if output.is_file() else {p.name: p.read_bytes() for p in output.iterdir()}
    assert before == after


def test_missing_checkpoint_is_rejected_before_output(fixture_trial):
    fixture_trial["checkpoint"] = fixture_trial["repo"] / "absent.dcp"
    result = invoke(fixture_trial)
    assert result.returncode == 2 and "missing checkpoint" in result.stderr
    assert not fixture_trial["output"].exists()


def test_replication_requires_independently_authorized_source_hash_and_identity(fixture_trial):
    f = fixture_trial
    args = [f["checkpoint"], f["output"], "0463f887d592452c940d3c70589becc330d70a0c",
            f["digest"], "replicate", "shared-realtime-0463-direction-replication-v1"]
    result = invoke(f, args=args)
    assert result.returncode == 2 and "is not authorized" in result.stderr
    assert not f["output"].exists()
    assert "REACHED_OPEN_CHECKPOINT" not in result.stdout


def test_read_only_admission_retains_sources_and_negative_receipt(fixture_trial):
    f = fixture_trial
    before = f["checkpoint"].read_bytes()
    result = invoke(f)
    assert result.returncode == 2 and "INTENTIONAL_OPEN_STUB" in result.stderr
    assert "REACHED_OPEN_CHECKPOINT" in result.stdout
    assert f["checkpoint"].read_bytes() == before
    assert (f["output"] / "trial_source.tcl").read_bytes() == RUNNER.read_bytes()
    for name in SOURCES:
        assert (f["output"] / name).read_text() == f"// frozen {name}\n"
    receipt = (f["output"] / "summary.txt").read_text()
    assert "DIRECTION_TRIAL_REJECTED operation_started=0 routing_performed=0" in receipt
    assert "original_sha256_after=" + f["digest"] in receipt
    assert "DIRECTION_TRIAL_FINISHED" not in receipt


def test_policy_limits_one_targeted_operation_and_no_constraint_or_numeric_mutation():
    text = RUNNER.read_text()
    commands = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert len(re.findall(r"^\s*phys_opt_design\b", commands, re.MULTILINE)) == 1
    assert "phys_opt_design -force_replication_on_nets $net -verbose" in commands
    assert len(re.findall(r"^\s*route_design\s*$", commands, re.MULTILINE)) == 1
    for forbidden in ("set_property", "create_clock", "set_false_path", "set_max_delay",
                      "set_multicycle_path", "set_clock_groups", "read_xdc", "reset_timing",
                      "place_design", "opt_design", "write_bitstream", "generate_target"):
        assert not re.search(rf"\b{forbidden}\b", commands), forbidden
    assert 'error "targeted replication was a no-op"' in commands
    assert "CONFIG.FFINIT INIT1" in commands
    assert "get_bel_pins -of_objects $logical" in commands
    assert "get_property IS_INVERTED $logical" in commands
    assert "original direction consumer set changed or duplicated" in commands
    assert "source/replica transition/pin/INIT mismatch" in commands
    assert "timing_qualification=independent_full_receiver_audit_required" in commands
    # Vivado 2022.2 embeds Tcl 8.5; desktop tclsh fixtures alone miss this.
    assert not re.search(r"^\s*try\s*\{", commands, re.MULTILINE)
    assert "set run_code [catch {" in commands


def test_signature_comparison_detects_init_pin_polarity_and_driver_mutants(tmp_path):
    text = RUNNER.read_text()
    helpers = text[text.index("proc same_dict "):text.index("proc primitive_inventory ")]
    harness = tmp_path / "helpers.tcl"
    harness.write_text(helpers + r'''
set physical [list FDRE {CONFIG.FFINIT INIT1 CONFIG.FFSR SRLOW} {C {CK 0} D {D 0}}]
set inputs {C BUFG_O CE CONST1 D LUT_O R CONST0}
set original [list $physical $inputs]
if {![same_signature $original $original]} {error "identity failed"}
set mutants [list \
  [list [list FDRE {CONFIG.FFINIT INIT0 CONFIG.FFSR SRLOW} {C {CK 0} D {D 0}}] $inputs] \
  [list [list FDRE {CONFIG.FFINIT INIT1 CONFIG.FFSR SRLOW} {C {CK 1} D {D 0}}] $inputs] \
  [list [list FDRE {CONFIG.FFINIT INIT1 CONFIG.FFSR SRLOW} {C {CK 0} D {SR 0}}] $inputs] \
  [list $physical {C BUFG_O CE CONST1 D DIFFERENT_LUT_O R CONST0}]]
foreach mutant $mutants {if {[same_signature $original $mutant]} {error "mutation escaped"}}
puts SIGNATURE_MUTANTS_CAUGHT
''')
    result = subprocess.run(["tclsh", str(harness)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "SIGNATURE_MUTANTS_CAUGHT"


@pytest.mark.parametrize("changed,message", [
    ("{source FDRE old_lut LUT3}", "targeted replication was a no-op"),
    ("{source FDRE}", "existing primitive removed/type changed"),
    ("{source FDRE old_lut LUT4}", "existing primitive removed/type changed"),
    ("{source FDRE old_lut LUT3 extra LUT3}", "unreviewed new primitive"),
    ("{source FDRE old_lut LUT3 other_replica FDRE}", "unreviewed new primitive"),
])
def test_negative_transformation_footprints_stop_before_semantic_assumptions(tmp_path, changed, message):
    text = RUNNER.read_text()
    helper = text[text.index("proc validate_replicas "):text.index("\nset routing_performed 0")]
    harness = tmp_path / "negative_footprint.tcl"
    harness.write_text(helper + f'''\nset fixture_after {changed}
proc primitive_inventory {{}} {{return $::fixture_after}}
if {{![catch {{validate_replicas {{source FDRE old_lut LUT3}} source {{}} old_lut {{}} {{}}}} why]}} {{
  error "negative mutation accepted"
}}
puts $why
''')
    result = subprocess.run(["tclsh", str(harness)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert message in result.stdout
