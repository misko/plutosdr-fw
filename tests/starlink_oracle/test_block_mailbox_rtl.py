"""Real dual-clock transform mailbox: ordering, stalls, commit, faults, resets.

This simulation does not qualify physical CDC constraints or a shared FFT.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
RTL = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_block_mailbox"


@pytest.mark.parametrize("address_width", [2, 3, 9])
@pytest.mark.parametrize("metadata_width", [70, 75])
@pytest.mark.parametrize("external_reset,input_extra,output_extra", [
    (0, 0, 0), (1, 0, 0), (1, 2, 0), (1, 0, 2),
])
@pytest.mark.parametrize("input_half,output_half,phase", [
    (5.0, 2.5, 0.7), (2.5, 5.0, 1.3), (5.0, 6.7, 2.1), (5.0, 5.0, 0.0),
])
def test_complete_blocks_only_across_clocks_and_resets(
        tmp_path, address_width, metadata_width, input_half, output_half, phase,
        external_reset, input_extra, output_extra):
    assert shutil.which("iverilog") and shutil.which("vvp")
    executable = tmp_path / "mailbox.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.ADDRESS_WIDTH={address_width}",
        f"-P{TOP}.METADATA_WIDTH={metadata_width}",
        f"-P{TOP}.RESET_RELEASE_EXTERNAL={external_reset}",
        f"-P{TOP}.INPUT_RELEASE_EXTRA_CYCLES={input_extra}",
        f"-P{TOP}.OUTPUT_RELEASE_EXTRA_CYCLES={output_extra}",
        f"-P{TOP}.INPUT_HALF_NS={input_half}",
        f"-P{TOP}.OUTPUT_HALF_NS={output_half}",
        f"-P{TOP}.OUTPUT_PHASE_NS={phase}",
        "-o", str(executable), str(RTL / "starlink_pss_block_mailbox.v"),
        str(RTL / "tb" / f"{TOP}.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert f"BLOCK_MAILBOX_PASS depth={1 << address_width} blocks=18 " in result.stdout
    assert f"words={18 << address_width} " in result.stdout
    assert "framing_faults=4 independent_resets=10 mid_read_resets=2" in result.stdout
    assert (f"external_reset={external_reset} release_skew_in={input_extra} "
            f"release_skew_out={output_extra}") in result.stdout
