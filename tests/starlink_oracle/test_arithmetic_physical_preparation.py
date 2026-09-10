"""Offline admission/source/parameter proof; Tcl mocks NEVER invoke Vivado."""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = ACQ / "build/bank-arithmetic-actual-candidate175-monitor-prepared-v3"
SPEC = importlib.util.spec_from_file_location(
    "physical_prepare", ACQ / "prepare_arithmetic_physical.py"
)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
RUN_SPEC = importlib.util.spec_from_file_location(
    "physical_run", ACQ / "run_arithmetic_synthesis.py"
)
RUN = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(RUN)
ADMIT_SPEC = importlib.util.spec_from_file_location(
    "actual_admission", ACQ / "verify_arithmetic_ooc_actual.py"
)
ADMIT = importlib.util.module_from_spec(ADMIT_SPEC)
ADMIT_SPEC.loader.exec_module(ADMIT)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("physical-fixture") / "prepared"
    receipt = PREPARE.prepare(ACTUAL, output)
    assert receipt["rtl_count"] == 8
    assert receipt["original_automation_status"] == "FAIL"
    assert receipt["functional_terminals"] == 11
    assert receipt["histories"] == {
        "recorded_paths": 115,
        "recorded_values": 345,
        "qualified_119bit_comparisons": 6,
    }
    return output


