"""Offline source admission, compile-only actual hierarchy and real-ROM observer."""

import itertools
import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB
from tests.starlink_oracle.test_exact_control_combined_preparation import compiled_scope

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
P = runpy.run_path(str(ACQ / "prepare_rom_read_ahead_actual.py"))
ORIGINAL = Path("/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1")
TOP = "tb_starlink_pss_fft_bank_owned_slice"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("rom-actual") / "prepared"
    assert P["prepare"](ORIGINAL, output) == dict(P["SETTINGS"], **{P["WORD"]: 1, P["META"]: 1})
    return output


def refresh(output):
    metadata = json.loads((output / "preparation.json").read_text())
    source = output / "frozen_sources"
    metadata["source_sha256"] = {p.name: P["sha"](p) for p in sorted(source.iterdir())}
    (output / "preparation.json").write_text(json.dumps(metadata, indent=2) + "\n")
    files = sorted(p for p in output.rglob("*") if p.is_file() and p != output / "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{P['sha'](p)}  {p.relative_to(output)}\n" for p in files))


def test_complete_source_closure_and_literal_inverses(prepared):
    old, new = ORIGINAL / "frozen_sources", prepared / "frozen_sources"
    old_metadata = json.loads((ORIGINAL / "preparation.json").read_text())
    metadata = json.loads((prepared / "preparation.json").read_text())
    added = {name + ".v" for name in P["VARIANTS"].values()} | {
        "starlink_pss_kernel_rom_read_ahead.v", P["OBSERVER"], "prepare_rom_read_ahead_actual.py"}
    assert set(metadata["source_sha256"]) == set(old_metadata["source_sha256"]) | added
    for name in old_metadata["source_sha256"]:
        if name not in (P["TOP"], P["RUNNER"]):
            assert (old / name).read_bytes() == (new / name).read_bytes(), name
    for name, edits in ((P["TOP"], P["BENCH_EDITS"]), (P["RUNNER"], P["RUNNER_EDITS"])):
        assert P["apply_edits"]((new / name).read_text(), edits, True) == (old / name).read_text()
    for name, new_name in P["VARIANTS"].items():
        assert P["apply_edits"]((new / (new_name + ".v")).read_text(), P["variant_edits"](name), True) == (old / (name + ".v")).read_text()
    assert metadata["compared_fields"] == old_metadata["compared_fields"]
    assert metadata["rom_origin_inventory"] == P["C1_INVENTORY"]
    assert (prepared / "rom-passing-C1-SHA256SUMS").read_bytes() == (ORIGINAL / "SHA256SUMS").read_bytes()
    assert P["verify_prepared"](prepared) == metadata["settings"]


@pytest.mark.parametrize("word,metadata", list(itertools.product((0, 1), repeat=2)))
def test_actual_hierarchy_elaboration_only_never_execute(prepared, tmp_path, word, metadata):
    source = prepared / "frozen_sources"
    settings = dict(P["SETTINGS"], **{P["WORD"]: word, P["META"]: metadata})
    (tmp_path / "stub.v").write_text(STUB)
    executable = tmp_path / "actual_hierarchy_STUB_NEVER_RUN.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-I", str(source), "-s", TOP,
        *[f"-P{TOP}.{k}={v}" for k, v in settings.items()], "-o", str(executable),
        *map(str, sorted(source.glob("*.v"))), *map(str, sorted(source.glob("*.sv"))),
        str(tmp_path / "stub.v")], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    compiled = executable.read_text()
    top_id, top = compiled_scope(compiled, TOP, TOP)
    dut_id, dut = compiled_scope(compiled, "dut", "starlink_pss_fft_bank_owned_rom_read_ahead", top_id)
    join_id, join = compiled_scope(compiled, "joiner", "starlink_pss_forward_kernel_join_read_ahead", dut_id)
    _, rom = compiled_scope(compiled, "kernel_rom", "starlink_pss_kernel_rom_read_ahead", join_id)
    _, old_rom = compiled_scope(compiled, "rom_input_reference", "starlink_pss_kernel_rom", top_id)
    ref_id, ref = compiled_scope(compiled, "exact_reference", "tb_starlink_pss_exact_control_reference", top_id)
    _, golden = compiled_scope(compiled, "dut", "starlink_pss_fft_bank_owned_slice_dec20d63_golden", ref_id)
    assert {k: top[k] for k in settings} == settings
    for scope in (dut, join, rom):
        assert scope[P["WORD"]] == word and scope[P["META"]] == metadata
        assert scope["PRIVATE_NEXT_START_SCRATCH"] == 1
    assert rom["DATA_WIDTH"] == old_rom["DATA_WIDTH"] == 18
    assert rom["BALANCED_BLOCK_IDENTITY_EQ"] == old_rom["BALANCED_BLOCK_IDENTITY_EQ"] == 1
    assert old_rom["PRIVATE_NEXT_START_SCRATCH"] == 1
    assert ref["REGISTERED_SCHEDULING"] == golden["REGISTERED_SCHEDULING"] == 1
    assert "DISTRIBUTED_FAST_FAULT" not in golden and P["WORD"] not in golden
    (tmp_path / "bindings.json").write_text(json.dumps({"scope":"compile_only_STUB_NEVER_RUN", "top":top, "dut":dut, "join":join, "rom":rom, "input_reference":old_rom, "dec20_reference":golden}, indent=2))


