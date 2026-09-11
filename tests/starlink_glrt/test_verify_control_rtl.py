"""Autonomous CFO job scheduling and detection gates with an independent oracle."""
from pathlib import Path
import subprocess

import pytest


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,arm=0,candidate_valid=0,candidates_done=0;
reg [2:0] candidate_rank=0;
reg [11:0] candidate_epoch=0;
reg [3:0] candidate_frequency=0;
reg [16:0] candidate_score=0;
wire candidate_ready,busy,fault,done,job_valid,score_ready,output_valid,output_decision;
reg job_ready=0,score_valid=0,score_done=0,score_fault=0,output_ready=1;
wire [11:0] job_epoch;
wire signed [12:0] job_cfo_units;
wire job_step_500;
wire [8:0] job_frequency_count;
wire [1:0] job_subset;
reg [8:0] score_frequency=0;
reg [16:0] score_q16=0;
reg [2:0] score_support=0;
wire [4:0] output_reasons;
wire [2:0] output_rank,output_support;
wire [11:0] output_epoch;
wire [3:0] output_coarse_frequency;
wire [16:0] output_coarse_score,output_acquire,output_verify,output_control,output_conditioned;
wire signed [12:0] output_cfo_units;
starlink_glrt_verify_control dut(.*);
integer fd,rc,n,c,j=0,f,e,base,step,count,subset,score,support,cycles=0,waits=0;
reg [4095:0] path;
reg held=0;
reg [125:0] previous;
wire [125:0] evidence={output_decision,output_reasons,output_rank,output_epoch,
 output_coarse_frequency,output_coarse_score,output_cfo_units,output_acquire,
 output_verify,output_control,output_conditioned,output_support};
always @(negedge clk) output_ready=cycles%7<4;
always @(posedge clk) begin
 cycles<=cycles+1;
 if(cycles>500000) $fatal(1,"timeout");
 if(resetn && !flush) begin
  if(held && (!output_valid || evidence!==previous)) $fatal(1,"unstable evidence");
  held<=output_valid && !output_ready;previous<=evidence;
  if(output_valid && output_ready)
   $display("R %d %d %d %d %d %d %d %d %d %d %d %d",output_decision,
    output_reasons,output_rank,output_epoch,output_coarse_frequency,output_coarse_score,
    output_cfo_units,output_acquire,output_verify,output_control,output_conditioned,output_support);
 end else held<=0;
end
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal;
 fd=$fopen(path,"r");rc=$fscanf(fd,"%d\n",n);if(rc!=1) $fatal;
 repeat(3) @(negedge clk);resetn=1;arm=1;@(negedge clk);arm=0;
 for(c=0;c<n;c=c+1) begin
  rc=$fscanf(fd,"%d %d %d\n",e,f,score);if(rc!=3 || !candidate_ready) $fatal;
  candidate_valid=1;candidate_rank=c;candidate_epoch=e;candidate_frequency=f;candidate_score=score;
  candidates_done=c==n-1;@(negedge clk);
 end
 candidate_valid=0;
 if(n==0) begin candidates_done=1;@(negedge clk);end
 candidates_done=0;
 for(j=0;j<n*5;j=j+1) begin
  rc=$fscanf(fd,"%d %d %d %d %d\n",e,base,step,count,subset);if(rc!=5) $fatal;
  while(!job_valid && !fault) @(negedge clk);
  repeat(3) begin
   if(!job_valid || job_epoch!=e || job_cfo_units!=base || job_step_500!=step ||
      job_frequency_count!=count || job_subset!=subset)
      $fatal(1,"job %d mismatches: %d %d %d %d %d",j,job_epoch,job_cfo_units,job_step_500,job_frequency_count,job_subset);
   @(negedge clk);
  end
  job_ready=1;@(negedge clk);job_ready=0;
  for(f=0;f<count;f=f+1) begin
   rc=$fscanf(fd,"%d %d\n",score,support);if(rc!=2 || !score_ready) $fatal;
   score_valid=1;score_frequency=f;score_q16=score;score_support=support;
   score_done=(j%2==1 && f==count-1);
   @(negedge clk);score_valid=0;score_done=0;
   if(f%7==0) @(negedge clk);
  end
  if(j%2==0) begin score_done=1;@(negedge clk);score_done=0;end
 end
 while(!done && !fault) @(negedge clk);
 if(!done || busy || fault) $fatal(1,"bad closure");
 // Fault/reset must cancel a partially collected window.
 arm=1;@(negedge clk);@(negedge clk);arm=0;
 if(!fault || output_valid || job_valid) $fatal(1,"busy restart not fenced");
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || busy || output_valid) $fatal(1,"flush failed");
 $display("PASS");$finish;
