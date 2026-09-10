"""Targeted active/NBA scheduler proof, not a vendor or controller substitute."""
import hashlib
import re
import runpy
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
PREPARED = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-product-actual-prepared-v1")
HELPER = runpy.run_path(str(ACQ / "prepare_checked_product_drain_witness.py"))
ORIGINAL = (PREPARED / "frozen_sources/tb_starlink_pss_fft_bank_owned_slice.sv").read_text()
AWAIT = ORIGINAL[ORIGINAL.index("  task automatic await_results("):ORIGINAL.index("  task automatic await_fault;")]

PREFIX = '''`timescale 1ns/1ps
module actor;
  localparam WAIT_BANK=2;
  reg fast_running=1, fast_fault=0, next_inverse=0, result_busy=0, output_bank_ready=1;
  reg [3:0] state=1;
endmodule
module tb;
  actor dut();
  reg fft_clk=0, clk=1, fault=0;
  integer fast_cycle=0, previous_admit=-1, published=32, profile=0, live_samples=0;
  real last_live=-1;
  always #5 fft_clk=~fft_clk;
  always @(negedge fft_clk) fast_cycle=fast_cycle+1;
  always @(posedge fft_clk) begin
    if (dut.fast_running===1'b1 && dut.fast_fault===1'b0 && fault===1'b0 &&
        published===32 && dut.state===dut.WAIT_BANK && dut.next_inverse===1'b0 &&
        dut.result_busy===1'b0 && dut.output_bank_ready===1'b1) begin
      live_samples=live_samples+1; last_live=$realtime;
    end
  end
  task automatic tick;
    @(posedge fft_clk); #0.001;
  endtask
'''


def simulate(tmp_path, task, program):
    source = tmp_path / "fixture.sv"
    source.write_text(PREFIX + AWAIT + task + program + "\nendmodule\n")
    shutil_source = ACQ / "prepare_checked_product_drain_witness.py"
    (tmp_path / "policy.sha256").write_text(hashlib.sha256(shutil_source.read_bytes()).hexdigest() + "\n")
    binary = tmp_path / "sim.vvp"
    compile_run = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(source)],
        env=clean_env(), text=True, capture_output=True, timeout=20)
    (tmp_path / "compile.log").write_text(compile_run.stdout + compile_run.stderr)
    assert compile_run.returncode == 0, compile_run.stdout + compile_run.stderr
    run = subprocess.run(["vvp", str(binary)], env=clean_env(), capture_output=True, text=True, timeout=20)
    (tmp_path / "run.log").write_text(run.stdout + run.stderr)
    (tmp_path / "exit.txt").write_text(str(run.returncode) + "\n")
    return run


def test_whole_v1_inverse_preserves_every_old_statement():
    new = HELPER["transform"](ORIGINAL)
    assert HELPER["transform"](new, True) == ORIGINAL
    assert AWAIT in new
    for token in ("await_results(QUICK_MUTATION ? 0 : 32);", "await_results(QUICK_MUTATION ? 0 : 6);"):
        assert ORIGINAL.count(token) == new.count(token) == 1
    assert hashlib.sha256((PREPARED / "checked_product_actual_result.py").read_bytes()).hexdigest() == "a04c648779af03ba0d156215fa274e5b2d4b92af7028fc38b95e66a35e452084"
    for wrong in (new.replace("service_cycles > 5215", "service_cycles > 5216"),
                  new.replace("dut.output_bank_ready === 1'b1", "1'b1", 1)):
        with pytest.raises(ValueError):
            HELPER["transform"](wrong, True)


@pytest.mark.parametrize("slow_fall", [6, 16])
@pytest.mark.parametrize("witness", [0, 1])
def test_old_post_nba_boundary_and_new_live_preedge(slow_fall, witness, tmp_path):
    program = f'''
  initial begin #{slow_fall}; clk=0; forever #7 clk=~clk; end
  initial begin
    previous_admit=0;
    @(posedge fft_clk); dut.state <= dut.WAIT_BANK;
  end
  initial begin
    await_results(32);
    if ({witness}) checked_profile_drain(32);
    @(negedge clk); dut.fast_running=0;
    #0.001;
    if (live_samples != {1 if witness or slow_fall == 16 else 0})
      $fatal(1,"SCHEDULER_SAMPLE_COUNT");
    if ({witness} && $realtime-last_live < 0.001)
      $fatal(1,"RESET_BEFORE_POST_SAMPLE_SETTLE");
    $display("DRAIN_SCHEDULER_PASS phase={slow_fall} witness={witness} samples=%0d",live_samples);
    $finish;
  end
'''
    run = simulate(tmp_path, HELPER["TASK"], program)
    assert run.returncode == 0 and not re.search(r"ERROR|FATAL", run.stdout)
    marker = f"DRAIN_SCHEDULER_PASS phase={slow_fall} witness={witness} samples={1 if witness or slow_fall == 16 else 0}"
    assert run.stdout.splitlines().count(marker) == 1
    assert run.stdout.count("CHECKED_PROFILE_DRAIN_WITNESS ") == witness


@pytest.mark.parametrize("service,passed", [(5215, True), (5216, False)])
def test_exact_service_budget(service, passed, tmp_path):
    program = f'''
  initial begin
    dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle={service};
    checked_profile_drain(32);
    $display("DRAIN_BUDGET_PASS service={service}"); $finish;
  end
'''
    run = simulate(tmp_path, HELPER["TASK"], program)
    assert (run.returncode == 0) == passed
    assert (f"DRAIN_BUDGET_PASS service={service}" in run.stdout) == passed
    if not passed:
        assert "CHECKED_PROFILE_DRAIN_SERVICE_BOUND" in run.stdout


