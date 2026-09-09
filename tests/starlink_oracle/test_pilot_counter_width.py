"""Execute paired/legacy 30 MS/s counter admission at the 2^32 boundary.

The real acquisition wrapper and DDC are elaborated. Only the unrelated score
engine is stubbed; forced input/output-valid beats accelerate telemetry tests.
This is not a numerical waveform, DMA, or 300-second hardware test.
"""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "hdl/library"


@pytest.mark.parametrize("paired", [0, 1])
def test_actual_paired_counter_width_and_saturation(tmp_path, paired):
    sources = [
        "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        "starlink_pss_acquisition/starlink_pss_x2_ddc.v",
        "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v",
        "axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
        "axi_starlink_pss_acquisition/tb/starlink_pss_iq_to_phase_map_stub.v",
    ]
    executable = tmp_path / "counter.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "pilot_counter_harness",
        "-P", f"pilot_counter_harness.PAIRED={paired}", "-o", str(executable),
        *(str(LIB / source) for source in sources),
        str(Path(__file__).with_name("pilot_counter_harness.sv")),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert f"PILOT_COUNTER_WIDTH_PASS paired={paired}" in result.stdout
