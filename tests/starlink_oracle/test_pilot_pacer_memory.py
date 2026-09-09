"""Pacer RAM storage equivalence; full receiver proves actual block-RAM mapping."""
from pathlib import Path
import subprocess

import pytest

RTL = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pilot_pacer_memory"


@pytest.mark.parametrize("address_width", [2, 7, 10])
def test_synchronous_read_first_and_disabled_read_hold(tmp_path, address_width):
    executable = tmp_path / "memory.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.ADDRESS_WIDTH={address_width}", "-o", str(executable),
        str(RTL / "starlink_pilot_ddc.v"), str(RTL / "tb" / f"{TOP}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    depth = 1 << address_width
    assert f"PILOT_PACER_MEMORY_PASS depth={depth} reads={depth * 12} held={depth * 4}" in result.stdout
    assert "collision_read_first=1 latency_cycles=1" in result.stdout
