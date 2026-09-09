"""Actual AXI/core stop transactions; no Linux, physical timing, or RF claims."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl"))) / "library"


@pytest.mark.parametrize("enabled,shared,rate,allowed", [
    (1, 1, 15, True), (0, 1, 15, True), (0, 0, 15, True),
    (0, 0, 30, True), (0, 0, 60, True), (1, 0, 15, False),
    (1, 1, 30, False), (1, 1, 60, False), (2, 1, 15, False),
])
@pytest.mark.parametrize("health_summary", [0, 1])
def test_actual_psma_stop_transactions(tmp_path, enabled, shared, rate, allowed, health_summary):
    top = "tb_axi_starlink_pss_map_stop"
    executable = tmp_path / "psma-stop.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.ENABLE_BOUNDARY_STOP={enabled}",
        f"-P{top}.USE_SHARED_XFFT={shared}", f"-P{top}.INPUT_RATE_MSPS={rate}",
        f"-P{top}.HEALTH_COUNTERS_FROM_FLAGS={health_summary}",
        "-o", str(executable),
        str(HDL / "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_map_stop.sv"),
        str(HDL / "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"),
        str(HDL / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"),
        str(HDL / "starlink_pss_acquisition/starlink_pss_phase_map.v"),
        str(HDL / "starlink_pss_acquisition/starlink_pss_phase_map_bank.v"),
        str(HDL / "starlink_pss_acquisition/starlink_pss_acquisition_health.v"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path,
                            check=False, capture_output=True, text=True, timeout=30)
    (tmp_path / "psma-stop.log").write_text(result.stdout + result.stderr)
    if not allowed:
        assert result.returncode != 0 and "FATAL:" in result.stdout
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert (f"PSMA_STOP_PASS enabled={enabled} shared={shared} rate={rate} "
            "actual_core=1 actual_axi=1 no_radio_claim=1") in result.stdout
    if enabled:
        assert (f"PSMA_STOP_HEALTH_PASS summary={health_summary} real_causes=5 "
                f"generic_counter_fallback={1 - health_summary}") in result.stdout


def test_real_stop_wiring_preserves_independent_canonical_tap(tmp_path):
    executable = tmp_path / "stop-wiring.vvp"
    sources = [
        "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_stop_wiring.sv",
        "axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
        "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v",
        "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        "starlink_pss_acquisition/starlink_pss_iq_to_phase_map.v",
        "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        "starlink_pss_acquisition/starlink_pss_score_phase_tagger.v",
        "starlink_pss_acquisition/starlink_pss_acquisition_health.v",
        "starlink_pss_acquisition/starlink_pss_phase_map.v",
        "starlink_pss_acquisition/starlink_pss_phase_map_bank.v",
    ]
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_axi_starlink_pss_stop_wiring",
        "-o", str(executable), *[str(HDL / source) for source in sources],
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "stop-wiring.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("PSMA_STOP_WIRING_PASS real_shell=1 real_iq_to_map=1 real_map=1 real_cdc=1 "
            "canonical_after_stop=1 fft_score_stub=1 no_pilot_capture_or_rf_claim=1") in result.stdout
