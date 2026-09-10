"""Offline P1 physical source admission; all vendor project calls are traps."""
import hashlib
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
ACTUAL = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-prepared-v1")
G = runpy.run_path(str(ACQ / "prepare_product_final_fence_physical.py"))
ROM = runpy.run_path(str(ACQ / "prepare_rom_read_ahead_physical.py"))
C1 = runpy.run_path(str(ACQ / "prepare_fault_cdc_physical.py"))
BASE = runpy.run_path(str(ACQ / "prepare_exact_control_physical.py"))
P = "PRODUCER_LOCAL_FINAL_FENCE"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("product-final-physical") / "prepared"
    result = G["prepare"](ACTUAL, output)
    assert result["producer_final"] == result["rom_word"] == result["rom_metadata"] == result["per_cause"] == 1
    assert result["rtl_count"] == 8
    assert result["qualified_observer"] == {"samples": 1246258, "raw_equal": 953795, "invalid_only": 292463}
    return output


def helper(prepared):
    return runpy.run_path(str(prepared / "prepare_exact_control_physical.py"))


def refresh(path):
    files = sorted(p for p in path.rglob("*") if p.is_file() and p != path / "SHA256SUMS")
    (path / "SHA256SUMS").write_text("".join(f"{G['identity'](p)}  {p.relative_to(path)}\n" for p in files))


def test_whole_helper_chain_inverse_and_exact_eight_source_closure(prepared, tmp_path):
    original = (ACQ / "prepare_exact_control_physical.py").read_text()
    old = ROM["adapt"](C1["adapt"](original))
    assert hashlib.sha256(old.encode()).hexdigest() == G["ROM_HELPER_SHA"]
    new = (prepared / "prepare_exact_control_physical.py").read_text()
    assert G["restore"](new) == old
    assert C1["restore"](ROM["restore"](G["restore"](new))) == original
    old_path = tmp_path / "old.py";old_path.write_text(old)
    old_api = runpy.run_path(str(old_path))
    h = helper(prepared)
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    for after, before, count in (
        (" || $producer_final != 1", "", 1),
        (" PRODUCER_LOCAL_FINAL_FENCE $producer_final", "", 1),
        (" PRODUCER_LOCAL_FINAL_FENCE=$producer_final", "", 1),
        (" PRIVATE_BLOCK_METADATA_READ_AHEAD PRODUCER_LOCAL_FINAL_FENCE}", " PRIVATE_BLOCK_METADATA_READ_AHEAD}", 1),
        ("; producer_local_final_fence=$producer_final", "", 1),
        ("starlink_pss_fft_bank_owned_product_fence", "starlink_pss_fft_bank_owned_rom_read_ahead", 2),
        (" starlink_pss_product_fence_mailbox\n", "\n", 1),
    ):
        assert text.count(after) == count, after
        text = text.replace(after, before)
    assert text == old_api["adapt_synthesis"]((ACQ / "synthesize_fft_bank_owned_slice.tcl").read_text())
    assert h["SETTINGS"] == json.loads((ACTUAL / "fence-preparation.json").read_text())["settings"]
    assert h["SETTINGS"] != json.loads((ACTUAL / "preparation.json").read_text())["settings"]
    assert len(h["RTL"]) == len(set(h["RTL"])) == 8
    assert {"starlink_pss_block_mailbox.v", "starlink_pss_product_fence_mailbox.v"} <= set(h["RTL"])
    for name in h["RTL"] + ("upper_edge_pss_kernel_q17.mem", "create_shared_realtime_xfft_ip.tcl"):
        assert (prepared / "frozen_sources" / name).read_bytes() == (ACTUAL / "frozen_sources" / name).read_bytes()
    assert (prepared / "run_exact_control_synthesis.py").read_bytes() == (ACQ / "run_exact_control_synthesis.py").read_bytes()
    assert G["identity"](prepared / "run_exact_control_synthesis.py") == ROM["OWNER_SHA"]
    for path, name in ((prepared / "route_completed_input_fence.tcl", "route_completed_input_fence.tcl"),
            (prepared / "synthesize_fft_bank_owned_slice.original.tcl", "synthesize_fft_bank_owned_slice.tcl"),
            (prepared / "frozen_sources/fft_bank_owned_resource_probe.xdc", "fft_bank_owned_resource_probe.xdc"),
            (prepared / "frozen_sources/fft_bank_owned_synth_threads.tcl", "fft_bank_owned_synth_threads.tcl")):
        assert G["identity"](path) == BASE["FIXED"][name]


