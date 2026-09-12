"""End-to-end native sample alignment, phase stepping, products and moments."""
from __future__ import annotations

import subprocess

import pytest

from tools.generate_glrt_direct_phase_rom import pack_phase_rom

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_products_rtl import products as product_oracle

BENCH = r'''
`timescale 1ns/1ps
module tb;
localparam N=COUNT_VALUE,SEGMENTS=SEGMENT_VALUE;
localparam C=$clog2(N+1),S=35+$clog2(N),T=S+$clog2(N),E=36+$clog2(N);
localparam PHASES=PHASE_VALUE,PB=PHASES<=1 ? 1 : $clog2(PHASES);
reg clk=0;always #5 clk=~clk;
reg resetn=0,flush=0,job_valid=0,input_valid=0,input_gap=0,input_closed=0,input_clipped=0,result_ready=1;
reg [63:0] job_start=0,input_index=0;
reg [31:0] seed=0,step=0;
reg signed [15:0] ii=0,iq=0;
wire job_ready,active,result_valid;
wire [63:0] result_start;
wire [31:0] result_seed,result_step;
wire [PB-1:0] result_reference_phase;
wire [C-1:0] count;
wire [7:0] fault;
wire signed [S-1:0] ri,rq,di,dq;
wire signed [T-1:0] ti,tq;
wire [E-1:0] energy;
starlink_glrt_native_engine #(.SAMPLE_COUNT(N),.SEGMENT_COUNT(SEGMENTS),
 .REFERENCE_STRIDE(STRIDE_VALUE),.SERIAL_ROTATE(0),.TEMPLATE_FILE("BANK_PATH"),
 .DIRECT_COEFFICIENT_FILE("DIRECT_PATH"),.DIRECT_REFERENCE_PHASES(PHASES)) dut (
 .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_ready(job_ready),
 .job_start(job_start),.job_phase_seed(seed),.job_phase_step(step),.input_valid(input_valid),
 .job_reference_phase(seed[PB-1:0]),.result_reference_phase(result_reference_phase),
 .input_gap(input_gap),.input_closed(input_closed),.input_clipped(input_clipped),
 .input_index(input_index),.input_i(ii),.input_q(iq),.active(active),
 .result_valid(result_valid),.result_ready(result_ready),.result_start(result_start),
 .result_phase_seed(result_seed),.result_phase_step(result_step),.result_count(count),.result_fault(fault),
 .reference_sum_i(ri),.reference_sum_q(rq),.delay_sum_i(di),.delay_sum_q(dq),
 .reference_prefix_integral_i(ti),.reference_prefix_integral_q(tq),.observed_energy(energy));
localparam PAYLOAD=64+64+C+8+4*S+2*T+E+PB;
wire [PAYLOAD-1:0] payload={result_start,result_seed,result_step,count,fault,ri,rq,di,dq,ti,tq,energy,result_reference_phase};
reg stalled=0;
reg [PAYLOAD-1:0] previous_payload;
always @(posedge clk) if(resetn) begin
 if(stalled && (!result_valid || payload !== previous_payload)) $fatal(1,"pending native result changed");
 if(result_valid && job_ready) $fatal(1,"pending native result admitted another job");
 if(job_valid && !job_ready && !flush) $fatal(1,"scheduled native job not admitted");
 stalled <= result_valid && !result_ready;
 previous_payload <= payload;
 if(result_valid && result_ready)
  $display("R %h %h %h %d %d %d %d %d %d %d %d %d %d",result_start,result_seed,result_step,count,fault,ri,rq,di,dq,ti,tq,energy,result_reference_phase);
end else stalled <= 0;
integer fd,rc;
reg [4095:0] path;
initial begin
 if(!$value$plusargs("INPUT=%s",path)) $fatal(1,"missing input");
 fd=$fopen(path,"r");
 repeat(3) @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %d %h %h %h %d %d %d %d %h %d %d %d\n",
   resetn,flush,job_valid,job_start,seed,step,input_valid,input_gap,input_closed,input_clipped,input_index,ii,iq,result_ready);
  if(rc!=14) $fatal(1,"malformed input");
  @(negedge clk);
 end
 resetn=1;flush=0;job_valid=0;input_valid=0;input_gap=0;input_closed=0;input_clipped=0;result_ready=1;
 repeat(100) @(negedge clk);
 if(active || result_valid || !job_ready) $fatal(1,"undrained native engine");
 $finish;
end
endmodule
'''


