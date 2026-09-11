"""Full-pilot accumulation and oscillator rotation against scalar integers."""
import math
from pathlib import Path
import random
import subprocess


def simulate(tmp_path, name, bench, rows, extra_files=None):
    root = Path(__file__).parents[2] / "hdl/library/starlink_glrt"
    for filename, content in (extra_files or {}).items():
        (tmp_path / filename).write_text(content)
    source, stimulus, executable = (tmp_path / n for n in ("tb.sv", "input.txt", "sim"))
    source.write_text(bench.replace("OSCILLATOR_PATH", str(tmp_path / "oscillator.mem")))
    stimulus.write_text("".join(rows))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(source), str(root / f"starlink_glrt_verify_{name}.v")], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run(["vvp", str(executable), f"+INPUT={stimulus}"],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return [list(map(int, line.split()[1:])) for line in result.stdout.splitlines() if line.startswith("R ")]


MAC_BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_first=0,input_last=0;
reg [11:0] input_length=0;
reg signed [15:0] input_i=0,input_q=0;
reg [71:0] coefficients=0;
reg [15:0] input_tag=0;
wire output_valid,fault;
wire [119:0] correlation_i,correlation_q;
wire [42:0] sample_energy;
wire [15:0] output_tag;
starlink_glrt_verify_mac3 dut(.*);
integer fd,rc;
reg [4095:0] path;
always @(posedge clk) if(output_valid && resetn && !flush)
 $display("R %d %d %d %d %d %d %d %d",output_tag,
 $signed(correlation_i[0+:40]),$signed(correlation_q[0+:40]),
 $signed(correlation_i[40+:40]),$signed(correlation_q[40+:40]),
 $signed(correlation_i[80+:40]),$signed(correlation_q[80+:40]),sample_energy);
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d %d %d %h %d\n",
      input_valid,input_first,input_last,input_length,input_i,input_q,coefficients,input_tag);
  if(rc!=8) $fatal;
  @(negedge clk);
 end
 input_valid=0;repeat(5) @(negedge clk);
 if(fault) $fatal(1,"valid jobs faulted");
 input_valid=1;input_first=1;input_last=1;input_length=2;
 @(negedge clk);input_valid=0;repeat(4) @(negedge clk);
 if(!fault || output_valid) $fatal(1,"bad length not fenced");
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || output_valid) $fatal(1,"flush failed");
 $finish;
end
endmodule
'''


def test_three_lanes_full_scale_and_full_pilot_accumulation(tmp_path):
    rng = random.Random(33331650)
    rows, expected = [], []
    for tag, length in enumerate((1, 11, 1650, 3333, 2, 3333), start=1):
        totals = [[0, 0] for _ in range(3)]
        energy = 0
        for tap in range(length):
            i, q = ((-32768, -32768) if tag == 4 else
                (rng.randrange(-32768, 32768), rng.randrange(-32768, 32768)))
            coefficients = [[-2048, -2048] for _ in range(3)] if tag == 4 else [
                [rng.randrange(-2048, 2048), rng.randrange(-2048, 2048)] for _ in range(3)]
            packed = 0
            for lane, (ci, cq) in enumerate(coefficients):
                totals[lane][0] += i * ci + q * cq
                totals[lane][1] += q * ci - i * cq
                packed |= ((ci & 4095) | ((cq & 4095) << 12)) << (24 * lane)
            energy += i * i + q * q
            rows.append(f"1 {int(tap == 0)} {int(tap == length - 1)} {length} {i} {q} {packed:x} {tag}\n")
            if rng.randrange(7) == 0:
                rows.append(f"0 0 0 {length} 0 0 0 {tag}\n")
        expected.append([tag, *(value for pair in totals for value in pair), energy])
    assert simulate(tmp_path, "mac3", MAC_BENCH, rows) == expected
    assert expected[3][1] > 2**38


ROTATE_BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0;
reg signed [11:0] reference_i=0,reference_q=0;
reg [95:0] phases=0;
reg [15:0] input_tag=0;
wire output_valid,clipped;
wire [71:0] coefficients;
wire [15:0] output_tag;
starlink_glrt_verify_rotate3 #(.OSCILLATOR_FILE("OSCILLATOR_PATH")) dut(.*);
integer fd,rc;
reg [4095:0] path;
always @(posedge clk) if(output_valid && resetn && !flush)
 $display("R %d %d %d %d %d %d %d %d",output_tag,
 $signed(coefficients[0+:12]),$signed(coefficients[12+:12]),
 $signed(coefficients[24+:12]),$signed(coefficients[36+:12]),
 $signed(coefficients[48+:12]),$signed(coefficients[60+:12]),clipped);
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %d\n",input_valid,reference_i,reference_q,phases,input_tag);
  if(rc!=5) $fatal;
  @(negedge clk);
 end
 input_valid=0;repeat(6) @(negedge clk);
 // Flush two in-flight rotations before either can become an output.
 input_valid=1;input_tag=65000;@(negedge clk);input_tag=65001;@(negedge clk);
 flush=1;@(negedge clk);flush=0;input_valid=0;repeat(6) @(negedge clk);
 if(output_valid) $fatal(1,"flush did not drain");
 $finish;
end
endmodule
'''


def test_three_hypothesis_rotation_rounding_clipping_and_flush(tmp_path):
    rng = random.Random(1024250)
    wave = [(round(math.cos(2 * math.pi * k / 1024) * 1024),
             round(math.sin(2 * math.pi * k / 1024) * 1024)) for k in range(1024)]
    rom = "".join(f"{(c & 4095) | ((s & 4095) << 12):06x}\n" for c, s in wave)
    rows, expected = [], []
    for tag in range(2500):
        i, q = rng.randrange(-2048, 2048), rng.randrange(-2048, 2048)
        phases = [rng.randrange(2**32) for _ in range(3)]
        packed = sum(phase << (32 * lane) for lane, phase in enumerate(phases))
        rows.append(f"1 {i} {q} {packed:x} {tag}\n")
        outputs, clipped = [], 0
        for phase in phases:
            c, s = wave[phase >> 22]
            for value in ((i * c - q * s + 512) >> 10, (i * s + q * c + 512) >> 10):
                clipped |= int(not -2048 <= value <= 2047)
                outputs.append((value + 2048) % 4096 - 2048)
        expected.append([tag, *outputs, clipped])
        if tag % 7 == 0:
            rows.append("0 0 0 0 0\n")
    actual = simulate(tmp_path, "rotate3", ROTATE_BENCH, rows, {"oscillator.mem": rom})
    assert actual == expected
    assert any(row[-1] for row in actual)
