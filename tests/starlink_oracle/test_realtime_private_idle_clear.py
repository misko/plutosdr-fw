"""Reachable private idle clearing plus immutable public golden equivalence."""

import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_private_idle_clear"


def run_probe(tmp_path, *, mutate=False):
    guard = ACQ / "starlink_pss_realtime_result_guard.v"
    if mutate:
        source = guard.read_text()
        before = "if (!active && !protocol_fault) begin"
        assert source.count(before) == 1
        guard = tmp_path / "mutant.v"
        guard.write_text(source.replace(before, "if (job_accept) begin", 1))
    executable = tmp_path / "idle-clear.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, "-o", str(executable), str(guard),
        str(ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"),
        str(ACQ / "tb/tb_starlink_pss_realtime_private_observations.sv"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return subprocess.run(["vvp", str(executable)], text=True, capture_output=True,
                          timeout=30, check=False)


@pytest.mark.parametrize("mutate", [False, True])
def test_idle_clearing_has_reachable_ack_witness_and_preserves_public_behavior(tmp_path, mutate):
    result = run_probe(tmp_path, mutate=mutate)
    output = result.stdout + result.stderr
    if mutate:
        assert result.returncode != 0 and "PRIVATE_IDLE_CLEAR_MISSING" in output, output
    else:
        assert result.returncode == 0 and "ERROR" not in output and "FATAL" not in output, output
        assert output.count("PRIVATE_IDLE_CLEAR_ACK_WITNESS") == 1, output
        assert "PRIVATE_OBSERVATIONS_PASS" in output, output
