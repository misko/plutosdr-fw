"""Actual PIL1 output-stage alignment and adversarial termination edges."""
from pathlib import Path
import shutil
import subprocess


def test_registered_observation_and_same_edge_termination(tmp_path):
    library = Path(__file__).resolve().parents[2] / "hdl/library"
    top = "tb_starlink_pilot_output_stage"
    sources = [
        library / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
        library / f"axi_starlink_pilot_capture/tb/{top}.sv",
        library / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        *(library / "starlink_pss_acquisition" / name for name in (
            "starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v")),
    ]
    executable = tmp_path / "stage.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable),
                    *map(str, sources)], check=True, capture_output=True, text=True, timeout=60)
    for name in ("pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"):
        shutil.copyfile(library / "starlink_pss_acquisition" / name, tmp_path / name)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=True,
                            capture_output=True, text=True, timeout=30)
    assert "PILOT_OUTPUT_STAGE_PASS cases=20 latency_clocks=1" in result.stdout.splitlines()
