"""Speculative descriptor storage never grants admission or publication."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_private_descriptor"
GATE = "if (!active && !awaiting_ack && !protocol_fault && job_valid)"
GOLDEN_SHA256 = "32585046dc3ef0eae35e36acb902d4d512fae44d21d0cdf6784a365f40b049af"
MARKER = (
    "PRIVATE_DESCRIPTOR_PASS idle_rows=2048 fault_rows=2032 speculative_rejections=1023 "
    "current_fault_captures=1016 active_faults=1 reset_challenges=2 healthy_jobs=3 "
    "exact_words=1536 ff4229_public_and_reasons=1"
)


def run_probe(tmp_path, replacement=None):
    guard = ACQ / "starlink_pss_realtime_result_guard.v"
    golden = ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"
    assert hashlib.sha256(golden.read_bytes()).hexdigest() == GOLDEN_SHA256
    source = guard.read_text()
    assert source.count(GATE) == 1
    if replacement:
        guard = tmp_path / "mutated_guard.v"
        guard.write_text(source.replace(GATE, replacement, 1))
    frozen = tmp_path / "frozen_sources"
    frozen.mkdir()
    sources = []
    for path in (guard, golden, ACQ / "tb" / f"{TOP}.sv"):
        copied = frozen / path.name
        copied.write_bytes(path.read_bytes())
        sources.append(copied)
    harness = frozen / Path(__file__).name
    harness.write_bytes(Path(__file__).read_bytes())
    (tmp_path / "source_hashes.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in [*sources, harness]
    ))
    executable = tmp_path / "private-descriptor.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, "-o", str(executable),
        *map(str, sources),
    ], check=False, capture_output=True, text=True, timeout=30)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "private-descriptor.log").write_text(result.stdout + result.stderr)
    return result


def test_private_descriptor_exact_admission_ownership_and_reset(tmp_path):
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count(MARKER) == 1


@pytest.mark.parametrize("replacement,witness", [
    ("if (job_accept)", "DESC_IDLE_CAPTURE"),
    (GATE[:-1] + " && !fault_now)", "DESC_IDLE_CAPTURE"),
    ("if (!awaiting_ack && !protocol_fault && job_valid)", "DESC_OWNERSHIP_HOLD"),
    ("if (!active && !protocol_fault && job_valid)", "DESC_OWNERSHIP_HOLD"),
    ("if (!active && !awaiting_ack && job_valid)", "DESC_OWNERSHIP_HOLD"),
    ("if (!active && !awaiting_ack && !protocol_fault)", "DESC_IDLE_CAPTURE"),
])
def test_descriptor_probe_rejects_recoupled_or_missing_ownership_gates(tmp_path, replacement, witness):
    result = run_probe(tmp_path, replacement)
    text = result.stdout + result.stderr
    assert result.returncode != 0 and witness in text, text
    assert MARKER not in text
