"""Sequential verification normalization: independent integer math and fencing."""
import math
import random
import subprocess
from pathlib import Path

from .test_coarse_norm_rtl import BENCH


def simulate(tmp_path, rows):
    bench = BENCH.replace("wire output_valid,zero_energy,ratio_clamped;",
                          "wire output_valid,zero_energy,ratio_clamped,fault;")
    bench = bench.replace("starlink_glrt_coarse_norm dut", "starlink_glrt_verify_norm #(.TAG_WIDTH(32)) dut")
    bench = bench.replace("cycle=cycle+1;", 'if(fault) $display("F %d",cycle); cycle=cycle+1;')
    source = tmp_path/"tb.sv"
    source.write_text(bench)
    stimulus = tmp_path/"input.txt"
    stimulus.write_text("\n".join(rows)+"\n")
    executable = tmp_path/"sim"
    rtl = Path(__file__).parents[2]/"hdl/library/starlink_glrt/starlink_glrt_coarse_norm.v"
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(source), str(rtl)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"],
                            check=True, capture_output=True, text=True, timeout=30)
    outputs, faults = [], []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[0] == "R":
            outputs.append((int(fields[1]), int(fields[2], 16), *map(int, fields[3:])))
        elif fields[0] == "F":
            faults.append(int(fields[1]))
    return outputs, faults


def expected(tag, numerator, denominator):
    nr, dr = math.isqrt(numerator), math.isqrt(denominator)
    return tag, min(65536, (nr << 16)//dr) if dr else 0, int(dr == 0), int(dr != 0 and nr > dr)


def test_three_lane_bursts_match_integer_math_and_preserve_tags(tmp_path):
    rng = random.Random(2500000750)
    powers = [0, 1, 2, 3, 4, 8, 9, 15, 16, 2**32-1, 2**32, 2**63-1, 2**64-1]
    cases = [(n, d) for n in powers for d in powers]
    cases += [(rng.randrange(2**64), rng.randrange(2**64)) for _ in range(2000)]
    rows, wanted = ["0 0 0 0 0 0"], []
    for start in range(0, len(cases), 3):
        for index, (numerator, denominator) in enumerate(cases[start:start+3], start):
            rows.append(f"1 0 1 {numerator:x} {denominator:x} {index:x}")
            wanted.append(expected(index, numerator, denominator))
        rows.extend(["1 0 0 0 0 0"]*160)
    actual, faults = simulate(tmp_path, rows)
    assert not faults
    assert [r[1:] for r in actual] == wanted
    assert actual[0][0] == 50
    assert actual[2][0] - actual[0][0] == 98


def test_flush_or_reset_at_every_burst_phase_discards_only_pending_results(tmp_path):
    rows, wanted = ["0 0 0 0 0 0"], []
    tag = 0
    for use_reset in (False, True):
        for cancel_after in range(1, 153):
            start = len(rows)
            accepted = []
            for lane in range(3):
                tag += 1
                n, d = tag**2, (tag+7)**2
                accepted.append(expected(tag, n, d))
                rows.append(f"1 0 1 {n:x} {d:x} {tag:x}")
            rows.extend(["1 0 0 0 0 0"]*cancel_after)
            cancel_cycle = len(rows)
            # The first request returns after 49 cycles; each following lane
            # occupies another 49. A cancellation edge suppresses its output.
            wanted.extend(value for lane, value in enumerate(accepted)
                          if start+49*(lane+1) < cancel_cycle)
            rows.append("0 0 1 ffff ffff ffffffff" if use_reset else "1 1 1 ffff ffff ffffffff")
            rows.extend(["1 0 0 0 0 0"]*160)
    actual, faults = simulate(tmp_path, rows)
    assert not faults
    assert [r[1:] for r in actual] == wanted


def test_overflow_faults_closed_and_flush_recovers(tmp_path):
    rows = ["0 0 0 0 0 0"] + [f"1 0 1 4 9 {n:x}" for n in range(12)]
    rows.extend(["1 0 0 0 0 0"]*180)
    flush_cycle = len(rows)
    rows += ["1 1 1 4 9 fffe", "1 0 1 4 9 ffff"] + ["1 0 0 0 0 0"]*160
    actual, faults = simulate(tmp_path, rows)
    assert faults == list(range(6, flush_cycle))
    assert [r[1:] for r in actual] == [expected(0xffff, 4, 9)]