@pytest.mark.parametrize("before,after", [
    ('"PRODUCER_LOCAL_FINAL_FENCE": 1', '"PRODUCER_LOCAL_FINAL_FENCE": 0'),
    ('"product_fence_mailbox",', '"block_mailbox",'),
    ('"fence-preparation.json"', '"preparation.json"'),
    ('rom["verify_result"](logfile, 1, frozen)', 'rom["verify_result"](logfile, 0, frozen)'),
    ('PRODUCER_LOCAL_FINAL_FENCE=$producer_final', 'PRODUCER_LOCAL_FINAL_FENCE=0'),
    ('"rtl_count": 8', '"rtl_count": 7'),
    ('8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c', '0'*64),
    ('e4f4c56ddab8f05d0f9b9da9a75f975e11cb8ad441581c904bfb094f3013982f', '0'*64),
])
def test_entire_inverse_rejects_source_gate_and_flag_mutations(before, after):
    new = G["adapt"](ROM["adapt"](C1["adapt"]((ACQ / "prepare_exact_control_physical.py").read_text())))
    assert new.count(before) == 1
    with pytest.raises(ValueError):
        G["restore"](new.replace(before, after, 1))


@pytest.mark.parametrize("mode", ["good", "missing", "zero", "duplicate", "conflict", "case", "unknown", "lost_readback"])
def test_actual_generic_binding_and_readback_rejects_bad_final_option(prepared, tmp_path, mode):
    text = (prepared / "synthesize_exact_control_prepared.tcl").read_text()
    fragment = text[text.index("set_property generic "):text.index("set_property STEPS.SYNTH_DESIGN")]
    token = P+"=$producer_final"
    replacement = {"missing":"", "zero":P+"=0", "duplicate":token+" "+P+"=1", "conflict":token+" "+P+"=0", "case":P.lower()+"=1", "unknown":P+"=x"}
    if mode in replacement:
        fragment = fragment.replace(token, replacement[mode], 1)
    readback = "$::bound" if mode != "lost_readback" else f"[lreplace $::bound [lsearch -glob $::bound {P}=*] [lsearch -glob $::bound {P}=*]]"
    script = tmp_path / "generic.tcl"
    script.write_text(f"""set registered 1;set distributed 1;set scratch 1;set per_cause 1
set rom_word 1;set rom_metadata 1;set producer_final 1;set source_dir /offline
proc get_filesets {{args}} {{return sources_1}}
proc set_property {{name value object}} {{set ::bound $value}}
proc get_property {{name object}} {{return {readback}}}
""" + fragment + 'puts "EXACT_P1_BOUND=$bound"\n')
    result = subprocess.run(["tclsh", str(script)], capture_output=True, text=True, check=False, timeout=5)
    (tmp_path / "generic.log").write_text(result.stdout+result.stderr)
    assert (result.returncode == 0) == (mode == "good"), result.stdout+result.stderr
    assert ("EXACT_P1_BOUND=" in result.stdout) == (mode == "good")


