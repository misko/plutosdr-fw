"""Exercise real runner admission/completion over fake Vivado, not FPGA proof."""

import hashlib
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
RUNNER = HDL / "library/axi_starlink_pss_tracker/simulate_global_descriptor_tracker.tcl"
AXI_PASS = (
    "AXI_TRACKER_PASS rate=15 taps=66 lags=61 winner_lag=30 packet_words=26 "
    "telemetry=serial_bram concurrent_snapshot=1 deferred_candidate=1 irq=level "
    "reset_epoch=coordinated"
)
METADATA_PASS = "AXI_TRACKER_METADATA_PASS checked_packets=3 retained_for_epoch_reset=1"
FINAL = "GLOBAL_DESCRIPTOR_TRACKER_FUNCTIONAL_VERIFIED hardware_and_timing_qualified=false"
ORIGIN = (
    "tracker_bd lopt_startpoints=i_system_wrapper/system_i/axi_ad9361/inst/i_rx/"
    "i_up_adc_common/i_xfer_cntrl/d_data_cntrl_int_reg[0]/C"
)


@pytest.mark.parametrize("case,error", [
    ("valid", None),
    ("existing", "output must be new"),
    ("missing", "missing frozen netlist context"),
    ("hash", "incomplete or mismatched netlist export receipt"),
    ("incomplete", "incomplete or mismatched netlist export receipt"),
    ("origin", "unqualified global lopt source"),
    ("no_axi_pass", "required terminal bench pass"),
    ("no_metadata_pass", "required terminal bench pass"),
    ("duplicate", "required terminal bench pass"),
    ("fatal", "fatal/error diagnostic"),
    ("error", "fatal/error diagnostic"),
])
def test_global_simulation_requires_bound_inputs_and_both_terminal_checks(tmp_path, case, error):
    context = tmp_path / "context"
    context.mkdir()
    netlist = context / "tracker_bd_netlist.v"
    netlist.write_text("MOCK NETLIST: NOT FUNCTIONAL EVIDENCE\n")
    digest = hashlib.sha256(netlist.read_bytes()).hexdigest()
    (context / "context.txt").write_text("\n".join([
        f"{digest if case != 'hash' else '0' * 64}  {netlist}",
        ORIGIN if case != "origin" else "tracker_bd lopt_startpoints=wrong/C",
        "DESCRIPTOR_CONTEXT_INSPECTED functional_and_physical_qualified=false"
        if case != "incomplete" else "NOT_FINISHED",
    ]))
    if case == "missing":
        netlist.unlink()
    output = tmp_path / "output"
    if case == "existing":
        output.mkdir()
        (output / "keep").write_text("preserved")
    lines = [AXI_PASS, METADATA_PASS]
    if case == "no_axi_pass":
        lines.remove(AXI_PASS)
    if case == "no_metadata_pass":
        lines.remove(METADATA_PASS)
    if case == "duplicate":
        lines.append(METADATA_PASS)
    if case in {"fatal", "error"}:
        lines.append(f"{case.title()}: deliberately failed mock simulation")
    mock_log = tmp_path / "mock-simulate.log"
    mock_log.write_text("\n".join(lines) + "\n")
    script = f"""
proc version {{args}} {{ return 2022.2 }}
proc create_project {{args}} {{ puts MOCK_PROJECT_CREATED }}
proc current_project {{}} {{ return mock_project }}
proc get_filesets {{args}} {{ return mock_fileset }}
proc set_property {{args}} {{}}
proc add_files {{args}} {{}}
proc close_sim {{}} {{}}
proc close_project {{}} {{}}
proc launch_simulation {{args}} {{
  file copy {{{mock_log}}} [file join $::project_dir global_tracker.sim sim_1 behav xsim simulate.log]
}}
set argc 2
set argv [list {{{context}}} {{{output}}}]
if {{[catch [list source {{{RUNNER}}}] message]}} {{ puts stderr $message; exit 2 }}
"""
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            check=False, timeout=10)
    if error:
        assert result.returncode == 2 and error in result.stderr, result
        assert FINAL not in result.stdout
        if (output / "scope.txt").exists():
            assert FINAL not in (output / "scope.txt").read_text()
    else:
        assert result.returncode == 0, result.stderr
        receipt = (output / "scope.txt").read_text()
        assert FINAL in receipt and FINAL in result.stdout
        assert f"result_log_sha256={hashlib.sha256(mock_log.read_bytes()).hexdigest()}" in receipt
        assert "ADC_DMA_IIO_RF_physical_CDC_timing_qualified=false" in receipt
        assert (output / "frozen_sources" / RUNNER.name).read_bytes() == RUNNER.read_bytes()
    if case in {"missing", "hash", "incomplete", "origin"}:
        assert not output.exists()
        assert "MOCK_PROJECT_CREATED" not in result.stdout
    if case == "existing":
        assert list(output.iterdir()) == [output / "keep"]
        assert (output / "keep").read_text() == "preserved"
