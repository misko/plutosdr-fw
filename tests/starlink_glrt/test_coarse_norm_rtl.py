"""Bit-exact pipeline throughput/flush checks against Python integer math."""
import math
import random
import subprocess
from pathlib import Path


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0;
reg [63:0] numerator_power=0,denominator_power=0;
reg [31:0] input_tag=0;
wire output_valid,zero_energy,ratio_clamped;
wire [16:0] score_q16;
wire [31:0] output_tag;
starlink_glrt_coarse_norm dut(.*);
integer fd,rc,cycle=0,rs,fl,vi;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");
 repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %h %h\n",rs,fl,vi,numerator_power,denominator_power,input_tag);
  if(rc!=6) $fatal;
  resetn=rs;flush=fl;input_valid=vi;
  @(posedge clk);#1;
  if(output_valid) $display("R %d %h %d %d %d",cycle,output_tag,score_q16,zero_energy,ratio_clamped);
  cycle=cycle+1;
  @(negedge clk);
 end
 $finish;
end
endmodule
'''


def test_every_cycle_integer_roots_ratio_latency_and_flush(tmp_path):
    rng=random.Random(600025750)
    powers=[0,1,2,3,4,8,9,15,16,2**32-1,2**32,2**63-1,2**64-1]
    cases=[(n,d) for n in powers for d in powers]
    cases += [(rng.randrange(2**64),rng.randrange(2**64)) for _ in range(2000)]
    rows=['0 0 0 0 0 0']*2
    expected=[]
    pending=[]
    for tag,(numerator,denominator) in enumerate(cases):
        # Interrupt a full pipe, including a valid input on the flush edge.
        flush=tag in (60,591)
        reset=tag==1300
        valid=tag%11!=0
        cycle=len(rows)
        rows.append(f'{int(not reset)} {int(flush)} {int(valid)} {numerator:x} {denominator:x} {tag:x}')
        if flush or reset:
            pending=[]
        elif valid:
            nr,dr=math.isqrt(numerator),math.isqrt(denominator)
            score=min(65536,(nr<<16)//dr) if dr else 0
            pending.append((cycle+47,tag,score,int(dr==0),int(dr!=0 and nr>dr)))
        due=[r for r in pending if r[0]==cycle]
        expected.extend(due)
        pending=[r for r in pending if r[0]>cycle]
    expected.extend(pending)
    rows+=['1 0 0 0 0 0']*50
    stimulus=tmp_path/'input.txt';stimulus.write_text('\n'.join(rows)+'\n')
    bench=tmp_path/'tb.sv';bench.write_text(BENCH)
    executable=tmp_path/'sim'
    root=Path(__file__).parents[2]/'hdl/library/starlink_glrt'
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(bench),
        str(root/'starlink_glrt_coarse_norm.v')],check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(executable),f'+INPUT={stimulus}'],check=True,
        capture_output=True,text=True,timeout=30)
    actual=[]
    for line in result.stdout.splitlines():
        fields=line.split()
        if fields[0]=='R':
            actual.append((int(fields[1]),int(fields[2],16),*map(int,fields[3:])))
    assert actual==expected
    assert len(actual)>1800
