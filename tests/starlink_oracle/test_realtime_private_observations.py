"""Fault-edge private state is observable only in tests, never publication."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_private_observations"
MARKER = (
    "PRIVATE_OBSERVATIONS_PASS fault_edges=10 fields_witnessed=7 quarantine_rows=1408 "
    "idle_orphans=1 reset_epochs=22 healthy_jobs=11 exact_words=5632 ff4229_public_and_reasons=1"
)


def run_probe(tmp_path, mutation=None):
    guard = ACQ / "starlink_pss_realtime_result_guard.v"
    if mutation:
        old, new = mutation
        source = guard.read_text()
        assert source.count(old) == 1
        guard = tmp_path / "mutated_guard.v"
        guard.write_text(source.replace(old, new, 1))
    frozen = tmp_path / "frozen_sources"
    frozen.mkdir()
    sources = []
    for path in (guard, ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v",
                 ACQ / "tb" / f"{TOP}.sv"):
        copied = frozen / path.name
        copied.write_bytes(path.read_bytes())
        sources.append(copied)
    (tmp_path / "source_hashes.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in sources
    ))
    executable = tmp_path / "private-observations.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, "-o", str(executable),
        *map(str, sources),
    ], check=False, capture_output=True, text=True, timeout=30)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "private-observations.log").write_text(result.stdout + result.stderr)
    return result


def test_private_capture_exact_quarantine_and_reset_reuse(tmp_path):
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count(MARKER) == 1


@pytest.mark.parametrize("old,new,witness", [
    ("if (active && !protocol_fault) begin", "if (active && !protocol_fault && !fault_now) begin",
     "OBS_FAULT_CAPTURE_MISSING"),
    ("if (active && !protocol_fault) begin", "if (!protocol_fault) begin", "OBS_IDLE_CAPTURE"),
    ("if (protocol_fault || fault_now) begin", "if (protocol_fault) begin", "OBS_PUBLIC_EQ"),
])
def test_probe_rejects_capture_and_quarantine_regressions(tmp_path, old, new, witness):
    result = run_probe(tmp_path, (old, new))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and witness in text, text
    assert MARKER not in text
