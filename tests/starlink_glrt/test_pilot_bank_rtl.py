from __future__ import annotations

import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT
from .pilot import round_shift, templates

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg resetn=0,flush=0,input_valid=0,input_gap=0,input_support=1,input_tag=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
wire input_accepted,batch_valid,batch_support,batch_tag,halted;
wire [1:0] batch_group;
wire [287:0] batch_values;
wire [63:0] batch_index;
wire [2:0] sticky_fault;
starlink_glrt_pilot_bank #(.INDEX_STRIDE(STRIDE),.TEMPLATE_FILE("TEMPLATE")) dut (.*);
genvar bank;
generate for(bank=0; bank<8; bank=bank+1) begin : row_proof
 localparam [2:0] BANK=bank;
 wire [2:0] lane=(BANK-dut.base_address[2:0])*3;
 wire [7:0] address=dut.base_address+lane*11;
 always @(posedge clk) if(dut.issue && dut.g_bank[bank].read_row !== address[7:3])
  $fatal(1,"bank row differs from original mapping on an issued read");
end endgenerate
integer fd,rc,vi,ga,fl,su,ta,si,sq,cycle=0,accepted_cycle=-1;
reg [63:0] ix;
reg [2047:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"input missing");
 fd=$fopen(path,"r");
 repeat(4) @(negedge clk);
 resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %d %d %h %d %d\n",vi,ga,fl,su,ta,ix,si,sq);
  if(rc!=8) $fatal(1,"bad input");
  input_valid=vi;input_gap=ga;flush=fl;input_support=su;input_tag=ta;
  input_index=ix;input_i=si;input_q=sq;
  @(posedge clk);
  cycle=cycle+1;
  if(input_accepted) accepted_cycle=cycle;
  #1;
  if(batch_valid && cycle!=accepted_cycle+15+batch_group*11)
   $fatal(1,"bank changed the valid batch cycle");
  if(batch_valid) $display("B %h %d %d %d %h",batch_index,batch_group,batch_tag,batch_support,batch_values);
  @(negedge clk);
 end
 $display("S %d %d",sticky_fault,halted);
 $finish;
end
endmodule
'''


@pytest.fixture(scope="session")
def banks(tmp_path_factory):
    root = tmp_path_factory.mktemp("pilot-bank-compile")
    cache = {}
    def get(stride, edge):
        key = (stride, edge)
        if key not in cache:
            bench = root/f"tb_{stride}_{edge}.sv"
            bench.write_text(BENCH.replace("(STRIDE)", f"({stride})").replace(
                '"TEMPLATE"', f'"{BANK_ROOT}/pilot_2500000_{edge}_q7.mem"'))
            executable = root/f"sim_{stride}_{edge}"
            built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                str(bench), str(BANK_ROOT/"starlink_glrt_pilot_bank.v")], capture_output=True,text=True)
            assert built.returncode == 0, built.stdout+built.stderr
            cache[key] = executable
        return cache[key]
    return get


def records(values, stride, first, spacing=40):
    rows = []
    for j,(i,q) in enumerate(values):
        rows.append(f"1 0 0 1 {j%2} {first+j*stride:x} {i} {q}")
        rows.extend(["0 0 0 1 0 0 0 0"]*(spacing-1))
    return rows+["0 0 0 1 0 0 0 0"]*50


def run(bank, rows, tmp_path):
    path=tmp_path/"input.txt"
    path.write_text("\n".join(rows)+"\n")
    result=subprocess.run(["vvp",str(bank),f"+INPUT={path}"],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    batches=[]
    status=None
    for line in result.stdout.splitlines():
        words=line.split()
        if words[0]=="B":
            batches.append((int(words[1],16),int(words[2]),int(words[3]),int(words[4]),int(words[5],16)))
        elif words[0]=="S":
            status=tuple(map(int,words[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)
    assert status is not None
    return batches,status


@pytest.mark.parametrize("stride",[1,2,4,10,24])
@pytest.mark.parametrize("edge",["upper","lower"])
@pytest.mark.parametrize("spacing",[39,40])
def test_all_sixteen_correlations_every_sample_bit_exact(stride,edge,spacing,banks,tmp_path):
    rng=np.random.default_rng(11814)
    values=rng.integers(-32768,32768,(600,2),dtype=np.int16)
    first=(1<<47)+27
    batches,status=run(banks(stride,edge),records(values,stride,first,spacing),tmp_path)
    assert status==(0,0)
    assert len(batches)==3*len(values)
    padded=np.concatenate((np.zeros((175,2),dtype=np.int16),values)).astype(np.int64)
    bank=templates(2500000,edge)[:16].astype(np.int64)
    for j in range(len(values)):
        x=padded[j:j+176].reshape(16,11,2)
        real=np.sum(x[:,:,0]*bank[:,:,0]+x[:,:,1]*bank[:,:,1],axis=1)
        imag=np.sum(x[:,:,1]*bank[:,:,0]-x[:,:,0]*bank[:,:,1],axis=1)
        expected=round_shift(np.column_stack((real,imag)),4)
        for group in range(3):
            index,g,tag,support,packed=batches[3*j+group]
            assert (index,g,tag,support)==(first+j*stride,group,j%2,int(j>=175))
            for lane in range(6):
                word=(packed>>(48*lane))&((1<<48)-1)
                components=[word&0xffffff,word>>24]
                components=[v-(1<<24) if v&(1<<23) else v for v in components]
                symbol=group*6+lane
                assert components==(expected[symbol].tolist() if symbol<16 else [0,0])


@pytest.mark.parametrize("spacing",[1,20,38])
def test_bank_overspeed_is_explicit_and_sticky(spacing,banks,tmp_path):
    rows=records(np.ones((100,2),dtype=np.int16),1,0,spacing)
    rows += ["0 0 1 1 0 0 0 0"]+records(np.ones((100,2),dtype=np.int16),1,100)
    _,status=run(banks(1,"upper"),rows,tmp_path)
    assert status[0]&2 and status[1]==1


@pytest.mark.parametrize("stride", [1, 2, 4, 10, 24])
def test_flush_during_issue_restarts_unreset_rows_and_cold_history(stride,banks,tmp_path):
    rng=np.random.default_rng(93017)
    first=rng.integers(-32768,32768,(320,2),dtype=np.int16)
    second=rng.integers(-32768,32768,(300,2),dtype=np.int16)
    simulator=banks(stride,"upper")
    first_rows=records(first,stride,19,39)
    second_rows=records(second,stride,(1<<42)+73,40)
    expected_first,status=run(simulator,first_rows,tmp_path)
    assert status==(0,0)
    expected_second,status=run(simulator,second_rows,tmp_path)
    assert status==(0,0)
    # Abort before the first of the three batches; all rows already advanced.
    partial=[f"1 0 0 1 0 {19+len(first)*stride:x} 1234 -4321"]
    partial += ["0 0 0 1 0 0 0 0"]*5
    rows=first_rows+partial+["0 0 1 1 0 0 0 0"]+second_rows
    actual,status=run(simulator,rows,tmp_path)
    assert status==(0,0)
    assert actual==expected_first+expected_second
