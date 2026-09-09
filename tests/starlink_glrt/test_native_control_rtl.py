"""Manual GLN1 admission, immutable records and exact native DMA ownership."""
from __future__ import annotations

import subprocess

import pytest

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_engine_rtl import bank_for, expected, sample

BENCH = r'''
`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,wr=0,iv=0,gap=0,clipped=0,good=1,base_idle=1,base_ready=1,ready=1;
reg [7:0] wa=0,ra=0;
reg [31:0] wd=0,cdc=0,pacer=0;
reg [3:0] strobe=15;
reg [63:0] index=0,latest=0;
reg signed [15:0] ii=0,iq=0;
wire [31:0] rd,cd;
wire owner,reserved,cv;
reg [31:0] fifo[0:7];
reg [2:0] wp=0,rp=0;
reg [3:0] used=0;
wire pop=used!=0 && ready;
wire cr=used!=8 || pop;
wire push=cv && cr;
starlink_glrt_native_control #(.SAMPLE_COUNT(COUNT_VALUE),.TEMPLATE_FILE("BANK_PATH")) dut (
 .clk(clk),.resetn(resetn),.write_request(wr),.write_address(wa),.read_address(ra),
 .write_data(wd),.write_strobe(strobe),.read_data(rd),.base_idle(base_idle),.base_ready(base_ready),
 .fifo_empty(used==0),.capture_ready(cr),.capture_pop(pop),.capture_owner(owner),.reserved(reserved),
 .capture_valid(cv),.capture_data(cd),.source_good(good),.cdc_dropped_count(cdc),.pacer_dropped_count(pacer),
 .latest_index(latest),.input_valid(iv),.input_gap(gap),.input_clipped(clipped),
 .input_index(index),.input_i(ii),.input_q(iq));
reg stalled=0;
reg [31:0] held;
always @(posedge clk) begin
 if(!resetn) begin wp<=0;rp<=0;used<=0;stalled<=0; end
 else begin
  if(iv) latest<=index;
  if(stalled && (used==0 || fifo[rp]!==held)) $fatal(1,"DMA promise retracted");
  stalled<=used!=0 && !ready;held<=fifo[rp];
  if(push) begin
   if(!owner || !reserved) $fatal(1,"native IQ without ownership");
   fifo[wp]<=cd;wp<=wp+1'b1;$display("CAP %h %h",index,cd);
  end
  if(pop) begin
   if(!owner) $fatal(1,"owner released with queued IQ");
   rp<=rp+1'b1;$display("OUT %h",fifo[rp]);
  end
  case({push,pop}) 2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:;endcase
 end
end
integer fd,rc,delay,op;
reg [63:0] a,v,arg;
initial begin
 fd=$fopen("input.txt","r");
 repeat(3) @(negedge clk);resetn=1;
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%d %d %h %h %h\n",delay,op,a,v,arg);
  if(rc!=5) $fatal(1,"bad input");
  wr=0;iv=0;gap=0;clipped=0;
  repeat(delay) @(negedge clk);
  case(op)
   0: ;
   1: begin wr=1;wa=a[7:0];wd=v[31:0];strobe=arg[3:0];end
   2: ra=a[7:0];
   3: begin iv=1;index=a;ii=v[15:0];iq=v[31:16];gap=arg[0];clipped=arg[1];end
   4: begin ready=v[0];good=v[1];base_idle=v[2];base_ready=v[3];end
   5: begin cdc=v[31:0];pacer=arg[31:0];end
   6: resetn=v[0];
   default:$fatal(1,"bad operation");
  endcase
  @(posedge clk);#1;
  if(op==2) $display("READ %h %h",ra,rd);
  @(negedge clk);
 end
 wr=0;iv=0;gap=0;clipped=0;
 repeat(30) @(negedge clk);
 $finish;
end
endmodule
'''


def write(address, value, strobe=15):
    return 0, 1, address, value, strobe


def read(address):
    return 0, 2, address, 0, 0


def wait(cycles=60):
    return cycles, 0, 0, 0, 0


def controls(*, ready=1, good=1, idle=1, base_ready=1):
    return 0, 4, 0, ready | good << 1 | idle << 2 | base_ready << 3, 0


def iqrow(index, *, gap=0, clipped=0):
    _, i, q = sample(index)
    return 0, 3, index, (i & 65535) | (q & 65535) << 16, gap | clipped << 1


def configure(job, capture=1, tag=17):
    start, seed, step = job
    return [write(a, v) for a, v in ((5, tag), (6, start & 0xffffffff),
        (7, start >> 32), (8, seed), (9, step), (10, capture))]


def body(job, count):
    return [write(2, 1), wait(), *(iqrow(job[0]+n) for n in range(count)), wait()]


def head():
    return [read(a) for a in range(0x80, 0xa0)]


def finish():
    return [write(2, 8), wait(), write(2, 4), read(3), read(4)]


def record(job, count, bank, *, capture=1, sequence=0, tag=17, iq_values=None):
    values = [sample(job[0]+n) for n in range(count)] if iq_values is None else iq_values
    value = expected(job, values, coefficient_oracle(bank, 24, count))
    start, seed, step, n, fault, *moments = value
    words = [0x474c4e31, sequence, tag, start & 0xffffffff, start >> 32, seed, step, n, fault]
    for number, width in zip(moments, (2, 2, 2, 2, 3, 3, 2), strict=True):
        words.extend((number >> (32*i)) & 0xffffffff for i in range(width))
    return words + [60000000, count, capture, count*capture, count*capture, 0, 0]


