"""Unrounded FIR sums at signed coefficient/input extremes and cancellation."""
import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT, quantize
from .test_fir_history_rtl import BENCH


@pytest.mark.parametrize("taps,lanes", [(17, 2), (17, 4), (17, 8),
                                      (145, 2), (145, 4), (145, 8),
                                      (201, 2), (201, 4), (201, 8)])
@pytest.mark.parametrize("mode", ["negative_rail", "positive_rail", "cancellation"])
def test_exact_unrounded_sums_do_not_wrap_before_quantization(tmp_path, taps, lanes, mode):
    half = (taps+1)//2
    if mode == "negative_rail":
        first = np.full(half, -131072, dtype=np.int64)
    elif mode == "positive_rail":
        first = np.full(half, 131071, dtype=np.int64)
    else:
        first = np.array([131071 if n % 2 else -131072 for n in range(half)], dtype=np.int64)
    bank = np.concatenate((first, first[-2::-1]))
    coefficients = tmp_path/"coefficients.mem"
    coefficients.write_text("".join(f"{int(value) & 0x3ffff:05x}\n" for value in bank))
    source = BENCH.replace("TAP_COUNT", str(taps)).replace("LANE_COUNT", str(lanes))
    source = source.replace('"COEFFICIENT"', f'"{coefficients}"')
    # Observe the exact total aligned with quantization, so saturation cannot
    # conceal an intermediate overflow. This does not drive any DUT state.
    source = source.replace("integer fd,", """
reg signed [63:0] unrounded_i,unrounded_q;
always @(posedge clk) begin
 unrounded_i <= dut.total_i; unrounded_q <= dut.total_q;
end
integer fd,""")
    source = source.replace('if(output_valid) $display("O', '''
  if(output_valid) $display("T %h %d %d",output_index,unrounded_i,unrounded_q);
  if(output_valid) $display("O''')
    bench, executable = tmp_path/"tb.sv", tmp_path/"sim"
    bench.write_text(source)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                            str(BANK_ROOT/"starlink_glrt_fir.v"),
                            str(BANK_ROOT/"starlink_glrt_sample_ring.v")],
                           capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    count = 1024
    values = np.tile([-32768, 32767], (count, 1)).astype(np.int64)
    values[256:512] = [32767, -32768]
    values[512::2] = [-32768, -32768]
    values[513::2] = [32767, 32767]
    rows = []
    mac_rows = (half+lanes-1)//lanes
    for index, (i, q) in enumerate(values):
        rows.append(f"1 1 {index:x} {index % 24} {i} {q}")
        if index % 24 == 23:
            rows.extend(["0 0 0 0 0 0"]*max(0, mac_rows+7-24))
    rows.extend(["0 0 0 0 0 0"]*(mac_rows+12))
    stimulus = tmp_path/"input.txt"
    stimulus.write_text("\n".join(rows)+"\n")
    result = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"],
                            capture_output=True, text=True, timeout=30, check=False)
    (tmp_path/"trace.txt").write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    observed, totals, status = [], [], None
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[0] in ("O", "T"):
            target = observed if fields[0] == "O" else totals
            target.append((int(fields[1], 16), *map(int, fields[2:])))
        elif fields[0] == "S":
            status = tuple(map(int, fields[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)
    sums = np.column_stack([np.convolve(values[:, axis], bank)[:count] for axis in range(2)])
    expected = []
    for index in range(0, count, 24):
        rounded, clips = quantize(sums[index])
        expected.append((index, *map(int, rounded), int(index >= taps-1), clips, 0))
    assert totals == [(index, *map(int, sums[index])) for index in range(0, count, 24)]
    assert observed == expected
    assert status == (count, 0, 0)
