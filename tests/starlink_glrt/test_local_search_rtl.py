"""Overlapping autonomous coarse/verification windows on one continuous stream."""
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest

from .test_coarse_peaks_rtl import reference as peaks_reference
from .test_verify_window_rtl import expected_scores, write_roms


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,input_valid=0,input_gap=0,output_ready=1;
reg signed [15:0] input_i=0,input_q=0;
reg [63:0] input_index=0;
wire busy,arm_ready,done,fault,output_valid,output_decision;
wire [31:0] rejected_arms;
wire [63:0] window_first_index;
wire [4:0] output_reasons;
wire [2:0] output_rank,output_support;
wire [11:0] output_epoch;
wire [3:0] output_coarse_frequency;
wire [16:0] output_coarse_score,output_acquire,output_verify,output_control,output_conditioned;
wire signed [12:0] output_cfo_units;
starlink_glrt_local_search #(.EPOCH_COUNT(64),.COEFFICIENT_FILE("COARSE"),
 .COARSE_ENERGY_FILE("COARSE_ENERGY"),.PILOT_FILE("PILOT"),
 .VERIFY_ENERGY_FILE("ENERGY"),.OSCILLATOR_FILE("WAVE")) dut(.*);
reg [31:0] samples[0:27999];
reg [4095:0] path;
integer cycles=0,n=0,divider=0,decisions=0,inject_gap=0,require_overlap=0,overlapped=0;
reg driving=0,held=0;
reg [189:0] previous;
wire [189:0] evidence={window_first_index,output_decision,output_reasons,output_rank,output_epoch,
 output_coarse_frequency,output_coarse_score,output_cfo_units,output_acquire,
 output_verify,output_control,output_conditioned,output_support};
always @(posedge clk) begin
 cycles<=cycles+1;
 if(driving && arm && n!=100) begin
  if(!arm_ready) $fatal(1,"window not admitted n=%d fault=%d owned=%d",n,fault,dut.coarse_owned);
  if(n==50000 && busy) overlapped=1;
 end
 if(cycles>30000000) $fatal(1,"timeout n=%d decisions=%d busy=%d fault=%d",n,decisions,busy,fault);
 if(resetn && !flush && !fault && !input_gap) begin
  if(held && (!output_valid || evidence!==previous)) $fatal(1,"unstable window/evidence");
  held<=output_valid && !output_ready;previous<=evidence;
  if(output_valid && output_ready) begin
   $display("R %d %d %d %d %d %d %d %d %d %d %d %d %d",window_first_index,
    output_decision,output_reasons,output_rank,output_epoch,output_coarse_frequency,output_coarse_score,
    output_cfo_units,output_acquire,output_verify,output_control,output_conditioned,output_support);
   if(output_decision) decisions<=decisions+1;
  end
 end else held<=0;
end
always @(negedge clk) if(driving) begin
 output_ready=cycles%11<7;
 arm=0;input_valid=0;input_gap=0;
 if(divider==0 && (n==0 || n==50000 || n==100)) begin
  arm=1;
 end
 if(divider==39) begin
  divider=0;input_valid=1;input_index=64'h20000000000003+n;
  if(n<14000) {input_q,input_i}=samples[n];
  else if(n>=50000 && n<64000) {input_q,input_i}=samples[14000+n-50000];
  else begin input_i=0;input_q=0;end
  if(inject_gap!=0 && n==60000) input_gap=1;
  n=n+1;
 end else divider=divider+1;
end
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 if($value$plusargs("GAP=%d",inject_gap)) begin end
 if($value$plusargs("OVERLAP=%d",require_overlap)) begin end
 $readmemh(path,samples);repeat(3) @(negedge clk);resetn=1;
 @(posedge clk);driving=1;
 if(inject_gap!=0) begin
  wait(fault);@(posedge clk);driving=0;@(negedge clk);input_valid=0;input_gap=0;arm=0;
  if(decisions!=0 || output_valid) $fatal(1,"incomplete window escaped gap fence");
 end else begin
  wait(decisions==2);@(posedge clk);driving=0;@(negedge clk);input_valid=0;arm=0;
  while(busy && !fault) @(negedge clk);
  repeat(3) @(negedge clk);
  if(fault || busy || !arm_ready || rejected_arms!=1 || (require_overlap!=0 && !overlapped))
    $fatal(1,"closure/overlap failed busy=%d fault=%d rejects=%d overlap=%d",busy,fault,rejected_arms,overlapped);
  // An index discontinuity while a fresh window is owned fences both stages.
  arm=1;@(negedge clk);arm=0;input_valid=1;input_index=input_index+17;
  @(negedge clk);input_valid=0;repeat(3) @(negedge clk);
  if(!fault || output_valid) $fatal(1,"implicit source gap not fenced");
 end
 flush=1;@(negedge clk);flush=0;repeat(4) @(negedge clk);
 if(fault || busy || output_valid || !arm_ready || rejected_arms!=0) $fatal(1,"flush failed");
 $display("PASS %d",cycles);$finish;
