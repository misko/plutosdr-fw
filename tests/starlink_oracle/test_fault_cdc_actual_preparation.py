"""Offline admission/observer checks only: no vendor FFT is executed here."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.fault_cdc_contract import restore_fault_cdc
from tests.starlink_oracle.test_exact_control import STUB
from tests.starlink_oracle.test_exact_control_combined_preparation import compiled_scope
from tests.starlink_oracle.test_fault_cdc import run as run_cdc

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ORIGINAL = Path("/tmp/starlink-completed-input.5EaJuD/extra-edge-combined-prepared-v1")
SPEC = importlib.util.spec_from_file_location(
    "cdc_actual", ACQ / "prepare_fault_cdc_actual.py"
)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
TOP = "tb_starlink_pss_fft_bank_owned_slice"
SETTINGS = {
    "REGISTERED_SCHEDULING": 1,
    "DISTRIBUTED_FAST_FAULT": 1,
    "PRIVATE_NEXT_START_SCRATCH": 1,
    "EXACT_EXTRA_EPOCHS": 1,
    "FAST_MHZ": 175,
    "QUICK_MUTATION": 0,
    "PER_CAUSE_FAULT_CDC": 1,
}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("cdc-actual") / "prepared"
    assert PREPARE.prepare(ORIGINAL, output) == SETTINGS
    return output


def test_entire_source_closure_inverse_and_unchanged_independent_reference(prepared):
    old = ORIGINAL / "frozen_sources"
    new = prepared / "frozen_sources"
    old_metadata = json.loads((ORIGINAL / "preparation.json").read_text())
    metadata = json.loads((prepared / "preparation.json").read_text())
    changed = {PREPARE.TOP, PREPARE.RUNNER, "starlink_pss_fft_bank_owned_slice.v"}
    added = {
        PREPARE.OBSERVER,
        "prepare_fault_cdc_actual.py",
        "prepare_exact_control_physical.py",
        "fault_cdc_contract.py",
    }
    assert set(metadata["source_sha256"]) == set(old_metadata["source_sha256"]) | added
    assert {p.name for p in new.iterdir()} == set(metadata["source_sha256"])
    for name in old_metadata["source_sha256"]:
        if name not in changed:
            assert (new / name).read_bytes() == (old / name).read_bytes(), name
    assert (
        restore_fault_cdc((new / "starlink_pss_fft_bank_owned_slice.v").read_text())
        == (old / "starlink_pss_fft_bank_owned_slice.v").read_text()
    )
    bench = (new / PREPARE.TOP).read_text()
    for addition in (
        "  parameter integer PER_CAUSE_FAULT_CDC = 0;\n",
        "    .PER_CAUSE_FAULT_CDC(PER_CAUSE_FAULT_CDC),\n",
        '  `include "starlink_pss_fault_cdc_actual_observer.svh"\n',
        "    fault_cdc_verify_terminal();\n",
    ):
        assert bench.count(addition) == 1
        bench = bench.replace(addition, "", 1)
    assert bench == (old / PREPARE.TOP).read_text()
    runner = (new / PREPARE.RUNNER).read_text()
    for addition in (
        PREPARE.TCL_RECEIPTS,
        PREPARE.TCL_BINDING,
        PREPARE.TCL_READBACK,
        PREPARE.EXTRA_GATE,
        "puts [fault_cdc_verify_receipt $log $per_cause]\n",
    ):
        assert runner.count(addition) == 1
        runner = runner.replace(addition, "", 1)
    runner = runner.replace(
        "[llength $exact_generics] != 7", "[llength $exact_generics] != 6", 1
    )
    runner = runner.replace(
        "PRIVATE_NEXT_START_SCRATCH EXACT_EXTRA_EPOCHS PER_CAUSE_FAULT_CDC}",
        "PRIVATE_NEXT_START_SCRATCH EXACT_EXTRA_EPOCHS}",
        1,
    )
    assert runner == (old / PREPARE.RUNNER).read_text()
    assert metadata["settings"] == SETTINGS
    assert metadata["cdc_origin_actual"]["settings"] == {
        k: v for k, v in SETTINGS.items() if k != "PER_CAUSE_FAULT_CDC"
    }
    assert "qualified_status_NOT_raw217" in metadata["scope"]
    restored_metadata = dict(metadata)
    for key in ("cdc_origin_actual", "cdc_tested_runtime_pin"):
        del restored_metadata[key]
    for key in ("settings", "scope", "source_sha256"):
        restored_metadata[key] = old_metadata[key]
    assert restored_metadata == old_metadata
    assert (prepared / "cdc-passing111-SHA256SUMS").read_bytes() == (
        ORIGINAL / "SHA256SUMS"
    ).read_bytes()
    for name, digest in metadata["source_sha256"].items():
        assert PREPARE.sha(new / name) == digest
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=prepared, check=True
    )
    assert not (prepared / "project").exists()
    with pytest.raises(FileExistsError):
        PREPARE.prepare(ORIGINAL, prepared)


@pytest.mark.parametrize("enabled", [0, 1])
def test_actual_hierarchy_compile_only_explicit_candidate_and_dec20_reference(
    prepared, tmp_path, enabled
):
    source = prepared / "frozen_sources"
    stub = tmp_path / "compile_only_stub.v"
    stub.write_text(STUB)
    executable = tmp_path / "NEVER_EXECUTE_vendor_stub.vvp"
    settings = dict(SETTINGS, PER_CAUSE_FAULT_CDC=enabled)
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            TOP,
            *[f"-P{TOP}.{k}={v}" for k, v in settings.items()],
            "-o",
            str(executable),
            *map(str, sorted(source.glob("*.v"))),
            *map(str, sorted(source.glob("*.sv"))),
            str(stub),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    text = executable.read_text()
    top_id, top = compiled_scope(text, TOP, TOP)
    candidate_id, candidate = compiled_scope(
        text, "dut", "starlink_pss_fft_bank_owned_slice", top_id
    )
    ref_id, ref_bench = compiled_scope(
        text, "exact_reference", "tb_starlink_pss_exact_control_reference", top_id
    )
    _, reference = compiled_scope(
        text, "dut", "starlink_pss_fft_bank_owned_slice_dec20d63_golden", ref_id
    )
    assert {k: top[k] for k in settings} == settings
    for key in (
        "REGISTERED_SCHEDULING",
        "DISTRIBUTED_FAST_FAULT",
        "PRIVATE_NEXT_START_SCRATCH",
        "PER_CAUSE_FAULT_CDC",
    ):
        assert candidate[key] == settings[key]
    assert reference["REGISTERED_SCHEDULING"] == 1
    assert ref_bench["REGISTERED_SCHEDULING"] == ref_bench["EXACT_EXTRA_EPOCHS"] == 1
    assert ref_bench["FAST_MHZ"] == 175 and ref_bench["QUICK_MUTATION"] == 0
    assert (
        not {
            "PER_CAUSE_FAULT_CDC",
            "DISTRIBUTED_FAST_FAULT",
            "PRIVATE_NEXT_START_SCRATCH",
        }
        & reference.keys()
    )
    join_id, join = compiled_scope(
        text, "joiner", "starlink_pss_forward_kernel_join", candidate_id
    )
    _, rom = compiled_scope(text, "kernel_rom", "starlink_pss_kernel_rom", join_id)
    assert join["PRIVATE_NEXT_START_SCRATCH"] == rom["PRIVATE_NEXT_START_SCRATCH"] == 1
    (tmp_path / "compiled-bindings.json").write_text(
        json.dumps(
            {
                "scope": "offline_elaboration_NOT_vendor_execution",
                "top": top,
                "candidate": candidate,
                "reference": reference,
                "reference_bench": ref_bench,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("option", [-1, 2, "x", "z"])
def test_prepare_invalid_option_and_unknown_origin_are_rejected(tmp_path, option):
    with pytest.raises(ValueError, match="explicit CDC option"):
        PREPARE.prepare(ORIGINAL, tmp_path / "absent", option)
    assert not (tmp_path / "absent").exists()


def test_unknown_origin_rejected_without_output(tmp_path):
    origin = tmp_path / "wrong"
    origin.mkdir()
    (origin / "SHA256SUMS").write_text("not the passing111 freeze\n")
    with pytest.raises(ValueError, match="exact passing combined actual inventory"):
        PREPARE.prepare(origin, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def tcl_receipt(tmp_path, text, enabled=1):
    log = tmp_path / "receipt.txt"
    log.write_text(text)
    result = subprocess.run(
        ["tclsh", "/dev/stdin", str(log)],
        input=PREPARE.TCL_RECEIPTS
        + f"\nset f [open [lindex $argv 0] r]; set log [read $f]; close $f\nputs [fault_cdc_verify_receipt $log {enabled}]\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    (tmp_path / "receipt-check.log").write_text(result.stdout + result.stderr)
    return result


RECEIPT = "FAULT_CDC_ACTUAL_PASS enabled=1 checks=120 stage0_high=10 stage1_high=9 reset_samples=4 current_fault_edges=3 final_fault_edges=2 private_core_reset_samples=0 scalar_source=actual_fast_fault reference_reset=slow_running\n"


def test_receipt_accepts_recorded_zero_private_reset_but_requires_other_witnesses(
    tmp_path,
):
    result = tcl_receipt(tmp_path, RECEIPT)
    assert result.returncode == 0 and result.stdout == "FAULT_CDC_RECEIPT_VERIFIED\n"


@pytest.mark.parametrize(
    "old,new",
    [
        ("enabled=1", "enabled=0"),
        ("checks=120", "checks=0"),
        ("stage0_high=10", "stage0_high=0"),
        ("stage1_high=9", "stage1_high=0"),
        ("reset_samples=4", "reset_samples=0"),
        ("current_fault_edges=3", "current_fault_edges=0"),
        ("final_fault_edges=2", "final_fault_edges=1"),
        ("private_core_reset_samples=0", "private_core_reset_samples=x"),
        ("scalar_source=actual_fast_fault", "scalar_source=expected_causes"),
        ("reference_reset=slow_running", "reference_reset=core_aresetn"),
        (RECEIPT, RECEIPT + RECEIPT),
        (RECEIPT, ""),
    ],
)
def test_receipt_rejects_wrong_scope_counts_missing_or_duplicate(tmp_path, old, new):
    assert tcl_receipt(tmp_path, RECEIPT.replace(old, new)).returncode != 0


def observer_bench():
    # Reuse actual runtime + frozen old runtime under the existing quiescent
    # recurrence fixture, NEVER the actual FFT stimulus. Additional forced
    # index/event snapshots exercise the observer, not FFT lifecycle coverage.
    text = (
        (ACQ / "tb/tb_starlink_pss_fault_cdc.sv")
        .read_text()
        .replace("candidate", "dut")
    )
    text = text.replace(
        "  reg clk=0,",
        '  parameter integer PER_CAUSE_FAULT_CDC=ENABLED;\n  `include "starlink_pss_fault_cdc_actual_observer.svh"\n  reg clk=0,',
        1,
    )
    text = text.replace(
        ".DISTRIBUTED_FAST_FAULT(1), .PER_CAUSE_FAULT_CDC(ENABLED)",
        ".DISTRIBUTED_FAST_FAULT(1), .PRIVATE_NEXT_START_SCRATCH(1), .PER_CAUSE_FAULT_CDC(ENABLED)",
        1,
    )
    text = text.replace(
        ".DISTRIBUTED_FAST_FAULT(1)) golden",
        ".DISTRIBUTED_FAST_FAULT(1), .PRIVATE_NEXT_START_SCRATCH(1)) golden",
        1,
    )
    text = text.replace(
        '    $display("FAULT_CDC_PASS',
        """    drive(12'h001);
    force dut.event_last_missing=1; force golden.event_last_missing=1;
    force dut.joiner.kernel_rom.expected_bin_index=511;
    repeat(4) @(negedge fft_clk);
    fault_cdc_verify_terminal();
    $display("FAULT_CDC_PASS""",
        1,
    )
    return text


@pytest.mark.parametrize("phase", [0, 713, 2857])
@pytest.mark.parametrize("enabled", [0, 1])
def test_observer_on_actual_runtime_quiescent_cdc_fixture(tmp_path, phase, enabled):
    shutil.copyfile(ACQ / "tb" / PREPARE.OBSERVER, tmp_path / PREPARE.OBSERVER)
    code, log = run_cdc(
        tmp_path,
        parameters=(f"ENABLED={enabled}", f"SLOW_PHASE_PS={phase}"),
        bench=observer_bench(),
    )
    assert code == 0, log
    assert "quiescent_stub_not_fft=1" in log
    assert tcl_receipt(tmp_path, log, enabled).returncode == 0


@pytest.mark.parametrize(
    "old,new,marker",
    [
        (
            "{fault_cdc_scalar[0], dut.fast_fault}",
            "{dut.fast_fault, dut.fast_fault}",
            "FAULT_CDC_ACTUAL_STAGE_MISMATCH",
        ),
        (
            "if (!dut.slow_running)",
            "if (!dut.core_aresetn)",
            "FAULT_CDC_ACTUAL_STAGE_MISMATCH",
        ),
        ("dut.fast_fault};", "1'b0};", "FAULT_CDC_ACTUAL_STAGE_MISMATCH"),
        (
            "fault_cdc_current_edges=fault_cdc_current_edges+1;",
            "fault_cdc_current_edges=0;",
            "FAULT_CDC_ACTUAL_COVERAGE_INCOMPLETE",
        ),
        (
            "fault_cdc_final_edges=fault_cdc_final_edges+1;",
            "fault_cdc_final_edges=0;",
            "FAULT_CDC_ACTUAL_COVERAGE_INCOMPLETE",
        ),
        (
            "fault_cdc_reset_samples=fault_cdc_reset_samples+1;",
            "fault_cdc_reset_samples=0;",
            "FAULT_CDC_ACTUAL_COVERAGE_INCOMPLETE",
        ),
    ],
)
def test_actual_observer_rejects_stage_source_reset_and_missing_witness_mutants(
    tmp_path, old, new, marker
):
    observer = (ACQ / "tb" / PREPARE.OBSERVER).read_text()
    assert observer.count(old) == 1
    (tmp_path / PREPARE.OBSERVER).write_text(observer.replace(old, new, 1))
    code, log = run_cdc(tmp_path, bench=observer_bench())
    assert code != 0 and marker in log, log


def test_omitted_top_binding_is_rejected_by_literal_runtime_readback(tmp_path):
    shutil.copyfile(ACQ / "tb" / PREPARE.OBSERVER, tmp_path / PREPARE.OBSERVER)
    bench = observer_bench().replace(", .PER_CAUSE_FAULT_CDC(ENABLED)", "", 1)
    code, log = run_cdc(tmp_path, bench=bench)
    assert code != 0 and "FAULT_CDC_ACTUAL_PARAMETER_FORWARDING_MISMATCH" in log, log
    assert "Time: 0 " in log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_observer_top_option_fails_closed(tmp_path, value):
    shutil.copyfile(ACQ / "tb" / PREPARE.OBSERVER, tmp_path / PREPARE.OBSERVER)
    # Icarus -P rejects X/Z with an error diagnostic but exits zero and leaves
    # the default parameter. Use a literal source override to apply those bits.
    bench = observer_bench().replace(
        "parameter integer PER_CAUSE_FAULT_CDC=ENABLED;",
        f"parameter integer PER_CAUSE_FAULT_CDC={value};",
        1,
    )
    code, log = run_cdc(tmp_path, bench=bench)
    assert code != 0 and "FAULT_CDC_ACTUAL_OPTION_INVALID" in log, log
    assert "error:" not in (tmp_path / "compile.log").read_text().lower()


def test_historical_log_parser_replay_is_explicitly_not_new_cdc_actual(
    prepared, tmp_path
):
    origin = ORIGINAL / "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log"
    log = tmp_path / "PARSER_ONLY_historical_log_plus_synthetic_CDC_receipt.log"
    log.write_text(origin.read_text() + RECEIPT)
    assert PREPARE.verify_result(log, 1, prepared / "frozen_sources") == {
        "samples": 1246258,
        "raw_equal": 953795,
        "invalid_only": 292463,
    }
    log.write_text(origin.read_text())
    with pytest.raises(ValueError, match="original or CDC receipt rejected"):
        PREPARE.verify_result(log, 1, prepared / "frozen_sources")


def test_tcl_preflight_reaches_only_create_project_trap(prepared, tmp_path):
    result = run_preflight(prepared, tmp_path)
    assert (
        result.returncode == 0
        and result.stdout.strip() == "OFFLINE_CREATE_PROJECT_TRAP"
    ), result.stdout + result.stderr
    assert not (prepared / "project").exists()


def run_preflight(prepared, tmp_path):
    script = tmp_path / "preflight.tcl"
    script.write_text("""proc version {args} {return "2022.2"}
proc set_param {name value} {
  if {$name ne "general.maxThreads" || $value != 2} {error "changed threads"}
}
proc create_project {args} {puts "OFFLINE_CREATE_PROJECT_TRAP"; exit 0}
set prepared [lindex $argv 0]
set argv [list $prepared]; set argc 1
source [file join $prepared frozen_sources simulate_exact_control_prepared.tcl]
error "unexpected fallthrough"
""")
    result = subprocess.run(
        ["tclsh", str(script), str(prepared)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    (tmp_path / "preflight.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize(
    "old,new",
    [
        (" PER_CAUSE_FAULT_CDC=1", ""),
        ("PER_CAUSE_FAULT_CDC=1", "REGISTERED_SCHEDULING=1"),
        ("REGISTERED_SCHEDULING=1", "PER_CAUSE_FAULT_CDC=1"),
        ("PER_CAUSE_FAULT_CDC=1", "PER_CAUSE_FAULT_CDC=1 PER_CAUSE_FAULT_CDC=1"),
        ("PER_CAUSE_FAULT_CDC=1", "per_cause_fault_cdc=1"),
        ("PER_CAUSE_FAULT_CDC=1", "PER_CAUSE_FAULT_CDC=01"),
        ("PER_CAUSE_FAULT_CDC=1", "PER_CAUSE_FAULT_CDC=2"),
        ("PER_CAUSE_FAULT_CDC=1", "PER_CAUSE_FAULT_CDC=x"),
        ("PER_CAUSE_FAULT_CDC=1", "PER_CAUSE_FAULT_CDC=z"),
        ("DISTRIBUTED_FAST_FAULT=1", "DISTRIBUTED_FAST_FAULT=0"),
        ("FAST_MHZ=175", "FAST_MHZ=200"),
    ],
)
def test_preflight_rejects_omitted_duplicate_malformed_and_wrong_options(
    prepared, tmp_path, old, new
):
    mutated = tmp_path / "deliberately_mutated_freeze"
    shutil.copytree(prepared, mutated)
    settings = mutated / "settings.tcl"
    original_sha = PREPARE.sha(settings)
    settings.write_text(settings.read_text().replace(old, new, 1))
    inventory = mutated / "SHA256SUMS"
    inventory.write_text(
        inventory.read_text().replace(original_sha, PREPARE.sha(settings), 1)
    )
    result = run_preflight(mutated, tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "OFFLINE_CREATE_PROJECT_TRAP" not in result.stdout
    assert not (mutated / "project").exists()


@pytest.mark.parametrize(
    "readback", ["exact", "omitted", "duplicate", "zero", "lowercase"]
)
def test_generic_readback_rejects_dropped_or_changed_forwarding(tmp_path, readback):
    generics = " ".join(f"{k}={v}" for k, v in SETTINGS.items())
    returned = generics
    for key, replacement in {
        "omitted": "",
        "duplicate": "REGISTERED_SCHEDULING=1",
        "zero": "PER_CAUSE_FAULT_CDC=0",
        "lowercase": "per_cause_fault_cdc=1",
    }.items():
        if readback == key:
            returned = generics.replace("PER_CAUSE_FAULT_CDC=1", replacement)
    script = tmp_path / "readback.tcl"
    script.write_text(
        f"set exact_generics {{{generics}}}\nproc get_filesets {{args}} {{return sim_1}}\nproc get_property {{args}} {{return {{{returned}}}}}\n"
        + PREPARE.TCL_READBACK
        + 'puts "READBACK_VERIFIED"\n'
    )
    result = subprocess.run(
        ["tclsh", str(script)], capture_output=True, text=True, check=False, timeout=5
    )
    (tmp_path / "readback.log").write_text(result.stdout + result.stderr)
    assert (result.returncode == 0) == (readback == "exact"), (
        result.stdout + result.stderr
    )


@pytest.mark.parametrize(
    "kind", ["existing", "dangling", "parent", "source", "source_children"]
)
def test_symlink_directory_admission_is_fail_closed_without_overwrite(tmp_path, kind):
    destination = tmp_path / "output"
    original = ORIGINAL
    target = tmp_path / "untouched_target"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("never overwrite\n")
    if kind == "existing":
        destination.symlink_to(target, target_is_directory=True)
    elif kind == "dangling":
        destination.symlink_to(tmp_path / "absent_target", target_is_directory=True)
    elif kind == "parent":
        alias = tmp_path / "alias"
        alias.symlink_to(target, target_is_directory=True)
        destination = alias / "new"
    elif kind == "source":
        original = tmp_path / "origin_alias"
        original.symlink_to(ORIGINAL, target_is_directory=True)
    else:
        original = tmp_path / "origin"
        original.mkdir()
        (original / "frozen_sources").symlink_to(
            ORIGINAL / "frozen_sources", target_is_directory=True
        )
    with pytest.raises(
        (ValueError, FileExistsError), match="symlinked actual|refusing to overwrite"
    ):
        PREPARE.prepare(original, destination)
    assert sentinel.read_text() == "never overwrite\n"
    assert {p.name for p in target.iterdir()} == {"sentinel.txt"}
    assert not (tmp_path / "absent_target").exists()
