"""Offline admission/source/parameter proof; Tcl mocks NEVER invoke Vivado."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = Path("/tmp/starlink-completed-input.5EaJuD/extra-edge-combined-prepared-v1")
SPEC = importlib.util.spec_from_file_location(
    "physical_prepare", ACQ / "prepare_exact_control_physical.py"
)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
RUN_SPEC = importlib.util.spec_from_file_location(
    "physical_run", ACQ / "run_exact_control_synthesis.py"
)
RUN = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(RUN)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("physical-fixture") / "prepared"
    receipt = PREPARE.prepare(ACTUAL, output)
    assert receipt["rtl_count"] == 7
    assert receipt["qualified_observer"] == {
        "samples": 1246258,
        "raw_equal": 953795,
        "invalid_only": 292463,
    }
    return output


def test_minimal_physical_adapter_whole_inverse_and_fixed_directives(prepared):
    original = (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    assert (
        PREPARE.sha(ACQ / "synthesize_fft_bank_owned_slice.tcl")
        == PREPARE.FIXED["synthesize_fft_bank_owned_slice.tcl"]
    )
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    text = PREPARE.once(
        text,
        'if {$argc != 3} { error "expected NEW_OUTPUT PREPARED EXPECTED_PREPARED_SHA256" }',
        'if {$argc != 2} { error "expected NEW_OUTPUT PASSED_SIMULATION_DIRECTORY" }',
    )
    text = PREPARE.once(
        text,
        "set script_dir [file join [file dirname [file normalize [info script]]] frozen_sources]",
        "set script_dir [file dirname [file normalize [info script]]]",
    )
    text = PREPARE.once(text, PREPARE.ADMISSION, PREPARE.LEGACY_ADMISSION)
    text = PREPARE.once(
        text,
        'puts $channel "source_preparation=$evidence_dir"\n'
        'puts $channel "expected_preparation_sha256=$expected_prepared"\n'
        'puts $channel "source_simulation_log=$simlog"\n',
        'puts $channel "source_simulation=$evidence_dir"\n',
    )
    text = PREPARE.once(text, PREPARE.GENERIC_CHECK, "")
    text = PREPARE.once(
        text,
        "  REGISTERED_SCHEDULING=$registered DISTRIBUTED_FAST_FAULT=$distributed \\\n  PRIVATE_NEXT_START_SCRATCH=$scratch] [get_filesets sources_1]\n",
        "  REGISTERED_SCHEDULING=$registered] [get_filesets sources_1]\n",
    )
    text = PREPARE.once(
        text,
        'puts $channel "distributed_fast_fault=$distributed; private_next_start_scratch=$scratch"\n',
        "",
    )
    text = PREPARE.once(
        text, 'puts $channel "effective_top_generics=$physical_generics"\n', ""
    )
    assert text.count(PREPARE.COPY_VERIFY) == 2
    text = text.replace(PREPARE.COPY_VERIFY, "")
    assert text == original
    for name in ("route_completed_input_fence.tcl",):
        assert (prepared / name).read_bytes() == (ACQ / name).read_bytes()
    source = prepared / "frozen_sources"
    assert {p.name for p in source.iterdir()} == set(PREPARE.SOURCE_NAMES)
    for name in PREPARE.RTL + (
        "create_shared_realtime_xfft_ip.tcl",
        "upper_edge_pss_kernel_q17.mem",
    ):
        assert (source / name).read_bytes() == (
            ACTUAL / "frozen_sources" / name
        ).read_bytes()
    for name in (
        "fft_bank_owned_resource_probe.xdc",
        "fft_bank_owned_synth_threads.tcl",
    ):
        assert (source / name).read_bytes() == (ACQ / name).read_bytes()
    with pytest.raises(FileExistsError):
        PREPARE.prepare(ACTUAL, prepared)


@pytest.mark.parametrize("mutation", [None, "distributed", "scratch", "registered"])
def test_tcl_exact_generic_binding_and_omission_witnesses(prepared, tmp_path, mutation):
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    fragment = text[
        text.index("set_property generic ") : text.index(
            "set_property STEPS.SYNTH_DESIGN"
        )
    ]
    if mutation == "distributed":
        fragment = fragment.replace("DISTRIBUTED_FAST_FAULT=$distributed ", "")
    elif mutation == "scratch":
        fragment = fragment.replace("PRIVATE_NEXT_START_SCRATCH=$scratch", "")
    elif mutation == "registered":
        fragment = fragment.replace(
            "REGISTERED_SCHEDULING=$registered", "REGISTERED_SCHEDULING=0"
        )
    mock = """
