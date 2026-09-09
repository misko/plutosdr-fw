"""Execute quiescent CLEAR admission/commit races through the actual AXI RTL."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("scenario", range(11), ids=[
    "common-reset-edge", "inactive-source-cancellation", "inactive-ddc-halt-and-token",
    "active-rejection", "stalled-promise-rejection", "same-edge-last-pop-rejection",
    "preceding-last-pop-acceptance", "reset-between-admission-and-commit",
    "independent-read-before-ack", "bvalid-stall-and-next-payload", "stop-clear-arm",
])
def test_registered_clear_transaction(tmp_path, scenario):
    library = Path(__file__).resolve().parents[2] / "hdl/library"
    top = "tb_starlink_pilot_clear_commit"
    sources = [
        library / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
        library / f"axi_starlink_pilot_capture/tb/{top}.sv",
        library / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        *(library / "starlink_pss_acquisition" / name for name in (
            "starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v")),
    ]
    executable = tmp_path / "clear.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
                    "-P", f"{top}.SCENARIO={scenario}", "-o", str(executable),
                    *map(str, sources)], check=True, capture_output=True, text=True, timeout=60)
    for name in ("pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"):
        shutil.copyfile(library / "starlink_pss_acquisition" / name, tmp_path / name)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=True,
                            capture_output=True, text=True, timeout=30)
    assert result.stdout.splitlines() == [f"PILOT_CLEAR_COMMIT_PASS scenario={scenario}"]
