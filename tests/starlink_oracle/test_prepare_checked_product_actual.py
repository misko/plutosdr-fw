"""Literal disabled actual harness preparation; compilation is actor-only."""
import hashlib
import json
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
HELPER = ACQ / "prepare_checked_product_actual.py"
API = runpy.run_path(str(HELPER))
ORIGIN = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-prepared-v1")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("disabled_actual")
    output = root / "prepared"
    result = API["prepare_disabled"](ORIGIN, output)
    (root / "preparation-receipt.json").write_text(json.dumps(result, indent=2))
    shutil.copyfile(HELPER, root / HELPER.name)
    shutil.copyfile(Path(__file__), root / Path(__file__).name)
    return output


def test_whole_old_bench_and_binding_restore(prepared):
    for name in API["ORIGINAL_SHA"]:
        new = (prepared / "frozen_sources" / name).read_text()
        old = (ORIGIN / "frozen_sources" / name).read_text()
        assert API["disabled_source"](name, new, inverse=True) == old
        # Old independent reference names are untouched, not redirected to
        # candidate hierarchy by a global replacement.
        assert new.count("exact_reference.dut.product_bank.") == old.count("exact_reference.dut.product_bank.")
    assert API["verify_disabled"](prepared)["runtime_modules"] == 14
    assert (prepared / "frozen_sources/simulate_exact_control_prepared.tcl").read_bytes() == (
        ORIGIN / "frozen_sources/simulate_exact_control_prepared.tcl").read_bytes()


def test_disabled_harness_elaborates_with_declared_control_actor_only(prepared, tmp_path):
    path = tmp_path / "compile"
    shutil.copytree(prepared / "frozen_sources", path)
    actor = ACQ / "tb/starlink_pss_fft512_control_actor.v"
    assert hashlib.sha256(actor.read_bytes()).hexdigest() == "a34d57daba44372d74c364dd6dd1b4acd898dcf9052814923eb5cc01e4b8f333"
    shutil.copyfile(actor, path / actor.name)
    command = ["iverilog", "-g2012", "-Wall", "-I.", "-s", "tb_starlink_pss_fft_bank_owned_slice",
               "-Ptb_starlink_pss_fft_bank_owned_slice.FAST_MHZ=175",
               *[f"-Ptb_starlink_pss_fft_bank_owned_slice.{key}=1" for key in (
                   "REGISTERED_SCHEDULING", "DISTRIBUTED_FAST_FAULT", "PRIVATE_NEXT_START_SCRATCH",
                   "PER_CAUSE_FAULT_CDC", "PRIVATE_ROM_READ_AHEAD", "PRIVATE_BLOCK_METADATA_READ_AHEAD",
                   "PRODUCER_LOCAL_FINAL_FENCE", "EXACT_EXTRA_EPOCHS")],
               "-o", "sim.vvp", *sorted(p.name for p in path.iterdir() if p.suffix in (".sv", ".v"))]
    result = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True,
                            text=True, timeout=30, check=False)
    (path / "compile.log").write_text(result.stdout + result.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": result.returncode,
        "scope": "actor_elaboration_only_NO_vvp_NO_vendor_NO_numerical_claim"}, indent=2))
    (path / "sources.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.iterdir() if p.is_file() and p.suffix in (".v", ".sv", ".svh", ".mem")}, indent=2))
    assert result.returncode == 0 and not re.search(r"(?im)error:", result.stderr), result.stderr


@pytest.mark.parametrize("name", list(API["RUNTIME_SHA"]))
def test_every_runtime_source_is_fixed(prepared, tmp_path, name):
    copy = tmp_path / "prepared"
    shutil.copytree(prepared, copy)
    target = copy / "frozen_sources" / name
    target.write_text(target.read_text() + "\n// changed frozen RTL\n")
    with pytest.raises(ValueError, match="changed"):
        API["verify_disabled"](copy)


@pytest.mark.parametrize("name", [
    "starlink_pss_fault_cdc_actual_observer.svh", "starlink_pss_rom_actual_observer.svh",
    "starlink_pss_forward_retirement_shadow.sv", "starlink_pss_exact_control_extra_epochs.svh",
    "starlink_pss_payload_bubble_shadow.sv", "prepare_exact_control_status_qualified.py",
    "samples_ci16.mem", "forward_q17.mem", "product_q17.mem", "inverse_q17.mem",
    "create_shared_realtime_xfft_ip.tcl", "simulate_exact_control_prepared.tcl",
])
def test_every_inherited_policy_remains_bound(prepared, tmp_path, name):
    copy = tmp_path / "prepared"
    shutil.copytree(prepared, copy)
    target = copy / "frozen_sources" / name
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="inherited body changed"):
        API["verify_disabled"](copy)