set registered 1; set distributed 1; set scratch 1; set source_dir /offline
proc get_filesets {args} {return sources_1}
proc set_property {name value object} {
  if {$name ne "generic" || $object ne "sources_1"} {error "unexpected property"}
  set ::bound $value
}
proc get_property {name object} {
  if {$name ne "GENERIC" || $object ne "sources_1"} {error "unexpected property"}
  return $::bound
}
"""
    result = subprocess.run(
        ["tclsh"],
        input=mock
        + "\nif {[catch {\n"
        + fragment
        + '\n} reason]} {puts $reason; exit 1}\nputs "OFFLINE_BOUND=$bound"\n',
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "generic-fragment.log").write_text(log)
    if mutation:
        assert result.returncode == 1 and "OFFLINE_BOUND=" not in log
        assert (
            "missing physical parameter "
            + {
                "distributed": "DISTRIBUTED_FAST_FAULT",
                "scratch": "PRIVATE_NEXT_START_SCRATCH",
                "registered": "REGISTERED_SCHEDULING",
            }[mutation]
            in log
        )
    else:
        assert result.returncode == 0
        assert (
            "OFFLINE_BOUND=KERNEL_ROM_FILE=/offline/upper_edge_pss_kernel_q17.mem REGISTERED_SCHEDULING=1 DISTRIBUTED_FAST_FAULT=1 PRIVATE_NEXT_START_SCRATCH=1"
            in log
        )


@pytest.mark.parametrize("mode", ["trap", "wrong_inventory", "overwrite"])
def test_tcl_preflight_stops_before_any_project_or_synthesis(prepared, tmp_path, mode):
    output = tmp_path / "NEVER_A_VIVADO_PROJECT"
    if mode == "overwrite":
        output.mkdir()
        (output / "sentinel").write_text("unchanged")
    expected = (
        "0" * 64 if mode == "wrong_inventory" else PREPARE.sha(prepared / "SHA256SUMS")
    )
    program = f"""
proc version {{args}} {{return 2022.2}}
proc set_param {{args}} {{}}
proc create_project {{args}} {{error "OFFLINE_STOP_BEFORE_CREATE_PROJECT"}}
set argc 3
set argv [list {{{output}}} {{{prepared}}} {expected}]
if {{[catch {{source {{{prepared / "synthesize_exact_control_prepared.tcl"}}}}} reason]}} {{
  puts $reason; exit 1
}}
error "preflight unexpectedly escaped"
"""
    result = subprocess.run(
        ["tclsh"],
        input=program,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "preflight.log").write_text(log)
    assert result.returncode == 1
    marker = {
        "trap": "OFFLINE_STOP_BEFORE_CREATE_PROJECT",
        "wrong_inventory": "unexpected exact-control physical preparation",
        "overwrite": "refusing to overwrite synthesis evidence",
    }[mode]
    assert marker in log, log
    if mode == "trap":
        assert not (output / "project").exists()
        assert {p.name for p in (output / "frozen_sources").glob("*.v")} == set(
            PREPARE.RTL
        )
    elif mode == "wrong_inventory":
        assert not output.exists()
    else:
        assert (output / "sentinel").read_text() == "unchanged"


def test_poisoned_tcl_parent_survives_both_sanitized_python_children(
    prepared, tmp_path
):
    output = tmp_path / "NEVER_A_VIVADO_PROJECT"
    poison = {
        "PYTHONHOME": "/nonexistent/exact-control-poison-home",
        "PYTHONPATH": "/nonexistent/exact-control-poison-path",
        "LD_LIBRARY_PATH": "/nonexistent/exact-control-poison-libraries",
    }
    expected = PREPARE.sha(prepared / "SHA256SUMS")
    parent_checks = "\n".join(
        f'if {{$::env({name}) ne "{value}"}} {{error "parent environment changed: {name}"}}'
        for name, value in poison.items()
    )
    program = f"""
