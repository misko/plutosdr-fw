"""Private writes with real mailboxes and the existing immutable guard golden.

These RTL tests do not qualify actual FFT arithmetic, sustained load or timing.
"""
import re
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TB = ACQ / "tb/tb_starlink_pss_realtime_private_bank.sv"


def run_probe(tmp_path, top, parameters=(), mutation=None):
    mailbox = ACQ / "starlink_pss_block_mailbox.v"
    if mutation:
        old, new = mutation
        source = mailbox.read_text()
        assert source.count(old) == 1
        mailbox = tmp_path / "mutated_mailbox.v"
        mailbox.write_text(source.replace(old, new, 1))
    executable = tmp_path / "probe.vvp"
    files = [mailbox, TB]
    if top == "tb_starlink_pss_private_bank_late_ack":
        files += [ACQ / "starlink_pss_realtime_result_guard.v"]
    if top == "tb_starlink_pss_realtime_private_bank":
        files += [
            ACQ / "starlink_pss_realtime_result_guard.v",
            ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v",
            ACQ / "tb/tb_starlink_pss_realtime_result_guard.sv",
            ACQ / "tb/tb_starlink_pss_realtime_result_guard_equivalence.sv",
        ]
    compiled = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable),
        *(f"-P{top}.{name}={value}" for name, value in parameters),
        *map(str, files),
    ], check=False, capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(["vvp", str(executable)], check=False, capture_output=True,
                          text=True, timeout=60)


@pytest.mark.parametrize("half,phase", [(5.0, 1.3), (3.1, 0.7), (6.7, 2.1)])
def test_private_bank_preserves_publication_faults_and_ack(tmp_path, half, phase):
    result = run_probe(tmp_path, "tb_starlink_pss_realtime_private_bank", (
        ("SLOW_HALF_NS", half), ("SLOW_PHASE_NS", phase),
    ))
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    assert "GUARD_FACTORED_EQ_PASS " in text
    assert len(re.findall(r"(?m)^PRIVATE_BANK_PASS healthy=23 rejected=37 "
                         r"independent_resets=12 .* public_golden_and_shadow=1$", text)) == 1


def test_malformed_private_prefix_and_final_never_publish(tmp_path):
    result = run_probe(tmp_path, "tb_starlink_pss_explicit_commit_mailbox")
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    assert text.splitlines().count(
        "EXPLICIT_MAILBOX_PASS healthy=3 malformed=12 held_rewrites=93 real_ram=1"
    ) == 1


@pytest.mark.parametrize("top,marker", [
    ("tb_starlink_pss_private_bank_late_ack",
     "PRIVATE_BANK_LATE_ACK_PASS cases=3 published_words=1536 reset_recovery=2 same_edge_sync_ack=1"),
    ("tb_starlink_pss_explicit_commit_disabled",
     "DISABLED_COMMIT_PASS variants=5 zero_one_x_z_omitted=1 exact_words_each=16 malformed_faults_each=1"),
])
def test_late_ack_quarantine_and_default_inertness(tmp_path, top, marker):
    result = run_probe(tmp_path, top)
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    assert text.splitlines().count(marker) == 1


def test_current_private_link_corruption_vetoes_guard_commit_receipt(tmp_path):
    result = run_probe(tmp_path, "tb_starlink_pss_private_bank_late_ack",
                       (("CORRUPT_LINK", 1),))
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    assert text.splitlines().count(
        "PRIVATE_LINK_FAULT_PASS nonfinal=3 held_final=3 exact_same_edge_reason=01 no_false_commit=1"
    ) == 1


def test_probe_rejects_delayed_private_link_fault_receipt(tmp_path):
    result = run_probe(tmp_path, "tb_starlink_pss_private_bank_late_ack",
                       (("CORRUPT_LINK", 1),), mutation=(
        "assign input_framing_fault_now = EXPLICIT_COMMIT && input_accept && !input_framing_valid;",
        "assign input_framing_fault_now = 1'b0;",
    ))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and "PRIVATE_LINK_CURRENT_FAULT_NOT_VETOED" in text, text
    assert "PRIVATE_LINK_FAULT_PASS " not in text


@pytest.mark.parametrize("value", [-1, 2, 3])
def test_invalid_explicit_commit_parameter_fails_at_time_zero(tmp_path, value):
    result = run_probe(tmp_path, "tb_starlink_pss_explicit_commit_mailbox",
                       (("EXPLICIT_COMMIT", value),))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and "EXPLICIT_COMMIT must be zero or one" in text
    assert "EXPLICIT_MAILBOX_PASS " not in text


@pytest.mark.parametrize("old,new,witness", [
    ("if (!EXPLICIT_COMMIT || input_commit_authorized)", "if (1'b1)",
     "EXPLICIT_MAILBOX_UNAUTHORIZED_FINAL"),
    ("else if (input_accept && write_position != LAST_POSITION)",
     "else if (input_accept)", "EXPLICIT_MAILBOX_UNAUTHORIZED_FINAL"),
    ("if (!input_framing_valid) begin", "if (1'b0) begin",
     "EXPLICIT_MAILBOX_MALFORMED_PUBLISHED"),
])
def test_probe_rejects_early_publication_wrap_and_missing_validation(tmp_path, old, new, witness):
    result = run_probe(tmp_path, "tb_starlink_pss_explicit_commit_mailbox",
                       mutation=(old, new))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and witness in text, text
    assert "EXPLICIT_MAILBOX_PASS " not in text