def bank_for(count):
    return [[[500+3*(n % 3), -300+2*(n % 5)], [5+n % 3, -7], [4, -4], [1, -1]]
        for n in range((count+71)//24)]


def sample(index):
    return index, (index*31 % 65536)-32768, (index*173 % 65536)-32768


def row(*, reset=1, flush=0, job=None, value=None, gap=0, closed=0, clipped=0, ready=1):
    start,seed,step = job or (0,0,0)
    index,i,q = value or (0,0,0)
    return f"{reset} {flush} {int(job is not None)} {start:x} {seed:x} {step:x} {int(value is not None)} {gap} {closed} {clipped} {index:x} {i} {q} {ready}\n"


def expected(job, samples, coefficients, fault=0):
    start,seed,step = job
    values = []
    for n, (index,i,q) in enumerate(samples):
        _,ri,rq,di,dq,_,clipped = coefficients[n]
        assert clipped == 0
        values.append(product_oracle((index,i,q,(seed+n*step) % 2**32,ri,rq,di,dq,0)))
    n = len(values)
    sums = [sum(value[k] for value in values) for k in (1,2,3,4)]
    prefix = [sum((n-1-j)*value[k] for j,value in enumerate(values)) for k in (1,2)]
    return [start,seed,step,n,fault,*sums,*prefix,sum(value[5] for value in values)]


def simulate(tmp_path, count, bank, rows, stride=1, direct=None, phases=1, serial=False):
    bank_path,bench,trace,executable = [tmp_path/name for name in ("bank.mem","tb.sv","input.txt","sim")]
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    direct_path = ""
    if direct is not None:
        direct_path = str(tmp_path/"direct.mem")
        assert len(direct) == count*phases
        phase_major = "".join(
            f"{sum((v & 65535) << (16*n) for n,v in enumerate(coefficients)):016x}\n"
            for coefficients in direct).encode()
        with open(direct_path,"wb") as stream:
            stream.write(pack_phase_rom(phase_major, phases=phases, samples=count))
    bench.write_text(BENCH.replace("COUNT_VALUE",str(count)).replace("SEGMENT_VALUE",str(len(bank)))
                     .replace("BANK_PATH",str(bank_path)).replace("STRIDE_VALUE",str(stride))
                     .replace("DIRECT_PATH",direct_path).replace("PHASE_VALUE",str(phases))
                     .replace(".SERIAL_ROTATE(0)",f".SERIAL_ROTATE({int(serial)})"))
    with trace.open("w") as file:
        file.writelines(rows)
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "cubic_reference", "cubic_coefficients", "direct_coefficients", "native_rotate", "native_products", "local_moments", "native_engine")]
    sources.append(BANK_ROOT.parent/"common/ad_dds_cordic_pipe.v")
    build = subprocess.run(["iverilog","-g2012","-s","tb","-o",str(executable),str(bench),*map(str,sources)],capture_output=True,text=True,check=False)
    assert build.returncode == 0,build.stdout+build.stderr
    run = subprocess.run(["vvp",str(executable),f"+INPUT={trace}"],capture_output=True,text=True,timeout=120,check=False)
    assert run.returncode == 0,run.stdout+run.stderr
    return [[*(int(word,16) for word in words[1:4]),*map(int,words[4:] if phases>1 else words[4:-1])]
        for line in run.stdout.splitlines() if (words:=line.split()) and words[0]=="R"]


def complete_job(job, count, *, ready=1):
    return [row(job=job,ready=ready)] + [row(ready=ready)]*59 + [
        row(value=sample(job[0]+n),closed=int(n==count-1),ready=ready) for n in range(count)]


@pytest.mark.parametrize("stride,direct_bank,phases,serial", [
    (24, True, 1, False), (24, True, 4, False), (24, True, 4, True),
    (24, False, 1, False), (12, False, 1, False), (12, False, 1, True),
    (4, False, 1, False), (2, False, 1, False), (1, False, 1, False)],
    ids=["2p5MSs-direct", "2p5MSs-phase4", "2p5MSs-serial-phase4", "2p5MSs-cubic-diagnostic",
         "5MSs", "5MSs-serial", "15MSs", "30MSs", "60MSs"])