proc version {{args}} {{return 2022.2}}
proc set_param {{args}} {{}}
proc create_project {{args}} {{
  # Exercise the later copied-source Python child too, without making a project.
  uplevel #0 {{{PREPARE.COPY_VERIFY}}}
  {parent_checks}
  puts "OFFLINE_BOTH_CHILDREN_VERIFIED_PARENT_UNCHANGED"
  error "OFFLINE_STOP_BEFORE_CREATE_PROJECT"
}}
set argc 3
set argv [list {{{output}}} {{{prepared}}} {expected}]
if {{[catch {{source {{{prepared / "synthesize_exact_control_prepared.tcl"}}}}} reason]}} {{
  puts $reason; exit 1
}}
error "preflight unexpectedly escaped"
"""
    result = subprocess.run(
        ["tclsh"],
        input=program,
        env=os.environ | poison,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "poisoned-preflight.log").write_text(log)
    assert result.returncode == 1
    assert "OFFLINE_BOTH_CHILDREN_VERIFIED_PARENT_UNCHANGED" in log, log
    assert "OFFLINE_STOP_BEFORE_CREATE_PROJECT" in log, log
    assert log.count('"rtl_count": 7') == 2
    assert not (output / "project").exists()
    clean = f"env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH {PREPARE.PYTHON} -B"
    assert PREPARE.ADMISSION.count(clean) == 1
    assert PREPARE.COPY_VERIFY.count(clean) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "exit17",
        "exception",
        "copy_tamper",
        "exit17_tamper",
        "bad_preflight",
        "pre_tcl_zero",
        "missing_marker",
        "duplicate_marker",
        "missing_dcp",
        "empty_resource",
        "blackbox",
    ],
)
def test_external_owner_preserves_postfailure_audit_without_vivado(
    prepared, tmp_path, monkeypatch, mode
):
    run = tmp_path / "mock-owned-run"
    expected = PREPARE.sha(prepared / "SHA256SUMS")
    if mode == "bad_preflight":
        expected = "0" * 64
    poison = {
        "PYTHONHOME": "/nonexistent/owner-poison-home",
        "PYTHONPATH": "/nonexistent/owner-poison-path",
        "LD_LIBRARY_PATH": "/nonexistent/owner-poison-libraries",
    }
    for key, value in poison.items():
        monkeypatch.setenv(key, value)
    calls = []

    def fake_launch(command, owned):
        calls.append(command)
        assert owned == run
        assert all(os.environ[key] == value for key, value in poison.items())
        if mode == "exception":
            raise OSError("OFFLINE_SYNTHETIC_LAUNCH_FAILURE")
        if mode == "pre_tcl_zero":
            (run / "launch.log").write_text("OFFLINE loader exited before Tcl\n")
            return 0
        copied = run / "synthesis/frozen_sources"
        shutil.copytree(prepared / "frozen_sources", copied)
        shutil.copyfile(
            prepared / "synthesize_exact_control_prepared.tcl",
            copied / "synthesize_exact_control_prepared.tcl",
        )
        if "tamper" in mode:
            (copied / PREPARE.RTL[0]).write_text("// OFFLINE changed copy\n")
        for name in RUN.PRODUCTS:
            if mode == "missing_dcp" and name.endswith(".dcp"):
                continue
            (run / "synthesis" / name).write_text(
                "black_boxes=0\n"
                if name == "resource_receipt.txt"
                else "OFFLINE MOCK ONLY, NOT A PHYSICAL PRODUCT\n"
            )
        if mode == "empty_resource":
            (run / "synthesis/resource_receipt.txt").write_text("")
        elif mode == "blackbox":
            (run / "synthesis/resource_receipt.txt").write_text("black_boxes=1\n")
        marker_count = (
            0 if mode == "missing_marker" else 2 if mode == "duplicate_marker" else 1
        )
        (run / "launch.log").write_text((RUN.MARKER + "\n") * marker_count)
        return 17 if mode.startswith("exit17") else 0

    monkeypatch.setattr(RUN, "launch_vivado", fake_launch)
    code = RUN.execute(prepared, expected, run)
    receipt = json.loads((run / "terminal.json").read_text())
    assert (
        code
        == {
            "success": 0,
            "exit17": 17,
            "exception": 127,
            "copy_tamper": 1,
            "exit17_tamper": 17,
            "bad_preflight": 1,
            "pre_tcl_zero": 1,
            "missing_marker": 1,
            "duplicate_marker": 1,
            "missing_dcp": 1,
            "empty_resource": 1,
            "blackbox": 1,
        }[mode]
    )
    assert receipt["returncode"] == code
    assert receipt["completion"]["verified"] == (mode == "success")
    if mode in {
        "pre_tcl_zero",
        "missing_marker",
        "duplicate_marker",
        "missing_dcp",
        "empty_resource",
        "blackbox",
    }:
        assert (
            receipt["tool_returncode"] == 0
        )  # Never confuse raw exit with completion.
        error = {
            "pre_tcl_zero": "missing copied-source closure",
            "missing_marker": "requires exactly one original terminal synthesis marker",
            "duplicate_marker": "requires exactly one original terminal synthesis marker",
            "missing_dcp": "missing or empty synthesis product: fft_bank_owned_synth.dcp",
            "empty_resource": "missing or empty synthesis product: resource_receipt.txt",
            "blackbox": "requires exact zero-black-box receipt",
        }[mode]
        assert error in receipt["completion"]["errors"]
    assert receipt["before_audit"] == (1 if mode == "bad_preflight" else 0)
    assert receipt["after_audit"] == (
        1 if "tamper" in mode or mode == "bad_preflight" else 0
    )
    assert len(calls) == (0 if mode == "bad_preflight" else 1)
    for phase in ("before", "after"):
        assert (run / f"{phase}-integrity.log").is_file()
        assert (run / f"{phase}-inventory.json").is_file()
    if calls:
        command = calls[0]
        assert command[0] == RUN.VIVADO
        assert command.index("-log") < command.index("-tclargs")
        assert command.index("-journal") < command.index("-tclargs")
        assert command[-3:] == [str(run / "synthesis"), str(prepared), expected]
    if mode == "exception":
        assert "OFFLINE_SYNTHETIC_LAUNCH_FAILURE" in receipt["execution_exception"]
    if "tamper" in mode:
        assert (
            "copied synthesis source differs"
            in (run / "after-integrity.log").read_text()
        )
    assert all(os.environ[key] == value for key, value in poison.items())
    with pytest.raises(FileExistsError):
        RUN.execute(prepared, expected, run)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_rtl",
        "extra_rtl",
        "rtl_changed",
        "constraint_changed",
        "adapter_changed",
    ],
)
def test_copied_source_closure_rejects_missing_extra_and_changed_inputs(
    prepared, tmp_path, mutation
):
    copied = tmp_path / "copied"
    shutil.copytree(prepared / "frozen_sources", copied)
    shutil.copyfile(
        prepared / "synthesize_exact_control_prepared.tcl",
        copied / "synthesize_exact_control_prepared.tcl",
    )
    if mutation == "missing_rtl":
        (copied / PREPARE.RTL[0]).unlink()
    elif mutation == "extra_rtl":
        (copied / "not_authorized.v").write_text("module not_authorized; endmodule\n")
    elif mutation == "rtl_changed":
        (copied / PREPARE.RTL[0]).write_text("// changed copy only\n")
    elif mutation == "constraint_changed":
        (copied / "fft_bank_owned_resource_probe.xdc").write_text(
            "# changed copy only\n"
        )
    else:
        (copied / "synthesize_exact_control_prepared.tcl").write_text(
            "# changed copy only\n"
        )
    with pytest.raises(
        ValueError, match="closure differs|copied synthesis source differs"
    ):
        PREPARE.verify_prepared(prepared, copied)


def test_complete_copied_input_identity_receipt(prepared, tmp_path):
    copied = tmp_path / "copied"
    shutil.copytree(prepared / "frozen_sources", copied)
    shutil.copyfile(
        prepared / "synthesize_exact_control_prepared.tcl",
        copied / "synthesize_exact_control_prepared.tcl",
    )
    assert (
        PREPARE.verify_prepared(prepared, copied, PREPARE.sha(prepared / "SHA256SUMS"))[
            "rtl_count"
        ]
        == 7
    )


@pytest.mark.parametrize(
    "mutation", ["runtime", "constraint", "route", "adapter", "binding"]
)
def test_rehashed_prepared_tamper_cannot_replace_actual_or_fixed_identity(
    prepared, tmp_path, mutation
):
    changed = tmp_path / "changed"
    shutil.copytree(prepared, changed)
    metadata = json.loads((changed / "physical_preparation.json").read_text())
    if mutation in {"runtime", "constraint"}:
        name = (
            PREPARE.RTL[0]
            if mutation == "runtime"
            else "fft_bank_owned_resource_probe.xdc"
        )
        path = changed / "frozen_sources" / name
        path.write_text(path.read_text() + "\n// changed test copy\n")
        metadata["source_sha256"][name] = PREPARE.sha(path)
    elif mutation == "route":
        path = changed / "route_completed_input_fence.tcl"
        path.write_text(path.read_text() + "\n# changed test copy\n")
    elif mutation == "adapter":
        path = changed / "synthesize_exact_control_prepared.tcl"
        path.write_text(path.read_text().replace("AreaOptimized_high", "Default"))
    else:
        path = changed / "exact_physical_settings.tcl"
        path.write_text(
            path.read_text().replace("set distributed 1", "set distributed 0")
        )
    (changed / "physical_preparation.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    files = sorted(
        p for p in changed.rglob("*") if p.is_file() and p.name != "SHA256SUMS"
    )
    (changed / "SHA256SUMS").write_text(
        "".join(f"{PREPARE.sha(p)}  {p.relative_to(changed)}\n" for p in files)
    )
    with pytest.raises(ValueError, match="reviewed identity"):
        PREPARE.verify_prepared(
            changed, expected_inventory=PREPARE.sha(prepared / "SHA256SUMS")
        )
    # Even absent the caller-supplied digest, immutable actual/fixed identities
    # are independently cross-checked, not trusted from the rewritten metadata.
    with pytest.raises(
        ValueError, match="source identities|fixed physical scripts|explicit bindings"
    ):
        PREPARE.verify_prepared(changed)


@pytest.mark.parametrize(
    "mutation",
    [
        "baseline",
        "settings",
        "exit",
        "snapshot",
        "fatal",
        "terminal",
        "extra",
        "original_marker",
        "status_accounting",
        "main_csv",
        "extra_csv",
    ],
)
def test_actual_admission_rejects_wrong_failed_and_incomplete_evidence(
    tmp_path, mutation
):
    if mutation == "baseline":
        with pytest.raises(ValueError, match="exact passing combined"):
            PREPARE.prepare(
                Path("/tmp/starlink-completed-input.5EaJuD/extra-edge-prepared-v1"),
                tmp_path / "absent",
            )
        assert not (tmp_path / "absent").exists()
        return
    actual = tmp_path / "actual"
    actual.mkdir()
    # Read-only links avoid duplicating immutable source/golden data. ONLY the
    # selected mutation file is copied before writing; never write a symlink.
    relative = {
        "settings": "settings.tcl",
        "exit": "actual-time.txt",
        "snapshot": "actual-after-source-verification.log",
        "fatal": "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log",
        "terminal": "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log",
        "extra": "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log",
        "original_marker": "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log",
        "status_accounting": "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log",
        "main_csv": "project/exact_control_actual.sim/sim_1/behav/xsim/fft_bank_owned_trace.csv",
        "extra_csv": "project/exact_control_actual.sim/sim_1/behav/xsim/exact_control_extra_trace.csv",
    }[mutation]
    required = [
        "SHA256SUMS",
        "preparation.json",
        "settings.tcl",
        "frozen_sources",
        "original-SHA256SUMS",
        "strict-diagnostic-SHA256SUMS",
        "qualified-baseline-SHA256SUMS",
        "combined-origin-SHA256SUMS",
        "actual-before-source-verification.log",
        "actual-after-source-verification.log",
        "actual-time.txt",
        "actual-launch.log",
    ]
    sim = "project/exact_control_actual.sim/sim_1/behav/xsim/"
    required += [
        sim + name
        for name in (
            "simulate.log",
            "fft_bank_owned_trace.csv",
            "exact_control_reference_trace.csv",
            "exact_control_extra_trace.csv",
            "exact_control_reference_extra_trace.csv",
        )
    ]
    for name in required:
        target = actual / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == relative:
            shutil.copyfile(ACTUAL / name, target)
        else:
            target.symlink_to(
                ACTUAL / name, target_is_directory=name == "frozen_sources"
            )
    target = actual / relative
    assert not target.is_symlink()
    text = target.read_text()
    if mutation == "settings":
        text = text.replace("DISTRIBUTED_FAST_FAULT=1", "DISTRIBUTED_FAST_FAULT=0")
    elif mutation == "exit":
        text = text.replace("Exit status: 0", "Exit status: 1")
    elif mutation == "snapshot":
        text = ""
    elif mutation == "fatal":
        text += "\nFatal: retained synthetic failure witness\n"
    elif mutation == "terminal":
        text = re.sub(r"^EXACT_CONTROL_ACTUAL_PASS.*\n", "", text, flags=re.MULTILINE)
    elif mutation == "extra":
        text = text.replace(
            "EXACT_CONTROL_EXTRA_EPOCHS_PASS final_faults=2",
            "EXACT_CONTROL_EXTRA_EPOCHS_PASS final_faults=1",
        )
    elif mutation == "original_marker":
        text = text.replace("REGISTERED_SCHEDULING_PASS", "REMOVED_REGISTERED_MARKER")
    elif mutation == "status_accounting":
        text = text.replace(
            "raw_equal=953795 invalid_only=292463",
            "raw_equal=953794 invalid_only=292463",
        )
    else:
        text += "corrupt test-copy CSV\n"
    target.write_text(text)
    marker = {
        "settings": None,
        "exit": "original process did not exit zero",
        "snapshot": "incomplete actual before/after",
        "fatal": "failed or incomplete actual",
        "terminal": "missing original actual marker",
        "extra": "literal frozen actual receipt rejected",
        "original_marker": "missing original actual marker",
        "status_accounting": "qualified observation accounting differs",
        "main_csv": "historical R1 full CSV differs",
        "extra_csv": "independent extra CSVs differ",
    }[mutation]
    with pytest.raises(
        subprocess.CalledProcessError if mutation == "settings" else ValueError,
        match=marker,
    ):
        PREPARE.prepare(actual, tmp_path / "must_remain_absent")
    assert not (tmp_path / "must_remain_absent").exists()
    # Current source file remains the exact passing actual artifact.
    assert PREPARE.sha(ACTUAL / "SHA256SUMS") == PREPARE.ACTUAL_INVENTORY