def test_minimal_physical_adapter_whole_inverse_and_fixed_directives(prepared):
    original = (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    assert (
        PREPARE.sha(ACQ / "synthesize_fft_bank_owned_slice.tcl")
        == PREPARE.FIXED["synthesize_fft_bank_owned_slice.tcl"]
    )
    text = (prepared / "synthesize_arithmetic_prepared.tcl").read_text()
    for old, new in reversed(PREPARE.synthesis_edits()):
        text = PREPARE.once(text, new, old)
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


@pytest.mark.parametrize("mutation", [None, "round", "operands", "registered"])
def test_tcl_exact_generic_binding_and_omission_witnesses(prepared, tmp_path, mutation):
    text = (prepared / "synthesize_arithmetic_prepared.tcl").read_text()
    fragment = text[
        text.index("set_property generic ") : text.index(
            "set_property STEPS.SYNTH_DESIGN"
        )
    ]
    if mutation == "round":
        fragment = fragment.replace("BOUNDARY_ROUND_SAT=$round ", "")
    elif mutation == "operands":
        fragment = fragment.replace("REGISTER_OPERANDS=$operands", "")
    elif mutation == "registered":
        fragment = fragment.replace(
            "REGISTERED_SCHEDULING=$registered", "REGISTERED_SCHEDULING=0"
        )
    mock = """
set registered 1; set round 1; set operands 1; set source_dir /offline
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
                "round": "BOUNDARY_ROUND_SAT",
                "operands": "REGISTER_OPERANDS",
                "registered": "REGISTERED_SCHEDULING",
            }[mutation]
            in log
        )
    else:
        assert result.returncode == 0
        assert (
            "OFFLINE_BOUND=KERNEL_ROM_FILE=/offline/upper_edge_pss_kernel_q17.mem REGISTERED_SCHEDULING=1 BOUNDARY_ROUND_SAT=1 REGISTER_OPERANDS=1"
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
if {{[catch {{source {{{prepared / "synthesize_arithmetic_prepared.tcl"}}}}} reason]}} {{
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
        "wrong_inventory": "unexpected arithmetic physical preparation",
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
if {{[catch {{source {{{prepared / "synthesize_arithmetic_prepared.tcl"}}}}} reason]}} {{
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
    assert log.count('"rtl_count": 8') == 2
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
            prepared / "synthesize_arithmetic_prepared.tcl",
            copied / "synthesize_arithmetic_prepared.tcl",
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
        prepared / "synthesize_arithmetic_prepared.tcl",
        copied / "synthesize_arithmetic_prepared.tcl",
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
        (copied / "synthesize_arithmetic_prepared.tcl").write_text(
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
        prepared / "synthesize_arithmetic_prepared.tcl",
        copied / "synthesize_arithmetic_prepared.tcl",
    )
    assert (
        PREPARE.verify_prepared(prepared, copied, PREPARE.sha(prepared / "SHA256SUMS"))[
            "rtl_count"
        ]
        == 8
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
        path = changed / "synthesize_arithmetic_prepared.tcl"
        path.write_text(path.read_text().replace("AreaOptimized_high", "Default"))
    else:
        path = changed / "arithmetic_physical_settings.tcl"
        path.write_text(path.read_text().replace("set round 1", "set round 0"))
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


def mirrored_actual(tmp_path):
    """Only test-copy mutations; original files are never opened for writing."""
    actual = tmp_path / "actual"
    evidence = PREPARE.admission_inputs()
    original = json.loads(evidence["originals.json"].read_text())
    for member in original["archive_file_sha256"]:
        if not member.startswith("candidate/"):
            continue
        relative = member.removeprefix("candidate/")
        if relative.startswith("outer/"):
            source = ACTUAL.parent / relative.removeprefix("outer/")
            target = tmp_path / relative.removeprefix("outer/")
        else:
            source, target = ACTUAL / relative, actual / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.startswith("frozen_sources/"):
            shutil.copyfile(source, target)  # Freeze verifier forbids symlink sources.
        else:
            target.symlink_to(source)
    return actual


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_manifest",
        "source",
        "extra_source",
        "missing_source",
        "phase",
        "failure_cause",
        "after_failure",
        "launch",
        "results",
        "fatal",
        "terminal",
        "events",
        "trace",
        "inventory",
        "wave",
        "generated_ip",
        "outer",
    ],
)
def test_source_specific_actual_admission_never_accepts_generic_failure(
    tmp_path, mutation
):
    actual = mirrored_actual(tmp_path)
    targets = {
        "wrong_manifest": "manifest.json",
        "source": "frozen_sources/" + PREPARE.RTL[0],
        "extra_source": "frozen_sources/not_authorized.v",
        "missing_source": "frozen_sources/" + PREPARE.RTL[0],
        "phase": "postflight.json",
        "failure_cause": "run_outcome.txt",
        "after_failure": "run_outcome.txt",
        "launch": "launch_started.txt",
        "results": "results.json",
        "fatal": str(ADMIT.SIM / "simulate.log"),
        "terminal": str(ADMIT.SIM / "simulate.log"),
        "events": str(ADMIT.SIM / "bank_arithmetic_events.csv"),
        "trace": str(ADMIT.SIM / "fft_bank_owned_trace.csv"),
        "inventory": str(ADMIT.SIM / "arithmetic_diagnostic_signals.txt"),
        "wave": str(ADMIT.SIM / "tb_starlink_pss_bank_arithmetic_actual_behav.wdb"),
        "generated_ip": "generated_ip_after.txt",
    }
    target = (
        actual.parent / ADMIT.OUTER
        if mutation == "outer"
        else actual / targets[mutation]
    )
    if mutation in ("results", "extra_source"):
        data = b"not authorized\n"
    elif mutation == "wave":
        data = b"changed WDB copy\n"
    else:
        data = target.read_bytes()
        if mutation == "failure_cause":
            data = data.replace(
                b"missing/duplicate/malformed diagnostic waveform inventory",
                b"different unreviewed failure",
            )
        elif mutation == "after_failure":
            data = data.replace(b"after_status=0", b"after_status=1")
        elif mutation == "fatal":
            data += b"Fatal: after all functional PASS markers\n"
        elif mutation == "terminal":
            data = data.replace(b"BANK_ARITHMETIC_ACTUAL_PASS", b"REMOVED_TERMINAL")
        else:
            data += b" changed test copy\n"
    if target.exists():
        target.unlink()  # Unlink only our test-copy/symlink, never its source.
    if mutation != "missing_source":
        target.write_bytes(data)
    with pytest.raises((ValueError, FileNotFoundError)):
        PREPARE.verify_actual(actual)
    assert not (ACTUAL / "results.json").exists()
    assert PREPARE.sha(ACTUAL / "manifest.json") == ADMIT.MANIFEST


@pytest.mark.parametrize("name", ADMIT.EVIDENCE_NAMES)
def test_posthoc_assessment_query_and_original_receipt_are_pinned(tmp_path, name):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for key, path in PREPARE.admission_inputs().items():
        shutil.copyfile(path, evidence / key)
    (evidence / name).write_bytes((evidence / name).read_bytes() + b"changed\n")
    with pytest.raises(ValueError, match="reviewed post-hoc evidence identity"):
        ADMIT.verify(ACTUAL, evidence)


@pytest.mark.parametrize(
    "mutation", ["value", "missing", "duplicate", "time", "qualifier", "transport"]
)
def test_recorded_histories_are_checked_not_just_path_marker(mutation):
    evidence = PREPARE.admission_inputs()
    full = json.loads(evidence["posthoc_assessment.json"].read_text())
    assessed = next(row for row in full["runs"] if row["arm"] == "candidate")
    text = evidence[ADMIT.EVIDENCE_NAMES[2]].read_text()
    paths = (
        (ACTUAL / ADMIT.SIM / "arithmetic_diagnostic_signals.txt")
        .read_text()
        .splitlines()
    )
    diagnostics = {"recorded_internal_signals": paths}
    if mutation == "time":
        text = text.replace("100000000000fs", "100000000001fs")
    else:
        suffix = {
            "qualifier": "/resetn",
            "transport": "/dut/product_commit_authorized",
        }.get(mutation, "/product_outputs")
        line = next(
            row
            for row in text.splitlines()
            if row.startswith("ACTUAL_WDB_VALUE\t")
            and row.split("\t")[3].endswith(suffix)
            and (mutation != "qualifier" or "reference " in row)
            and (mutation != "transport" or "1261765777375fs" in row)
        )
        if mutation == "missing":
            text = text.replace(line + "\n", "", 1)
        elif mutation == "duplicate":
            text += line + "\n"
        else:
            value = "0" if mutation == "qualifier" else "1"
            # Choose a reference vector to exercise actual 119-bit comparison.
            if mutation == "value":
                line = next(
                    row
                    for row in text.splitlines()
                    if row.startswith("ACTUAL_WDB_VALUE\t")
                    and "reference /product_outputs\t" in row
                )
            text = text.replace(line, line.rsplit("\t", 1)[0] + "\t" + value, 1)
    with pytest.raises(ValueError):
        ADMIT.verify_histories(text, diagnostics, assessed)


@pytest.mark.parametrize("index", range(11))
def test_every_adapter_anchor_is_unique(index):
    original = (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    old, _ = PREPARE.synthesis_edits()[index]
    for changed in (original.replace(old, "", 1), original + "\n" + old):
        with pytest.raises(ValueError, match="nonunique"):
            PREPARE.adapt_synthesis(changed)


def test_no_runtime_edits_no_future_receipt_substitution_and_dependency_closure(
    prepared,
):
    assert len(PREPARE.SOURCE_NAMES) == 12
    assert (prepared / "verify_arithmetic_ooc_actual.py").read_bytes() == (
        ACQ / "verify_arithmetic_ooc_actual.py"
    ).read_bytes()
    assert not (ACTUAL / ADMIT.SIM / "arithmetic_diagnostic_receipt.txt").exists()
    assert not (ACTUAL / "results.json").exists()
    assert (
        "set false_path"
        not in (prepared / "synthesize_arithmetic_prepared.tcl").read_text()
    )
    for name in PREPARE.RTL:
        assert (ACQ / name).read_bytes() == (
            ACTUAL / "frozen_sources" / name
        ).read_bytes()
    for name, path in PREPARE.admission_inputs().items():
        assert (
            prepared / "admission_evidence" / name
        ).read_bytes() == path.read_bytes()
