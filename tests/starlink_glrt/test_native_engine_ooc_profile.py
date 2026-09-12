"""Exercise real OOC profile validation without running FPGA implementation."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("rate,serial,accepted", [
    (5000000, 0, True), (5000000, 1, True), (15000000, 0, True),
    (15000000, 1, False), (30000000, 1, False), (60000000, 1, False),
    (5000001, 0, False), (5000000, 2, False),
])
def test_native_engine_ooc_rate_selects_reference_stride_and_safe_rotation(
    tmp_path, rate, serial, accepted
):
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path / "ooc"
    bench = tmp_path / "profile.tcl"
    bank = repo / "hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"
    script = repo / "tools/starlink_glrt_native_products_ooc.tcl"
    # Only tool entry points are stubbed. Stop at synthesis after all real
    # rate, ROM shape, mode and serial-cadence validation has executed.
    bench.write_text("\n".join([
        "proc version {args} {return 2022.2}",
        "proc create_project {args} {}",
        "proc set_msg_config {args} {}",
        "proc read_verilog {args} {}",
        'proc synth_design {args} {puts $args; exit 0}',
        f"set ::env(STARLINK_GLRT_OOC_SERIAL_ROTATE) {serial}",
        f"set argv [list {{{output}}} {{{bank}}} {rate}]",
        "set argc [llength $argv]",
        f"source {{{script}}}",
    ]) + "\n")
    result = subprocess.run(["tclsh", str(bench)], capture_output=True,
                            text=True, timeout=10, check=False)
    assert (result.returncode == 0) == accepted, result.stdout + result.stderr
    if accepted:
        assert f"REFERENCE_STRIDE={60000000 // rate}" in result.stdout
        assert f"SERIAL_ROTATE={serial}" in result.stdout
        assert "DIRECT_COEFFICIENT_FILE=" not in result.stdout
    else:
        assert not output.exists()
