"""Source-specific offline policy. Tcl/owner mocks never invoke Vivado."""
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = ACQ / "build/local-admission-actual-R1B1O1-L1-175-prepared-v4"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


PREPARE = load(ACQ / "prepare_local_admission_physical.py", "local_physical")
GATE = load(ACQ / PREPARE.ADMISSION, "local_admission")


def clean_env():
    return {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"}}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("local-physical") / "prepared"
    result = PREPARE.prepare(ACTUAL, output)
    assert result["rtl_count"] == 8 and result["source_count"] == 12
    assert result["functional_terminals"] == 11 and result["original_automation_status"] == "PASS"
    assert result["histories"]["values"] == 2193
    return output


def test_complete_source_inverse_defaults_and_original_physical_recipe(prepared):
    source = prepared / "frozen_sources"
    assert {p.name for p in source.iterdir()} == set(PREPARE.source_names())
    for name, expected in GATE.RTL_HASHES.items():
        assert GATE.sha(source / name) == expected
        assert (source / name).read_bytes() == (ACTUAL / "frozen_sources" / name).read_bytes()
    top = (source / next(iter(GATE.RTL_HASHES))).read_text()
    assert "parameter integer LOCAL_FIRST_ADMISSION = 0" in top
    assert ".LOCAL_FIRST_ADMISSION(LOCAL_FIRST_ADMISSION)" in top
    reference = (prepared / "synthesize_arithmetic_prepared.reference.tcl").read_text()
    assert PREPARE.adapt((prepared / PREPARE.SYNTHESIS).read_text(), PREPARE.synthesis_edits(), True) == reference
    assert reference == PREPARE.base().adapt_synthesis((ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text())
    assert PREPARE.adapt((prepared / PREPARE.RUNNER).read_text(), PREPARE.runner_edits(), True) == (ACQ / "run_arithmetic_synthesis.py").read_text()
    for name in ("fft_bank_owned_resource_probe.xdc", "fft_bank_owned_synth_threads.tcl"):
        assert (source / name).read_bytes() == (ACQ / name).read_bytes()
    assert (prepared / "route_completed_input_fence.tcl").read_bytes() == (ACQ / "route_completed_input_fence.tcl").read_bytes()
    assert (prepared / PREPARE.POLICY).read_bytes() == Path(__file__).read_bytes()
    with pytest.raises(FileExistsError):
        PREPARE.prepare(ACTUAL, prepared)
    assert not (prepared / "project").exists()


def test_standalone_frozen_admission_from_other_cwd(prepared, tmp_path):
    command = [GATE.PYTHON, "-B", str(prepared / "prepare_local_admission_physical.py"), "--verify",
               os.path.relpath(prepared, tmp_path), "--expected", GATE.sha(prepared / "SHA256SUMS")]
    result = subprocess.run(command, cwd=tmp_path, env=clean_env(), capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "standalone.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["histories"]["guard_equal_snapshots"] == 17
    assert not list(prepared.rglob("__pycache__"))


@pytest.mark.parametrize("which", ["synthesis", "owner"])
def test_each_missing_or_duplicate_literal_adapter_anchor(prepared, which):
    original, edits = ((prepared / "synthesize_arithmetic_prepared.reference.tcl", PREPARE.synthesis_edits())
                       if which == "synthesis" else (ACQ / "run_arithmetic_synthesis.py", PREPARE.runner_edits()))
    text = original.read_text()
    for old, _ in edits:
        for mutation in (text.replace(old, "", 1), text + old):
            with pytest.raises(ValueError, match="nonunique"):
                PREPARE.adapt(mutation, edits)


@pytest.mark.parametrize("mutation", [None, "omit_L", "L0", "LX", "LZ", "omit_R", "omit_B", "omit_O"])
def test_exact_physical_generic_forwarding_readback(prepared, tmp_path, mutation):
    text = (prepared / PREPARE.SYNTHESIS).read_text()
    fragment = text[text.index("set_property generic "):text.index("set_property STEPS.SYNTH_DESIGN")]
    replacements = {"omit_L": (" LOCAL_FIRST_ADMISSION=$local] [get_filesets sources_1]", "] [get_filesets sources_1]"),
                    "L0": ("LOCAL_FIRST_ADMISSION=$local] [get_filesets sources_1]", "LOCAL_FIRST_ADMISSION=0] [get_filesets sources_1]"),
                    "LX": ("LOCAL_FIRST_ADMISSION=$local] [get_filesets sources_1]", "LOCAL_FIRST_ADMISSION=x] [get_filesets sources_1]"),
                    "LZ": ("LOCAL_FIRST_ADMISSION=$local] [get_filesets sources_1]", "LOCAL_FIRST_ADMISSION=z] [get_filesets sources_1]"),
                    "omit_R": ("REGISTERED_SCHEDULING=$registered ", ""),
                    "omit_B": ("BOUNDARY_ROUND_SAT=$round ", ""), "omit_O": ("REGISTER_OPERANDS=$operands ", "")}
    if mutation:
        old, new = replacements[mutation]
        assert fragment.count(old) == 1
        fragment = fragment.replace(old, new)
    mock = """
set registered 1; set round 1; set operands 1; set local 1; set source_dir /offline
proc get_filesets {args} {return sources_1}
proc set_property {name value object} {set ::bound $value}
proc get_property {name object} {return $::bound}
"""
    result = subprocess.run(["tclsh"], input=mock + "\nif {[catch {\n" + fragment +
                            '\n} reason]} {puts $reason; exit 1}\nputs "OFFLINE_BOUND=$bound"\n',
                            env=clean_env(), capture_output=True, text=True, check=False, timeout=10)
    (tmp_path / "generics.log").write_text(result.stdout + result.stderr)
    if mutation:
        assert result.returncode == 1 and "missing physical parameter" in result.stdout
    else:
        assert result.returncode == 0 and "LOCAL_FIRST_ADMISSION=1" in result.stdout


@pytest.mark.parametrize("mode", ["trap", "wrong_inventory", "overwrite", "alias_output", "alias_prepared"])
def test_tcl_admission_and_copied_verifier_stop_before_project(prepared, tmp_path, mode):
    output = tmp_path / "NO_PHYSICAL_PROJECT"
    passed = prepared
    expected = "0" * 64 if mode == "wrong_inventory" else GATE.sha(prepared / "SHA256SUMS")
    if mode == "overwrite": output.mkdir()
    if mode == "alias_output":
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        output = tmp_path / "alias/new"
    if mode == "alias_prepared":
        (tmp_path / "alias").symlink_to(prepared, target_is_directory=True)
        passed = tmp_path / "alias"
    poison = {"PYTHONHOME": "/missing/local-home", "PYTHONPATH": "/missing/local-path", "LD_LIBRARY_PATH": "/missing/local-lib"}
    check_parent = "\n".join(f'if {{$::env({key}) ne "{value}"}} {{error "PARENT_ENV_CHANGED"}}' for key, value in poison.items())
    program = f"""
proc version {{args}} {{return 2022.2}}
proc set_param {{args}} {{}}
proc create_project {{args}} {{
  uplevel #0 {{{PREPARE.base().COPY_VERIFY}}}
  {check_parent}
  puts "OFFLINE_COPIED_INPUTS_VERIFIED"; error "OFFLINE_STOP_BEFORE_PROJECT"
}}
set argc 3; set argv [list {{{output}}} {{{passed}}} {expected}]
if {{[catch {{source {{{prepared / PREPARE.SYNTHESIS}}}}} reason]}} {{puts $reason; exit 1}}
error "unexpected escape"
"""
    result = subprocess.run(["tclsh"], input=program, env=os.environ | poison,
                            capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "tcl-preflight.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 1
    marker = "symlink physical path" if mode.startswith("alias") else {
        "trap": "OFFLINE_STOP_BEFORE_PROJECT", "wrong_inventory": "unexpected arithmetic physical preparation",
        "overwrite": "refusing to overwrite synthesis evidence"}.get(mode)
    assert marker in result.stdout, result.stdout + result.stderr
    if mode == "trap": assert "OFFLINE_COPIED_INPUTS_VERIFIED" in result.stdout
    assert not (output / "project").exists()


@pytest.mark.parametrize("mutation", ["runtime", "constraint", "route", "adapter", "binding", "owner", "extra", "helper"])
def test_rehashed_package_cannot_replace_source_or_recipe(prepared, tmp_path, mutation):
    changed = tmp_path / "changed"
    shutil.copytree(prepared, changed)
    target = {"runtime": "frozen_sources/" + next(iter(GATE.RTL_HASHES)),
              "constraint": "frozen_sources/fft_bank_owned_resource_probe.xdc",
              "route": "route_completed_input_fence.tcl", "adapter": PREPARE.SYNTHESIS,
              "binding": PREPARE.SETTINGS, "owner": PREPARE.RUNNER, "extra": "not_declared.py",
              "helper": PREPARE.BASE_REFERENCE}[mutation]
    path = changed / target
    path.write_text((path.read_text() if path.exists() else "") + "\n# OFFLINE MUTATION\n")
    inventory = PREPARE.inventory(changed)
    (changed / "SHA256SUMS").write_text("".join(f"{v}  {k}\n" for k, v in sorted(inventory.items())))
    with pytest.raises(ValueError):
        PREPARE.verify(changed, GATE.sha(changed / "SHA256SUMS"))


@pytest.mark.parametrize("mutation", ["missing", "extra", "changed", "alias", "dangling"])
def test_original49_source_closure_rejected_offline_without_touching_original(tmp_path, mutation):
    actual = tmp_path / "actual"
    actual.mkdir()
    shutil.copy(ACTUAL / "manifest.json", actual / "manifest.json")
    shutil.copytree(ACTUAL / "frozen_sources", actual / "frozen_sources")
    source = actual / "frozen_sources"
    name = next(iter(GATE.RTL_HASHES))
    if mutation == "missing": (source / name).unlink()
    elif mutation == "extra": (source / "extra.v").write_text("extra")
    elif mutation == "changed": (source / name).write_text("changed")
    else:
        (source / name).unlink()
        (source / name).symlink_to(ACTUAL / "frozen_sources" / (name if mutation == "alias" else "absent.v"))
    with pytest.raises(ValueError): GATE.verify_sources(actual)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "blank", "wrong_root", "guard_bit", "counter", "arithmetic_bit", "late_error", "wrong_time", "reference"])
def test_recorded_history_values_not_just_path_inventory(prepared, mutation):
    evidence = prepared / "admission_evidence"
    text = (evidence / "wdb_outer.log").read_text()
    reference = (evidence / "arithmetic_wdb_reference.log").read_text()
    rows = text.splitlines()
    index = next(i for i, row in enumerate(rows) if row.startswith("LOCAL_WDB_VALUE\tobserver\t100000000000\t") and "/actual_view\t" in row)
    fields = rows[index].split("\t")
    if mutation == "missing": rows.pop(index)
    elif mutation == "duplicate": rows.append(rows[index])
    elif mutation == "late_error": rows.append("ERROR: late failure after receipt")
    elif mutation == "reference": reference = reference.replace("\t600ba0066440280000000800380000", "\t1", 1)
    else:
        if mutation == "blank": fields[-1] = "<Blank>"
        elif mutation == "wrong_root": fields[-2] = fields[-2].replace("L=1", "L=0")
        elif mutation == "guard_bit": fields[-1] = fields[-1][:-1] + ("1" if fields[-1][-1] == "0" else "0")
        elif mutation == "wrong_time": fields[2] = "2"
        else:
            suffix = "/pre_checks\t" if mutation == "counter" else "/dut/product_position\t"
            index = next(i for i, row in enumerate(rows) if row.startswith("LOCAL_WDB_VALUE\t") and "\t100000000000\t" in row and suffix in row)
            fields = rows[index].split("\t")
            fields[-1] = "0" if fields[-1] != "0" else "1"
        rows[index] = "\t".join(fields)
    if mutation == "reference": assert reference != (evidence / "arithmetic_wdb_reference.log").read_text()
    with pytest.raises(ValueError):
        GATE.verify_histories("\n".join(rows), (ACTUAL / GATE.SIM / "arithmetic_diagnostic_signals.txt").read_text().splitlines(),
                             (ACTUAL / GATE.SIM / "local_guard_diagnostic_signals.txt").read_text().splitlines(), reference)


@pytest.mark.parametrize("mode", ["success", "exit17", "exception", "tamper", "exit17_tamper", "bad_preflight", "loader_zero", "no_marker", "duplicate_marker", "missing_dcp", "blackbox"])
def test_one_shot_owner_completion_postfailure_integrity_and_parent_env(prepared, tmp_path, monkeypatch, mode):
    runner = load(prepared / PREPARE.RUNNER, "local_owner_" + mode)
    owned = tmp_path / "MOCK_ONLY_NO_PHYSICAL_RUN"
    expected = "0" * 64 if mode == "bad_preflight" else GATE.sha(prepared / "SHA256SUMS")
    poison = {"PYTHONHOME": "/missing/owner-home", "PYTHONPATH": "/missing/owner-path", "LD_LIBRARY_PATH": "/missing/owner-lib"}
    for key, value in poison.items(): monkeypatch.setenv(key, value)
    calls = []

    def fake_launch(command, run):
        calls.append(command)
        assert all(os.environ[key] == value for key, value in poison.items())
        if mode == "exception": raise OSError("OFFLINE_LAUNCH_EXCEPTION")
        if mode == "loader_zero":
            (run / "launch.log").write_text("OFFLINE loader exit0 before Tcl\n")
            return 0
        copied = run / "synthesis/frozen_sources"
        shutil.copytree(prepared / "frozen_sources", copied)
        shutil.copy(prepared / PREPARE.SYNTHESIS, copied / PREPARE.SYNTHESIS)
        if "tamper" in mode: (copied / next(iter(GATE.RTL_HASHES))).write_text("changed copy")
        for name in runner.PRODUCTS:
            if mode == "missing_dcp" and name.endswith(".dcp"): continue
            (run / "synthesis" / name).write_text(("black_boxes=1\n" if mode == "blackbox" else "black_boxes=0\n")
                                                  if name == "resource_receipt.txt" else "OFFLINE MOCK NOT PHYSICAL\n")
        count = 0 if mode == "no_marker" else 2 if mode == "duplicate_marker" else 1
        (run / "launch.log").write_text((runner.MARKER + "\n") * count)
        return 17 if mode.startswith("exit17") else 0

    monkeypatch.setattr(runner, "launch_vivado", fake_launch)
    status = runner.execute(prepared, expected, owned)
    receipt = json.loads((owned / "terminal.json").read_text())
    assert status == (0 if mode == "success" else 127 if mode == "exception" else 17 if mode.startswith("exit17") else 1)
    assert receipt["completion"]["verified"] == (mode == "success")
    assert receipt["after_audit"] == (1 if "tamper" in mode or mode == "bad_preflight" else 0)
    assert len(calls) == (0 if mode == "bad_preflight" else 1)
    for phase in ("before", "after"): assert (owned / (phase + "-integrity.log")).is_file()
    if calls:
        assert calls[0].index("-log") < calls[0].index("-tclargs") and calls[0].index("-journal") < calls[0].index("-tclargs")
        assert calls[0][-3:] == [str(owned / "synthesis"), str(prepared), expected]
    assert all(os.environ[key] == value for key, value in poison.items())
    with pytest.raises(FileExistsError): runner.execute(prepared, expected, owned)


@pytest.mark.parametrize("mode", ["nonzero", "wrong_result", "environment"])
def test_full_frozen_actual_child_is_mandatory_and_sanitized(prepared, monkeypatch, mode):
    real = GATE.subprocess.run
    parent = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"): monkeypatch.setenv(key, "/missing/poison")
    observed = []

    def child(command, **kwargs):
        observed.append(command)
        assert command[1] == "-B" and command[-2:] == ["--expected", GATE.MANIFEST]
        assert not {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"} & set(kwargs["env"])
        if mode == "nonzero": return SimpleNamespace(returncode=1, stdout="", stderr="mock fail")
        if mode == "wrong_result": return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        return real(command, **kwargs)

    monkeypatch.setattr(GATE.subprocess, "run", child)
    if mode == "environment":
        assert GATE.verify(ACTUAL, prepared / "admission_evidence")["functional_terminals"] == 11
    else:
        with pytest.raises(ValueError): GATE.verify(ACTUAL, prepared / "admission_evidence")
    assert len(observed) == 1
    assert all(os.environ[key] == "/missing/poison" for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"))
    assert os.environ.get("PATH") == parent.get("PATH")


@pytest.mark.parametrize("mode", ["output_parent", "prepared_alias", "owner_parent", "dangling"])
def test_lexical_alias_rejection_before_directory_or_physical_execution(prepared, tmp_path, mode):
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path / "missing" if mode == "dangling" else prepared if mode == "prepared_alias" else tmp_path,
                     target_is_directory=True)
    if mode in {"output_parent", "dangling"}:
        with pytest.raises(ValueError, match="symlink"): PREPARE.prepare(ACTUAL, alias / "new")
    elif mode == "prepared_alias":
        with pytest.raises(ValueError, match="symlink"): PREPARE.verify(alias, GATE.sha(prepared / "SHA256SUMS"))
    else:
        runner = load(prepared / PREPARE.RUNNER, "local_alias_owner")
        with pytest.raises(ValueError, match="symlink"): runner.execute(prepared, GATE.sha(prepared / "SHA256SUMS"), alias / "new")
    assert not (tmp_path / "new").exists()