@pytest.mark.parametrize("file,before,after", [
    (P["TOP"], ".PRIVATE_ROM_READ_AHEAD(PRIVATE_ROM_READ_AHEAD)", ".PRIVATE_ROM_READ_AHEAD(0)"),
    (P["TOP"], ".PRIVATE_BLOCK_METADATA_READ_AHEAD(PRIVATE_BLOCK_METADATA_READ_AHEAD)", ".PRIVATE_BLOCK_METADATA_READ_AHEAD(0)"),
    ("starlink_pss_forward_kernel_join_read_ahead.v", ".PRIVATE_NEXT_START_SCRATCH(PRIVATE_NEXT_START_SCRATCH)", ".PRIVATE_NEXT_START_SCRATCH(0)"),
    ("starlink_pss_fft_bank_owned_rom_read_ahead.v", "input_valid((REGISTERED_SCHEDULING", "input_valid((1"),
    (P["OBSERVER"], ".input_block_start_index(dut.joiner.kernel_rom.input_block_start_index)", ".input_block_start_index(dut.joiner.kernel_rom.output_block_start_index)"),
    (P["OBSERVER"], ".output_ready(dut.joiner.kernel_rom.output_ready)", ".output_ready(dut.joiner.kernel_rom.output_ready), .input_ready(dut.joiner.kernel_rom.input_ready)"),
])
def test_rehashed_source_mutations_still_fail_admission(prepared, tmp_path, file, before, after):
    output = tmp_path / "mutated"
    shutil.copytree(prepared, output)
    path = output / "frozen_sources" / file
    path.write_text(P["once"](path.read_text(), before, after))
    refresh(output)
    with pytest.raises(ValueError):
        P["verify_prepared"](output)


@pytest.mark.parametrize("name,before,after", [
    ("starlink_pss_fault_cdc_actual_observer.svh", "fault_cdc_final_edges=fault_cdc_final_edges+1;", "fault_cdc_final_edges=0;"),
    ("starlink_pss_exact_control_actual_compare.sv", "$fatal", "$display"),
    ("tb_starlink_pss_exact_control_reference.sv", "$fatal", "$display"),
    ("prepare_exact_control_status_qualified.py", "raise ValueError", "raise RuntimeError"),
    ("starlink_pss_kernel_rom_dec20d63_golden.v", "output_valid <= 1'b0", "output_valid <= 1'b1"),
    ("samples_ci16.mem", "\n", "0\n"),
])
def test_rehashed_inherited_observers_reference_helper_vectors_reject(prepared, tmp_path, name, before, after):
    output = tmp_path / "mutated"
    shutil.copytree(prepared, output)
    path = output / "frozen_sources" / name
    original = path.read_text()
    assert before in original
    path.write_text(original.replace(before, after, 1))
    refresh(output)
    with pytest.raises(ValueError, match="inherited C1 artifact changed"):
        P["verify_prepared"](output)


