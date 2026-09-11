"""Shared coarse correlation lanes: scalar integer truth and malformed jobs."""
import random
import subprocess
from pathlib import Path


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_first=0,input_last=0;
reg signed [15:0] input_i=0,input_q=0;
reg [143:0] coefficients=0;
reg [31:0] input_tag=0;
wire output_valid,fault;
wire [191:0] correlation_i,correlation_q;
wire [34:0] sample_energy;
wire [31:0] output_tag;
starlink_glrt_coarse_mac6 dut(.*);
integer fd,rc,rs,fl,vi,fi,la,si,sq;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d %d %d %d %h %h\n",rs,fl,vi,fi,la,si,sq,coefficients,input_tag);
  if(rc!=9) $fatal;
  resetn=rs;flush=fl;input_valid=vi;input_first=fi;input_last=la;input_i=si;input_q=sq;
  @(posedge clk);#1;
  if(output_valid) $display("R %h %h %h %h",output_tag,correlation_i,correlation_q,sample_energy);
  if(fault) $display("F");
  @(negedge clk);
 end
 $finish;
end
endmodule
'''


def test_six_lanes_extrema_bubbles_adjacent_jobs_and_fault_fence(tmp_path):
    rng=random.Random(6000750)
    idle='1 0 0 0 0 0 0 0 0'
    rows=['0 0 0 0 0 0 0 0 0']*2
    expected=[]
    def job(tag,bubbles=False):
        re=[0]*6;im=[0]*6;energy=0
        for tap in range(11):
            i,q=(-32768,-32768) if tag==0 else (rng.randrange(-32768,32768),rng.randrange(-32768,32768))
            coeff=[(-2048,2047) if tag==0 else (rng.randrange(-2048,2048),rng.randrange(-2048,2048)) for _ in range(6)]
            packed=sum(((a&4095)|((b&4095)<<12))<<(lane*24) for lane,(a,b) in enumerate(coeff))
            rows.append(f'1 0 1 {int(tap==0)} {int(tap==10)} {i} {q} {packed:x} {tag:x}')
            if bubbles and tap%3==1:rows.extend([idle]*2)
            energy+=i*i+q*q
            for lane,(a,b) in enumerate(coeff):
                re[lane]+=i*a+q*b;im[lane]+=q*a-i*b
        expected.append((tag,sum((x&0xffffffff)<<(lane*32) for lane,x in enumerate(re)),
            sum((x&0xffffffff)<<(lane*32) for lane,x in enumerate(im)),energy))
    for tag in range(100):job(tag,bubbles=tag%2==0)
    rows.extend([idle]*3)
    # Last on a first tap is malformed. A subsequent complete-looking job is
    # fenced until flush, and its output may not escape.
    rows.append('1 0 1 1 1 5 6 1 ffffffff')
    job(1000);expected.pop()
    rows.extend([idle]*2)
    rows.append('1 1 0 0 0 0 0 0 0')
    job(2000)
    rows.extend([idle]*3)
    stimulus=tmp_path/'input.txt';stimulus.write_text('\n'.join(rows)+'\n')
    bench=tmp_path/'tb.sv';bench.write_text(BENCH)
    executable=tmp_path/'sim'
    rtl=Path(__file__).parents[2]/'hdl/library/starlink_glrt/starlink_glrt_coarse_mac6.v'
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(bench),str(rtl)],
        check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(executable),f'+INPUT={stimulus}'],check=True,
        capture_output=True,text=True,timeout=20)
    actual=[tuple(int(v,16) for v in line.split()[1:]) for line in result.stdout.splitlines() if line.startswith('R ')]
    assert actual==expected
    assert result.stdout.count('\nF\n')>0
