"""Final-only authorization: exact additive delta and adversarial output check.

The actual FFT service and guard/mailbox structural measurement are separate.
No radio, throughput, or timing qualification is inferred from these tests.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle import test_realtime_private_bank as private_bank
from tests.starlink_oracle.completed_input_contract import (
    restore_default_completed_input_guard,
)
from tests.starlink_oracle.mailbox_metadata_contract import (
    restore_legacy_metadata_comparison,
)

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "ccdf64365e8145113115f2e933ee8b2901f6d3e0"


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def baseline(name):
    result = subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/{name}.v"],
        text=True, capture_output=True, timeout=10, check=True)
    return tokens(result.stdout)


def replace_once(source, old, new):
    assert source.count(old) == 1
    return source.replace(old, new, 1)


def test_guard_delta_is_only_final_qualification_export_and_exact_handshake():
    name = "starlink_pss_realtime_result_guard"
    source = restore_default_completed_input_guard((ACQ / f"{name}.v").read_text())
    source = replace_once(source, "outputwiremailbox_commit_valid,", "")
    source = replace_once(source,
        ("assignmailbox_commit_valid=resetn&&active&&!protocol_fault&&return_valid&&"
         "return_last&&final_qualified&&!final_fault_now;"
         "wirefinal_commit=mailbox_commit_valid&&mailbox_input_ready;"),
        ("wirefinal_commit=resetn&&active&&!protocol_fault&&return_valid&&return_last&&"
         "final_qualified&&!final_fault_now&&mailbox_input_ready;"))
    assert source == baseline(name)


def test_service_delta_is_only_final_authorization_and_mailbox_retains_its_contract():
    name = "starlink_pss_shared_realtime_xfft_service"
    source = tokens((ACQ / f"{name}.v").read_text())
    source = replace_once(source,
        "wirereturn_valid,return_private_valid,return_commit_valid,return_last;",
        "wirereturn_valid,return_private_valid,return_last;")
    source = replace_once(source, ".mailbox_commit_valid(return_commit_valid),", "")
    source = replace_once(source, ".input_commit_authorized(return_commit_valid),",
        ".input_commit_authorized(return_valid),")
    assert source == baseline(name)
    name = "starlink_pss_block_mailbox"
    assert tokens(restore_legacy_metadata_comparison((ACQ / f"{name}.v").read_text())) == baseline(name)


@pytest.mark.parametrize("mutation", [False, True])
@pytest.mark.parametrize("completed", [0, 1])
def test_new_output_is_subject_to_all_existing_final_veto_rows(tmp_path, mutation, completed):
    top = "tb_starlink_pss_realtime_final_veto_equivalence"
    source = (ACQ / "starlink_pss_realtime_result_guard.v").read_text()
    if mutation:
        source = replace_once(source,
            "return_phase_allowed && return_last && final_qualified && !final_public_fault;",
            "return_phase_allowed && return_last && final_qualified;")
    runtime = tmp_path / "guard.v"
    runtime.write_text(source)
    bench_source = (ACQ / "tb" / f"{top}.sv").read_text()
    if completed:
        # Full-tuple algebraic adapter, not a claim that injected input events
        # satisfy the bank slice's closed-input producer premise. Both wrapper
        # scheduling modes use this same enabled final-public veto; actual-core
        # suites independently check that producer premise and scheduling.
        bench_source = replace_once(bench_source,
            "wire completed_input_certified = 1'bz, completed_input_fault_now = 1'bz;",
            "wire completed_input_certified = 1'b1;\n"
            "wire completed_input_fault_now = external_fault_now || "
            "certified_input_beat || certified_input_complete;")
        bench_source = replace_once(bench_source,
            "#(.WATCHDOG_CYCLES(WATCHDOG_CYCLES)) dut",
            "#(.WATCHDOG_CYCLES(WATCHDOG_CYCLES), .USE_COMPLETED_INPUT_FAULT(1)) dut")
    bench = tmp_path / f"{top}.sv"
    bench.write_text(bench_source)
    executable = tmp_path / "final_auth.vvp"
    compiled = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        "-o", str(executable), str(runtime), str(bench)],
        text=True, capture_output=True, timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], text=True, capture_output=True,
        timeout=60, check=False)
    (tmp_path / "final_auth.log").write_text(result.stdout + result.stderr)
    if mutation:
        assert result.returncode != 0 and "FINAL_AUTH_VETO_MISMATCH" in result.stdout
        assert "FINAL_VETO_EQ_PASS" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.splitlines().count(
            "FINAL_VETO_EQ_PASS watchdog=5 rows=262656 edges=512 mutation_witnesses=9 "
            "boundaries=10 reset=1 quarantined_rows=131072") == 1


@pytest.mark.parametrize("half,phase", [(5.0, 1.3), (3.1, 0.7), (6.7, 2.1)])
def test_final_authorization_with_real_mailbox_and_frozen_public_shadow(tmp_path, monkeypatch, half, phase):
    # Select the actual new guard output in a private copy of the existing
    # adversarial bench. The legacy mailbox shadow and golden guard stay intact.
    source = private_bank.TB.read_text()
    source = replace_once(source,
        "wire commit_drive = probe.stimulus.guard_valid;",
        "wire commit_drive = probe.stimulus.dut.mailbox_commit_valid;")
    bench = tmp_path / "final_auth_private_bank.sv"
    bench.write_text(source)
    monkeypatch.setattr(private_bank, "TB", bench)
    result = private_bank.run_probe(tmp_path, "tb_starlink_pss_realtime_private_bank",
        (("SLOW_HALF_NS", half), ("SLOW_PHASE_NS", phase)))
    transcript = result.stdout + result.stderr
    (tmp_path / "final_auth_private_bank.log").write_text(transcript)
    assert result.returncode == 0, transcript
    assert "GUARD_FACTORED_EQ_PASS " in transcript
    assert len(re.findall(r"(?m)^PRIVATE_BANK_PASS healthy=23 rejected=37 "
        r"independent_resets=12 .* public_golden_and_shadow=1$", transcript)) == 1


@pytest.mark.parametrize("corrupt", [0, 1])
def test_final_authorization_preserves_late_ack_and_private_link_corruption_veto(tmp_path, monkeypatch, corrupt):
    source = private_bank.TB.read_text()
    source = replace_once(source,
        ".input_commit_authorized(valid), .input_ready(ready), .input_fault(fault),",
        ".input_commit_authorized(guard.mailbox_commit_valid), .input_ready(ready), .input_fault(fault),")
    bench = tmp_path / "final_auth_late_ack.sv"
    bench.write_text(source)
    monkeypatch.setattr(private_bank, "TB", bench)
    result = private_bank.run_probe(tmp_path, "tb_starlink_pss_private_bank_late_ack",
        (("CORRUPT_LINK", corrupt),))
    transcript = result.stdout + result.stderr
    (tmp_path / "final_auth_late_ack.log").write_text(transcript)
    assert result.returncode == 0, transcript
    marker = ("PRIVATE_LINK_FAULT_PASS nonfinal=3 held_final=3 exact_same_edge_reason=01 no_false_commit=1"
        if corrupt else "PRIVATE_BANK_LATE_ACK_PASS cases=3 published_words=1536 reset_recovery=2 same_edge_sync_ack=1")
    assert transcript.splitlines().count(marker) == 1
