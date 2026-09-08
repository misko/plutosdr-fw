from __future__ import annotations

import random
import subprocess

from .ddc import BANK_ROOT


def test_restoring_glrt_ratio_full_width_boundaries_and_random(tmp_path):
    rng = random.Random(133853)
    vectors = [(0, 0), (1, 0), (0, 1), (1, 1), ((1 << 51)-1, (1 << 55)-1)]
    vectors += [(peak, 64*peak+offset) for peak in (1, 71, 1 << 34, (1 << 48)-1)
                for offset in (-1, 0, 1)]
    vectors += [(rng.randrange(1 << 51), rng.randrange(1 << 55)) for _ in range(100)]
    vectors += [(rng.randrange(1 << 40), rng.randrange(1 << 48, 1 << 55)) for _ in range(100)]
    path = tmp_path / "vectors.txt"
    path.write_text("\n".join(f"{p:x} {e:x}" for p, e in vectors)+"\n")
    bench = tmp_path / "tb.sv"
    bench.write_text(r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0, flush=0, start=0;
reg [50:0] peak_power=0;
reg [54:0] symbol_energy=0;
wire busy, done, zero_energy, clamped;
wire [16:0] score_q16;
starlink_glrt_ratio dut (.*);
integer fd, rc, cycles;
initial begin
 fd=$fopen("VECTORS","r");
 repeat(4) @(negedge clk);
 resetn=1;
 while (!$feof(fd)) begin
  rc=$fscanf(fd,"%h %h\n",peak_power,symbol_energy);
  if (rc != 2) $fatal(1,"bad input");
  start=1;
  @(posedge clk); #1;
  @(negedge clk);
  start=0;
  cycles=0;
  while (!done && cycles<75) begin
   @(posedge clk); #1;
   cycles=cycles+1;
   @(negedge clk);
  end
  if (!done || busy) $fatal(1,"unbounded division");
  $display("R %d %d %d %d",score_q16,zero_energy,clamped,cycles);
  @(negedge clk);
 end
 $finish;
end
endmodule
'''.replace("VECTORS", str(path)))
    executable = tmp_path / "sim"
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(bench), str(BANK_ROOT / "starlink_glrt_ratio.v")], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    process = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    rows = [tuple(map(int, line.split()[1:])) for line in process.stdout.splitlines() if line.startswith("R ")]
    assert len(rows) == len(vectors)
    for (peak, energy), (score, zero, clamped, cycles) in zip(vectors, rows):
        exact = (peak << 22)//energy if energy else 0
        assert score == min(exact, 65536)
        assert zero == int(energy == 0)
        assert clamped == int(exact > 65536)
        assert cycles == (73 if energy else 0)