@pytest.mark.parametrize("old,new", [
    (".CHECKED_PRODUCT_BANK(0)", ".CHECKED_PRODUCT_BANK(1)"),
    ("EXACT_EXTRA_COVERAGE_MISSING", "WEAKENED_COVERAGE"),
    ("inverse output mismatch/invalid publication", "WEAKENED_NUMERICAL_CHECK"),
    ("exact_reference.dut.product_bank.request_toggle", "exact_reference.dut.original_product_bank.product_bank.request_toggle"),
])
def test_whole_observer_inverse_rejects_edits(prepared, old, new):
    source = (prepared / "frozen_sources" / API["TOP"]).read_text()
    if old == "EXACT_EXTRA_COVERAGE_MISSING":
        # The included file is separately immutable, not flattened into the bench.
        source = source.replace("EXACT_ACTUAL_REFERENCE_OR_COVERAGE_INCOMPLETE", new)
    else:
        assert old in source
        source = source.replace(old, new, 1)
    with pytest.raises(ValueError):
        API["disabled_source"](API["TOP"], source, inverse=True)


def test_no_overwrite_symlink_or_extra_actor(prepared, tmp_path):
    with pytest.raises(FileExistsError):
        API["prepare_disabled"](ORIGIN, prepared)
    link = tmp_path / "aliased"
    link.symlink_to(prepared, target_is_directory=True)
    with pytest.raises(ValueError, match="aliased"):
        API["verify_disabled"](link)
    copy = tmp_path / "copy"
    shutil.copytree(prepared, copy)
    (copy / "frozen_sources/starlink_pss_fft512_control_actor.v").write_text("module fake;endmodule\n")
    with pytest.raises(ValueError, match="unexpected"):
        API["verify_disabled"](copy)


