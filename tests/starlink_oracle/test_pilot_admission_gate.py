"""Compare factored PIL1 admission with the original actual RTL expressions."""
from pathlib import Path
import shutil
import subprocess

LIB = Path(__file__).resolve().parents[2] / "hdl/library"


def test_active_admission_gate_matches_original(tmp_path):
    top = "tb_starlink_pilot_admission_gate"
    executable = tmp_path / "gate.vvp"
    files = [LIB / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
             LIB / f"axi_starlink_pilot_capture/tb/{top}.sv",
             LIB / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"]
    files += [LIB / "starlink_pss_acquisition" / name for name in
              ("starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v")]
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable),
                    *map(str, files)], check=True, capture_output=True, text=True, timeout=30)
    for name in ("pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"):
        shutil.copyfile(LIB / "starlink_pss_acquisition" / name, tmp_path / name)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=True,
                            capture_output=True, text=True, timeout=60)
    assert "PILOT_ADMISSION_GATE_EQUIVALENCE_PASS checked=262144 " in result.stdout
