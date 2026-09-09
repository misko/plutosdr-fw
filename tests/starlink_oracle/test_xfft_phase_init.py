"""Exercise real adapter job initialization with and without identity checking."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.mark.parametrize("identity", [0, 1])
def test_output_position_is_clear_before_next_input(tmp_path, identity):
    (tmp_path / "build").mkdir()
    executable = tmp_path / "phase-init.vvp"
    top = "tb_starlink_pss_xfft_block_adapter"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.CHECK_IDENTITY={identity}", "-o", str(executable),
        str(ACQ / "starlink_pss_xfft_block_adapter.v"),
        str(ACQ / "tb" / f"{top}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path,
                            check=True, capture_output=True, text=True, timeout=60)
    assert (f"XFFT_PHASE_INIT_INVARIANT_PASS identity={identity} healthy_blocks=2 "
            "reset_between_blocks=0" in result.stdout)
    assert "XFFT_ADAPTER_PASS" in result.stdout