@pytest.mark.parametrize("name", ["rom-passing-C1-SHA256SUMS", "rom-origin-settings.tcl", "rom-origin-preparation.json"])
def test_rehashed_inherited_inventory_and_metadata_backups_reject(prepared, tmp_path, name):
    output = tmp_path / "mutated"
    shutil.copytree(prepared, output)
    path = output / name
    path.write_text(path.read_text() + "\n")
    refresh(output)
    with pytest.raises(ValueError, match="inherited C1"):
        P["verify_prepared"](output)


@pytest.mark.parametrize("key", [P["WORD"], P["META"]])
@pytest.mark.parametrize("kind", ["missing", "duplicate", "other-key", "zero", "case", "unknown"])
def test_option_list_not_just_length(prepared, tmp_path, key, kind):
    output = tmp_path / "mutated"
    shutil.copytree(prepared, output)
    path = output / "settings.tcl"
    changes = {"missing":"", "duplicate":f"{key}=1 {key}=1", "other-key":"PRIVATE_NEXT_START_SCRATCH=1",
               "zero":f"{key}=0", "case":f"{key.lower()}=1", "unknown":f"{key}=x"}
    path.write_text(path.read_text().replace(key + "=1", changes[kind]))
    refresh(output)
    with pytest.raises(ValueError, match="binding"):
        P["verify_prepared"](output)


def test_no_overwrite_symlink_and_failed_original_process(prepared, tmp_path):
    with pytest.raises(FileExistsError):
        P["prepare"](ORIGINAL, prepared)
    link = tmp_path / "link"
    link.symlink_to(prepared, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        P["prepare"](ORIGINAL, link / "output")
    with pytest.raises(ValueError, match="symlink"):
        P["prepare"](link, tmp_path / "new")
    origin = tmp_path / "failed-origin"
    origin.mkdir()
    for line in (ORIGINAL / "SHA256SUMS").read_text().splitlines():
        name = line.split("  ", 1)[1]
        target = origin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ORIGINAL / name, target)
    shutil.copyfile(ORIGINAL / "SHA256SUMS", origin / "SHA256SUMS")
    (origin / "actual-process-exit.txt").write_text("1\n")
    with pytest.raises(ValueError, match="process failed"):
        P["prepare"](origin, tmp_path / "no-output")
    assert not (tmp_path / "no-output").exists()


