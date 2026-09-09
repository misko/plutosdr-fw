"""Execute optional map-core publication fencing; no wrapper/IIO/RF claims."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl"))
LIB = HDL / "library/starlink_pss_acquisition"
STOP_TB = LIB / "tb/tb_starlink_pss_phase_map_stop.sv"
SOURCES = [LIB / "starlink_pss_phase_map.v", LIB / "starlink_pss_phase_map_bank.v"]


def _run(tmp_path, top, *arguments):
    executable = tmp_path / "map_stop.vvp"
    (tmp_path / "build").mkdir()
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable),
        *map(str, arguments), *map(str, SOURCES),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=True,
                            capture_output=True, text=True, timeout=30)
    assert "FAIL" not in result.stdout
    return result.stdout


@pytest.mark.parametrize("bins,frames", [(4, 2), (8, 4), (16, 4)])
def test_optional_core_boundary_stop(tmp_path, bins, frames):
    output = _run(tmp_path, "tb_starlink_pss_phase_map_stop",
                  f"-Ptb_starlink_pss_phase_map_stop.BINS={bins}",
                  f"-Ptb_starlink_pss_phase_map_stop.FRAMES={frames}", STOP_TB)
    assert (f"MAP_STOP_PASS bins={bins} frames={frames} cuts={bins * frames + 1} "
            "core_only=1 no_radio_claim=1") in output


def test_unchanged_legacy_map_with_unconnected_stop_ports(tmp_path):
    output = _run(tmp_path, "tb_starlink_pss_phase_map",
                  "-s", "legacy_map_stop_monitor", STOP_TB,
                  LIB / "tb/tb_starlink_pss_phase_map.sv")
    assert "PHASE_MAP_PASS bins=8 frames=4 ping_pong=1 complete_only=1" in output
    assert "LEGACY_STOP_INERT_PASS omitted_z=1 forced_x=1 forced_one=1" in output


def test_enabled_stop_with_production_segmented_geometry(tmp_path):
    executable = tmp_path / "production-stop.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pss_phase_map_stop_production",
        "-o", str(executable), *map(str, SOURCES),
        str(LIB / "tb/tb_starlink_pss_phase_map_stop_production.sv"),
    ], check=True, capture_output=True, text=True, timeout=30)
    profile = HDL / "library/axi_starlink_pss_periodic_injector/tb/m2_period_scores_u8.mem"
    result = subprocess.run(["vvp", str(executable), f"+profile={profile}"],
                            cwd=tmp_path, check=False, capture_output=True,
                            text=True, timeout=120)
    (tmp_path / "production-stop.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MAP_STOP_PRODUCTION_FAIL" not in result.stdout
    assert ("MAP_STOP_PRODUCTION_PASS bins=20000 frames=64 segments_per_bank=10 "
            "request_position=640013 exact_words=20000 accepted=1280000 ") in result.stdout
    assert "generation=1 start=00000001fff80000 end=00000002000b8800" in result.stdout
    assert "peak_phase=7311 core_only=1 no_radio_claim=1" in result.stdout
