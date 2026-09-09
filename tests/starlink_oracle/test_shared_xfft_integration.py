"""Executable opt-in policy and PSMA health/ABI checks, not full fit evidence."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = ROOT / "hdl"


def _board_admission(fields):
    # Execute the actual independent pre-mutation BD admission. The former
    # mid-file inline validator moved into the shared pure policy helper.
    # Full BD parameter/readback execution is covered separately by the
    # boundary build-option tests; this retains every original case below.
    source = (HDL / "projects/pluto/system_bd.tcl").read_text()
    policy = source[:source.index("# Add custom repo")]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("STARLINK_PSS_")}
    environment.update({key: str(value) for key, value in fields.items() if value is not None})
    script = f"if {{[catch {{\n{policy}}} message]}} {{puts stderr $message; exit 2}}\n"
    script += 'puts "$starlink_pss_shared_xfft $starlink_pss_realtime_xfft"\n'
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          env=environment, cwd=HDL / "projects/pluto", timeout=10, check=False)


@pytest.mark.parametrize("profile,rate,choice,allowed", [
    ("paired-pilot", 15, None, True), ("paired-pilot", 15, "0", True),
    ("paired-pilot", 15, "1", True), ("paired-pilot", 30, "1", False),
    ("paired-pilot", 60, "1", False), ("full", 15, "1", False),
    ("detector-only", 15, "1", False), ("acquisition-only", 15, "1", False),
    ("paired-pilot", 15, "2", False), ("paired-pilot", 15, "1.0", False),
    ("paired-pilot", 15, "true", False), ("full", 60, "0", True),
])
def test_shared_clock_is_explicit_and_bounded(profile, rate, choice, allowed):
    result = _board_admission({"STARLINK_PSS_PROFILE": profile, "STARLINK_PSS_RATE_MSPS": rate,
                               "STARLINK_PSS_SHARED_XFFT": choice})
    if allowed:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f'{choice or "0"} 0'
    else:
        assert result.returncode == 2 and ("shared-XFFT" in result.stderr or
                                          "STARLINK_PSS_SHARED_XFFT" in result.stderr)


def _simulate(tmp_path, top, sources, parameters):
    executable = tmp_path / "test.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
                    *[f"-P{top}.{key}={value}" for key, value in parameters.items()],
                    "-o", str(executable), *map(str, sources)],
                   text=True, capture_output=True, check=True, timeout=30)
    (tmp_path / "build").mkdir(exist_ok=True)
    return subprocess.run(["vvp", str(executable)], cwd=tmp_path, text=True,
                          capture_output=True, timeout=30, check=False)


@pytest.mark.parametrize("shared", [0, 1])
def test_service_fault_has_distinct_sticky_health_identity(tmp_path, shared):
    acq = HDL / "library/starlink_pss_acquisition"
    result = _simulate(tmp_path, "tb_starlink_pss_acquisition_health", [
        acq / "starlink_pss_acquisition_health.v",
        acq / "tb/tb_starlink_pss_acquisition_health.sv",
    ], {"USE_SHARED_XFFT": shared})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ACQUISITION_HEALTH_PASS" in result.stdout
    assert f"shared_xfft={shared}" in result.stdout


@pytest.mark.parametrize("rate,shared,allowed", [
    (15, 1, True), (30, 1, False), (60, 1, False), (15, 2, False),
    (15, 0, True), (30, 0, True), (60, 0, True),
])
def test_shared_abi_is_explicit_and_old_versions_unchanged(tmp_path, rate, shared, allowed):
    acq = HDL / "library/axi_starlink_pss_acquisition"
    result = _simulate(tmp_path, "tb_axi_starlink_pss_phase_map_sync_rate", [
        HDL / "library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        acq / "axi_starlink_pss_phase_map_sync.v",
        acq / "tb/tb_axi_starlink_pss_phase_map_sync_rate.sv",
    ], {"INPUT_RATE_MSPS": rate, "USE_SHARED_XFFT": shared})
    if allowed:
        assert result.returncode == 0, result.stdout + result.stderr
        version = "1.5" if shared else {15: "1.1", 30: "1.2", 60: "1.4"}[rate]
        assert f"PSMA_RATE_PASS rate={rate} version={version}" in result.stdout
    else:
        assert result.returncode != 0 and "FATAL:" in result.stdout


def test_real_clock_connections_and_packaged_sources_are_present():
    board = (HDL / "projects/pluto/system_bd.tcl").read_text()
    packager = (HDL / "library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition_ip.tcl").read_text()
    assert "CONFIG.USE_SHARED_XFFT $starlink_pss_shared_xfft" in board
    assert "ad_connect sys_200m_clk starlink_pss_acquisition/fft_clk" in board
    assert "ad_connect sys_cpu_resetn starlink_pss_acquisition/fft_resetn" in board
    for name in ("starlink_pss_iq_to_score_shared.v", "starlink_pss_block_mailbox.v",
                 "starlink_pss_shared_xfft_service.v", "starlink_pss_shared_xfft_constr.xdc"):
        assert f'"$acq_dir/{name}"' in packager
    assert "PROCESSING_ORDER LATE" in packager


@pytest.mark.parametrize("profile,rate,shared,realtime,allowed", [
    ("paired-pilot", 15, "1", None, True),
    ("paired-pilot", 15, "1", "0", True),
    ("paired-pilot", 15, "1", "1", True),
    ("paired-pilot", 15, "0", "1", False),
    ("paired-pilot", 30, "1", "1", False),
    ("paired-pilot", 60, "1", "1", False),
    ("full", 15, "1", "1", False),
    ("detector-only", 15, "1", "1", False),
    ("acquisition-only", 15, "0", "1", False),
    ("paired-pilot", 15, "1", "2", False),
    ("paired-pilot", 15, "1", "1.0", False),
    ("paired-pilot", 15, "1", "true", False),
    ("full", 60, "0", "0", True),
])
def test_realtime_board_selector_is_additive_and_restricted(profile, rate, shared, realtime, allowed):
    result = _board_admission({"STARLINK_PSS_PROFILE": profile, "STARLINK_PSS_RATE_MSPS": rate,
                               "STARLINK_PSS_SHARED_XFFT": shared,
                               "STARLINK_PSS_REALTIME_XFFT": realtime})
    assert result.returncode == (0 if allowed else 2), result.stdout + result.stderr
    if allowed:
        assert result.stdout.strip() == f'{shared} {realtime or "0"}'


@pytest.mark.parametrize("rate,shared,pilot,realtime,allowed", [
    (15, 1, 1, 1, True), (15, 1, 1, 0, True), (15, 0, 0, 0, True),
    (30, 0, 0, 0, True), (60, 0, 0, 0, True), (15, 0, 1, 1, False),
    (15, 1, 0, 1, False), (30, 1, 1, 1, False), (60, 1, 1, 1, False),
    (15, 1, 1, 2, False),
    (15, 2, 1, 1, False), (15, 1, 2, 1, False),
])
def test_actual_receiver_rtl_realtime_admission(tmp_path, rate, shared, pilot, realtime, allowed):
    acq = HDL / "library/axi_starlink_pss_acquisition"
    signal = HDL / "library/starlink_pss_acquisition"
    bench = tmp_path / "admission.sv"
    bench.write_text(f"""module realtime_admission;
      axi_starlink_pss_acquisition #(.INPUT_RATE_MSPS({rate}),
        .USE_SHARED_XFFT({shared}), .ENABLE_PILOT_TAP({pilot}),
        .USE_REALTIME_XFFT({realtime})) dut();
      initial begin #1;
        if (dut.acquisition.USE_REALTIME_XFFT != {realtime}) $fatal(1, "lost selector");
        $display("REALTIME_WRAPPER_ADMISSION_PASS"); $finish;
      end
    endmodule
    """)
    result = _simulate(tmp_path, "realtime_admission", [
        signal / "starlink_pss_sample_cdc.v", signal / "starlink_pss_x2_ddc.v",
        HDL / "library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        acq / "axi_starlink_pss_phase_map_sync.v",
        acq / "tb/starlink_pss_iq_to_phase_map_stub.v",
        acq / "axi_starlink_pss_acquisition.v", bench,
    ], {})
    assert (result.returncode == 0) == allowed, result.stdout + result.stderr
    assert ("REALTIME_WRAPPER_ADMISSION_PASS" in result.stdout) == allowed
