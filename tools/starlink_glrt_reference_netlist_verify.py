"""Check a routed coefficient fixture using Icarus and Vivado UNISIM models."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from tools.starlink_glrt_native_replay import coefficients

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg [3:0] stimulus=0;
wire [88:0] observation;
starlink_glrt_cubic_coefficients_ooc_wrapper dut(.*);
reg [84:0] truth [0:79199];
integer count=0, cycle=0, job, index;
initial $readmemh("expected.mem",truth);
always @(posedge clk) begin
 #1;
 cycle=cycle+1;
 if(cycle > 180000) $fatal(1,"coefficient completion timeout");
 if(stimulus[3]) begin
  if(observation[87] === 1'b1) begin
   index=count%79200;
   if(observation[84:0] !== truth[index])
    $fatal(1,"coefficient mismatch job=%0d index=%0d actual=%h expected=%h",
     count/79200,index,observation[84:0],truth[index]);
   if(observation[86] !== (index==79199)) $fatal(1,"wrong last flag");
   if(observation[85] !== 1'b0) $fatal(1,"unexpected cancellation");
   count=count+1;
  end else if(observation[87] !== 1'b0) $fatal(1,"unknown output valid");
 end
end
initial begin
 // UNISIM global startup holds GSR for 100 ns; keep explicit reset beyond it.
 repeat(30) @(negedge clk);
 stimulus=4'b1001;
 repeat(5) @(negedge clk);
 for(job=0;job<2;job=job+1) begin
  if(observation[88] !== 1'b1) $fatal(1,"job not ready");
  stimulus=4'b1011;
  @(negedge clk);
  stimulus=4'b1001;
  while(count < (job+1)*79200) @(negedge clk);
  // The coefficient window ends before the trailing polynomial guard does.
  repeat(64) @(negedge clk);
  if(observation[88:87] !== 2'b10) $fatal(1,"job failed to retire");
 end
 if(count != 158400) $fatal(1,"duplicate coefficients");
 $display("REFERENCE_NETLIST_PASS jobs=2 coefficients=158400");
 $finish;
end
endmodule
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, required=True)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--unisim-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    netlist, bank, models = args.netlist.resolve(), args.bank.resolve(), args.unisim_root.resolve()
    sources = [Path(__file__).resolve(), netlist, bank, models.parent/"glbl.v", *sorted(models.glob("*.v"))]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    (output/"protocol.json").write_text(json.dumps({"source_sha256": hashes,
        "scope": "routed_coefficient_netlist_functional_simulation", "jobs": 2,
        "samples_per_job": 79200, "maximum_rate": "one_output_per_clock",
        "hardware_test": False}, indent=2)+"\n")
    expected = []
    for index, row in enumerate(coefficients(bank.read_bytes())):
        word = index << 68  # Four clip flags are zero in the qualified bank.
        for column, value in enumerate(row):
            word |= (value & 65535) << (16*(3-column))
        expected.append(f"{word:022x}\n")
    (output/"expected.mem").write_text("".join(expected))
    (output/"bench.sv").write_text(BENCH)
    commands = [
        ["iverilog", "-g2012", "-s", "tb", "-s", "glbl", "-y", str(models),
         "-o", "sim", str(models.parent/"glbl.v"), str(netlist), "bench.sv"],
        ["vvp", "sim"],
    ]
    for name, command in zip(("compile", "simulate"), commands, strict=True):
        result = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=300, check=False)
        (output/f"{name}.log").write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(f"{name} failed; see {output/name}.log")
    if "REFERENCE_NETLIST_PASS jobs=2 coefficients=158400" not in result.stdout:
        raise ValueError("missing complete netlist verification result")
    if hashes != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}:
        raise ValueError("verification inputs changed")
    summary = {"status": "pass", "exact_coefficients": 158400, "jobs": 2,
               "hardware_test": False, "complete_receiver_qualified": False}
    (output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
