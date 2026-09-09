"""Isolated immediate delivery checker, not an integrated FFT-service proof."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_input_guard"


@pytest.mark.parametrize("identity,healthy,rejected", [(0, 5, 22), (1, 4, 26)])
def test_exact_input_certificates_and_immediate_starvation(tmp_path, identity, healthy, rejected):
    executable = tmp_path / "input_guard.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.CHECK_IDENTITY={identity}", "-o", str(executable),
        str(ACQ / "starlink_pss_realtime_input_guard.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"identity={identity} healthy={healthy} rejected={rejected}" in result.stdout
    assert "source_demand_checked=1 production_connected=0" in result.stdout
