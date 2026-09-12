"""Buffered coarse-search integration against independent scalar integer math."""
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from .test_coarse_peaks_rtl import reference as retained_reference

BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,input_valid=0,input_gap=0;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
reg output_ready=1;
reg copy_enable=0;
reg [13:0] copy_address=0;
wire copy_ready,copy_valid;
wire [13:0] copy_offset;
wire [31:0] copy_data;
wire busy,done,fault,output_valid;
wire [63:0] window_first_index;
wire [11:0] output_epoch;
wire output_epoch_left_tie;
wire [3:0] output_frequency;
wire [16:0] output_score;
wire [5:0] output_support;
wire [31:0] rejected_arms;
starlink_glrt_coarse_window #(.EPOCH_COUNT(12),.SOURCE_INDEX_STRIDE(STRIDE),.COEFFICIENT_FILE("COEFF"),.ENERGY_FILE("ENERGY")) dut(.*);
integer fd,rc,si,sq,cycles=0,waits=0;
reg [2047:0] path;
reg held=0;
reg [38:0] previous;
always @(posedge clk) begin
 if(resetn && !flush) begin
  if(held && (!output_valid || {output_epoch,output_frequency,output_score,output_support}!==previous))
    $fatal(1,"output changed under backpressure");
  held<=output_valid && !output_ready;
  previous<={output_epoch,output_frequency,output_score,output_support};
  if(output_valid && output_ready) $display("R %d %d %d %d",output_epoch,output_frequency,output_score,output_support);
 end else held<=0;
end
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
 // Busy admission must count a rejected window without corrupting this one.
 arm=1;@(negedge clk);arm=0;
 while(!done && !fault && waits<100000) begin
  output_ready=waits%7!=0;
  @(negedge clk);waits=waits+1;
 end
 if(fault || !done || rejected_arms!=1 || window_first_index!=64'h10000000000001)
   $fatal(1,"closure failed fault=%d done=%d rejected=%d",fault,done,rejected_arms);
 $display("DONE %d",waits);
 // Copy uses the same RAM read port and returns every original CI16 word.
 $fclose(fd);fd=$fopen(path,"r");
 for(cycles=0;cycles<14000;cycles=cycles+1) begin
  rc=$fscanf(fd,"%d %d\n",si,sq);if(rc!=2 || !copy_ready) $fatal(1,"copy not ready");
  copy_enable=1;copy_address=cycles;@(negedge clk);
  if(!copy_valid || copy_offset!=cycles || $signed(copy_data[15:0])!=si || $signed(copy_data[31:16])!=sq)
    $fatal(1,"copy mismatch at %d",cycles);
 end
 copy_enable=0;@(negedge clk);if(copy_valid) $fatal(1,"unexpected copy response");
 // A source gap during capture must fence the job before any result.
 arm=1;@(negedge clk);arm=0;input_valid=1;input_gap=1;
 @(negedge clk);input_valid=0;input_gap=0;
 if(!fault || output_valid) $fatal(1,"gap not fenced");
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || busy || output_valid) $fatal(1,"flush failed");
 $finish;
