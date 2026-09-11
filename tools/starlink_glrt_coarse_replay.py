"""Replay one archived CI16 window through the complete FPGA coarse grid.

Expected scores are external independently generated uint32 data (11 x 3333).
No RF or hardware mutation. Keep simulation and source digests with the result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np


BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,input_valid=0,input_gap=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg output_ready=1;
wire busy,done,fault,output_valid;
wire [63:0] window_first_index;
wire [11:0] output_epoch;
wire [3:0] output_frequency;
wire [16:0] output_score;
wire [5:0] output_support;
wire [31:0] rejected_arms;
starlink_glrt_coarse_window #(.COEFFICIENT_FILE("COEFF_PATH"),.ENERGY_FILE("ENERGY_PATH")) dut(.*);
integer fd,rc,si,sq,cycles=0,waits=0;
reg [4095:0] path;
always @(posedge clk) if(resetn && output_valid && output_ready)
  $display("R %d %d %d %d",output_epoch,output_frequency,output_score,output_support);
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);
 resetn=1;arm=1;@(negedge clk);arm=0;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d\n",si,sq);if(rc!=2) $fatal;
  input_valid=1;input_i=si;input_q=sq;input_index=64'h10000000000001+cycles*24;
  @(negedge clk);cycles=cycles+1;
 end
 input_valid=0;
 while(!done && !fault && waits<10000000) begin @(negedge clk);waits=waits+1;end
 if(fault || !done || rejected_arms!=0 || window_first_index!=64'h10000000000001)
   $fatal(1,"closure failed");
 $display("DONE %d",waits);$finish;
end
endmodule
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(iq_path: Path, expected_path: Path, roms: Path, output: Path) -> dict:
    iq = np.fromfile(iq_path, dtype="<i2")
    expected = np.fromfile(expected_path, dtype="<u4")
    if iq.size != 28_000 or expected.size != 11 * 3333 or np.any(expected > 65536):
        raise ValueError("requires a full CI16 window and an 11 x 3333 Q16 grid")
    iq = iq.reshape(14000, 2)
    expected = expected.reshape(11, 3333)
    manifest = json.loads((roms / "manifest.json").read_text())
    if manifest["schema"] != "coarse-q9-rom-v1" or manifest["edge"] != "upper":
        raise ValueError("requires reviewed upper-edge ROM format")
    for name, value in manifest["files"].items():
        if digest(roms / name) != value:
            raise ValueError("ROM digest mismatch")
    root = Path(__file__).resolve().parents[1] / "hdl/library/starlink_glrt"
    sources = [root / f"starlink_glrt_coarse_{name}.v" for name in ("window", "mac6", "norm")]
    tracked = [*sources, iq_path, expected_path, roms / "manifest.json", Path(__file__).resolve()]
    hashes = {str(path): digest(path) for path in tracked}
    output.mkdir(parents=True, exist_ok=False)
    bench, stimulus, executable = (output / name for name in ("tb.sv", "iq.txt", "sim"))
    bench.write_text(BENCH.replace("COEFF_PATH", str(roms / "coarse_upper_q9.mem"))
        .replace("ENERGY_PATH", str(roms / "coarse_upper_energy.mem")))
    stimulus.write_text("".join(f"{i} {q}\n" for i, q in iq))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(bench), *map(str, sources)], capture_output=True, text=True)
    (output / "compile.log").write_text(build.stdout + build.stderr)
    build.check_returncode()
    started = time.monotonic()
    with (output / "simulation.log").open("w") as log:
        run = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"], stdout=log,
            stderr=subprocess.STDOUT, timeout=900)
    run.check_returncode()
    rows = []
    clocks = None
    for line in (output / "simulation.log").read_text().splitlines():
        if line.startswith("R "):
            rows.append(tuple(map(int, line.split()[1:])))
        elif line.startswith("DONE "):
            clocks = int(line.split()[1])
    if len(rows) != 11 * 3333 or clocks is None:
        raise ValueError("incomplete grid or closure")
    mismatches = []
    for index, (epoch, frequency, score, support) in enumerate(rows):
        expected_support = sum(epoch + 22 + 286 * symbol + offset + 11 <= 14000
            for symbol in range(12) for offset in (0, 3333, 6667, 10000, 13333))
        if (epoch, frequency) != divmod(index, 11) or support != expected_support:
            raise ValueError("grid coordinate/support mismatch")
        if score != int(expected[frequency, epoch]):
            mismatches.append([epoch, frequency, score, int(expected[frequency, epoch])])
    for path in tracked:
        if digest(path) != hashes[str(path)]:
            raise ValueError("source/evidence changed during replay")
    result = {"scope": "complete_coarse_grid_rtl_not_local_detection_or_board_verification",
        "grid_scores": len(rows), "mismatch_count": len(mismatches), "first_mismatches": mismatches[:20],
        "clocks_after_last_input": clocks, "compute_ms_at_100mhz": clocks / 100_000,
        "observation_ms_at_2_5msps": 5.6, "simulation_seconds": time.monotonic() - started,
        "sources": hashes, "passed": not mismatches}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    if mismatches:
        raise ValueError("RTL differs from numerical oracle")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("iq", "expected", "roms", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.iq, args.expected, args.roms, args.output), indent=2))
