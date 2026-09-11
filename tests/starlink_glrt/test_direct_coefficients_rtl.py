"""Direct coefficient ROM: signed payload, backpressure, cancellation and restart."""
import subprocess

import pytest

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import BENCH


@pytest.mark.parametrize("count", [1, 17])
@pytest.mark.parametrize("reset", [False, True])
def test_direct_bank_preserves_every_word_and_restarts_after_cancel(tmp_path, count, reset):
    values = [(32767-n, -32768+n, 71*n-13, 29-37*n) for n in range(count)]
    bank = tmp_path/"bank.mem"
    bank.write_text("".join(f"{sum((v & 65535) << (16*k) for k,v in enumerate(row)):016x}\n"
                            for row in values))
    first = BENCH.index("starlink_glrt_cubic_coefficients #(")
    last = BENCH.index(" dut (", first)
    source = (BENCH[:first] + 'starlink_glrt_direct_coefficients #(.SAMPLE_COUNT(N),'
              '.TEMPLATE_FILE("BANK_PATH"))' + BENCH[last:])
    for key, value in {"SEGMENT_VALUE": 1, "FIRST_VALUE": 1, "COUNT_VALUE": count,
                       "BANK_PATH": bank}.items():
        source = source.replace(key, str(value))
    bench, trace, executable = (tmp_path/name for name in ("tb.sv", "trace", "sim"))
    bench.write_text(source)
    # Fill and stall both pipeline slots, then discard before either is consumed.
    cycles = [(1,0,1,0)] + [(1,0,0,0)]*15
    cycles += [(0,0,0,0) if reset else (1,1,0,0), (1,0,0,0)]
    cycles += [(1,0,1,0)] + [(1,0,0,int(n % 9 == 0)) for n in range(9*count+30)]
    cycles += [(1,0,1,1)] + [(1,0,0,1)]*(count+10)
    trace.write_text("".join(" ".join(map(str,row))+"\n" for row in cycles))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                            str(BANK_ROOT/"starlink_glrt_direct_coefficients.v")],
                           capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={trace}"],
                         capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    actual = [list(map(int,line.split()[1:])) for line in run.stdout.splitlines()
              if line.startswith("R ")]
    expected = [[n, *row, int(n==count-1), 0] for n,row in enumerate(values)]
    assert actual == expected*2
