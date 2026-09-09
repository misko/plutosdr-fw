"""Differentially check private counter timing optimization against default RTL."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.mark.parametrize("identity", [0, 1])
def test_raw_counter_preserves_public_contract(tmp_path, identity):
    top = "tb_starlink_pss_xfft_counter_cut"
    executable = tmp_path / "counter-cut.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.CHECK_IDENTITY={identity}", "-o", str(executable),
        str(ACQ / "starlink_pss_xfft_block_adapter.v"),
        str(ACQ / "tb" / f"{top}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path,
                            check=True, capture_output=True, text=True, timeout=60)
    assert (f"XFFT_COUNTER_CUT_PASS identity={identity} fault_cases=30 "
            "speculative_advances=30" in result.stdout)
    assert "public_interface_equivalent=1 healthy_shadow_counter=1" in result.stdout
