"""Offline-only physical adapter checks; synthetic admission is explicitly mocked.

No vendor process and no claim that a checked-product actual result passed.
The real generated admission remains unchanged in every copied helper.
"""
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-product-actual-prepared-v2")
GEN = runpy.run_path(str(ACQ / "prepare_checked_product_physical.py"))
BODY, EDITS, OWNER = GEN["build"](ACQ)
P1 = GEN["restore"](BODY, EDITS)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def namespace(path):
    data = {"__file__": str(path)}
    exec(compile(BODY, str(path), "exec"), data)
    return data


def test_complete_old_helper_inverse_and_fixed_runtime():
    assert hashlib.sha256(P1.encode()).hexdigest() == GEN["P1_HELPER_SHA"]
    helper = namespace(ACQ / "not_executed.py")
    assert len(helper["RTL"]) == 14 and len(set(helper["RTL"])) == 14
    binding = runpy.run_path(str(ACQ / "prepare_checked_product_actual.py"))
    assert set(helper["RTL"]) == set(binding["RUNTIME_SHA"])
    for name, expected in binding["RUNTIME_SHA"].items():
        assert digest(ACQ / name) == digest(ACTUAL / "frozen_sources" / name) == expected
    assert digest(ACQ / "run_exact_control_synthesis.py") == OWNER
    assert helper["SETTINGS"]["CHECKED_PRODUCT_BANK"] == 1
    assert len(helper["SETTINGS"]) == 11


@pytest.mark.parametrize("before,after", [
    ("rtl_count\": 14", "rtl_count\": 13"),
    ("CHECKED_PRODUCT_BANK=$checked_product", "CHECKED_PRODUCT_BANK=0"),
    ("timed_out\": False", "timed_out\": True"),
    ("timeout=90", "timeout=91"),
])
def test_inverse_rejects_mutated_whole_body(before, after):
    assert before in BODY
    with pytest.raises(ValueError):
        GEN["restore"](BODY.replace(before, after, 1), EDITS)


@pytest.fixture
def mocked_prepared(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    helper_file = tools / "prepare_exact_control_physical.py"
    helper_file.write_text(BODY)
    helper = namespace(helper_file)
    for name in (*helper["FIXED"], "run_exact_control_synthesis.py"):
        shutil.copyfile(ACQ / name, tools / name)
    # Explicit test-local mock only; the emitted helper still has real admission.
    actual = tmp_path / "stub_actual"
    source = actual / "frozen_sources"
    source.mkdir(parents=True)
    for name in helper["SOURCE_NAMES"]:
        if name not in ("fft_bank_owned_resource_probe.xdc", "fft_bank_owned_synth_threads.tcl"):
            shutil.copyfile(ACTUAL / "frozen_sources" / name, source / name)
    report = {"actual_directory": str(actual), "settings": helper["SETTINGS"],
        "source_sha256": {p.name: digest(p) for p in source.iterdir()},
        "qualified_observer": {"scope": "TEST_STUB_NOT_ACTUAL_ACCEPTANCE"}}
    helper["verify_actual"].__globals__["verify_actual"] = lambda path: report
    prepared = tmp_path / "prepared"
    result = helper["prepare"](actual, prepared)
    assert result["rtl_count"] == 14 and result["checked_product"] == 1
    assert (prepared / "prepare_exact_control_physical.py").read_text() == BODY
    (tmp_path / "TEST_SCOPE.txt").write_text("Mocked admission; no actual or vendor qualification.\n")
    return helper, prepared


def test_copier_complete_closure_and_literal_physical_suffix(mocked_prepared):
    helper, prepared = mocked_prepared
    assert len((prepared / "SHA256SUMS").read_text().splitlines()) == 25
    new = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    old = {}
    exec(compile(P1, "old", "exec"), old)
    original = (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    previous = old["adapt_synthesis"](original)
    # The synthesis implementation body, part/factory/strategy/constraints and
    # resource/zero-BB reports are untouched; only declarations/receipts differ.
    anchor = "set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY"
    new_tail = new[new.index(anchor):].replace(
        "; checked_product_bank=$checked_product", "")
    assert new_tail == previous[previous.index(anchor):]
    for name in (*helper["FIXED"], "run_exact_control_synthesis.py"):
        path = prepared / (name if name in ("route_completed_input_fence.tcl", "run_exact_control_synthesis.py")
            else "synthesize_fft_bank_owned_slice.original.tcl" if name == "synthesize_fft_bank_owned_slice.tcl"
            else "frozen_sources/" + name)
        assert digest(path) == digest(ACQ / name)
    names = re.search(r"set rtl_names \{([^}]+)\}", new)[1].split()
    assert {name + ".v" for name in names} == set(helper["RTL"]) and len(names) == 14
    assert "set_property top starlink_pss_fft_bank_owned_checked_product " in new
    copied = prepared.parent / "copied"
    shutil.copytree(prepared / "frozen_sources", copied)
    shutil.copyfile(prepared / "synthesize_exact_control_prepared.tcl", copied / "synthesize_exact_control_prepared.tcl")
    assert helper["verify_prepared"](prepared, copied)["rtl_count"] == 14
    for name in helper["RTL"]:
        path = copied / name
        body = path.read_bytes()
        path.write_bytes(body + b"\n")
        with pytest.raises(ValueError, match="copied synthesis source differs"):
            helper["verify_prepared"](prepared, copied)
        path.write_bytes(body)


def tcl(body, tmp_path):
    path = tmp_path / "mock.tcl"
    path.write_text(body)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "PYTHONOPTIMIZE")}
    run = subprocess.run(["tclsh", str(path)], capture_output=True, text=True, env=env, timeout=15)
    (tmp_path / "stdout.log").write_text(run.stdout)
    (tmp_path / "stderr.log").write_text(run.stderr)
    return run


