"""Producer-local final-only authorization; no vendor FFT or controller proof."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RECIPE = json.loads(Path(__file__).with_name("product_final_fence_delta.json").read_text())
TOP = "starlink_pss_fft_bank_owned_product_fence"
MAIL = "starlink_pss_product_fence_mailbox"
BENCH = "tb_starlink_pss_product_final_fence"


def frozen(name):
    return subprocess.check_output(["git", "-C", str(ROOT / "hdl"), "show",
        RECIPE["base"] + f":library/starlink_pss_acquisition/{name}.v"], text=True)


def once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def restored(source, name):
    for old, new in reversed(RECIPE["modules"][name]["edits"]):
        source = once(source, new, old)
    return source


def test_whole_module_inverse_and_all_original_runtime_unchanged():
    for name, record in RECIPE["modules"].items():
        source = (ACQ / f"{name}.v").read_text()
        old = frozen(record["original"])
        assert restored(source, name) == old
        assert (ACQ / f'{record["original"]}.v').read_text() == old
    for name in ("starlink_pss_realtime_input_guard", "starlink_pss_realtime_result_guard",
                 "starlink_pss_forward_kernel_join_read_ahead", "starlink_pss_kernel_rom_read_ahead",
                 "starlink_pss_spectrum_product"):
        assert (ACQ / f"{name}.v").read_text() == frozen(name)


def wire(source, name):
    return re.search(r"  wire " + name + r" = .*?;", source, re.DOTALL)[0]


def test_only_sampled_final_select_changes_and_excluded_cones_absent():
    top = (ACQ / f"{TOP}.v").read_text()
    mail = (ACQ / f"{MAIL}.v").read_text()
    terms = re.findall(r"\b\w+(?:\[\d\])?", wire(top, "producer_final_fault_now").split("=", 1)[1])
    assert terms == ["duplicate_start_fault_now", "input_guard_fault", "source_fault_fast[1]",
        "vendor_fault_now", "fast_fault", "kernel_fault", "product_overflow", "product_bank_fault",
        "product_bank_framing_fault_now", "result_fault"]
    assert "input_fault_now" not in terms and "handoff_fault_now" not in terms
    old = frozen("starlink_pss_fft_bank_owned_rom_read_ahead")
    for name in ("external_fault_now", "product_commit_authorized", "forward_handoff_ack",
                 "completion_accept", "any_fast_fault"):
        assert wire(top, name) == wire(old, name)
    assert mail.count("input_final_seal_authorized") == 2  # port + final-only select
    assert "if (write_position == LAST_POSITION) begin\n          if (!EXPLICIT_COMMIT || (USE_PRODUCER_FINAL_FENCE ?" in mail


def run(tmp_path, enabled=1, width=2, mutate_top=None, mutate_mail=None, broken=0):
    top = (ACQ / f"{TOP}.v").read_text()
    mail = (ACQ / f"{MAIL}.v").read_text()
    if mutate_top:
        top = once(top, *mutate_top)
    if mutate_mail:
        mail = once(mail, *mutate_mail)
    (tmp_path / "candidate.v").write_text(mail)
    (tmp_path / "reference.v").write_text(once(frozen("starlink_pss_block_mailbox"),
        "module starlink_pss_block_mailbox #(", "module frozen_product_mailbox #("))
    shutil.copyfile(ACQ / "starlink_pss_realtime_input_guard.v", tmp_path / "guard.v")
    old = frozen("starlink_pss_fft_bank_owned_rom_read_ahead")
    predicates = "\n".join([wire(old, "external_fault_now"), wire(old, "product_commit_authorized"),
        wire(top, "producer_final_fault_now"), wire(top, "producer_final_seal_authorized")])
    bench = once((ACQ / f"tb/{BENCH}.sv").read_text(),
                 "  // FROZEN_AND_CANDIDATE_PREDICATES", predicates)
    (tmp_path / "bench.sv").write_text(bench)
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", BENCH,
        f"-P{BENCH}.ENABLED={enabled}", f"-P{BENCH}.ADDRESS_WIDTH={width}",
        f"-P{BENCH}.BROKEN_CALLER={broken}", "-o", "sim.vvp", "candidate.v",
        "reference.v", "guard.v", "bench.sv"], cwd=tmp_path, capture_output=True,
        text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "sim.vvp"], cwd=tmp_path, capture_output=True,
                            text=True, timeout=60, check=False)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    return result.returncode, result.stdout + result.stderr


@pytest.mark.parametrize("enabled,width", [(0, 2), (1, 2), (0, 9), (1, 9)])
def test_real_checker_paired_mailbox_all_public_state_data_and_sampled_fence(tmp_path, enabled, width):
    code, log = run(tmp_path, enabled, width)
    assert code == 0 and log.count("PRODUCT_FINAL_FENCE_PASS") == 1, log
    assert "input_bits=70 final_rows=71 current_rows=7 inverse_epochs=1" in log
    words = (1 << width) if width == 9 else (1 << width) - 1
    assert f"epoch_resets=2 words={words} short_inverse_poison={int(width != 9)}" in log
    assert re.search(r"nonsampled_private=[1-9]\d*", log)


@pytest.mark.parametrize("term", ["duplicate_start_fault_now", "source_fault_fast[1]",
    "vendor_fault_now", "kernel_fault", "product_overflow", "result_fault"])
def test_current_missing_veto_mutants_rejected_on_real_final_edge(tmp_path, term):
    source = (ACQ / f"{TOP}.v").read_text()
    before = wire(source, "producer_final_fault_now")
    after = before.replace(term, "1'b0")
    with pytest.raises(AssertionError):
        restored(once(source, before, after), TOP)
    code, log = run(tmp_path, mutate_top=(before, after))
    assert code != 0 and "SAMPLED_FINAL_AUTHORIZATION_MISMATCH" in log, log


def test_raw_private_publication_mutant_rejected(tmp_path):
    code, log = run(tmp_path, mutate_mail=(
        "input_final_seal_authorized : input_commit_authorized", "1'b1 : input_commit_authorized"))
    assert code != 0 and "PRODUCT_PUBLIC_STATE_MISMATCH" in log, log


def test_deliberately_broken_active_input_caller_is_not_equivalence(tmp_path):
    code, log = run(tmp_path, broken=1)
    assert code != 0 and "PRODUCER_FINAL_CALLER_INVARIANT_BROKEN" in log, log


@pytest.mark.parametrize("name,knob", [(TOP, "PRODUCER_LOCAL_FINAL_FENCE"), (MAIL, "USE_PRODUCER_FINAL_FENCE")])
@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_knobs_fail_closed_before_execution(tmp_path, name, knob, value):
    sources = [ACQ / f"{n}.v" for n in (
        TOP, MAIL, "starlink_pss_block_mailbox", "starlink_pss_realtime_input_guard",
        "starlink_pss_realtime_result_guard", "starlink_pss_forward_kernel_join_read_ahead",
        "starlink_pss_kernel_rom_read_ahead", "starlink_pss_spectrum_product")]
    (tmp_path / "stub.v").write_text(STUB)
    (tmp_path / "upper_edge_pss_kernel_q17.mem").write_text("000000000\n" * 512)
    (tmp_path / "invalid.sv").write_text(
        f"module invalid; {name} #(.{knob}({value})) dut (); endmodule\n")
    command = ["iverilog", "-g2012", "-s", "invalid",
               "-o", "sim.vvp", *map(str, sources), "stub.v", "invalid.sv"]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "sim.vvp"], cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    assert result.returncode != 0 and f"{knob} must be zero or one" in log
    assert "Time: 0 " in log


@pytest.mark.parametrize("enabled,missing_binding", [(0, False), (1, False), (1, True)])
def test_full_top_flag_forwarding_and_quiescent_one_sided_reset_shadow(tmp_path, enabled, missing_binding):
    top = (ACQ / f"{TOP}.v").read_text()
    if missing_binding:
        top = once(top, ".USE_PRODUCER_FINAL_FENCE(PRODUCER_LOCAL_FINAL_FENCE)",
                   ".USE_PRODUCER_FINAL_FENCE(0)")
    (tmp_path / "top.v").write_text(top)
    (tmp_path / "old.v").write_text(once(frozen("starlink_pss_fft_bank_owned_rom_read_ahead"),
        "module starlink_pss_fft_bank_owned_rom_read_ahead #(", "module frozen_top #("))
    (tmp_path / "stub.v").write_text(STUB)
    (tmp_path / "upper_edge_pss_kernel_q17.mem").write_text("000000000\n" * 512)
    bench = """`timescale 1ns/1ps
module binding;
  reg clk=0,fft_clk=0,resetn=0,fft_resetn=0;
  always #5 clk=~clk;always #3 fft_clk=~fft_clk;
`define PORTS .clk(clk),.fft_clk(fft_clk),.resetn(resetn),.fft_resetn(fft_resetn),.input_valid(1'b0),.input_data(36'b0),.input_position(9'b0),.input_last(1'b0),.input_block_start(64'b0),.output_ready(1'b0)
`define OPTIONS .REGISTERED_SCHEDULING(1),.DISTRIBUTED_FAST_FAULT(1),.PER_CAUSE_FAULT_CDC(1),.PRIVATE_NEXT_START_SCRATCH(1),.PRIVATE_ROM_READ_AHEAD(1),.PRIVATE_BLOCK_METADATA_READ_AHEAD(1)
  starlink_pss_fft_bank_owned_product_fence #(`OPTIONS,.PRODUCER_LOCAL_FINAL_FENCE(ENABLED)) dut (`PORTS);
  frozen_top #(`OPTIONS) old (`PORTS);
`define VIEW(m) {m.fast_running,m.slow_running,m.input_ready,m.output_valid,m.output_data,m.output_position,m.output_last,m.output_metadata,m.fault,m.state,m.core_release,m.fast_fault,m.product_commit_authorized,m.product_bank.request_toggle,m.product_bank.acknowledge_toggle}
  integer checks=0;
  always @(posedge clk or posedge fft_clk) begin
    #0.001;
    if (`VIEW(dut)!==`VIEW(old)) $fatal(1,"QUIESCENT_TOP_RESET_SHADOW_MISMATCH");
    checks=checks+1;
  end
  initial begin
    #0.002;
    if(dut.product_bank.USE_PRODUCER_FINAL_FENCE!==ENABLED) $fatal(1,"TOP_FINAL_FLAG_FORWARDING_MISMATCH");
    #23;resetn=1;fft_resetn=1;#101;
    resetn=0;#31;resetn=1;#101;
    fft_resetn=0;#31;fft_resetn=1;#101;
    if(checks<50 || !dut.fast_running || !dut.slow_running) $fatal(1,"TOP_RESET_COVERAGE_MISSING");
    $display("PRODUCT_FINAL_TOP_BINDING_PASS enabled=%0d checks=%0d one_sided=2 scope=parked_FFT_no_active_or_paused_clock_reset_claim",ENABLED,checks);
    $finish;
  end
endmodule
""".replace("ENABLED", str(enabled))
    (tmp_path / "binding.sv").write_text(bench)
    names = [MAIL, "starlink_pss_block_mailbox", "starlink_pss_realtime_input_guard",
             "starlink_pss_realtime_result_guard", "starlink_pss_forward_kernel_join_read_ahead",
             "starlink_pss_kernel_rom_read_ahead", "starlink_pss_spectrum_product"]
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "binding", "-o", "sim.vvp",
        "top.v", "old.v", "stub.v", "binding.sv", *[str(ACQ / f"{name}.v") for name in names]],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "sim.vvp"], cwd=tmp_path, capture_output=True,
                            text=True, timeout=10, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if missing_binding:
        assert result.returncode != 0 and "TOP_FINAL_FLAG_FORWARDING_MISMATCH" in log, log
    else:
        assert result.returncode == 0 and log.count("PRODUCT_FINAL_TOP_BINDING_PASS") == 1, log
        assert f"enabled={enabled}" in log and "one_sided=2" in log
