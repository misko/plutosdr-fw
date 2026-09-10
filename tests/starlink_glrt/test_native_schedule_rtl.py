"""Finite predictions preserve native coordinates, deadlines and loss accounting."""
from __future__ import annotations

import subprocess
from fractions import Fraction

import pytest

from .ddc import BANK_ROOT

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg resetn=0,cancel=0,source_good=1,config_valid=0,engine_ready=1,result_space=1;
reg [63:0] latest_index=0,config_start=0,config_expires=0;
reg [31:0] config_tag=0,config_phase_seed=0;
reg [15:0] config_fraction=0;
reg [47:0] config_period_q16=0,config_step_q16=0,config_step_delta_q16=0;
reg [7:0] config_repeats=0;
wire config_ready,config_rejected,reserved,job_valid,decision_valid,counter_exhausted;
wire [63:0] job_start,decision_start;
wire [31:0] job_phase_seed,job_phase_step,job_tag,decision_tag;
wire [7:0] job_repeat,decision_repeat;
wire [2:0] decision_reason;
wire [31:0] configured,admitted,late,no_space,unavailable,expired,cancelled;
starlink_glrt_native_schedule dut(.*);
integer fd,rc,op;
reg [63:0] a,b,c,d,e,f,g,h;
always @(posedge clk) if(resetn && job_valid) begin
 if(!engine_ready || !result_space || !source_good || cancel) $fatal(1,"bad admission");
 if(job_start-latest_index<64 || job_start-latest_index>512) $fatal(1,"wrong lead");
 $display("J %h %h %h %h %h",job_tag,job_repeat,job_start,job_phase_seed,job_phase_step);
end
initial begin
 fd=$fopen("input.txt","r");
 repeat(3) @(negedge clk);resetn=1;
 @(negedge clk);
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %h %h %h %h %h %h %h %h\n",op,a,b,c,d,e,f,g,h);
  if(rc!=9) $fatal(1,"bad trace");
  config_valid=0;cancel=0;
  case(op)
   0: ;
   1: begin
    if(!config_ready) $fatal(1,"test violated config backpressure");
    config_valid=1;config_tag=a;config_start=b;config_fraction=c;
    config_period_q16=d;config_step_q16=e;config_step_delta_q16=f;
    config_repeats=g;config_expires=h;config_phase_seed=32'hfffffff9;
   end
   2: begin latest_index=a;engine_ready=b[0];result_space=b[1];source_good=b[2];end
   3: cancel=1;
   default:$fatal(1,"bad op");
  endcase
  @(posedge clk);#1;
  if(config_rejected) $display("R");
  if(decision_valid) $display("D %h %h %h %h",decision_tag,decision_repeat,decision_start,decision_reason);
  @(negedge clk);
 end
 config_valid=0;cancel=0;
 repeat(3) @(negedge clk);
 $display("S %d %d %d %d %d %d %d %d",configured,admitted,late,no_space,unavailable,expired,cancelled,reserved);
 $finish;
