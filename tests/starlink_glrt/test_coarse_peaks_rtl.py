"""Candidate ordering, exact circular suppression and complete-grid ownership."""
import random
import subprocess
from pathlib import Path

import pytest


BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,input_valid=0,output_ready=1;
reg [11:0] input_epoch=0;
reg [3:0] input_frequency=0;
reg [16:0] input_score=0;
wire input_ready,busy,output_valid,done,fault;
wire [2:0] output_rank;
wire [11:0] output_epoch;
wire output_epoch_left_tie;
wire [3:0] output_frequency;
wire [16:0] output_score;
starlink_glrt_coarse_peaks #(.EPOCH_COUNT(EPOCHS)) dut(.*);
integer fd,rc,e,f,s,cycles=0;
reg [4095:0] path;
reg held=0;
reg [36:0] previous;
always @(posedge clk) begin
 if(resetn && !flush) begin
  if(held && (!output_valid || {output_rank,output_epoch,output_frequency,output_score,output_epoch_left_tie}!==previous))
    $fatal(1,"candidate changed under backpressure");
  held<=output_valid && !output_ready;
  previous<={output_rank,output_epoch,output_frequency,output_score,output_epoch_left_tie};
  if(output_valid && output_ready) $display("R %d %d %d %d %d",output_rank,output_epoch,output_frequency,output_score,output_epoch_left_tie);
 end else held<=0;
end
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);
 resetn=1;arm=1;@(negedge clk);arm=0;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d\n",e,f,s);if(rc!=3) $fatal;
  while(!input_ready && !fault) begin input_valid=0;@(negedge clk);end
  if(fault) $fatal(1,"grid not admitted");
  input_valid=1;input_epoch=e;input_frequency=f;input_score=s;
  @(negedge clk);
  if((e+f)%13==0) begin input_valid=0;@(negedge clk);end
 end
 input_valid=0;
 while(!done && !fault && cycles<350000) begin
  output_ready=cycles%17<8;
  @(negedge clk);cycles=cycles+1;
 end
 if(fault || !done || busy) $fatal(1,"candidate closure failed");
 $display("DONE %d",cycles);
 // New grid must start at (0,0), and failure must fence stale candidates.
 arm=1;@(negedge clk);arm=0;input_valid=1;input_epoch=1;input_frequency=0;
 @(negedge clk);input_valid=0;
 if(!fault || output_valid) $fatal(1,"malformed grid not fenced");
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || output_valid || busy) $fatal(1,"flush did not recover");
 // Premature restart also must not mix two grids.
 arm=1;@(negedge clk);@(negedge clk);arm=0;
 if(!fault) $fatal(1,"busy arm not fenced");
 $finish;
end
endmodule
'''


def reference(rows):
    epochs = len(rows)
    peaks = []
    for f in range(11):
        for e in range(epochs):
            center = rows[e][f]
            left = rows[e - 1][f] if e else -1
            right = rows[e + 1][f] if e + 1 < epochs else -1
            if center > 0 and center >= left and center >= right and (center > left or center > right):
                peaks.append((center, e, f))
    peaks.sort(key=lambda p: (-p[0], abs(p[2] - 5), p[1], p[2]))
    selected = []
    for score, epoch, frequency in peaks:
        if any(min(abs(epoch - other[1]), epochs - abs(epoch - other[1])) < 20
                and abs(frequency - other[2]) <= 1 for other in selected):
            continue
        selected.append((len(selected), epoch, frequency, score))
        if len(selected) == 8:
            break
    return selected


@pytest.mark.parametrize("kind", ["zero", "plateau", "long_plateau", "ties", "random", "full_grid", "dense_ties"])
def test_complete_selection_matches_independent_sort(tmp_path, kind):
    rng = random.Random(602508)
    epochs = 3333 if kind in ("full_grid", "dense_ties") else 64
    rows = [[0] * 11 for _ in range(epochs)]
    if kind == "plateau":
        rows = [[12345] * 11 for _ in range(epochs)]
    elif kind == "long_plateau":
        for epoch in range(10,51):rows[epoch][5]=65536
    elif kind == "ties":
        for epoch, frequency, score in [(0, 5, 65536), (epochs - 1, 5, 65536),
                (20, 4, 65536), (20, 6, 65536), (39, 5, 65536), (40, 3, 65536),
                (63, 0, 65536), (0, 10, 65536), (20, 10, 65536)]:
            rows[epoch][frequency] = score
    elif kind in ("random", "full_grid"):
        rows = [[rng.randrange(65537) for _ in range(11)] for _ in range(epochs)]
    elif kind == "dense_ties":
        rows = [[60000 if e % 3 != 2 else 0] * 11 for e in range(epochs)]
    bench, stimulus, executable = (tmp_path / name for name in ("tb.sv", "grid.txt", "sim"))
    bench.write_text(BENCH.replace("EPOCHS", str(epochs)))
    stimulus.write_text("".join(f"{e} {f} {score}\n" for e, row in enumerate(rows)
        for f, score in enumerate(row)))
    rtl = Path(__file__).parents[2] / "hdl/library/starlink_glrt/starlink_glrt_coarse_peaks.v"
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(bench), str(rtl)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"],
        capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    actual = [tuple(map(int, line.split()[1:])) for line in run.stdout.splitlines() if line.startswith("R ")]
    assert actual == [(*row,int(row[1]>0 and rows[row[1]-1][row[2]]==row[3])) for row in reference(rows)]
    if kind == "long_plateau":assert any(row[-1] for row in actual)
