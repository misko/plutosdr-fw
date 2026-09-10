"""Opt-in completed-input phase equivalence, not FFT numerical or RF proof."""
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_completed_input_fence"


@pytest.mark.parametrize("mutation", [0, 1])
def test_completed_input_fence_and_duplicate_mutation(tmp_path, mutation):
    executable = tmp_path / "completed.vvp"
    compile_result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.MUTATE_DUPLICATE={mutation}", "-o", str(executable),
        str(ACQ / "starlink_pss_realtime_input_guard.v"),
        str(ACQ / "starlink_pss_realtime_result_guard.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                            timeout=60, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if mutation:
        assert result.returncode != 0, log
        assert "COMPLETED_INPUT_EQ_MISMATCH phase=2 kind=0" in log, log
        assert "COMPLETED_INPUT_FENCE_PASS" not in log
    else:
        assert result.returncode == 0, log
        assert "COMPLETED_INPUT_FENCE_PASS healthy=4 rejected=26 simultaneous_edges=1" in log
        assert "commits=3" in log
