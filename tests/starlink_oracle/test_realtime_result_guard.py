"""Isolated realtime result guard + real mailbox; not FFT/service qualification."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_result_guard"


@pytest.mark.parametrize("slow_half,phase", [(5.0, 1.3), (3.1, 0.7), (6.7, 2.1)])
def test_private_result_publication_and_final_fault_fence(tmp_path, slow_half, phase):
    executable = tmp_path / "result_guard.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.SLOW_HALF_NS={slow_half}", f"-P{TOP}.SLOW_PHASE_NS={phase}",
        "-o", str(executable), str(ACQ / "starlink_pss_realtime_result_guard.v"),
        str(ACQ / "starlink_pss_block_mailbox.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REALTIME_RESULT_GUARD_PASS healthy=23 rejected=37 independent_resets=12 " in result.stdout
    assert "private_words=511 held_slots=1 real_mailbox=1 ack_reuse=2 isolated_only=1" in result.stdout
