"""Offline K1/M1 physical admission; vendor entry points remain traps."""

import hashlib
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi/rom-actual-prepared-v1")
GEN = runpy.run_path(str(ACQ / "prepare_rom_read_ahead_physical.py"))
C1 = runpy.run_path(str(ACQ / "prepare_fault_cdc_physical.py"))
BASE = runpy.run_path(str(ACQ / "prepare_exact_control_physical.py"))
K, M = "PRIVATE_ROM_READ_AHEAD", "PRIVATE_BLOCK_METADATA_READ_AHEAD"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("rom-physical") / "prepared"
    result = GEN["prepare"](ACTUAL, output)
    assert result["rom_word"] == result["rom_metadata"] == result["per_cause"] == 1
    assert result["rtl_count"] == 7
    assert result["qualified_observer"] == {"samples": 1246258, "raw_equal": 953943, "invalid_only": 292315}
    return output


def helper(prepared):
    return runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))


def refresh(directory):
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p != directory / "SHA256SUMS")
    (directory / "SHA256SUMS").write_text("".join(f"{GEN['identity'](p)}  {p.relative_to(directory)}\n" for p in files))


def test_full_helper_adapter_owner_and_source_inverses(prepared, tmp_path):
    original = (ACQ / "prepare_exact_control_physical.py").read_text()
    c1 = C1["adapt"](original)
    assert hashlib.sha256(c1.encode()).hexdigest() == GEN["C1_HELPER_SHA"]
    derived = (prepared / "prepare_exact_control_physical.py").read_text()
    assert GEN["restore"](derived) == c1
    assert C1["restore"](GEN["restore"](derived)) == original
    assert GEN["identity"](ACQ / "prepare_fault_cdc_physical.py") == GEN["C1_GENERATOR_SHA"]
    assert (prepared / "run_exact_control_synthesis.py").read_bytes() == (ACQ / "run_exact_control_synthesis.py").read_bytes()
    assert GEN["identity"](prepared / "run_exact_control_synthesis.py") == GEN["OWNER_SHA"]
    frozen_c1 = tmp_path / "frozen_C1_helper.py"
    frozen_c1.write_text(c1)
    old = runpy.run_path(str(frozen_c1))
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    for new, before in (
        (" || $rom_word != 1 || $rom_metadata != 1", ""),
        (" PRIVATE_ROM_READ_AHEAD $rom_word PRIVATE_BLOCK_METADATA_READ_AHEAD $rom_metadata", ""),
        (" PRIVATE_ROM_READ_AHEAD=$rom_word PRIVATE_BLOCK_METADATA_READ_AHEAD=$rom_metadata", ""),
        ("; private_rom_read_ahead=$rom_word; private_block_metadata_read_ahead=$rom_metadata", ""),
        (GEN["ROM_GENERIC_UNIQUE"], ""),
    ):
        assert text.count(new) == 1
        text = text.replace(new, before, 1)
    for before, new in GEN["NAMES"].items():
        assert text.count(new) == (2 if "bank_owned" in before else 1)
        text = text.replace(new, before)
    assert text == old["adapt_synthesis"]((ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text())
    h = helper(prepared)
    assert h["SETTINGS"] == json.loads((ACTUAL / "preparation.json").read_text())["settings"]
    assert len(h["RTL"]) == 7
    assert {p.name for p in (prepared / "frozen_sources").iterdir()} == set(h["SOURCE_NAMES"])
    for name in h["RTL"] + ("create_shared_realtime_xfft_ip.tcl", "upper_edge_pss_kernel_q17.mem"):
        assert (prepared / "frozen_sources" / name).read_bytes() == (ACTUAL / "frozen_sources" / name).read_bytes()
    for name in ("fft_bank_owned_resource_probe.xdc", "fft_bank_owned_synth_threads.tcl"):
        assert GEN["identity"](prepared / "frozen_sources" / name) == BASE["FIXED"][name]
    for name, original_name in (("route_completed_input_fence.tcl", "route_completed_input_fence.tcl"),
                                ("synthesize_fft_bank_owned_slice.original.tcl", "synthesize_fft_bank_owned_slice.tcl")):
        assert GEN["identity"](prepared / name) == BASE["FIXED"][original_name]
    assert all((ACQ / (old_name + ".v")).read_bytes() == (ACTUAL / "frozen_sources" / (old_name + ".v")).read_bytes()
               for old_name in GEN["NAMES"])


@pytest.mark.parametrize("before,after", [
    ('"PRIVATE_ROM_READ_AHEAD": 1', '"PRIVATE_ROM_READ_AHEAD": 0'),
    ('"PRIVATE_BLOCK_METADATA_READ_AHEAD": 1', '"PRIVATE_BLOCK_METADATA_READ_AHEAD": 0'),
    ('rom["verify_result"](logfile, 1, 1, frozen)', 'rom["verify_result"](logfile, 1, 0, frozen)'),
    ('"ROM actual stored pre/post inventory or runner differs"', '"weakened"'),
    ('PRIVATE_ROM_READ_AHEAD=$rom_word', 'PRIVATE_ROM_READ_AHEAD=0'),
    ('PRIVATE_BLOCK_METADATA_READ_AHEAD=$rom_metadata', 'PRIVATE_BLOCK_METADATA_READ_AHEAD=0'),
    ('"rtl_count": 7', '"rtl_count": 6'),
])
def test_whole_inverse_rejects_missing_knobs_checks_and_unrelated_changes(before, after):
    source = GEN["adapt"](C1["adapt"]((ACQ / "prepare_exact_control_physical.py").read_text()))
    assert before in source
    with pytest.raises(ValueError):
        GEN["restore"](source.replace(before, after, 1))


@pytest.mark.parametrize("key", [K, M])
@pytest.mark.parametrize("mode", ["good", "missing", "zero", "duplicate", "conflict", "case", "unknown", "lost_readback"])
def test_explicit_generic_set_and_actual_readback_reject_bad_flags(prepared, tmp_path, key, mode):
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    fragment = text[text.index("set_property generic "):text.index("set_property STEPS.SYNTH_DESIGN")]
    variable = "$rom_word" if key == K else "$rom_metadata"
    token = f"{key}={variable}"
    replacements = {"missing":"", "zero":f"{key}=0", "duplicate":f"{token} {key}=1",
                    "conflict":f"{token} {key}=0", "case":f"{key.lower()}=1", "unknown":f"{key}=x"}
    if mode in replacements:
        fragment = fragment.replace(token, replacements[mode], 1)
    readback = "$::bound"
    if mode == "lost_readback":
        readback = f"[lreplace $::bound [lsearch -glob $::bound {key}=*] [lsearch -glob $::bound {key}=*]]"
    mock = f"""set registered 1; set distributed 1; set scratch 1; set per_cause 1
set rom_word 1; set rom_metadata 1; set source_dir /offline
proc get_filesets {{args}} {{return sources_1}}
proc set_property {{name value object}} {{set ::bound $value}}
proc get_property {{name object}} {{return {readback}}}
"""
    script = tmp_path / "generic.tcl"
    script.write_text(mock + fragment + 'puts "EXACT_K1M1_BOUND=$bound"\n')
    result = subprocess.run(["tclsh", str(script)], capture_output=True, text=True, timeout=5, check=False)
    (tmp_path / "generic.log").write_text(result.stdout + result.stderr)
    assert (result.returncode == 0) == (mode == "good"), result.stdout + result.stderr
    if mode == "good":
        assert K + "=1" in result.stdout and M + "=1" in result.stdout
    else:
        assert "EXACT_K1M1_BOUND=" not in result.stdout


@pytest.mark.parametrize("mode", ["trap", "bad_inventory", "existing_output", "poisoned_python"])
def test_full_admission_stops_before_vendor_project(prepared, tmp_path, mode, monkeypatch):
    output = tmp_path / "NO_VENDOR_PROJECT"
    if mode == "existing_output":
        output.mkdir()
    expected = GEN["identity"](prepared / "SHA256SUMS") if mode != "bad_inventory" else "0" * 64
    script = tmp_path / "trap.tcl"
    script.write_text('''proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {args} {puts "OFFLINE_ROM_CREATE_PROJECT_TRAP"; exit 0}
set script [lindex $argv 0]
set argv [lrange $argv 1 end]; set argc [llength $argv]
source $script
error "unexpected fallthrough"
''')
    if mode == "poisoned_python":
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
            monkeypatch.setenv(key, "/deliberately-invalid-ROM-python-environment")
    before = {key:os.environ.get(key) for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH")}
    result = subprocess.run(["tclsh", str(script), str(prepared / "synthesize_exact_control_prepared.tcl"),
                             str(output), str(prepared), expected], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "preflight.log").write_text(result.stdout + result.stderr)
    assert {key:os.environ.get(key) for key in before} == before
    good = mode in ("trap", "poisoned_python")
    assert (result.returncode == 0) == good, result.stdout + result.stderr
    assert ("OFFLINE_ROM_CREATE_PROJECT_TRAP" in result.stdout) == good
    assert not (output / "project").exists()


@pytest.mark.parametrize("kind", ["existing", "dangling", "parent", "source"])
def test_no_overwrite_or_symlink_admission(tmp_path, kind):
    target = tmp_path / "target"
    target.mkdir()
    output, actual = tmp_path / "output", ACTUAL
    if kind == "existing":
        output.mkdir()
    elif kind == "dangling":
        output.symlink_to(tmp_path / "missing", target_is_directory=True)
    elif kind == "parent":
        alias = tmp_path / "alias"
        alias.symlink_to(target, target_is_directory=True)
        output = alias / "output"
    else:
        actual = tmp_path / "actual-alias"
        actual.symlink_to(ACTUAL, target_is_directory=True)
    with pytest.raises((ValueError, FileExistsError)):
        GEN["prepare"](actual, output)
    assert not list(target.iterdir())


@pytest.mark.parametrize("name", ["starlink_pss_fft_bank_owned_rom_read_ahead.v", "starlink_pss_forward_kernel_join_read_ahead.v", "starlink_pss_kernel_rom_read_ahead.v"])
def test_rehashed_physical_source_corruption_rejects(prepared, tmp_path, name):
    output = tmp_path / "mutated"
    shutil.copytree(prepared, output)
    path = output / "frozen_sources" / name
    path.write_text(path.read_text() + "\n// corrupted frozen source\n")
    metadata = json.loads((output / "physical_preparation.json").read_text())
    metadata["source_sha256"][name] = GEN["identity"](path)
    (output / "physical_preparation.json").write_text(json.dumps(metadata))
    refresh(output)
    with pytest.raises(ValueError, match="identities no longer close"):
        helper(prepared)["verify_prepared"](output, expected_inventory=GEN["identity"](output / "SHA256SUMS"))


def test_copied_closure_and_failed_original_are_not_admitted(prepared, tmp_path):
    output = tmp_path / "copied"
    shutil.copytree(prepared / "frozen_sources", output)
    shutil.copyfile(prepared / "synthesize_exact_control_prepared.tcl", output / "synthesize_exact_control_prepared.tcl")
    h = helper(prepared)
    assert h["verify_prepared"](prepared, output, GEN["identity"](prepared / "SHA256SUMS"))["rom_word"] == 1
    (output / "starlink_pss_kernel_rom_read_ahead.v").write_text("not the tested ROM\n")
    with pytest.raises(ValueError, match="copied synthesis source differs"):
        h["verify_prepared"](prepared, output, GEN["identity"](prepared / "SHA256SUMS"))
    with pytest.raises(ValueError, match="incomplete actual before/after"):
        h["verify_actual"](Path("/tmp/starlink-rom-prefetch.j829ht/rom-actual-prepared-v1"))
    with pytest.raises(ValueError, match="exact passing combined actual inventory"):
        h["verify_actual"](Path("/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1"))


@pytest.mark.parametrize("mode", ["empty_status", "bad_status", "missing_post_hash", "wrong_owner", "missing_rom", "wrong_rom", "corrupt_old_observer"])
def test_copied_actual_receipt_and_source_mutations_reject(prepared, tmp_path, mode):
    # Bounded copied observation fixture only; no new vendor run/project.
    actual = tmp_path / "actual"
    actual.mkdir()
    for line in (ACTUAL / "SHA256SUMS").read_text().splitlines():
        name = line.split("  ", 1)[1]
        target = actual / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ACTUAL / name, target)
    shutil.copyfile(ACTUAL / "SHA256SUMS", actual / "SHA256SUMS")
    if mode == "corrupt_old_observer":
        (actual / "frozen_sources/starlink_pss_exact_control_actual_compare.sv").write_text("weakened old observer\n")
        with pytest.raises(subprocess.CalledProcessError):
            helper(prepared)["verify_actual"](actual)
        return
    owner = tmp_path / "rom-actual-owner-v1"
    owner.mkdir()
    for name in ("before-integrity.log", "after-integrity.log", "time.txt", "launch.log", "owner.sh",
                 "process-exit.txt", "after-integrity-exit.txt", "after-ip-exit.txt", "receipt-exit.txt",
                 "before.sha256", "after.sha256"):
        shutil.copyfile(ACTUAL.parent / "rom-actual-owner-v1" / name, owner / name)
    simulation = actual / "project/exact_control_actual.sim/sim_1/behav/xsim"
    simulation.mkdir(parents=True)
    log = (ACTUAL / "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log").read_text()
    if mode == "empty_status":
        (owner / "receipt-exit.txt").write_text("")
    elif mode == "bad_status":
        (owner / "receipt-exit.txt").write_text("1\n")
    elif mode == "missing_post_hash":
        (owner / "after.sha256").write_text("")
    elif mode == "wrong_owner":
        (owner / "owner.sh").write_text("changed owner\n")
    elif mode == "missing_rom":
        log = "\n".join(line for line in log.splitlines() if not line.startswith("ROM_READ_AHEAD_ACTUAL_PASS")) + "\n"
    elif mode == "wrong_rom":
        log = log.replace("ROM_READ_AHEAD_ACTUAL_PASS word=1 metadata=1", "ROM_READ_AHEAD_ACTUAL_PASS word=0 metadata=1")
    (simulation / "simulate.log").write_text(log)
    with pytest.raises(ValueError, match="persisted status|stored pre/post|owner differs|ROM terminal rejected"):
        helper(prepared)["verify_actual"](actual)
