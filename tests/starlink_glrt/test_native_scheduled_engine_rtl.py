"""Continuous multirate scheduling into the full-pilot arithmetic engine."""
from __future__ import annotations

import subprocess
from fractions import Fraction

import pytest

from tools.generate_glrt_direct_phase_rom import pack_phase_rom

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_engine_rtl import BENCH, bank_for, expected, sample


@pytest.mark.parametrize("blocked_middle", [False, True])
@pytest.mark.parametrize("rate", [2500000, 15000000, 30000000, 60000000])
def test_scheduler_drives_full_pilots_and_accounts_for_unavailable_slot(tmp_path, blocked_middle, rate):
    stride = 60000000//rate
    count, base, seed, step = 79200//stride, 2**55 + 73, 2**32 - 711, 7310173
    phases = 4 if rate == 2500000 else 1
    fraction = 24576 if phases == 4 else 0
    period = round(Fraction(rate*65536, 750))
    start = base+(1024+stride-1)//stride
    bank = bank_for(79200)
    bank_path = tmp_path / "bank.mem"
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    direct_path, direct = "", None
    if phases == 4:
        direct = [tuple((n*(k+1)*13+37) % 4000-2000 for k in range(4)) for n in range(count*phases)]
        direct_path = tmp_path / "direct.mem"
        phase_major = "".join(f"{sum((v & 65535) << (16*n) for n,v in enumerate(c)):016x}\n"
                              for c in direct).encode()
        direct_path.write_bytes(pack_phase_rom(phase_major, phases=phases, samples=count))
    # Reuse the engine's result stability assertions and complete moment output.
    bench = BENCH[:BENCH.index("integer fd,rc;")]
    bench = bench.replace("job_valid=0,", "")
    bench = bench.replace("reg [63:0] job_start=0,input_index=0;",
                          "wire job_valid; wire [63:0] job_start; reg [63:0] input_index=0;")
    bench = bench.replace("reg [31:0] seed=0,step=0;", "wire [31:0] seed,step;")
    bench = bench.replace(".job_reference_phase(seed[PB-1:0])", ".job_reference_phase(scheduled_phase)")
    bench = bench.replace("wire [PB-1:0] result_reference_phase;",
                          "wire [PB-1:0] result_reference_phase,scheduled_phase;")
    bench += r'''
localparam [63:0] BASE=BASE_VALUE;
reg config_valid=0;
wire config_ready,config_rejected,reserved;
wire [31:0] configured,admitted,late,no_space,unavailable,expired,cancelled;
reg result_space=1;
integer cycle,native_index=0,results=0;
starlink_glrt_native_schedule #(.SAMPLE_COUNT(N),.ISSUE_LEAD(ISSUE_VALUE),
 .MINIMUM_LEAD(MINIMUM_VALUE),.MAX_PERIOD_SAMPLES(MAX_PERIOD_VALUE),
 .REFERENCE_PHASES(PHASES)) schedule (
 .clk(clk),.resetn(resetn),.cancel(1'b0),.source_good(1'b1),
 .latest_index(input_index),.config_valid(config_valid),.config_ready(config_ready),
 .config_tag(32'd17),.config_start(64'dSTART_VALUE),
 .config_expires(64'dEXPIRY_VALUE),.config_fraction(16'dFRACTION_VALUE),
 .config_period_q16(48'dPERIOD_Q16),.config_step_q16(48'dSTEP_Q16),
 .config_step_delta_q16(48'd88932352),.config_phase_seed(32'dSEED_VALUE),
 .config_repeats(8'd3),.config_rejected(config_rejected),.reserved(reserved),
 .engine_ready(job_ready),.result_space(result_space),.job_valid(job_valid),
 .job_start(job_start),.job_phase_seed(seed),.job_phase_step(step),
 .job_reference_phase(scheduled_phase),
 .configured(configured),.admitted(admitted),.late(late),.no_space(no_space),
 .unavailable(unavailable),.expired(expired),.cancelled(cancelled));
always @(posedge clk) if(resetn) begin
 if(config_rejected) $fatal(1,"valid schedule rejected");
 if(result_valid && result_ready) results <= results+1;
end
initial begin
 repeat(3) @(negedge clk);
 resetn=1; input_index=BASE; config_valid=1;
 @(negedge clk); config_valid=0;
 for(cycle=0;cycle<402000;cycle=cycle+1) begin
  input_valid=((cycle+1)*3/(5*STRIDE_VALUE) != cycle*3/(5*STRIDE_VALUE));
  if(input_valid) begin
   input_index=BASE+native_index;
   ii=(input_index*31)%65536-32768;
   iq=(input_index*173)%65536-32768;
   native_index=native_index+1;
  end
  result_space=!(BLOCK_VALUE && input_index>=BASE+BLOCK_FIRST && input_index<BASE+BLOCK_LAST);
  @(negedge clk);
 end
 input_valid=0;
 repeat(100) @(negedge clk);
 if(active || result_valid || !job_ready || reserved) $fatal(1,"undrained schedule");
 if(configured!=3 || admitted!=EXPECTED_RESULTS || results!=EXPECTED_RESULTS ||
    no_space!=BLOCK_VALUE || late || unavailable || expired || cancelled)
  $fatal(1,"schedule/result conservation failed");
 $finish;
end
endmodule
'''
    for key, value in {"COUNT_VALUE": count, "SEGMENT_VALUE": len(bank),
                       "BANK_PATH": bank_path, "BASE_VALUE": base,
                       "STEP_Q16": step*65536, "SEED_VALUE": seed,
                       "BLOCK_VALUE": int(blocked_middle),
                       "STRIDE_VALUE": stride, "DIRECT_PATH": direct_path, "PHASE_VALUE": phases,
                       "ISSUE_VALUE": (512+stride-1)//stride,
                       "MINIMUM_VALUE": (64+stride-1)//stride,
                       "MAX_PERIOD_VALUE": 81000//stride, "START_VALUE": start,
                       "EXPIRY_VALUE": start+(240000+stride-1)//stride,
                       "PERIOD_Q16": period, "FRACTION_VALUE": fraction,
                       "BLOCK_FIRST": 80000//stride, "BLOCK_LAST": 82000//stride,
                       "EXPECTED_RESULTS": 3-int(blocked_middle)}.items():
        bench = bench.replace(key, str(value))
    bench_path, executable = tmp_path / "tb.sv", tmp_path / "sim"
    bench_path.write_text(bench)
    sources = [BANK_ROOT/f"starlink_glrt_{name}.v" for name in (
        "cubic_reference", "cubic_coefficients", "direct_coefficients", "native_rotate", "native_products",
        "local_moments", "native_engine", "native_schedule")]
    sources.append(BANK_ROOT.parent / "common/ad_dds_cordic_pipe.v")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
                            str(bench_path), *map(str, sources)], capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    observed = [[*(int(word, 16) for word in words[1:4]), *map(int, words[4:])]
                for line in run.stdout.splitlines() if (words := line.split()) and words[0] == "R"]
    frames = (0, 2) if blocked_middle else (0, 1, 2)
    truth = []
    for frame in frames:
        position = Fraction(start*65536+fraction+frame*period, 65536)
        whole, phase = divmod(round(position*phases), phases)
        job = whole, seed, step+frame*1357
        coefficients = ([[n,*c,int(n==count-1),0]
                         for n,c in enumerate(direct[phase*count:(phase+1)*count])]
                        if direct is not None else coefficient_oracle(bank, 24, count, stride))
        truth.append(expected(job, [sample(job[0]+n) for n in range(count)], coefficients)+[phase])
    assert observed == truth
