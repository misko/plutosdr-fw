"""Reject incompatible compile-time tracking geometry instead of mislabeling IQ."""
import subprocess

import pytest

from .ddc import BANK_ROOT


@pytest.mark.parametrize("parameters", [
    ".SOURCE_RATE(2500000)",  # Lower-rate results cannot claim legacy GLS1.
    ".TRACKING(1),.SOURCE_RATE(25000000)",
    ".TRACKING(1),.SOURCE_RATE(30000000),.SAMPLE_COUNT(79200)",
    ".TRACKING(1),.SOURCE_RATE(2500000),.SAMPLE_COUNT(3300),.REFERENCE_PHASES(1)",
    ".TRACKING(1),.REFERENCE_PHASES(4)",
])
def test_invalid_result_profile_fails_before_any_packet(tmp_path, parameters):
    bench, executable = tmp_path/"tb.sv", tmp_path/"sim"
    bench.write_text(f"""`timescale 1ns/1ps
module tb;
starlink_glrt_native_scheduled_results #({parameters}) dut();
initial begin #10; $finish; end
endmodule
""")
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "native_schedule", "native_result_queue", "native_scheduled_results")]
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench), *map(str, sources)], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=5, check=False)
    assert run.returncode != 0 and "unsupported scheduled result profile" in run.stdout
