"""Full-width exact energy products and every occupied-slot interruption."""
from pathlib import Path
import random
import subprocess

import pytest


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0;
reg [42:0] input_a=0;
reg [34:0] input_b=0;
wire busy,output_valid,fault;
wire [77:0] product;
starlink_glrt_verify_energy_serial dut(.*);
integer fd,rc,r,f,v;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %h\n",r,f,v,input_a,input_b);if(rc!=5) $fatal;
  resetn=r;flush=f;input_valid=v;@(posedge clk);#1;
  if(output_valid) $display("R %h",product);
  if(fault) $display("F");
  @(negedge clk);
 end
 $finish;
end
endmodule
'''
IDLE='1 0 0 123456789ab 123456789'
RESET='0 0 0 0 0'
FLUSH='1 1 0 0 0'


def simulate(tmp_path,rows):
    (tmp_path/'tb.sv').write_text(BENCH)
    (tmp_path/'input.txt').write_text('\n'.join(rows)+'\n')
    rtl=Path(__file__).parents[2]/'hdl/library/starlink_glrt/starlink_glrt_verify_window3.v'
    executable=tmp_path/'sim'
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(tmp_path/'tb.sv'),str(rtl)],
                   check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(executable),f'+INPUT={tmp_path/"input.txt"}'],
                          check=True,capture_output=True,text=True,timeout=20)
    (tmp_path/'simulation.log').write_text(result.stdout+result.stderr)
    return [int(line.split()[1],16) for line in result.stdout.splitlines() if line.startswith('R ')],result.stdout


def test_exact_full_width_products_and_minimum_spacing(tmp_path):
    rng=random.Random(433517)
    a_values=[0,1,2**17-1,2**17,2**34-1,2**34,2**43-1]
    b_values=[0,1,2**17-1,2**17,2**34,2**35-1]
    pairs=[(a,b) for a in a_values for b in b_values]
    pairs += [(rng.randrange(2**43),rng.randrange(2**35)) for _ in range(1000)]
    rows=[RESET]*2
    for a,b in pairs:
        rows += [f'1 0 1 {a:x} {b:x}']+[IDLE]*3
    actual,log=simulate(tmp_path,rows+[IDLE])
    assert actual==[a*b for a,b in pairs] and '\nF\n' not in log


@pytest.mark.parametrize('slot',[1,2,3])
@pytest.mark.parametrize('interrupt',['collision','flush','reset'])
def test_every_occupied_slot_fences_partial_results_and_recovers(tmp_path,slot,interrupt):
    first='1 0 1 7ffffffffff 7ffffffff'
    damage={'collision':'1 0 1 123 456','flush':FLUSH,'reset':RESET}[interrupt]
    rows=[RESET,first]+[IDLE]*(slot-1)+[damage]+[IDLE]*5
    rows += [FLUSH,'1 0 1 123456 789abc']+[IDLE]*4
    actual,log=simulate(tmp_path,rows)
    assert actual==[0x123456*0x789abc]
    assert ('\nF\n' in log)==(interrupt=='collision')
