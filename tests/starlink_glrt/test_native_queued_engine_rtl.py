"""Actual 750 Hz full-pilot computation with a slow consumer and reserved RAM."""
from __future__ import annotations

import subprocess
from fractions import Fraction

import pytest

from tools.generate_glrt_direct_phase_rom import pack_phase_rom
from tools.starlink_glrt_tracking_abi import TrackingBatch, TrackingResult

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_engine_rtl import BENCH, bank_for, expected, sample


def signed(words):
    value = sum(word << (32*n) for n, word in enumerate(words))
    bits = len(words)*32
    return value-(1 << bits) if value >> (bits-1) else value


@pytest.mark.parametrize("fault_mode", [0, 1, 2], ids=["full-750hz", "cancel", "source-loss"])
@pytest.mark.parametrize("tracking_rate", [None, 2500000, 5000000, 15000000, 30000000, 60000000])
def test_scheduled_engine_queue_preserves_results_and_accounts_for_missing_repeats(
        tmp_path, fault_mode, tracking_rate):
    stride = 60000000//tracking_rate if tracking_rate else 1
    count = 79200//stride if tracking_rate or not fault_mode else 96
    period_q16 = round(Fraction(80000*65536, stride)) if tracking_rate or not fault_mode else 1000*65536
    offset = (1024+stride-1)//stride
    phases = 4 if tracking_rate == 2500000 else 1
    fraction = 24576 if phases == 4 else 0
    base, seed, step = 2**55+73, 2**32-711, 7310173
    bank = bank_for(79200 if tracking_rate else count)
    bank_path, bench_path, executable = [tmp_path/name for name in ("bank.mem", "tb.sv", "sim")]
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    direct_path, direct = "", None
    if phases == 4:
        direct = [tuple((n*(k+1)*13+37) % 4000-2000 for k in range(4)) for n in range(count*phases)]
        direct_path = tmp_path/"direct.mem"
        phase_major = "".join(f"{sum((v & 65535) << (16*n) for n,v in enumerate(c)):016x}\n"
                              for c in direct).encode()
        direct_path.write_bytes(pack_phase_rom(phase_major, phases=phases, samples=count))
    bench = BENCH[:BENCH.index("integer fd,rc;")]
    bench = bench.replace(".SERIAL_ROTATE(0)", f".SERIAL_ROTATE({int(tracking_rate in (2500000, 5000000))})")
    bench = bench.replace("job_valid=0,", "").replace(",result_ready=1;", ";")
    bench = bench.replace("reg [63:0] job_start=0,input_index=0;",
        "wire job_valid,result_ready; wire [63:0] job_start; reg [63:0] input_index=0;")
    bench = bench.replace("reg [31:0] seed=0,step=0;", "wire [31:0] seed,step;")
    bench = bench.replace("wire [PB-1:0] result_reference_phase;",
                          "wire [PB-1:0] result_reference_phase,scheduled_phase;")
    bench = bench.replace(".job_reference_phase(seed[PB-1:0])", ".job_reference_phase(scheduled_phase)")
    bench = bench.replace(".flush(flush)", ".flush(flush || controller_flush)")
    bench = bench.replace(".input_gap(input_gap)", ".input_gap(input_gap || controller_gap)")
    bench += r'''
localparam [63:0] BASE=BASE_VALUE;
reg config_valid=0,cancel=0,source_good=1;
wire config_ready,config_rejected,reserved,controller_flush,controller_gap;
wire [31:0] configured,admitted,late,no_space,unavailable,expired,cancelled,committed,popped;
wire [1:0] queued,high_water;
wire queue_fault,read_valid,head_valid;
reg read_request=0,pop=0;
reg [4:0] read_word=0;
wire [31:0] read_data;
integer cycle,native_index=0,read_count=0;
starlink_glrt_native_scheduled_results #(.SAMPLE_COUNT(N),.DEPTH_BITS(1),
 .TRACKING(TRACKING_VALUE),.SOURCE_RATE(RATE_VALUE)) control (
 .clk(clk),.resetn(resetn),.cancel(cancel),.source_good(source_good),.latest_index(input_index),
 .config_valid(config_valid),.config_ready(config_ready),.config_rejected(config_rejected),
 .config_tag(32'd17),.config_start(BASE+64'dSTART_OFFSET),.config_expires(BASE+64'dEXPIRY_OFFSET),
 .config_fraction(16'dFRACTION_VALUE),.config_period_q16(48'dPERIOD_Q16),
 .config_step_q16(48'dSTEP_Q16),.config_step_delta_q16(48'd88932352),
 .config_phase_seed(32'dSEED_VALUE),.config_repeats(8'd5),.reserved(reserved),
 .engine_ready(job_ready),.job_valid(job_valid),.job_start(job_start),
 .job_phase_seed(seed),.job_phase_step(step),.engine_flush(controller_flush),.engine_gap(controller_gap),
 .job_reference_phase(scheduled_phase),.result_reference_phase(result_reference_phase),
 .engine_result(result_valid),.engine_result_ready(result_ready),.result_start(result_start),
 .result_seed(result_seed),.result_step(result_step),.result_count(count),.result_fault(fault),
 .ri(ri),.rq(rq),.di(di),.dq(dq),.ti(ti),.tq(tq),.energy(energy),
 .read_request(read_request),.pop(pop),.read_word(read_word),.read_valid(read_valid),
 .head_valid(head_valid),.queue_fault(queue_fault),.read_data(read_data),
 .queued(queued),.high_water(high_water),.configured(configured),.admitted(admitted),
 .late(late),.no_space(no_space),.unavailable(unavailable),.expired(expired),
 .cancelled(cancelled),.committed(committed),.popped(popped),.counter_exhausted());
always @(posedge clk) if(resetn && (config_rejected || queue_fault))
 $fatal(1,"valid scheduled producer protocol failed");
initial begin
 repeat(3) @(negedge clk);
 resetn=1; input_index=BASE; config_valid=1;
 @(negedge clk); config_valid=0;
 fork
  begin
   for(cycle=0;cycle<TOTAL_CYCLES;cycle=cycle+1) begin
    input_valid=((cycle+1)*3/(5*STRIDE_VALUE) != cycle*3/(5*STRIDE_VALUE));
    if(input_valid) begin
     input_index=BASE+native_index;
     ii=(input_index*31)%65536-32768;
     iq=(input_index*173)%65536-32768;
     native_index=native_index+1;
    end
    if(input_index>=BASE+64'dFAULT_OFFSET) begin
     if(FAULT_MODE==1) cancel=1;
     if(FAULT_MODE==2) source_good=0;
    end
    @(negedge clk);
   end
   input_valid=0;
  end
  begin
   // Hold two results for ~4 ms: the third repeat must be explicitly skipped.
   repeat(DRAIN_CYCLE) @(negedge clk);
   if(queued!=2 || no_space!=NO_SPACE) $fatal(1,"unexpected queue/drop state before drain");
   repeat(RESULTS) begin
    while(!head_valid) @(negedge clk);
    $write("Q");
    for(integer k=0;k<32;k=k+1) begin
     read_request=1;read_word=k;@(negedge clk);
     if(!read_valid) $fatal(1,"committed word missing");
     $write(" %h",read_data);
    end
    $write("\n");read_request=0;pop=1;@(negedge clk);pop=0;
    read_count=read_count+1;
   end
  end
 join
 repeat(100) @(negedge clk);
 if(active || result_valid || !job_ready || reserved || queued ||
    configured!=5 || admitted!=RESULTS || committed!=RESULTS || popped!=RESULTS || read_count!=RESULTS ||
    high_water!=2 || no_space!=NO_SPACE || late || unavailable!=UNAVAILABLE || expired || cancelled!=CANCELLED)
  $fatal(1,"queued full-pilot conservation failed");
 $finish;
end
initial begin #8000000; $fatal(1,"scheduled engine timed out"); end
endmodule
'''
    for key, value in {"COUNT_VALUE": count, "SEGMENT_VALUE": len(bank), "BANK_PATH": bank_path,
                       "BASE_VALUE": base, "STEP_Q16": step*65536, "SEED_VALUE": seed,
                       "STRIDE_VALUE": stride, "DIRECT_PATH": direct_path, "PHASE_VALUE": phases,
                       "TRACKING_VALUE": int(tracking_rate is not None), "RATE_VALUE": tracking_rate or 60000000,
                       "START_OFFSET": offset, "FRACTION_VALUE": fraction,
                       "EXPIRY_OFFSET": offset+(5*period_q16)//65536+1, "PERIOD_Q16": period_q16,
                       "TOTAL_CYCLES": 669000 if tracking_rate or not fault_mode else 10000,
                       "DRAIN_CYCLE": 399000 if tracking_rate or not fault_mode else 8000,
                       "FAULT_OFFSET": offset+period_q16//65536+40, "FAULT_MODE": fault_mode,
                       "NO_SPACE": int(not fault_mode), "RESULTS": 4 if not fault_mode else 2,
                       "UNAVAILABLE": 3 if fault_mode == 2 else 0,
                       "CANCELLED": 3 if fault_mode == 1 else 0}.items():
        bench = bench.replace(key, str(value))
    bench_path.write_text(bench)
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "cubic_reference", "cubic_coefficients", "direct_coefficients", "native_rotate", "native_products",
        "local_moments", "native_engine", "native_schedule", "native_result_queue",
        "native_scheduled_results")]
    sources.append(BANK_ROOT.parent/"common/ad_dds_cordic_pipe.v")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench_path), *map(str, sources)], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    records = [[int(word, 16) for word in line.split()[1:]]
               for line in run.stdout.splitlines() if line.startswith("Q ")]
    frames = (0, 1, 3, 4) if not fault_mode else (0, 1)
    assert len(records) == len(frames)
    coefficients = coefficient_oracle(bank, 24, count, stride) if direct is None else None
    for sequence, (frame, record) in enumerate(zip(frames, records, strict=True)):
        origin = Fraction((base+offset)*65536+fraction+frame*period_q16, 65536)
        whole, phase = divmod(round(origin*phases), phases)
        job = (whole, seed, step+frame*1357)
        if direct is not None:
            coefficients = [[n, *c, int(n==count-1), 0]
                            for n,c in enumerate(direct[phase*count:(phase+1)*count])]
        failed = fault_mode and frame == 1
        if failed:
            assert 0 < record[7] < count
        else:
            assert record[7] == count
        oracle = expected(job, [sample(job[0]+n) for n in range(record[7])], coefficients)
        assert record[:3] == [0x474c5431 if tracking_rate else 0x474c5331, sequence, 17]
        fault = (0x108 if fault_mode == 1 else 0x201) if failed else 0
        assert record[3:9] == [job[0] % 2**32, job[0] >> 32, *job[1:], record[7], fault]
        assert [signed(record[k:k+2]) for k in (9, 11, 13, 15)] == oracle[5:9]
        assert [signed(record[k:k+3]) for k in (17, 20)] == oracle[9:11]
        assert record[23]+(record[24] << 32) == oracle[11]
        if tracking_rate:
            assert record[25:] == [tracking_rate, count, frame, phase,
                                   0xdc509401 if phases == 4 else 0xb04a2fab, 0x10000, 0]
            # These synthetic coefficients test bit-exact transport, not the
            # pinned scientific fit. Association must still preserve geometry.
            b = TrackingBatch(tracking_rate, 3, 17, base+offset, fraction, period_q16,
                step*65536, 88932352, seed, 5, base+offset+5*period_q16//65536+1)
            text = "GLT1 00010000 00000003 "+" ".join(f"{w:08x}" for w in record)
            TrackingResult.from_sysfs(text).require_association(b, sequence=sequence)
        else:
            assert record[25:] == [60000000, count, frame, 0, 0, 0, 0]
