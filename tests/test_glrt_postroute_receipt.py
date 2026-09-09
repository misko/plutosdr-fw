"""Clock attestation ignores Vivado's variable banner, preserving timing inputs."""
import ast
from pathlib import Path
import re

import pytest


@pytest.fixture
def clock_body():
    # Load only the receipt's pure normalizer; never execute its shell/Vivado flow.
    script = Path(__file__).resolve().parents[1] / "scripts/retry_glrt_postroute.sh"
    source = script.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "clock_body")
    namespace = {"re": re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), "exec"), namespace)
    return namespace["clock_body"]


REPORT = """Copyright Xilinx
{rule}
| Tool Version : Vivado v.2022.2
| Date         : {date}
| Command      : report_clocks -file {path}
| Device       : 7z010-clg400
{rule}
Clock Report
Clock       Period(ns)  Waveform(ns)    Attributes  Sources
clk_fpga_0  10.000      {{0.000 5.000}}   P           {{PS7/FCLKCLK[0]}}
rx_clk      16.270      {{0.000 8.135}}   P           {{rx_clk_in}}
User Uncertainty
clk_fpga_0  0.154
User Jitter
clk_fpga_0  0.300
"""


def reports(tmp_path):
    before, after = tmp_path / "before.rpt", tmp_path / "after.rpt"
    before.write_text(REPORT.format(rule="-" * 130, date="05:52:03", path="before.rpt"))
    after.write_text(REPORT.format(rule="-" * 129, date="05:56:00", path="after.rpt"))
    return before, after


def test_variable_banner_does_not_fail_identical_clocks(clock_body, tmp_path):
    before, after = reports(tmp_path)
    assert clock_body(before) == clock_body(after)


@pytest.mark.parametrize("old,new", [
    ("10.000", "10.100"),
    ("{0.000 5.000}", "{0.000 4.900}"),
    ("{rx_clk_in}", "{other_clock}"),
    ("0.154", "0.100"),
    ("0.300", "0.100"),
    ("7z010-clg400", "7z020-clg400"),
])
def test_changed_clock_or_device_still_fails_comparison(clock_body, tmp_path, old, new):
    before, after = reports(tmp_path)
    after.write_text(after.read_text().replace(old, new))
    assert clock_body(before) != clock_body(after)
