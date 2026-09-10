"""C1 physical admission only; all vendor entry points are offline traps."""

import importlib.util
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = Path("/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1")
SPEC = importlib.util.spec_from_file_location(
    "cdc_physical", ACQ / "prepare_fault_cdc_physical.py"
)
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)
OLD = runpy.run_path(str(ACQ / "prepare_exact_control_physical.py"))


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("cdc-physical") / "prepared"
    result = GEN.prepare(ACTUAL, output)
    assert result["per_cause"] == 1 and result["rtl_count"] == 7
    assert result["qualified_observer"] == {
        "samples": 1246258,
        "raw_equal": 953795,
        "invalid_only": 292463,
    }
    return output


def test_entire_helper_owner_and_adapter_inverse_to_frozen111(prepared):
    actual = (prepared / "prepare_exact_control_physical.py").read_text()
    original = (ACQ / "prepare_exact_control_physical.py").read_text()
    assert GEN.restore(actual) == original
    assert GEN.identity(ACQ / "prepare_exact_control_physical.py") == GEN.BASE_SHA
    assert GEN.identity(prepared / "run_exact_control_synthesis.py") == GEN.OWNER_SHA
    assert (prepared / "run_exact_control_synthesis.py").read_bytes() == (
        ACQ / "run_exact_control_synthesis.py"
    ).read_bytes()
    helper = runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    for old, new in (
        (" || $per_cause != 1", ""),
        (" PER_CAUSE_FAULT_CDC $per_cause", ""),
        (" PER_CAUSE_FAULT_CDC=$per_cause", ""),
        ("; per_cause_fault_cdc=$per_cause", ""),
        (GEN.CDC_GENERIC_UNIQUE, ""),
    ):
        assert text.count(old) == 1
        text = text.replace(old, new, 1)
    assert text == OLD["adapt_synthesis"](
        (ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text()
    )
    source = prepared / "frozen_sources"
    assert {p.name for p in source.iterdir()} == set(OLD["SOURCE_NAMES"])
    for name in OLD["RTL"] + (
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
        assert GEN.identity(source / name) == OLD["FIXED"][name]
    assert (
        GEN.identity(prepared / "route_completed_input_fence.tcl")
        == OLD["FIXED"]["route_completed_input_fence.tcl"]
    )
    assert (
        GEN.identity(prepared / "synthesize_fft_bank_owned_slice.original.tcl")
        == OLD["FIXED"]["synthesize_fft_bank_owned_slice.tcl"]
    )
    metadata = json.loads((prepared / "physical_preparation.json").read_text())
    assert metadata["actual"]["inventory_sha256"] == GEN.ACTUAL_SHA
    assert metadata["actual"]["settings"] == helper["SETTINGS"]
    assert helper["SETTINGS"]["PER_CAUSE_FAULT_CDC"] == 1
    assert (
        metadata["actual"]["source_sha256"]["starlink_pss_fft_bank_owned_slice.v"]
        == GEN.WRAPPER_SHA
    )
    assert metadata["actual"]["cdc_terminal"].startswith(
        "FAULT_CDC_ACTUAL_PASS enabled=1 checks=712146 "
    )
    assert "set per_cause 1\n" in (prepared / "exact_physical_settings.tcl").read_text()
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=prepared, check=True
    )
    with pytest.raises(FileExistsError):
        GEN.prepare(ACTUAL, prepared)


@pytest.mark.parametrize(
    "old,new",
    [
        ('"PER_CAUSE_FAULT_CDC": 1', '"PER_CAUSE_FAULT_CDC": 0'),
        (
            'cdc["verify_result"](logfile, 1, frozen)',
            'cdc["verify_result"](logfile, 0, frozen)',
        ),
        ("PER_CAUSE_FAULT_CDC=$per_cause", "PER_CAUSE_FAULT_CDC=0"),
        ("|| $per_cause != 1", "|| $per_cause != 0"),
        ("PER_CAUSE_FAULT_CDC $per_cause", "PER_CAUSE_FAULT_CDC 0"),
        ('return "', 'return "CORRUPTED'),
    ],
)
def test_whole_inverse_rejects_malformed_cdc_additions_and_unrelated_changes(old, new):
    text = GEN.adapt((ACQ / "prepare_exact_control_physical.py").read_text())
    if old == 'return "':
        old, new = '"rtl_count": 7', '"rtl_count": 6'
    assert old in text
    with pytest.raises(ValueError):
        GEN.restore(text.replace(old, new, 1))


@pytest.mark.parametrize(
    "mode",
    [
        "good",
        "omit",
        "zero",
        "duplicate",
        "conflicting",
        "lowercase",
        "dropped_readback",
    ],
)
def test_actual_generic_fragment_exact_c1_and_bad_binding_witnesses(
    prepared, tmp_path, mode
):
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    fragment = text[
        text.index("set_property generic ") : text.index(
            "set_property STEPS.SYNTH_DESIGN"
        )
    ]
    replacement = {
        "omit": "",
        "zero": "PER_CAUSE_FAULT_CDC=0",
        "duplicate": "PER_CAUSE_FAULT_CDC=$per_cause PER_CAUSE_FAULT_CDC=1",
        "conflicting": "PER_CAUSE_FAULT_CDC=$per_cause PER_CAUSE_FAULT_CDC=0",
        "lowercase": "per_cause_fault_cdc=$per_cause",
    }
    if mode in replacement:
        fragment = fragment.replace(
            "PER_CAUSE_FAULT_CDC=$per_cause", replacement[mode], 1
        )
    readback = (
        "$::bound" if mode != "dropped_readback" else "[lreplace $::bound end end]"
    )
    mock = f"""set registered 1; set distributed 1; set scratch 1; set per_cause 1; set source_dir /offline
proc get_filesets {{args}} {{return sources_1}}
proc set_property {{name value object}} {{set ::bound $value}}
proc get_property {{name object}} {{return {readback}}}
"""
    script = tmp_path / "generic.tcl"
    script.write_text(mock + fragment + 'puts "EXACT_C1_BOUND=$bound"\n')
    result = subprocess.run(
        ["tclsh", str(script)], capture_output=True, text=True, check=False, timeout=5
    )
    (tmp_path / "generic.log").write_text(result.stdout + result.stderr)
    assert (result.returncode == 0) == (mode == "good"), result.stdout + result.stderr
    if mode == "good":
        assert result.stdout.strip().endswith("PER_CAUSE_FAULT_CDC=1")
    else:
        assert "EXACT_C1_BOUND=" not in result.stdout


@pytest.mark.parametrize(
    "mode", ["trap", "wrong_inventory", "existing_output", "poisoned_python"]
)
def test_preflight_never_enters_vendor_project_and_sanitizes_python(
    prepared, tmp_path, mode, monkeypatch
):
    output = tmp_path / "NO_VENDOR_PROJECT"
    if mode == "existing_output":
        output.mkdir()
    expected = GEN.identity(prepared / "SHA256SUMS")
    if mode == "wrong_inventory":
        expected = "0" * 64
    script = tmp_path / "trap.tcl"
    script.write_text("""proc version {args} {return "2022.2"}
proc set_param {args} {}
proc create_project {args} {puts "OFFLINE_CREATE_PROJECT_TRAP"; exit 0}
set script [lindex $argv 0]
set argv [lrange $argv 1 end]; set argc [llength $argv]
source $script
error "unexpected fallthrough"
""")
    if mode == "poisoned_python":
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
            monkeypatch.setenv(key, "/deliberately-invalid-python-environment")
    before = {
        key: os.environ.get(key)
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH")
    }
    result = subprocess.run(
        [
            "tclsh",
            str(script),
            str(prepared / "synthesize_exact_control_prepared.tcl"),
            str(output),
            str(prepared),
            expected,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    (tmp_path / "preflight.log").write_text(result.stdout + result.stderr)
    assert {key: os.environ.get(key) for key in before} == before
    if mode in ("trap", "poisoned_python"):
        assert (
            result.returncode == 0 and "OFFLINE_CREATE_PROJECT_TRAP" in result.stdout
        ), result.stdout + result.stderr
    else:
        assert (
            result.returncode != 0
            and "OFFLINE_CREATE_PROJECT_TRAP" not in result.stdout
        )
    assert not (output / "project").exists()


@pytest.mark.parametrize("kind", ["output", "dangling", "parent", "source"])
def test_preparer_no_overwrite_and_symlink_aliases_fail_closed(tmp_path, kind):
    output = tmp_path / "output"
    actual = ACTUAL
    target = tmp_path / "target"
    target.mkdir()
    if kind == "output":
        output.symlink_to(target, target_is_directory=True)
    elif kind == "dangling":
        output.symlink_to(tmp_path / "absent", target_is_directory=True)
    elif kind == "parent":
        link = tmp_path / "alias"
        link.symlink_to(target, target_is_directory=True)
        output = link / "output"
    else:
        actual = tmp_path / "source_alias"
        actual.symlink_to(ACTUAL, target_is_directory=True)
    with pytest.raises((ValueError, FileExistsError)):
        GEN.prepare(actual, output)
    assert not list(target.iterdir())


def test_old111_run_is_not_admitted(prepared):
    helper = runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))
    with pytest.raises(ValueError, match="exact passing combined actual inventory"):
        helper["verify_actual"](ACTUAL.with_name("extra-edge-combined-prepared-v1"))


@pytest.mark.parametrize(
    "mode",
    ["original_exit", "missing_cdc", "wrong_cdc", "incomplete_source", "failed_time"],
)
def test_c1_actual_admission_rejects_failed_incomplete_or_wrong_receipts(
    prepared, tmp_path, mode
):
    # A copied observation fixture, not a new simulation. Only source members
    # and files read by admission are copied; no vendor project is run.
    copied = tmp_path / "copied_actual"
    copied.mkdir()
    for name in (
        "SHA256SUMS",
        "preparation.json",
        "settings.tcl",
        "original-SHA256SUMS",
        "strict-diagnostic-SHA256SUMS",
        "qualified-baseline-SHA256SUMS",
        "combined-origin-SHA256SUMS",
        "cdc-passing111-SHA256SUMS",
        "actual-before-source-verification.log",
        "actual-after-source-verification.log",
        "actual-time.txt",
        "actual-launch.log",
        "actual-process-exit.txt",
    ):
        shutil.copyfile(ACTUAL / name, copied / name)
    shutil.copytree(ACTUAL / "frozen_sources", copied / "frozen_sources")
    if mode == "original_exit":
        (copied / "actual-process-exit.txt").write_text("1\n")
    if mode == "failed_time":
        (copied / "actual-time.txt").write_text("Exit status: 1\n")
    if mode == "incomplete_source":
        (copied / "actual-after-source-verification.log").write_text("incomplete\n")
    source_sim = ACTUAL / "project/exact_control_actual.sim/sim_1/behav/xsim"
    dest_sim = copied / "project/exact_control_actual.sim/sim_1/behav/xsim"
    dest_sim.mkdir(parents=True)
    log = (source_sim / "simulate.log").read_text()
    if mode == "missing_cdc":
        log = (
            "\n".join(
                line
                for line in log.splitlines()
                if not line.startswith("FAULT_CDC_ACTUAL_PASS")
            )
            + "\n"
        )
    if mode == "wrong_cdc":
        log = log.replace(
            "FAULT_CDC_ACTUAL_PASS enabled=1", "FAULT_CDC_ACTUAL_PASS enabled=0"
        )
    (dest_sim / "simulate.log").write_text(log)
    helper = runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))
    with pytest.raises(
        ValueError,
        match="original C1 process|CDC receipt|original or CDC receipt|incomplete actual|original process",
    ):
        helper["verify_actual"](copied)


def test_copied_seven_source_closure_and_owner_remain_frozen(prepared, tmp_path):
    source = tmp_path / "copied"
    shutil.copytree(prepared / "frozen_sources", source)
    shutil.copyfile(
        prepared / "synthesize_exact_control_prepared.tcl",
        source / "synthesize_exact_control_prepared.tcl",
    )
    helper = runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))
    assert (
        helper["verify_prepared"](
            prepared, source, GEN.identity(prepared / "SHA256SUMS")
        )["per_cause"]
        == 1
    )
    (source / "starlink_pss_fft_bank_owned_slice.v").write_text("wrong CDC candidate\n")
    with pytest.raises(ValueError, match="copied synthesis source differs"):
        helper["verify_prepared"](
            prepared, source, GEN.identity(prepared / "SHA256SUMS")
        )