@pytest.mark.parametrize("signal,value", [
    ("dut.fast_running", "0"), ("dut.fast_running", "1'bx"), ("dut.fast_running", "1'bz"),
    ("dut.fast_fault", "1"), ("dut.fast_fault", "1'bx"), ("fault", "1"),
    ("fault", "1'bz"), ("dut.output_bank_ready", "0"), ("dut.output_bank_ready", "1'bx"),
    ("dut.result_busy", "1"), ("dut.result_busy", "1'bz"), ("dut.next_inverse", "1"),
    ("dut.state", "1"), ("published", "31"),
])
def test_no_reset_fault_or_unfinished_owner_as_drain(signal, value, tmp_path):
    program = f'''
  initial begin
    dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=5215;
    {signal}={value};
    checked_profile_drain(32);
    $fatal(1,"FALSE_DRAIN_ACCEPTANCE");
  end
'''
    run = simulate(tmp_path, HELPER["TASK"], program)
    assert run.returncode != 0 and "FALSE_DRAIN_ACCEPTANCE" not in run.stdout
    expected = "CHECKED_PROFILE_DRAIN_RESET_OR_FAULT" if signal in ("dut.fast_running", "dut.fast_fault", "fault") else "CHECKED_PROFILE_DRAIN_SERVICE_BOUND"
    assert expected in run.stdout


@pytest.mark.parametrize("signal", ["dut.fast_running", "dut.fast_fault", "fault"])
def test_reset_or_fault_within_post_sample_delay(signal, tmp_path):
    value = 0 if signal == "dut.fast_running" else 1
    program = f'''
  initial begin dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=1; checked_profile_drain(32); $fatal(1,"FALSE_DRAIN_ACCEPTANCE"); end
  initial begin @(posedge fft_clk); {signal} <= {value}; end
'''
    run = simulate(tmp_path, HELPER["TASK"], program)
    assert run.returncode != 0 and "CHECKED_PROFILE_DRAIN_RESET_OR_FAULT" in run.stdout
    assert "FALSE_DRAIN_ACCEPTANCE" not in run.stdout


@pytest.mark.parametrize("predicate,drive", [
    ("dut.output_bank_ready === 1'b1", "dut.output_bank_ready=0"),
    ("dut.result_busy === 1'b0", "dut.result_busy=1"),
    ("dut.next_inverse === 1'b0", "dut.next_inverse=1"),
    ("dut.state === dut.WAIT_BANK", "dut.state=1"),
    ("published === count", "published=31"),
])
def test_missing_drain_predicate_mutants(predicate, drive, tmp_path):
    task = HELPER["TASK"].replace(predicate, "1'b1")
    assert task != HELPER["TASK"]
    program = f'''
  initial begin
    dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=1; {drive};
    checked_profile_drain(32);
    if (live_samples != 1) $fatal(1,"MISSING_LIVE_DRAIN_PREDICATE");
    $finish;
  end
'''
    run = simulate(tmp_path, task, program)
    assert run.returncode != 0 and "MISSING_LIVE_DRAIN_PREDICATE" in run.stdout


def test_missing_preedge_wait_mutant(tmp_path):
    task = HELPER["TASK"].replace("      @(posedge fft_clk);", "")
    program = '''
  initial begin #6; clk=0; forever #7 clk=~clk; end
  initial begin previous_admit=0; fast_cycle=1; @(posedge fft_clk); dut.state <= dut.WAIT_BANK; end
  initial begin
    await_results(32); checked_profile_drain(32);
    @(negedge clk); dut.fast_running=0; #0.001;
    if (live_samples != 1) $fatal(1,"MISSING_LIVE_PREEDGE_WAIT"); $finish;
  end
'''
    run = simulate(tmp_path, task, program)
    assert run.returncode != 0 and "MISSING_LIVE_PREEDGE_WAIT" in run.stdout


@pytest.mark.parametrize("predicate,drive", [
    ("dut.fast_running !== 1'b1 || ", "dut.fast_running=0"),
    ("dut.fast_fault !== 1'b0 || ", "dut.fast_fault=1"),
    (" || fault !== 1'b0", "fault=1"),
])
def test_missing_reset_or_fault_fence_mutants(predicate, drive, tmp_path):
    assert HELPER["TASK"].count(predicate) == 2
    task = HELPER["TASK"].replace(predicate, "")
    program = f'''
  initial begin
    dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=1; {drive};
    checked_profile_drain(32);
    if (live_samples != 1) $fatal(1,"MISSING_CURRENT_RESET_FAULT_FENCE"); $finish;
  end
'''
    run = simulate(tmp_path, task, program)
    assert run.returncode != 0 and "MISSING_CURRENT_RESET_FAULT_FENCE" in run.stdout


def test_missing_post_sample_settle_mutant(tmp_path):
    task = HELPER["TASK"].replace("      #0.001;\n", "")
    program = '''
  initial begin dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=1;
    checked_profile_drain(32); $fatal(1,"MISSING_POST_SAMPLE_SETTLE"); end
  initial begin @(posedge fft_clk); dut.fast_running <= 0; end
'''
    run = simulate(tmp_path, task, program)
    assert run.returncode != 0 and "MISSING_POST_SAMPLE_SETTLE" in run.stdout


def test_missing_absolute_budget_mutant(tmp_path):
    task = HELPER["TASK"].replace(" || service_cycles > 5215", "")
    program = '''
  initial begin dut.state=dut.WAIT_BANK; previous_admit=0; fast_cycle=5216;
    checked_profile_drain(32); $fatal(1,"MISSING_ABSOLUTE_SERVICE_BOUND"); end
'''
    run = simulate(tmp_path, task, program)
    assert run.returncode != 0 and "MISSING_ABSOLUTE_SERVICE_BOUND" in run.stdout