def test_mocked_tcl_admission_sanitizes_python_and_stops_before_vendor(prepared, tmp_path):
    program = """proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {args} {error ROM_CREATE_PROJECT_TRAP}
set argc 1
set argv [list [lindex $argv 0]]
if {[catch {source [file join [lindex $argv 0] frozen_sources simulate_exact_control_prepared.tcl]} message]} {
  puts $message
}
puts "PARENT_ENV=$env(PYTHONHOME),$env(PYTHONPATH),$env(LD_LIBRARY_PATH)"
"""
    env = dict(os.environ, PYTHONHOME="/nonexistent/rom-python-home",
               PYTHONPATH="/nonexistent/rom-python-path", LD_LIBRARY_PATH="/nonexistent/rom-loader")
    result = subprocess.run(["tclsh", "/dev/stdin", str(prepared)], input=program,
                            env=env, capture_output=True, text=True, check=False, timeout=20)
    (tmp_path / "admission.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and "ROM_CREATE_PROJECT_TRAP" in result.stdout, result.stdout + result.stderr
    assert '"PRIVATE_ROM_READ_AHEAD": 1' in result.stdout
    assert "PARENT_ENV=/nonexistent/rom-python-home,/nonexistent/rom-python-path,/nonexistent/rom-loader" in result.stdout
    assert not (prepared / "project").exists()


@pytest.mark.parametrize("module", list(P["VARIANTS"].values()))
@pytest.mark.parametrize("key", [P["WORD"], P["META"]])
@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_new_public_entry_options_fail_closed(tmp_path, module, key, value):
    shutil.copyfile(ORIGINAL / "frozen_sources/upper_edge_pss_kernel_q17.mem", tmp_path / "upper_edge_pss_kernel_q17.mem")
    (tmp_path / "stub.v").write_text(STUB)
    (tmp_path / "invalid.sv").write_text(
        f'module invalid; {module} #(.KERNEL_ROM_FILE("upper_edge_pss_kernel_q17.mem"),.{key}({value})) dut(); '
        'initial begin #1; $fatal(1,"invalid option escaped"); end endmodule\n')
    modules = [ACQ / n for n in P["RTL_SHA"]] + [ACQ / (n + ".v") for n in P["VARIANTS"].values()] + [ACQ / "starlink_pss_kernel_rom_read_ahead.v"]
    result = subprocess.run(["iverilog", "-g2012", "-s", "invalid", "-o", str(tmp_path / "invalid.vvp"),
                             *map(str, modules), str(tmp_path / "stub.v"), str(tmp_path / "invalid.sv")],
                            capture_output=True, text=True, check=False, timeout=20)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", "invalid.vvp"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=10)
    log = result.stdout + result.stderr
    (tmp_path / "simulation.log").write_text(log)
    assert result.returncode != 0 and f"{key} must be zero or one" in log and "Time: 0 " in log, log
    assert "invalid option escaped" not in log


def observer_run(tmp_path, word=1, metadata=1, corruption=0, alias=0, observer=None, bench=None):
    source = ACQ / "tb/tb_starlink_pss_rom_actual_observer.sv"
    (tmp_path / "bench.sv").write_text(source.read_text() if bench is None else bench)
    (tmp_path / P["OBSERVER"]).write_text((ACQ / "tb" / P["OBSERVER"]).read_text() if observer is None else observer)
    shutil.copyfile(ORIGINAL / "frozen_sources/upper_edge_pss_kernel_q17.mem", tmp_path / "upper_edge_pss_kernel_q17.mem")
    executable = tmp_path / "observer.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-I", str(tmp_path), "-s", "tb_rom_actual_observer",
        f"-Ptb_rom_actual_observer.{P['WORD']}={word}", f"-Ptb_rom_actual_observer.{P['META']}={metadata}",
        f"-Ptb_rom_actual_observer.CORRUPTION={corruption}", f"-Ptb_rom_actual_observer.ALIAS_PORT={alias}",
        "-o", str(executable), str(ACQ / "starlink_pss_kernel_rom.v"),
        str(ACQ / "starlink_pss_kernel_rom_read_ahead.v"), str(ACQ / "starlink_pss_forward_kernel_join_read_ahead.v"),
        str(tmp_path / "bench.sv")], capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, capture_output=True, text=True, timeout=15, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulation.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("word,metadata", list(itertools.product((0, 1), repeat=2)))
@pytest.mark.parametrize("alias", [0, 1])
def test_real_joiner_rom_observer_not_bank_lifecycle(tmp_path, word, metadata, alias):
    code, log = observer_run(tmp_path, word, metadata, alias=alias)
    assert code == 0 and log.count("ROM_READ_AHEAD_ACTUAL_PASS") == 1, log
    assert "real_joiner_rom=1 vendor_fft=0 bank_lifecycle=0" in log
    assert f"alias_port={alias} same_time_drive=1" in log
    assert receipt(tmp_path, log, word, metadata).returncode == 0


@pytest.mark.parametrize("corruption", [1, 2, 3, 4, 5])
def test_unqualified_word_state_valid_and_fault_corruption_rejects(tmp_path, corruption):
    code, log = observer_run(tmp_path, corruption=corruption)
    assert code != 0 and "ROM_ACTUAL_UNCONDITIONAL_MISMATCH" in log, log


