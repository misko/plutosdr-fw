from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT

BENCH = r'''
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,sample_tick=0,proposal_valid=0;
reg [63:0] proposal_epoch=0;
reg [50:0] proposal_numerator=0;
wire selected_valid,pending,sticky_fault;
wire [63:0] selected_epoch,selected_count,merged_count;
starlink_glrt_candidate_select #(.LOOKAHEAD_SAMPLES(LOOKAHEAD)) dut(.*);
integer fd,rc,fl,ti,va,cycle;
reg [63:0] ep;
reg [50:0] nu;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");
 repeat(4) @(negedge clk);
 resetn=1;cycle=0;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %h\n",fl,ti,va,ep,nu);
  if(rc!=5) $fatal;
  flush=fl;sample_tick=ti;proposal_valid=va;proposal_epoch=ep;proposal_numerator=nu;
  @(posedge clk);#1;
  $display("O %d %d %h %d %d %d %d",cycle,selected_valid,selected_epoch,
    selected_count,merged_count,pending,sticky_fault);
  cycle=cycle+1;
  @(negedge clk);
 end
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("lookahead", [1, 5, 176])
def test_bounded_selection_ties_deadline_and_flush(lookahead, tmp_path):
    rng = np.random.default_rng(617992)
    rows = []
    # Deliberate equal peaks and a larger peak on the inclusive deadline.
    rows.append((0, 1, 1, 1 << 50, 123))
    rows.extend((0, 1, 1, (1 << 50)+j+1, 123 if j < lookahead-1 else 124)
                for j in range(lookahead))
    # Clusters, idle pauses, clean flush, and full-width unsigned numerators.
    for j in range(2000):
        tick = int(rng.random() < .55)
        valid = int(tick and rng.random() < .4)
        rows.append((int(j in (617, 999)), tick, valid, (1 << 51)+j,
                     int(rng.integers(0, 1 << 51))))
    rows.extend([(0, 1, 0, 0, 0)]*(lookahead+1))
    bench, executable, inputs = tmp_path/"tb.sv", tmp_path/"sim", tmp_path/"input.txt"
    bench.write_text(BENCH.replace("(LOOKAHEAD)", f"({lookahead})"))
    inputs.write_text("\n".join(f"{fl} {ti} {va} {ep:x} {nu:x}" for fl, ti, va, ep, nu in rows)+"\n")
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                            str(BANK_ROOT/"starlink_glrt_candidate_select.v")], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout+built.stderr
    process = subprocess.run(["vvp", str(executable), f"+INPUT={inputs}"], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stdout+process.stderr
    actual = [tuple(int(word, 16 if j == 2 else 10) for j, word in enumerate(line.split()[1:]))
              for line in process.stdout.splitlines() if line.startswith("O ")]
    pending, remaining, best_epoch, best_num, selected_epoch, selected, merged = False, 0, 0, 0, 0, 0, 0
    expected = []
    for cycle, (flush, tick, valid, epoch, numerator) in enumerate(rows):
        output_valid = False
        if flush:
            pending, remaining, best_epoch, best_num, selected_epoch = False, 0, 0, 0, 0
        elif pending:
            if valid:
                merged += 1
                if numerator > best_num:
                    best_epoch, best_num = epoch, numerator
            if tick:
                remaining -= 1
                if not remaining:
                    selected += 1
                    selected_epoch = best_epoch
                    pending, output_valid = False, True
        elif valid:
            pending, remaining, best_epoch, best_num = True, lookahead, epoch, numerator
        expected.append((cycle, int(output_valid), selected_epoch, selected, merged, int(pending), 0))
    assert actual == expected
    assert next(row for row in actual if row[1])[2] == (1 << 50)+lookahead