@pytest.mark.parametrize("mode", ["trap", "bad_inventory", "existing_output", "poisoned_python"])
def test_full_source_admission_stops_before_vendor_project(prepared, tmp_path, mode, monkeypatch):
    output = tmp_path / "NO_VENDOR_PROJECT"
    if mode == "existing_output":
        output.mkdir()
    expected = G["identity"](prepared / "SHA256SUMS") if mode != "bad_inventory" else "0"*64
    script = tmp_path / "trap.tcl"
    script.write_text('''proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {args} {puts "OFFLINE_P1_CREATE_PROJECT_TRAP";exit 0}
set script [lindex $argv 0]
set argv [lrange $argv 1 end];set argc [llength $argv]
source $script
error "unexpected fallthrough"
''')
    if mode == "poisoned_python":
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
            monkeypatch.setenv(key, "/deliberately-invalid-P1-python-environment")
    before = {key:os.environ.get(key) for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH")}
    result = subprocess.run(["tclsh", str(script), str(prepared / "synthesize_exact_control_prepared.tcl"), str(output), str(prepared), expected], capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "preflight.log").write_text(result.stdout+result.stderr)
    assert before == {key:os.environ.get(key) for key in before}
    good = mode in ("trap", "poisoned_python")
    assert (result.returncode == 0) == good, result.stdout+result.stderr
    assert ("OFFLINE_P1_CREATE_PROJECT_TRAP" in result.stdout) == good
    assert not (output / "project").exists()


@pytest.mark.parametrize("kind", ["existing", "dangling", "parent", "source"])
def test_no_overwrite_or_symlink_admission(tmp_path, kind):
    target = tmp_path / "target";target.mkdir()
    output, actual = tmp_path / "output", ACTUAL
    if kind == "existing":
        output.mkdir()
    elif kind == "dangling":
        output.symlink_to(tmp_path / "missing", target_is_directory=True)
    elif kind == "parent":
        alias = tmp_path / "alias";alias.symlink_to(target, target_is_directory=True)
        output = alias / "output"
    else:
        actual = tmp_path / "actual-alias";actual.symlink_to(ACTUAL, target_is_directory=True)
    with pytest.raises((ValueError, FileExistsError)):
        G["prepare"](actual, output)
    assert not list(target.iterdir())


@pytest.mark.parametrize("name", ["starlink_pss_fft_bank_owned_product_fence.v", "starlink_pss_product_fence_mailbox.v", "starlink_pss_block_mailbox.v"])
def test_rehashed_source_corruption_does_not_close_actual(prepared, tmp_path, name):
    target = tmp_path / "mutated";shutil.copytree(prepared, target)
    path = target / "frozen_sources" / name;path.write_text(path.read_text()+"\n// changed\n")
    meta = json.loads((target / "physical_preparation.json").read_text())
    meta["source_sha256"][name] = G["identity"](path)
    (target / "physical_preparation.json").write_text(json.dumps(meta));refresh(target)
    with pytest.raises(ValueError, match="identities no longer close"):
        helper(prepared)["verify_prepared"](target, expected_inventory=G["identity"](target / "SHA256SUMS"))


def test_copied_closure_and_old_ROM_run_are_rejected(prepared, tmp_path):
    copied = tmp_path / "copied";shutil.copytree(prepared / "frozen_sources", copied)
    shutil.copyfile(prepared / "synthesize_exact_control_prepared.tcl", copied / "synthesize_exact_control_prepared.tcl")
    h = helper(prepared)
    assert h["verify_prepared"](prepared, copied, G["identity"](prepared / "SHA256SUMS"))["rtl_count"] == 8
    (copied / "starlink_pss_product_fence_mailbox.v").write_text("wrong\n")
    with pytest.raises(ValueError, match="copied synthesis source differs"):
        h["verify_prepared"](prepared, copied, G["identity"](prepared / "SHA256SUMS"))
    with pytest.raises(ValueError, match="exact passing combined actual inventory"):
        h["verify_actual"](ACTUAL.parent / "rom-relocated-actual-v2.CWJkzwEi/rom-actual-prepared-v1")


@pytest.mark.parametrize("mode", ["empty_status", "wrong_owner", "missing_final", "wrong_final"])
def test_original_actual_receipts_cannot_be_weakened(prepared, tmp_path, mode):
    actual = tmp_path / "actual";actual.mkdir()
    for line in (ACTUAL / "SHA256SUMS").read_text().splitlines():
        name = line.split("  ", 1)[1];target = actual / name
        target.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(ACTUAL / name, target)
    shutil.copyfile(ACTUAL / "SHA256SUMS", actual / "SHA256SUMS")
    owner = tmp_path / "product-final-actual-owner-v1";owner.mkdir()
    for name in ("before-integrity.log", "after-integrity.log", "time.txt", "launch.log", "owner.sh",
                 "process-exit.txt", "after-integrity-exit.txt", "after-ip-exit.txt", "receipt-exit.txt", "before.sha256", "after.sha256"):
        shutil.copyfile(ACTUAL.parent / "product-final-actual-owner-v1" / name, owner / name)
    simulation = actual / "project/exact_control_actual.sim/sim_1/behav/xsim";simulation.mkdir(parents=True)
    log = (ACTUAL / "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log").read_text()
    if mode == "empty_status":
        (owner / "receipt-exit.txt").write_text("")
    elif mode == "wrong_owner":
        (owner / "owner.sh").write_text("wrong owner\n")
    elif mode == "missing_final":
        log = "\n".join(line for line in log.splitlines() if not line.startswith("PRODUCT_FINAL_FENCE_ACTUAL_PASS"))+"\n"
    else:
        log = log.replace("PRODUCT_FINAL_FENCE_ACTUAL_PASS enabled=1", "PRODUCT_FINAL_FENCE_ACTUAL_PASS enabled=0")
    (simulation / "simulate.log").write_text(log)
    with pytest.raises(ValueError, match="persisted status|owner differs|product final terminal rejected"):
        helper(prepared)["verify_actual"](actual)
