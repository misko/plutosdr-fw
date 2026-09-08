import subprocess

import pytest

from .ddc import BANK_ROOT


@pytest.mark.parametrize("bits", [2, 7])
def test_data_phase_gap_overflow_and_independent_reset_purge(bits, tmp_path):
    top = "tb_starlink_glrt_sample_cdc"
    executable = tmp_path/"sim"
    built = subprocess.run(["iverilog", "-g2012", "-s", top, "-o", str(executable),
                            f"-P{top}.FIFO_ADDRESS_WIDTH={bits}",
                            str(BANK_ROOT/"tb"/f"{top}.sv"), str(BANK_ROOT/"starlink_glrt_sample_cdc.v")],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stdout+built.stderr
    process = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stdout+process.stderr
    assert "SAMPLE_CDC_PASS" in process.stdout
    assert f"fifo_depth={1 << bits} drops=6 independent_reset_purge=2 gap_recovery=1" in process.stdout