end
endmodule
'''


@pytest.mark.parametrize("with_peaks", [False, True])
@pytest.mark.parametrize("stride", [1,24])
@pytest.mark.parametrize("full_scale", [False, True])
@pytest.mark.parametrize("folded", [False, True])
def test_complete_coarse_grid_prefix_reuse_backpressure_and_source_gap(tmp_path, with_peaks, stride, full_scale, folded):
    rng=np.random.default_rng(6014250)
    values=rng.integers(-128,129,(14000,2),dtype=np.int16)
    if full_scale:
        # Exercise signed square operands at both CI16 limits as well as zero;
        # asymmetric I/Q catches cross-lane or cross-group pipeline pairing.
        values=rng.choice(np.array([-32768,-32767,-1,0,1,32766,32767],dtype=np.int16),
                          size=(14000,2))
    coefficients=rng.integers(-512,513,(12,12,11,2),dtype=np.int64)
    coefficients[:,11]=0
    coeff_path=tmp_path/'coeff.mem';energy_path=tmp_path/'energy.mem'
    words=[];energies=[]
    for symbol in range(12):
        for group in range(2):
            block=coefficients[symbol,group*6:group*6+6]
            energies.append(sum(int(np.sum(c*c))<<(27*lane) for lane,c in enumerate(block)))
            for tap in range(11):
                words.append(sum(((int(c[tap,0])&4095)|((int(c[tap,1])&4095)<<12))<<(24*lane)
                    for lane,c in enumerate(block)))
    coeff_path.write_text(''.join(f'{word:036x}\n' for word in words))
    energy_path.write_text(''.join(f'{word:041x}\n' for word in energies))
    stimulus=tmp_path/'iq.txt';stimulus.write_text(''.join(f'{i} {q}\n' for i,q in values))
    expected=[]
    for epoch in range(12):
        totals=[0]*11;support=0
        for symbol in range(12):
            for frame in range(5):
                start=epoch+22+symbol*286+round(frame*2500000/750)
                if start+11>14000:continue
                support+=1
                samples=values[start:start+11].astype(np.int64)
                energy=int(np.sum(samples*samples))
                for frequency in range(11):
                    c=coefficients[symbol,frequency]
                    real=int(np.sum(samples[:,0]*c[:,0]+samples[:,1]*c[:,1]))
                    imag=int(np.sum(samples[:,1]*c[:,0]-samples[:,0]*c[:,1]))
                    numerator=math.isqrt(real*real+imag*imag)
                    denominator=math.isqrt(energy*int(np.sum(c*c)))
                    totals[frequency]+=min(65536,(numerator<<16)//denominator) if denominator else 0
        expected.extend((epoch,f,total//support,support) for f,total in enumerate(totals))
    source = BENCH
    names = ['window', 'mac6', 'norm']
    if with_peaks:
        source = source.replace('starlink_glrt_coarse_window #', 'starlink_glrt_coarse_search #')
        source = source.replace('wire [5:0] output_support;', 'wire [2:0] output_rank;')
        source = source.replace('output_support', 'output_rank')
        source = source.replace('[38:0] previous', '[35:0] previous')
        # Search-wrapper fault latching takes one additional edge.
        source = source.replace('if(!fault || output_valid)', '@(negedge clk);if(!fault || output_valid)')
        source = source.replace('$finish;', r'''
 // A later discontinuity must invalidate feedback from a complete old window.
 arm=1;@(negedge clk);arm=0;input_valid=1;input_i=0;input_q=0;
 for(cycles=0;cycles<14000;cycles=cycles+1) begin
  input_index=cycles*24;@(negedge clk);
 end
 input_index=14001*24;@(negedge clk);input_valid=0;
 if(!fault || output_valid) $fatal(1,"compute-time discontinuity not fenced");
 $finish;
''')
        names.extend(['peaks', 'search'])
        rows = [[item[2] for item in expected[e*11:e*11+11]] for e in range(12)]
        expected = [(epoch, frequency, score, rank) for rank, epoch, frequency, score in retained_reference(rows)]
    source=source.replace('(STRIDE)',f'({stride})').replace('cycles*24',f'cycles*{stride}').replace('14001*24',f'14001*{stride}')
    source=source.replace('.EPOCH_COUNT(12)',f'.EPOCH_COUNT(12),.FOLDED_NORM({int(folded)})')
    bench=tmp_path/'tb.sv';bench.write_text(source.replace('"COEFF"',f'"{coeff_path}"').replace('"ENERGY"',f'"{energy_path}"'))
    executable=tmp_path/'sim'
    root=Path(__file__).parents[2]/'hdl/library/starlink_glrt'
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(bench),
        *[str(root/f'starlink_glrt_coarse_{name}.v') for name in names]],
        check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(executable),f'+INPUT={stimulus}'],check=True,
        capture_output=True,text=True,timeout=60)
    (tmp_path/'simulation.log').write_text(result.stdout+result.stderr)
    actual=[tuple(map(int,line.split()[1:])) for line in result.stdout.splitlines() if line.startswith('R ')]
    assert actual==expected
    assert 'DONE' in result.stdout
