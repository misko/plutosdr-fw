"""Check actual adapter gate equivalence across control and metadata cases."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.mark.parametrize("identity", [0, 1])
def test_factored_output_gate_matches_original(tmp_path, identity):
    executable = tmp_path / "gate.vvp"
    top = "tb_starlink_pss_xfft_output_gate"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.CHECK_IDENTITY={identity}", "-o", str(executable),
        str(ACQ / "starlink_pss_xfft_block_adapter.v"),
        str(ACQ / "tb" / f"{top}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], check=True,
                            capture_output=True, text=True, timeout=60)
    assert (f"XFFT_OUTPUT_GATE_EQUIVALENCE_PASS identity={identity} checked=524288 "
            in result.stdout)
    assert (f"XFFT_INPUT_TRANSPORT_EQUIVALENCE_PASS identity={identity} checked=524288 "
            in result.stdout)
    assert "old_retirement_equal=1 validation_preserved=1" in result.stdout