def test_source_specific_cli_from_root(prepared):
    result = subprocess.run(["/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python", "-B", str(HELPER),
                             "--verify-disabled", str(prepared)], cwd="/", env=clean_env(),
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["scope"] == "disabled_compile_only_NOT_vendor_admission"


@pytest.fixture(scope="module")
def enabled_prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("enabled_actual")
    output = root / "prepared"
    result = API["prepare_enabled"](ORIGIN, output)
    (root / "preparation-receipt.json").write_text(json.dumps(result, indent=2))
    shutil.copyfile(Path(__file__), root / Path(__file__).name)
    return output


def test_enabled_harness_elaborates_actor_only(enabled_prepared, tmp_path):
    # Exactly the same compilation-only seam as the disabled case. This does
    # not run the control actor against vendor FFT numerical vectors.
    test_disabled_harness_elaborates_with_declared_control_actor_only(enabled_prepared, tmp_path)


def test_enabled_whole_source_inverse_and_original_runner(enabled_prepared):
    original = (ORIGIN / "frozen_sources" / API["TOP"]).read_text()
    body = (enabled_prepared / "frozen_sources" / API["TOP"]).read_text()
    changes = json.loads((enabled_prepared / "checked-whole-source-inverse.json").read_text())
    assert API["restore_enabled_source"](body, changes) == original
    assert len(changes) == 40
    assert API["verify_enabled"](enabled_prepared)["vendor_launch_admitted"] is False
    assert "starlink_pss_exact_control_reference_bench exact_reference" not in body
    assert "checked_actual_verify_terminal();" in body
    assert (enabled_prepared / "frozen_sources/simulate_exact_control_prepared.tcl").read_bytes() == (
        ORIGIN / "frozen_sources/simulate_exact_control_prepared.tcl").read_bytes()


@pytest.mark.parametrize("name", [
    API["TOP"], API["ENABLED_OBSERVER"], "starlink_pss_forward_retirement_shadow.sv",
    "starlink_pss_fault_cdc_actual_observer.svh", "starlink_pss_rom_actual_observer.svh",
    "starlink_pss_exact_control_extra_epochs.svh", "inverse_q17.mem",
    "create_shared_realtime_xfft_ip.tcl", "simulate_exact_control_prepared.tcl",
])
def test_enabled_rehashed_policy_mutation_rejected(enabled_prepared, tmp_path, name):
    target = tmp_path / "prepared"
    shutil.copytree(enabled_prepared, target)
    path = target / "frozen_sources" / name
    path.write_bytes(path.read_bytes() + b"\n// changed\n")
    # A locally refreshed inventory is not independent provenance.
    manifest = target / "SHA256SUMS"
    manifest.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(target)}\n"
        for p in sorted(target.rglob("*")) if p.is_file() and p != manifest))
    with pytest.raises(ValueError, match="changed"):
        API["verify_enabled"](target)


def test_enabled_inverse_receipt_cannot_authorize_changed_observer(enabled_prepared, tmp_path):
    target = tmp_path / "prepared"
    shutil.copytree(enabled_prepared, target)
    changes_path = target / "checked-whole-source-inverse.json"
    changes = json.loads(changes_path.read_text())
    changes[-1][1] = changes[-1][1].replace("PASS", "WEAKENED")
    changes_path.write_text(json.dumps(changes))
    with pytest.raises(ValueError, match="inverse receipt changed"):
        API["verify_enabled"](target)


def test_enabled_no_overwrite_symlink_and_portable_cli(enabled_prepared, tmp_path):
    with pytest.raises(FileExistsError):
        API["prepare_enabled"](ORIGIN, enabled_prepared)
    alias = tmp_path / "alias"
    alias.symlink_to(enabled_prepared, target_is_directory=True)
    with pytest.raises(ValueError, match="aliased"):
        API["verify_enabled"](alias)
    result = subprocess.run(["/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python", "-B",
        str(enabled_prepared / "prepare_checked_product_actual.py"),
        "--verify-enabled", str(enabled_prepared)], cwd="/", env=clean_env(),
        capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["absolute_service_cap"] == 5215


@pytest.mark.parametrize("old,new", [
    ("if(!checked_start_binding)", "if(1'b0)"),
    ("!checked_old_guard_ack || !checked_head_identity", "!checked_old_guard_ack || 1'b0"),
    ("checked_bad_word[checked_core_index] ||", "1'b0 ||"),
    ("checked_core_index!=512 || checked_raw_index!=512", "1'b0 || 1'b0"),
    ("!checked_bound_receipt || !dut.product_handoff_state_owned", "1'b0 || 1'b0"),
    ("checked_retained_owner();", "; // missing retained interval check"),
])
def test_weakened_observer_is_rejected_by_source_admission(enabled_prepared, tmp_path, old, new):
    target = tmp_path / "prepared"
    shutil.copytree(enabled_prepared, target)
    observer = target / "frozen_sources" / API["ENABLED_OBSERVER"]
    body = observer.read_text()
    assert old in body
    observer.write_text(body.replace(old, new))
    metadata = target / "checked-preparation.json"
    values = json.loads(metadata.read_text())
    values["observer_sha256"] = hashlib.sha256(observer.read_bytes()).hexdigest()
    metadata.write_text(json.dumps(values))
    with pytest.raises(ValueError, match="frozen enabled source changed"):
        API["verify_enabled"](target)