def simulate(tmp_path, count, rows):
    bank = bank_for(count)
    bank_path, bench, trace, exe = [tmp_path/name for name in ("bank.mem", "tb.sv", "input.txt", "sim")]
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    bench.write_text(BENCH.replace("COUNT_VALUE", str(count)).replace("BANK_PATH", str(bank_path)))
    trace.write_text("".join(f"{delay} {op} {a:x} {v:x} {arg:x}\n" for delay, op, a, v, arg in rows))
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "cubic_reference", "cubic_coefficients", "native_rotate", "native_products", "local_moments", "native_engine", "native_control")]
    sources.append(BANK_ROOT.parent/"common/ad_dds_cordic_pipe.v")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(exe), str(bench), *map(str, sources)], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    (tmp_path/"trace.txt").write_text(run.stdout+run.stderr)
    assert run.returncode == 0, run.stdout+run.stderr
    parsed = {"READ": [], "CAP": [], "OUT": []}
    for line in run.stdout.splitlines():
        words = line.split()
        if words and words[0] in parsed:
            parsed[words[0]].append(tuple(int(word, 16) for word in words[1:]))
        elif "$finish called at" not in line:
            pytest.fail(line)
    return parsed


@pytest.mark.parametrize("count", [96, 79200])
def test_original_iq_and_immutable_exact_result_then_restart(tmp_path, count):
    job = (2**55+73, 2**32-7, 91771)
    rows = [*configure(job), *body(job, count), *head(), write(5, 99), write(2, 1), *head(),
        *finish(), *configure(job, capture=0), *body(job, count), *head(), *finish()]
    result = simulate(tmp_path, count, rows)
    headers = [v for a, v in result["READ"] if a >= 0x80]
    expected_head = record(job, count, bank_for(count))
    assert headers == expected_head*2 + record(job, count, bank_for(count), capture=0)
    assert result["CAP"] == [(job[0]+n, iqrow(job[0]+n)[3]) for n in range(count)]
    assert result["OUT"] == [(word,) for _, word in result["CAP"]]
    assert [v for a, v in result["READ"] if a == 4] == [0, 0]
    assert all(v & 0x1e == 0 for a, v in result["READ"] if a == 3)


def test_pending_dma_hides_result_and_prohibits_pop_clear_until_drained(tmp_path):
    count, job = 96, (1000, 7, 19)
    rows = [*configure(job), write(2, 1), wait(), *(iqrow(job[0]+n) for n in range(count-4)),
        controls(ready=0), *(iqrow(job[0]+n) for n in range(count-4, count)), wait(),
        read(3), read(0x0c), *head(), write(2, 8), write(2, 4), read(3),
        controls(), wait(), *head(), *finish()]
    result = simulate(tmp_path, count, rows)
    headers = [v for a, v in result["READ"] if a >= 0x80]
    assert headers == [0]*32 + record(job, count, bank_for(count))
    statuses = [v for a, v in result["READ"] if a == 3]
    assert statuses[0] & 0x1c == statuses[1] & 0x1c == 0x18
    assert result["OUT"] == [(word,) for _, word in result["CAP"]]
    assert len(result["OUT"]) == count


@pytest.mark.parametrize("failure", ["overflow", "abort", "source", "cdc", "pacer", "gap", "clip", "index"])
def test_fault_retains_dma_prefix_and_recovers_after_pop_and_clear(tmp_path, failure):
    count, job = 96, (1000, 7, 19)
    if failure == "overflow":
        action = [controls(ready=0), *(iqrow(job[0]+n) for n in range(60, 80))]
    else:
        action = {
            "abort": [write(2, 2)], "source": [controls(good=0)],
            "cdc": [(0, 5, 0, 1, 0)], "pacer": [(0, 5, 0, 0, 1)],
            "gap": [iqrow(job[0]+60, gap=1)], "clip": [iqrow(job[0]+60, clipped=1)],
            "index": [iqrow(job[0]+61)],
        }[failure]
    rows = [*configure(job), write(2, 1), wait(), *(iqrow(job[0]+n) for n in range(60)), *action,
        wait(), controls(), wait(), *head(), *finish(), *configure(job), *body(job, count), *head(), *finish()]
    result = simulate(tmp_path, count, rows)
    headers = [v for a, v in result["READ"] if a >= 0x80]
    failed, recovered = headers[:32], headers[32:]
    assert failed[0] == 0x474c4e31 and 0 < failed[7] < count and failed[8] != 0
    retained = len(result["CAP"])-count
    assert retained == failed[28] == failed[29] and failed[7] <= retained
    # Even an aborted arithmetic pipeline exposes only the exact moment prefix.
    prefix = record(job, failed[7], bank_for(count))
    assert failed[9:25] == prefix[9:25]
    assert recovered == record(job, count, bank_for(count))
    assert result["OUT"] == [(word,) for _, word in result["CAP"]]


@pytest.mark.parametrize("condition", ["base_busy", "base_clear", "source_bad", "tag_zero", "partial", "combination"])
def test_invalid_admission_never_reserves_dma(tmp_path, condition):
    job = (1000, 7, 19)
    rows = configure(job, tag=0 if condition == "tag_zero" else 17)
    rows += [controls(idle=condition != "base_busy", good=condition != "source_bad", base_ready=condition != "base_clear")]
    rows += [write(2, 3 if condition == "combination" else 1, strobe=3 if condition == "partial" else 15),
        wait(), read(3), read(4), read(0x0d), *head()]
    result = simulate(tmp_path, 96, rows)
    regs = dict(result["READ"])
    assert regs[3] & 0x1e == 0 and regs[4] == 1 and regs[0x0d] == 0
    assert not result["CAP"] and not result["OUT"] and all(regs[a] == 0 for a in range(0x80, 0xa0))