end
endmodule
'''


def make_case(candidates):
    """Supply arbitrary scorer responses; derive scheduling/decision separately."""
    jobs=[];records=[]
    for rank,case in enumerate(candidates):
        epoch,frequency,coarse=case['coarse']
        coarse_cfo=(frequency-5)*800
        grid=list(range(max(-4000,coarse_cfo-800),min(4000,coarse_cfo+800)+1,5))
        target=case.get('target',coarse_cfo)
        def scores(values):
            return [int(case.get('peak',10000)-min(case.get('peak',10000),
                min(abs(v-t) for t in case.get('targets',(target,))))) for v in values]
        responses=scores(grid)
        center=max(zip(responses,grid),key=lambda x:(x[0],-abs(x[1]),-x[1]))[1]
        jobs.append(((epoch,grid[0],1,len(grid),0),responses))
        fine=list(range(max(-4000,center-20),min(4000,center+20)+1))
        conditioned=scores(fine)
        best,final=max(zip(conditioned,fine),key=lambda x:(x[0],-abs(x[1]),-x[1]))
        jobs.append(((epoch,fine[0],0,len(fine),2),conditioned))
        acq,verify,control=case.get('evidence',(11000,10000,2000))
        support=case.get('support',3)
        for sub,value in ((0,acq),(1,verify),(3,control)):
            jobs.append(((epoch,final,0,1,sub),[value]))
        records.append([0,0,rank,epoch,frequency,coarse,final,acq,verify,control,best,support])
    if not records:
        decision=[1,1]+[0]*10
    else:
        winner=max(records,key=lambda r:(r[8]-r[9],r[8],r[10],r[7],-abs(r[6]),-r[3]))
        flags=(2 if winner[11]<2 else 0)|(4 if winner[8]<5243 else 0)|(8 if winner[8]-winner[9]<2622 else 0)
        for other in records:
            distance=abs(winner[3]-other[3])*3
            distance=min(distance,abs(10000-distance))
            if (distance>12 or abs(winner[6]-other[6])>20) and winner[8]-winner[9]-(other[8]-other[9])<656:
                flags|=16
        decision=[1,flags,*winner[2:]]
    rows=[f'{len(candidates)}\n',*(' '.join(map(str,c['coarse']))+'\n' for c in candidates)]
    for index,(descriptor,values) in enumerate(jobs):
        rows.append(' '.join(map(str,descriptor))+'\n')
        rows.extend(f'{value} {candidates[index//5].get("support",3)}\n' for value in values)
    return ''.join(rows),records+[decision]


@pytest.fixture(scope='module')
def controller_binary(tmp_path_factory):
    path=tmp_path_factory.mktemp('verify-control')
    (path/'tb.sv').write_text(BENCH)
    rtl=Path(__file__).parents[2]/'hdl/library/starlink_glrt/starlink_glrt_verify_control.v'
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(path/'sim'),str(path/'tb.sv'),str(rtl)],capture_output=True,text=True)
    assert build.returncode==0,build.stdout+build.stderr
    return path/'sim'


@pytest.mark.parametrize('cases',[
    [],[{'coarse':(100,5,20000)}],
    [{'coarse':(100,5,20000),'evidence':(6000,5242,0)}],
    [{'coarse':(100,5,20000),'evidence':(6000,5243,2622)}],
    [{'coarse':(100,5,20000),'evidence':(6000,5243,2621)}],
    [{'coarse':(100,5,20000),'support':1}],
    [{'coarse':(100,5,20000),'peak':0,'evidence':(0,0,0)}],
    [{'coarse':(100,5,20000),'target':-2.5}],
    [{'coarse':(100,5,20000),'targets':(-10,10)}],
    [{'coarse':(100,5,20000)},{'coarse':(200,5,19000)}],
    [{'coarse':(0,5,20000)},{'coarse':(3332,5,19000)}],
    [{'coarse':(0,5,20000)},{'coarse':(3329,5,19000)}],
    [{'coarse':(100,5,20000)},{'coarse':(104,5,19000),'target':20}],
    [{'coarse':(100,5,20000)},{'coarse':(104,5,19000),'target':21}],
    [{'coarse':(100+k*100,f,30000-k),'target':(f-5)*800,'evidence':(10000,10000+k*700,2000)}
     for k,f in enumerate((0,10,1,9,2,8,3,7))],
])
def test_autonomous_jobs_ties_evidence_and_acceptance(tmp_path,controller_binary,cases):
    stimulus,expected=make_case(cases)
    path=tmp_path/'case.txt';path.write_text(stimulus)
    run=subprocess.run(['vvp',str(controller_binary),f'+INPUT={path}'],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr
    actual=[list(map(int,line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('R ')]
    assert actual==expected
    assert 'PASS' in run.stdout


@pytest.fixture(scope='module')
def fault_binary(tmp_path_factory):
    path=tmp_path_factory.mktemp('verify-control-fault')
    source=BENCH.split('initial begin',1)[0]+r'''