def test_three_full_native_pilots_on_750_hz_opportunities_with_original_indexes(tmp_path, stride, direct_bank, phases, serial):
    count,base = 79200//stride,2**55+73
    bank = bank_for(79200)
    direct = [tuple((n*(k+1)*13+37) % 4000-2000 for k in range(4)) for n in range(count*phases)] if direct_bank else None
    # Integer rounding at each absolute rational epoch, not a repeatedly
    # rounded period at 2.5 or 5 MS/s.
    jobs = [(base+(64+stride-1)//stride+(frame*80000+stride//2)//stride,
             (2**32-1-frame*711) % 2**32,(7310173+frame*1357) % 2**32) for frame in range(3)]
    def rows():
        native_index = 0
        for cycle in range(400000):
            job = jobs[0] if cycle==0 else jobs[1] if cycle==133333 else jobs[2] if cycle==266667 else None
            valid = (cycle+1)*3//(5*stride) != cycle*3//(5*stride)
            yield row(job=job,value=sample(base+native_index) if valid else None)
            native_index += int(valid)
    result = simulate(tmp_path,count,bank,rows(),stride,direct,phases,serial)
    truth = []
    for job in jobs:
        phase = job[1] % phases
        coefficients = ([[n,*c,int(n==count-1),0] for n,c in enumerate(direct[phase*count:(phase+1)*count])]
                        if direct_bank else coefficient_oracle(bank,24,count,stride))
        truth.append(expected(job,[sample(job[0]+n) for n in range(count)],coefficients)
                     + ([phase] if phases>1 else []))
    assert result == truth


@pytest.mark.parametrize("failure,fault", [("gap",1),("index",1),("closed",2),("clipped",0x42),("flush",8)])
def test_native_fault_preserves_only_delivered_products_and_fresh_job_recovers(tmp_path,failure,fault):
    count = 96
    bank = bank_for(count)
    coefficients = coefficient_oracle(bank,24,count)
    first,second = (1000,2**32-3,1777),(5000,17,2**32-7331)
    prefix = [sample(first[0]+n) for n in range(60)]
    rows = [row(job=first)] + [row()]*59 + [row(value=value) for value in prefix]
    rows += [row(value=sample(first[0]+61)) if failure=="index" else
        row(value=sample(first[0]+60),**{failure:1})]
    rows += [row()]*40 + complete_job(second,count)
    assert simulate(tmp_path,count,bank,rows) == [
        expected(first,prefix[:38],coefficients,fault),
        expected(second,[sample(second[0]+n) for n in range(count)],coefficients)]


def test_job_without_reference_lead_time_is_explicitly_rejected(tmp_path):
    count = 96
    bank = bank_for(count)
    job = (1000,7,919)
    assert simulate(tmp_path,count,bank,[row(job=job),row(value=sample(job[0]))]) == [
        expected(job,[],[],0x12)]


@pytest.mark.parametrize("distance", [-2**40, -1, 1, 2**40])
def test_before_start_ordering_never_admits_wrong_absolute_sample(tmp_path, distance):
    count=96
    bank=bank_for(count)
    coefficients=coefficient_oracle(bank,24,count)
    job=(2**60+1000,7,919)
    rows=[row(job=job)]+[row()]*59
    # A clipped observation before the requested origin is irrelevant. A late
    # first observation is a source discontinuity even across large high bits.
    rows += [row(value=sample(job[0]+distance),clipped=int(distance<0))]
    if distance<0:
        rows += [row(value=sample(job[0]+n),closed=int(n==count-1)) for n in range(count)]
        truth=expected(job,[sample(job[0]+n) for n in range(count)],coefficients)
    else:
        truth=expected(job,[],[],1)
    assert simulate(tmp_path,count,bank,rows)==[truth]


def test_reference_clipping_is_rejected_before_any_product_is_admitted(tmp_path):
    count = 96
    bank = bank_for(count)
    bank[0]=[[-2048,0],[0,0],[0,0],[0,0]]
    bank[1]=[[2047,0],[0,0],[0,0],[0,0]]
    job = (1000,7,919)
    assert simulate(tmp_path,count,bank,complete_job(job,count)) == [expected(job,[],[],0x22)]


def test_complete_result_survives_backpressure_and_flush_after_completion(tmp_path):
    count = 96
    bank = bank_for(count)
    job = (1000,2**31+7,919)
    rows = complete_job(job,count,ready=0) + [row(ready=0)]*50
    rows += [row(flush=1,ready=0)] + [row(ready=0)]*20 + [row()]
    assert simulate(tmp_path,count,bank,rows) == [
        expected(job,[sample(job[0]+n) for n in range(count)],coefficient_oracle(bank,24,count))]


def test_out_of_range_job_closes_with_zero_moments(tmp_path):
    count = 96
    job = (2**64-32,1,71)
    assert simulate(tmp_path,count,bank_for(count),[row(job=job)]) == [expected(job,[],[],4)]


def test_reset_removes_old_generation_and_fresh_job_has_clean_phase_and_totals(tmp_path):
    count = 96
    bank = bank_for(count)
    first,second = (1000,99,7131),(5000,821,2**32-31)
    rows = complete_job(first,count)[:100] + [row(reset=0),row()]+complete_job(second,count)
    assert simulate(tmp_path,count,bank,rows) == [
        expected(second,[sample(second[0]+n) for n in range(count)],coefficient_oracle(bank,24,count))]