@pytest.mark.parametrize("mutation", ["healthy", "missing", "zero", "duplicate", "conflict", "lowercase", "unknown"])
def test_exact_checked_generic_readback(mutation, tmp_path):
    helper = namespace(tmp_path / "not_executed.py")
    options = "REGISTERED_SCHEDULING DISTRIBUTED_FAST_FAULT PRIVATE_NEXT_START_SCRATCH PER_CAUSE_FAULT_CDC PRIVATE_ROM_READ_AHEAD PRIVATE_BLOCK_METADATA_READ_AHEAD PRODUCER_LOCAL_FINAL_FENCE CHECKED_PRODUCT_BANK".split()
    values = [name + "=1" for name in options]
    if mutation == "missing":
        values.pop()
    elif mutation == "zero":
        values[-1] = "CHECKED_PRODUCT_BANK=0"
    elif mutation == "duplicate":
        values.append(values[-1])
    elif mutation == "conflict":
        values.append("CHECKED_PRODUCT_BANK=0")
    elif mutation == "lowercase":
        values[-1] = values[-1].lower()
    elif mutation == "unknown":
        values[-1] = "CHECKED_PRODUCT_BANK=x"
    pre = "\n".join(f"set {name} 1" for name in (
        "registered", "distributed", "scratch", "per_cause", "rom_word", "rom_metadata", "producer_final", "checked_product"))
    body = pre + "\nproc get_filesets {args} {return sources_1}\nproc get_property {args} {return {" + " ".join(values) + "}}\n"
    run = tcl(body + helper["GENERIC_CHECK"] + '\nputs "GENERIC_OFFLINE_STUB_PASS"\n', tmp_path)
    assert (run.returncode == 0) == (mutation == "healthy"), run.stdout + run.stderr


def test_full_tcl_admission_stops_before_create_project(mocked_prepared, tmp_path):
    _, prepared = mocked_prepared
    output = tmp_path / "never_vendor"
    # Intercept only Python admission calls; all hashing/copying remains real.
    stub = '''proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {args} {puts "OFFLINE_CREATE_PROJECT_TRAP"; exit 0}
rename exec real_exec
proc exec {args} {
  if {[lindex $args 0] eq "env"} {
    if {[lsearch -exact $args --verify] < 0 || [lsearch -exact $args -B] < 0} {error "unexpected child"}
    return "TEST_STUB_ADMISSION_NOT_ACTUAL_PASS"
  }
  return [real_exec {*}$args]
}
'''
    program = stub + f"set argc 3\nset argv [list {{{output}}} {{{prepared}}} {digest(prepared / 'SHA256SUMS')}]\nsource {{{prepared / 'synthesize_exact_control_prepared.tcl'}}}\n"
    result = tcl(program, tmp_path)
    assert result.returncode == 0 and result.stdout.count("OFFLINE_CREATE_PROJECT_TRAP") == 1
    assert not (output / "project").exists()
    assert len(list((output / "frozen_sources").glob("*.v"))) == 14