initial begin
 if(!$value$plusargs("MODE=%d",n)) $fatal;
 repeat(3) @(negedge clk);resetn=1;arm=1;@(negedge clk);arm=0;
 candidate_valid=1;candidates_done=1;candidate_epoch=100;candidate_frequency=5;candidate_score=20000;
 case(n)
  0:candidate_epoch=3333;1:candidate_frequency=11;2:candidate_rank=1;
  3:candidate_score=65537;4:candidate_score=0;
 endcase
 @(negedge clk);candidate_valid=0;candidates_done=0;
 if(n>=5) begin
  while(!job_valid && !fault) @(negedge clk);
  if(n==9) begin score_valid=1;@(negedge clk);score_valid=0;end
  else begin
   job_ready=1;@(negedge clk);job_ready=0;
   case(n)
    5:score_done=1;
    6:begin score_valid=1;score_frequency=1;end
    7:begin score_valid=1;score_q16=65537;end
    8:begin score_valid=1;score_support=5;end
    10:score_fault=1;
   endcase
   @(negedge clk);score_valid=0;score_done=0;score_fault=0;
  end
 end
 repeat(5) @(negedge clk);
 if(!fault || output_valid || job_valid || candidate_ready || busy) $fatal(1,"malformed input escaped fence mode=%d",n);
 flush=1;@(negedge clk);flush=0;@(negedge clk);
 if(fault || busy || output_valid) $fatal(1,"flush failed");
 $display("FAULT_PASS");$finish;
end
endmodule
'''
    (path/'tb.sv').write_text(source)
    rtl=Path(__file__).parents[2]/'hdl/library/starlink_glrt/starlink_glrt_verify_control.v'
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(path/'sim'),str(path/'tb.sv'),str(rtl)],capture_output=True,text=True)
    assert build.returncode==0,build.stdout+build.stderr
    return path/'sim'


@pytest.mark.parametrize('mode',range(11))
def test_malformed_candidate_score_stream_and_scorer_faults(fault_binary,mode):
    run=subprocess.run(['vvp',str(fault_binary),f'+MODE={mode}'],capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stdout+run.stderr
    assert 'FAULT_PASS' in run.stdout
    assert not any(line.startswith('R ') for line in run.stdout.splitlines())