end
endmodule
'''


def coarse_grid(iq, coefficients):
    rows=[]
    for epoch in range(64):
        totals=[0]*11;pairs=0
        for symbol in range(12):
            for offset in (0,3333,6667,10000,13333):
                start=epoch+22+symbol*286+offset
                if start+11>14000:continue
                pairs+=1;samples=iq[start:start+11].astype(np.int64)
                energy=int(np.sum(samples*samples))
                for frequency in range(11):
                    c=coefficients[symbol,frequency]
                    real=int(np.sum(samples[:,0]*c[:,0]+samples[:,1]*c[:,1]))
                    imag=int(np.sum(samples[:,1]*c[:,0]-samples[:,0]*c[:,1]))
                    denominator=math.isqrt(energy*int(np.sum(c*c)))
                    totals[frequency]+=min(65536,(math.isqrt(real*real+imag*imag)<<16)//denominator) if denominator else 0
        rows.append([value//pairs for value in totals])
    return rows


def reference(iq,coefficients,pilot,wave,subsets):
    rows=coarse_grid(iq,coefficients);records=[]
    for rank,raw_epoch,frequency,coarse in peaks_reference(rows):
        epoch=raw_epoch-int(raw_epoch>0 and rows[raw_epoch-1][frequency]==coarse)
        base=(frequency-5)*800
        def evaluate(start,step,count,subset):
            return expected_scores(iq,pilot,wave,subsets,[(epoch,start,step==5,count,subset)])
        start=max(-4000,base-800);count=(min(4000,base+800)-start)//5+1
        values=evaluate(start,5,count,0)
        center=max(values,key=lambda r:(r[2],-abs(start+r[1]*5),-(start+r[1]*5)))[1]*5+start
        start=max(-4000,center-20);count=min(4000,center+20)-start+1
        values=evaluate(start,1,count,2)
        best=max(values,key=lambda r:(r[2],-abs(start+r[1]),-(start+r[1])))
        final=start+best[1];conditioned=best[2]
        acq=evaluate(final,1,1,0)[0];verify=evaluate(final,1,1,1)[0];control=evaluate(final,1,1,3)[0]
        records.append([0,0,rank,epoch,frequency,coarse,final,acq[2],verify[2],control[2],conditioned,min(verify[3],control[3])])
    if not records:return [[1,1]+[0]*10]
    winner=max(records,key=lambda r:(r[8]-r[9],r[8],r[10],r[7],-abs(r[6]),-r[3]))
    flags=(2 if winner[11]<2 else 0)|(4 if winner[8]<5243 else 0)|(8 if winner[8]-winner[9]<2622 else 0)
    for other in records:
        distance=abs(winner[3]-other[3])*3;distance=min(distance,abs(10000-distance))
        if (distance>12 or abs(winner[6]-other[6])>20) and winner[8]-winner[9]-(other[8]-other[9])<656:flags|=16
    return records+[[1,flags,*winner[2:]]]


@pytest.fixture(scope='module')
def local_engine(tmp_path_factory):
    path=tmp_path_factory.mktemp('local-engine');rng=np.random.default_rng(14000750)
    pilot=np.zeros((8192,2),dtype=np.int64)
    pilot[22:3322]=rng.integers(-600,601,(3300,2))
    pilot[4096+22:4096+3322]=np.roll(pilot[22:3322].reshape(300,11,2),71,axis=0).reshape(3300,2)
    wave,subsets=write_roms(path,pilot)
    coefficients=np.zeros((12,12,11,2),dtype=np.int64)
    for symbol in range(12):
        base=pilot[22+symbol*286:33+symbol*286]
        for f in range(11):
            angle=np.arange(11)*2*np.pi*((f-5)*80000)/2500000
            coefficients[symbol,f,:,0]=np.rint(base[:,0]*np.cos(angle)-base[:,1]*np.sin(angle))
            coefficients[symbol,f,:,1]=np.rint(base[:,0]*np.sin(angle)+base[:,1]*np.cos(angle))
    words=[];energies=[]
    for s in range(12):
        for g in range(2):
            block=coefficients[s,g*6:g*6+6]
            energies.append(sum(int(np.sum(c*c))<<(27*lane) for lane,c in enumerate(block)))
            for t in range(11):
                words.append(sum(((int(c[t,0])&4095)|((int(c[t,1])&4095)<<12))<<(24*lane) for lane,c in enumerate(block)))
    (path/'coarse.mem').write_text(''.join(f'{w:036x}\n' for w in words))
    (path/'coarse_energy.mem').write_text(''.join(f'{e:041x}\n' for e in energies))
    bench=BENCH
    for placeholder,name in (('COARSE','coarse.mem'),('COARSE_ENERGY','coarse_energy.mem'),
                             ('PILOT','pilot.mem'),('ENERGY','energy.mem'),('WAVE','wave.mem')):
        bench=bench.replace(f'"{placeholder}"',f'"{path/name}"')
    (path/'tb.sv').write_text(bench)
    root=Path(__file__).parents[2]/'hdl/library/starlink_glrt'
    sources=[root/f'starlink_glrt_{name}.v' for name in ('local_search','coarse_search','coarse_window',
        'coarse_mac6','coarse_norm','coarse_peaks','verify_control','verify_window3','verify_mac3','verify_rotate3')]
    build=subprocess.run(['verilator','--binary','--timing','--top-module','tb','-Wno-fatal','--Mdir',str(path/'obj'),
        '-o','sim','-j','4',str(path/'tb.sv'),*map(str,sources)],capture_output=True,text=True,timeout=120)
    (path/'build.log').write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stdout+build.stderr
    return path,coefficients,pilot,wave,subsets


@pytest.mark.parametrize('kind',['pilot','zero','gap'])
def test_two_windows_copy_overlap_absolute_coordinates_and_fault_fences(tmp_path,local_engine,kind):
    path,coefficients,pilot,wave,subsets=local_engine
    rng=np.random.default_rng(21300)
    windows=[]
    for epoch,cfo in ((17,123400),(31,-218700)):
        samples=np.zeros(14000,dtype=np.complex128)
        template=pilot[:3333,0]+1j*pilot[:3333,1]
        for offset in (0,3333,6667,10000,13333):
            count=min(3333,14000-offset-epoch)
            if count>0:samples[offset+epoch:offset+epoch+count]=template[:count]
        samples*=8*np.exp(2j*np.pi*np.arange(14000)*cfo/2500000)
        iq=np.rint(np.column_stack((samples.real,samples.imag))+rng.normal(0,20,(14000,2))).astype(np.int16)
        if kind=='zero':iq[:]=0
        windows.append(iq)
    stimulus=tmp_path/'iq.mem'
    stimulus.write_text(''.join(f'{(int(i)&65535)|((int(q)&65535)<<16):08x}\n' for iq in windows for i,q in iq))
    run=subprocess.run([str(path/'obj/sim'),f'+INPUT={stimulus}',f'+GAP={int(kind=="gap")}',
        f'+OVERLAP={int(kind!="zero")}'],capture_output=True,text=True,timeout=90)
    (tmp_path/'simulation.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0,run.stdout+run.stderr
    actual=[list(map(int,line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('R ')]
    if kind!='gap':
        expected=[]
        for index,iq in enumerate(windows):
            records=reference(iq,coefficients,pilot,wave,subsets)
            if kind=='pilot':
                assert records[-1][1]==0
                assert abs(records[-1][6]*100-(123400 if index==0 else -218700))<=100
                assert records[-1][3]==(17 if index==0 else 31)
            expected.extend([[0x20000000000003+index*50000,*r] for r in records])
        assert actual==expected
    else:assert not any(r[1] for r in actual)
    assert 'PASS' in run.stdout
