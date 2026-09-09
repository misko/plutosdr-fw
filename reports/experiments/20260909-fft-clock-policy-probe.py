"""Admission and clock-only delta for the isolated throughput experiment."""
import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_CLOCK_EXPERIMENT_HDL", Path(__file__).parent / "hdl"))
RUNNER = HDL / "library/starlink_pss_acquisition/simulate_iq_to_score_shared.tcl"


def invoke(output, clock, realtime="1"):
    environment = dict(os.environ)
    environment.pop("STARLINK_PSS_SIM_FFT_MHZ", None)
    if clock is not None:
        environment["STARLINK_PSS_SIM_FFT_MHZ"] = clock
    code = f"""
proc version {{args}} {{return 2022.2}}
proc create_project {{args}} {{error ADMITTED}}
set argv [list {{{output}}} capacity 64 bursty-stalled {realtime}]
set argc [llength $argv]
if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}
"""
    return subprocess.run(["tclsh"], input=code, env=environment, text=True,
                          capture_output=True, timeout=10, check=False)


@pytest.mark.parametrize("clock", ["", "149", "151", "176", "201", "150.0", " 150", "150 ", "1e2", "true", "[exit]"])
def test_bad_clock_rejected_before_allocation(tmp_path, clock):
    output = tmp_path / "evidence"
    result = invoke(output, clock)
    assert "simulation FFT clock must be 150, 175, or 200 MHz" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("clock", ["150", "175"])
def test_lower_clock_needs_explicit_realtime(tmp_path, clock):
    output = tmp_path / "evidence"
    result = invoke(output, clock, "0")
    assert "lower simulation FFT clock requires explicit realtime mode" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("clock,half", [(None, "2.5"), ("200", "2.5"), ("175", "2.858"), ("150", "3.334")])
def test_only_fft_stimulus_clock_changes_and_rounding_is_conservative(tmp_path, clock, half):
    old, new = tmp_path / "old", tmp_path / "new"
    for output, choice in [(old, None), (new, clock)]:
        result = invoke(output, choice)
        assert result.returncode == 2 and "ADMITTED" in result.stderr
    name = "tb_starlink_pss_iq_to_score_xfft_longrun.sv"
    old_bench = (old / name).read_text().splitlines()[1:]
    new_bench = (new / name).read_text().splitlines()[1:]
    old_body, new_body = "\n".join(old_bench), "\n".join(new_bench)
    old_clock = "forever #2.5 fft_clk = !fft_clk;"
    new_clock = f"forever #{half} fft_clk = !fft_clk;"
    assert new_body.count(new_clock) == 1
    assert new_body.replace(new_clock, old_clock, 1) == old_body
    if clock is not None:
        assert float(half) * 2 >= 1000 / int(clock)
    for path in (new / "frozen_sources").iterdir():
        assert path.read_bytes() == (old / "frozen_sources" / path.name).read_bytes()


def test_generated_ip_configuration_stays_pinned_to_baseline():
    relative = "library/starlink_pss_acquisition/simulate_iq_to_score_shared.tcl"
    baseline = subprocess.run(["git", "-C", str(RUNNER.parent), "show", f"6090190c4442d2fd0e825136d87b692e2ad6deef:{relative}"],
                              capture_output=True, text=True, timeout=10, check=True).stdout
    source = RUNNER.read_text()
    first, last = "create_ip -name xfft", "foreach name $rtl_names { add_files"
    assert source.split(first, 1)[1].split(last, 1)[0] == baseline.split(first, 1)[1].split(last, 1)[0]