end
endmodule
'''


def config(tag, start, *, fraction=0, period=80000*65536, step=0, delta=0, count=4, expires=2**64-1):
    return (1, tag, start, fraction, period, step % 2**48, delta % 2**48, count, expires)


def tick(index, *, ready=True, space=True, good=True):
    return (2, index, int(ready) | int(space)<<1 | int(good)<<2, 0, 0, 0, 0, 0, 0)


WAIT = (0,)*9
CANCEL = (3,)+(0,)*8


def simulate(tmp_path, rows):
    (tmp_path/"tb.sv").write_text(BENCH)
    (tmp_path/"input.txt").write_text("".join(
        f"{row[0]} "+" ".join(f"{value:x}" for value in row[1:])+"\n" for row in rows))
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", "sim", "tb.sv",
        str(BANK_ROOT/"starlink_glrt_native_schedule.v")], cwd=tmp_path,
        capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stdout+built.stderr
    run = subprocess.run(["vvp", "sim"], cwd=tmp_path, capture_output=True, text=True,
                         timeout=30, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    result = {"J": [], "D": [], "R": [], "S": []}
    for line in run.stdout.splitlines():
        words = line.split()
        if words[0] in result:
            result[words[0]].append(tuple(int(v, 10 if words[0]=="S" else 16) for v in words[1:]))
    return result


@pytest.mark.parametrize("fraction,period,step,delta", [
    (0, 80000*65536, 91771*65536, 381*65536+32768),
    (32768, 80000*65536+16384, -91771*65536-32768, -381*65536-49152),
    (65535, 79999*65536+65535, 2**48-1, 65537),
])
def test_all_750_hz_opportunities_two_prefilled_batches_and_exact_fractional_predictions(
        tmp_path, fraction, period, step, delta):
    first = 2**55+1001
    expected_jobs, rows = [], []
    starts = [round(Fraction(first*65536+fraction+n*period, 65536)) for n in range(64)]
    for batch in range(2):
        q = first*65536+fraction+batch*32*period
        rows += [config(batch+1, q//65536, fraction=q % 65536, period=period,
                        step=step+batch*32*delta, delta=delta, count=32), WAIT, WAIT]
    for n, start in enumerate(starts):
        # Include both sides of the exact issue boundary. No host configuration
        # occurs after the second batch was queued, long before either ran.
        rows += [tick(start-513), tick(start-512), WAIT, WAIT]
        expected_jobs.append((n//32+1,n % 32,start,0xfffffff9,
                              round(Fraction(step+n*delta,65536)) % 2**32))
    result = simulate(tmp_path, rows)
    assert result["J"] == expected_jobs
    assert result["D"] == [(tag,n,start,0) for tag,n,start,_,_ in expected_jobs]
    assert result["R"] == []
    assert result["S"] == [(64,64,0,0,0,0,0,0)]


def test_busy_capacity_and_late_opportunities_are_counted_and_do_not_rebase_future_jobs(tmp_path):
    first = 1_000_000
    rows = [config(9,first),WAIT,WAIT,
        tick(first-512,ready=False),tick(first-63,ready=False),
        tick(first+80000-512,space=False),tick(first+80000-63,space=False),
        tick(first+160000),tick(first+240000-64)]
    result = simulate(tmp_path, rows)
    assert [row[-1] for row in result["D"]] == [3,2,1,0]
    assert result["J"] == [(9,3,first+240000,0xfffffff9,0)]
    assert result["S"] == [(4,1,1,1,1,0,0,0)]


@pytest.mark.parametrize("cause", ["cancel", "source", "expiry", "overflow"])
def test_all_remaining_predictions_are_fenced_with_complete_accounting(tmp_path, cause):
    first = 1_000_000 if cause!="overflow" else 2**64-100000
    end = first+79200 if cause=="expiry" else 2**64-1
    rows = [config(1,first,expires=end),WAIT,WAIT]
    if cause in ("cancel","source"):
        rows += [config(2,first+320000),WAIT]
    rows += [tick(first-512),WAIT]
    if cause=="cancel": rows += [CANCEL]
    elif cause=="source": rows += [tick(first-511,good=False)]
    else: rows += [tick(min(first+80000-512,2**64-1)),WAIT]
    result = simulate(tmp_path, rows)
    expected = {"cancel":(8,1,0,0,0,0,7,0), "source":(8,1,0,0,7,0,0,0),
                "expiry":(4,1,0,0,0,3,0,0), "overflow":(4,1,0,0,0,3,0,0)}
    assert len(result["J"]) == 1
    assert result["S"] == [expected[cause]]


@pytest.mark.parametrize("changes", [{"tag":0},{"count":0},{"count":65},
    {"period":79200*65536},{"start":1},{"expires":999999}])
def test_invalid_descriptor_does_not_create_a_schedule(tmp_path, changes):
    fields = {"tag":1,"start":1000000,**changes}
    result = simulate(tmp_path,[config(**fields),WAIT,WAIT])
    assert result["R"] == [()]
    assert result["J"] == []
    assert result["S"] == [(0,0,0,0,0,0,0,0)]
