"""Continuous 60 MS/s scheduling into the full-pilot arithmetic engine."""
from __future__ import annotations

import subprocess

import pytest

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import expected as coefficient_oracle
from .test_cubic_reference_rtl import packed_words
from .test_native_engine_rtl import BENCH, bank_for, expected, sample


@pytest.mark.parametrize("blocked_middle", [False, True])
def test_scheduler_drives_full_pilots_and_accounts_for_unavailable_slot(tmp_path, blocked_middle):
    count, base, seed, step = 79200, 2**55 + 73, 2**32 - 711, 7310173
    bank = bank_for(count)
    bank_path = tmp_path / "bank.mem"
    bank_path.write_text("".join(f"{word:027x}\n" for word in packed_words(bank)))
    # Reuse the engine's result stability assertions and complete moment output.
    bench = BENCH[:BENCH.index("integer fd,rc;")]
    bench = bench.replace("job_valid=0,", "")
    bench = bench.replace("reg [63:0] job_start=0,input_index=0;",
                          "wire job_valid; wire [63:0] job_start; reg [63:0] input_index=0;")
    bench = bench.replace("reg [31:0] seed=0,step=0;", "wire [31:0] seed,step;")
    bench += r'''
localparam [63:0] BASE=BASE_VALUE;
reg config_valid=0;
wire config_ready,config_rejected,reserved;
wire [31:0] configured,admitted,late,no_space,unavailable,expired,cancelled;
reg result_space=1;
integer cycle,native_index=0,results=0;
starlink_glrt_native_schedule schedule (
 .clk(clk),.resetn(resetn),.cancel(1'b0),.source_good(1'b1),
 .latest_index(input_index),.config_valid(config_valid),.config_ready(config_ready),
 .config_tag(32'd17),.config_start(BASE+64'd1024),
 .config_expires(BASE+64'd241024),.config_fraction(16'd0),
 .config_period_q16(48'd5242880000),.config_step_q16(48'dSTEP_Q16),
 .config_step_delta_q16(48'd88932352),.config_phase_seed(32'dSEED_VALUE),
 .config_repeats(8'd3),.config_rejected(config_rejected),.reserved(reserved),
 .engine_ready(job_ready),.result_space(result_space),.job_valid(job_valid),
 .job_start(job_start),.job_phase_seed(seed),.job_phase_step(step),
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
  input_valid=((cycle+1)*3/5 != cycle*3/5);
  if(input_valid) begin
   input_index=BASE+native_index;
   ii=(input_index*31)%65536-32768;
   iq=(input_index*173)%65536-32768;
   native_index=native_index+1;
  end
  result_space=!(BLOCK_VALUE && input_index>=BASE+80000 && input_index<BASE+82000);
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
                       "STRIDE_VALUE": 1, "DIRECT_PATH": "", "PHASE_VALUE": 1,
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
    coefficients = coefficient_oracle(bank, 24, count)
    frames = (0, 2) if blocked_middle else (0, 1, 2)
    jobs = [(base+1024+frame*80000, seed, step+frame*1357) for frame in frames]
    assert observed == [expected(job, [sample(job[0]+n) for n in range(count)], coefficients)+[0]
                        for job in jobs]
