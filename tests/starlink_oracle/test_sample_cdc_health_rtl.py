"""Actual ingress RTL: unchanged same-cycle overflow flag and FIFO transport."""

from pathlib import Path
import subprocess

import pytest


RTL = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.mark.parametrize("depth_bits", [2, 7])
def test_sample_fifo_overflow_reset_and_gap_recovery(tmp_path, depth_bits):
    top = "tb_starlink_pss_sample_cdc"
    output = _run(tmp_path, top, [f"-P{top}.FIFO_ADDRESS_WIDTH={depth_bits}"])
    assert "SAMPLE_CDC_PASS" in output
    assert f"fifo_depth={1 << depth_bits} drops=6" in output
    assert "independent_reset_purge=2 gap_recovery=1" in output


def test_destination_overflow_is_exactly_same_edge_as_counter(tmp_path):
    output = _run(tmp_path, "tb_starlink_pss_sample_cdc_health", [])
    assert "SAMPLE_CDC_HEALTH_PASS words=8324 same_edge=1 independent_resets=2" in output


def _run(directory, top, parameters):
    executable = directory / "cdc.vvp"
    (directory / "build").mkdir()
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top, *parameters,
        "-o", str(executable), str(RTL / "starlink_pss_sample_cdc.v"),
        str(RTL / "tb" / f"{top}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=directory,
                            check=True, capture_output=True, text=True, timeout=30)
    return result.stdout