def test_pending_actual_is_rejected_without_output(tmp_path):
    helper = namespace(tmp_path / "not_executed.py")
    actual = tmp_path / "candidate"
    actual.mkdir()
    with pytest.raises(FileNotFoundError):
        helper["prepare"](actual, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("key,bad", [
    ("vendor_exit", 1), ("vendor_exit", False), ("timed_out", True),
    ("interruption", "Timeout"), ("source_pins_unchanged", False),
    ("live_sources_unchanged", False), ("generated_wrapper_matches_known", False),
    ("result_exit", 1), ("functional_accepted", False), ("physical_qualified", True),
    ("deployment_eligible", True),
])
def test_original_actual_failure_or_timeout_not_admitted(key, bad, tmp_path):
    helper = namespace(tmp_path / "not_executed.py")
    owner = tmp_path / "checked-drain-actual-parent.wlpL6hYk"
    owner.mkdir()
    result = {"vendor_exit": 0, "timed_out": False, "interruption": None,
        "source_pins_unchanged": True, "live_sources_unchanged": True,
        "generated_wrapper_matches_known": True, "result_exit": 0,
        "functional_accepted": True, "physical_qualified": False, "deployment_eligible": False}
    result[key] = bad
    (owner / "outcome.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="pending/failed/unqualified"):
        helper["verify_actual"](tmp_path / "candidate")


@pytest.mark.parametrize("kind", ["output", "tools", "alias"])
def test_no_overwrite_or_alias(kind, tmp_path):
    output = tmp_path / "prepared"
    if kind == "output":
        output.mkdir()
    elif kind == "tools":
        output.with_name(output.name + "-tools").mkdir()
    else:
        output.symlink_to(tmp_path / "nonexistent")
    with pytest.raises((ValueError, FileExistsError)):
        GEN["prepare"](tmp_path / "unused_actual", output)


def test_v2_tcl_is_literal_same_as_preserved_v1():
    preserved = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-physical-v1-preserved.dQFhr7fV/prepare_checked_product_physical.py")
    assert digest(preserved) == "9454bd225b7888d90fba6e2afb288b35b672060f38495b111dcf52176a271e6c"
    old = runpy.run_path(str(preserved))
    old_body, old_edits, _ = old["build"](ACQ)
    assert old["restore"](old_body, old_edits) == GEN["restore"](BODY, EDITS) == P1
    original = (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    old_namespace = {}
    exec(compile(old_body, "old_unexecuted", "exec"), old_namespace)
    current = namespace(ACQ / "new_unexecuted.py")
    old_tcl = old_namespace["adapt_synthesis"](original)
    assert current["adapt_synthesis"](original) == old_tcl
    assert hashlib.sha256(old_tcl.encode()).hexdigest() == "b01efa80e900af1d19765a0ed06703fc7c3d1d86d32ee5d09d3ce225c75c602f"


@pytest.fixture
def mocked_actual_prefix(tmp_path, monkeypatch):
    """Mocked original outcome + CLI stdout for negative admission unit tests.

    Never read the running actual's outcome/results or invoke its CLI. All test
    copies retain their real source89; forged receipts are confined to tmp_path.
    """
    actual = tmp_path / "mock_actual_NOT_QUALIFIED"
    actual.mkdir()
    members = {}
    for line in (ACTUAL / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        target = actual / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ACTUAL / name, target)
        assert digest(target) == expected
        members[name] = expected
    shutil.copyfile(ACTUAL / "SHA256SUMS", actual / "SHA256SUMS")
    owner = tmp_path / "checked-drain-actual-parent.wlpL6hYk"
    owner.mkdir()
    shutil.copyfile(ACTUAL.parent / owner.name / "owner.py", owner / "owner.py")
    outcome = {"vendor_exit": 0, "timed_out": False, "interruption": None,
        "source_pins_unchanged": True, "live_sources_unchanged": True,
        "generated_wrapper_matches_known": True, "result_exit": 0,
        "functional_accepted": True, "physical_qualified": False, "deployment_eligible": False}
    for name, value in {
        "outcome.json": outcome,
        "input-pins.json": {"manifest": GEN["ACTUAL_INVENTORY"], "files": members},
        "after-sources.json": {"manifest_unchanged": True, "source_errors": [], "live_errors": []},
        "execution.json": {k: outcome[k] for k in ("vendor_exit", "timed_out", "interruption")},
    }.items():
        (owner / name).write_text(json.dumps(value))
    result = {"scope": "TEST_CLI_OUTPUT_NOT_ACTUAL_ACCEPTANCE", "final_drain_witnesses": {
        "scope": "two_final_live_preedge_drains_after_unchanged_full_result_gate",
        "markers": [[0, 32, 100, 200, 100], [1, 6, 300, 410, 110]]}}
    (owner / "result-check.json").write_text(json.dumps({"exit": 0, "stdout": json.dumps(result)}))
    helper = namespace(tmp_path / "unexecuted.py")
    def fake_cli(command, **kwargs):
        assert command[-2:] == ["--verify-result", str(actual)]
        assert command[2] == str(actual / "prepare_checked_product_drain_actual.py")
        assert not any(k in kwargs["env"] for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE", "LD_LIBRARY_PATH"))
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")
    monkeypatch.setattr(helper["subprocess"], "run", fake_cli)
    return helper, actual, owner, result


@pytest.mark.parametrize("mutation", ["missing", "wrong_scope", "missing_row", "duplicate", "wrong_count", "wrong_service", "over_budget", "boolean"])
def test_v1_or_false_drain_cli_result_rejected(mocked_actual_prefix, mutation):
    helper, actual, _, result = mocked_actual_prefix
    drain = result["final_drain_witnesses"]
    if mutation == "missing":
        result.pop("final_drain_witnesses")
    elif mutation == "wrong_scope":
        drain["scope"] = "old_full_result_without_drain"
    elif mutation == "missing_row":
        drain["markers"].pop()
    elif mutation == "duplicate":
        drain["markers"][1] = drain["markers"][0]
    elif mutation == "wrong_count":
        drain["markers"][0][1] = 31
    elif mutation == "wrong_service":
        drain["markers"][0][4] = 99
    elif mutation == "over_budget":
        drain["markers"][0][3:] = [5316, 5216]
    elif mutation == "boolean":
        drain["markers"][0][0] = False
    with pytest.raises(ValueError, match="frozen drain-aware|exact two final drain"):
        helper["verify_actual"](actual)


def test_complete_cli_result_must_equal_original_owner_json(mocked_actual_prefix):
    helper, actual, owner, _ = mocked_actual_prefix
    (owner / "result-check.json").write_text(json.dumps({"exit": 0, "stdout": "{}"}))
    with pytest.raises(ValueError, match="differs from original owner"):
        helper["verify_actual"](actual)


@pytest.mark.parametrize("mutation", ["v1_inventory", "old_owner", "changed_source", "old_cli"])
def test_source_specific_v1_or_corrupt_v2_rejected(mocked_actual_prefix, mutation):
    helper, actual, owner, _ = mocked_actual_prefix
    if mutation == "v1_inventory":
        shutil.copyfile(ACTUAL.parent / "checked-product-actual-prepared-v1/SHA256SUMS", actual / "SHA256SUMS")
        expected = "actual89 inventory"
    elif mutation == "old_owner":
        shutil.copyfile(ACTUAL.parent / "checked-actual-parent.xtGiofa6/owner.py", owner / "owner.py")
        expected = "owner changed"
    else:
        name = "frozen_sources/starlink_pss_fft_bank_owned_checked_product.v" if mutation == "changed_source" else "prepare_checked_product_drain_actual.py"
        path = actual / name
        path.write_bytes(path.read_bytes() + b"\n")
        expected = "actual source changed"
    with pytest.raises(ValueError, match=expected):
        helper["verify_actual"](actual)