@pytest.mark.parametrize("before,after,marker", [
    (".input_block_start_index(dut.joiner.kernel_rom.input_block_start_index)", ".input_block_start_index(dut.joiner.kernel_rom.output_block_start_index)", "ROM_ACTUAL_UNCONDITIONAL_MISMATCH"),
    (".PRIVATE_NEXT_START_SCRATCH(1)", ".PRIVATE_NEXT_START_SCRATCH(0)", "ROM_ACTUAL_UNCONDITIONAL_MISMATCH"),
    ("rom_pre_checks=rom_pre_checks+1;", "rom_pre_checks=0;", "ROM_ACTUAL_COVERAGE_INCOMPLETE"),
    ("rom_post_checks=rom_post_checks+1;", "rom_post_checks=0;", "ROM_ACTUAL_COVERAGE_INCOMPLETE"),
    ("rom_final_fault_edges=rom_final_fault_edges+1;", "rom_final_fault_edges=0;", "ROM_ACTUAL_COVERAGE_INCOMPLETE"),
    ("rom_private_reset_edges=rom_private_reset_edges+1;", "rom_private_reset_edges=0;", "ROM_ACTUAL_COVERAGE_INCOMPLETE"),
])
def test_observer_reference_binding_and_coverage_mutants(tmp_path, before, after, marker):
    observer = P["once"]((ACQ / "tb" / P["OBSERVER"]).read_text(), before, after)
    code, log = observer_run(tmp_path, observer=observer)
    assert code != 0 and marker in log, log


RECEIPT = "ROM_READ_AHEAD_ACTUAL_PASS word=1 metadata=1 pre=1024 post=1024 accepts=512 first=1 last=1 stalls=2 resets=2 current_fault_edges=2 final_fault_edges=2 private_reset_edges=2 old_source=C1 input_ports_only=1 unconditional_old_state=1\n"


def receipt(tmp_path, log, word=1, metadata=1):
    path = tmp_path / "receipt-input.log"
    path.write_text(log)
    result = subprocess.run(["tclsh", "/dev/stdin", str(path)],
        input=P["TCL_RECEIPT"] + f"\nset f [open [lindex $argv 0] r]; set log [read $f]; close $f\nputs [rom_verify_receipt $log {word} {metadata}]\n",
        capture_output=True, text=True, timeout=5, check=False)
    (tmp_path / "receipt.log").write_text(result.stdout + result.stderr)
    return result


def test_receipt_requires_actual_private_reset_edges_and_qualified_fields(tmp_path):
    assert receipt(tmp_path, RECEIPT).returncode == 0


@pytest.mark.parametrize("before,after", [
    ("word=1", "word=0"), ("metadata=1", "metadata=0"), ("pre=1024", "pre=0"),
    ("post=1024", "post=1023"), ("accepts=512", "accepts=511"), ("first=1", "first=0"),
    ("last=1", "last=0"), ("stalls=2", "stalls=0"), ("resets=2", "resets=0"),
    ("current_fault_edges=2", "current_fault_edges=0"), ("final_fault_edges=2", "final_fault_edges=1"),
    ("private_reset_edges=2", "private_reset_edges=0"),
    ("input_ports_only=1", "input_ports_only=0"), ("unconditional_old_state=1", "unconditional_old_state=0"),
    (RECEIPT, RECEIPT + RECEIPT), (RECEIPT, ""),
])
def test_receipt_rejects_scope_counts_settings_missing_duplicate(tmp_path, before, after):
    assert receipt(tmp_path, RECEIPT.replace(before, after)).returncode != 0


def test_reference_has_only_actual_rom_inputs_and_direct_comparisons():
    observer = (ACQ / "tb" / P["OBSERVER"]).read_text()
    ports = re.search(r"\) rom_input_reference \((.*?)\n  \);", observer, re.DOTALL)[1]
    names = ("clk", "resetn", "flush", "input_valid", "input_bin_index", "input_block_exponent", "input_last", "input_block_start_index", "output_ready")
    assert re.findall(r"\.(\w+)\(dut\.joiner\.kernel_rom\.(\w+)\)", ports) == [(n, n) for n in names]
    assert len(re.findall(r"\.\w+\(", ports)) == len(names)
    assert "if (`ROM_ACTUAL_VIEW(dut.joiner.kernel_rom) !== `ROM_ACTUAL_VIEW(rom_input_reference))" in observer
    assert not re.search(r"\b(force|release|assign)\b.*dut\.", observer)
    assert P["sha"](ACQ / "tb" / P["OBSERVER"]) == P["OBSERVER_SHA"]
