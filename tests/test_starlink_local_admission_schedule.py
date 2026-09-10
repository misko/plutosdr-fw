"""Offline Active/inactive/NBA scheduling model, never a vendor-kernel replay."""
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
FAILED = ACQ / "build/local-admission-actual-R1B1O1-L1-175-prepared-v3/frozen_sources"
OBSERVER = "starlink_pss_local_admission_actual_observer.sv"
BENCH = "tb_starlink_pss_local_admission_schedule.sv"
OLD_SHA = "ea16d902560799e4ddb694b8172fb689d6c2468378053ddad127655f9be7d368"


def old_observer():
    source = (FAILED / OBSERVER).read_bytes()
    assert hashlib.sha256(source).hexdigest() == OLD_SHA
    return source.decode()


def test_exactly_two_zero_time_pre_waits_no_masks_post_stimulus_or_runtime_changes():
    old = old_observer()
    new = (ACQ / "tb" / OBSERVER).read_text()
    for before, after in (("    compare(0);", "    #0; compare(0);"), ("    compare(2);", "    #0; compare(2);")):
        assert old.count(before) == 1
        old = old.replace(before, after, 1)
    assert new == old
    assert new.count("#0.001;") == 2
    assert "actual_view !== original_view || default_view !== original_view" in new
    for path in FAILED.glob("*.v"):
        if (ACQ / path.name).is_file():
            assert path.read_bytes() == (ACQ / path.name).read_bytes()
    assert (ACQ / "tb/starlink_pss_local_admission_actual_checks.svh").read_bytes() == (FAILED / "starlink_pss_local_admission_actual_checks.svh").read_bytes()
    assert (ACQ / "tb/tb_starlink_pss_bank_arithmetic_actual.sv").read_bytes() == (FAILED / "tb_starlink_pss_bank_arithmetic_actual.sv").read_bytes()


def simulate(path, original, copy, observer, fault):
    for name in ("local_admission_original_guard.v", "starlink_pss_realtime_input_guard_local_admission.v"):
        shutil.copy(FAILED / name, path / name)
    shutil.copy(ACQ / "tb" / BENCH, path / BENCH)
    source = old_observer() if observer == "old" else (ACQ / "tb" / OBSERVER).read_text()
    if observer == "old":
        # Diagnostic-only formatting of the failing offline control, never the
        # actual observer. Mixed-X hex nibbles cannot identify differing bits.
        assert source.count("actual=%039h original=%039h default=%039h") == 1
        source = source.replace("actual=%039h original=%039h default=%039h",
                                "actual=%0155b original=%0155b default=%0155b")
    if observer == "post_only":
        source = source.replace("#0; compare(0);", "#0;").replace("#0; compare(2);", "#0;")
    elif observer == "late_pre":
        source = source.replace("#0; compare(0);", "#0.001; compare(0);").replace("#0; compare(2);", "#0.001; compare(2);")
    (path / OBSERVER).write_text(source)
    clean = {k: v for k, v in os.environ.items() if k not in {"LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"}}
    top = "tb_starlink_pss_local_admission_schedule"
    command = ["iverilog", "-g2012", "-s", top, "-o", "model",
               f"-P{top}.ORIGINAL_DUT={original}", f"-P{top}.ACTIVE_COPY={copy}", f"-P{top}.FAULT={fault}"]
    if original:
        command.append("-DORIGINAL_GUARD_DUT")
    command += ["local_admission_original_guard.v", "starlink_pss_realtime_input_guard_local_admission.v", OBSERVER, BENCH]
    compiled = subprocess.run(command, cwd=path, env=clean, capture_output=True, text=True, check=False, timeout=15)
    (path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", "model"], cwd=path, env=clean, capture_output=True, text=True, check=False, timeout=15)
    log = result.stdout + result.stderr
    (path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("original", [0, 1])
@pytest.mark.parametrize("copy", [0, 1])
def test_settled_pre_nba_full_state_equivalence_every_clock_reset_and_unknown_startup(tmp_path, original, copy):
    status, log = simulate(tmp_path, original, copy, "settled", 0)
    assert status == 0 and "LOCAL_SCHEDULE_MODEL_PASS" in log, log
    row = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", log)}
    assert row["clock_events"] == row["pre_checks"] == row["post_checks"]
    assert row["reset_events"] >= 4 and row["nba_checks"] >= 512
    assert row["original"] == original and row["active_copy"] == copy
    assert row["healthy_words"] == 512 and row["unknown_resets"] == 2
    assert row["no_vendor_replay"] == 1


@pytest.mark.parametrize("original", [0, 1])
def test_old_immediate_observer_reproduces_active_alias_failure_with_original_rtl_control(tmp_path, original):
    status, log = simulate(tmp_path, original, 1, "old", 0)
    assert status != 0 and "LOCAL_GUARD_UNCONDITIONAL_STATE_OUTPUT_MISMATCH" in log, log
    assert "phase=0 time=0" in log
    assert "LOCAL_SCHEDULE_MODEL_PASS" not in log
    vectors = dict(re.findall(r"(actual|original|default)=([01xz]{155})", log))
    assert len(vectors) == 3
    assert vectors["original"] == vectors["default"]
    differences = [(154 - i, actual, reference) for i, (actual, reference) in
                   enumerate(zip(vectors["actual"], vectors["original"], strict=True))
                   if actual != reference]
    (tmp_path / "startup_bit_differences.txt").write_text(repr(differences) + "\n")
    assert differences


@pytest.mark.parametrize("original", [0, 1])
@pytest.mark.parametrize("fault", [1, 2, 3, 4])
def test_zero_wait_still_rejects_pre_nba_state_current_fault_public_data_and_reset_corruption(tmp_path, original, fault):
    status, log = simulate(tmp_path, original, 1, "settled", fault)
    assert status != 0 and "LOCAL_GUARD_UNCONDITIONAL_STATE_OUTPUT_MISMATCH" in log, log
    assert "phase=" + ("2" if fault == 4 else "0") in log
    assert "time=0 " not in log
    assert "LOCAL_SCHEDULE_MODEL_PASS" not in log


@pytest.mark.parametrize("observer", ["post_only", "late_pre"])
@pytest.mark.parametrize("fault", [1, 2, 3, 4])
def test_one_edge_witness_would_be_hidden_by_missing_or_post_nba_pre_check_mutants(tmp_path, observer, fault):
    # Positive result is deliberately the BAD observer control. It demonstrates
    # each transient disappears in NBA, so a post-only checker cannot detect it.
    status, log = simulate(tmp_path, 0, 1, observer, fault)
    assert status == 0 and "LOCAL_SCHEDULE_MODEL_PASS" in log, log
    assert f"fault={fault}" in log
