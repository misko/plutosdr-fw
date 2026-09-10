"""Idle-only mailbox predicate, frozen public behavior and real-link premise.

Synthetic core events and real dual-clock mailboxes, not actual FFT arithmetic,
physical timing, production throughput, native IIO or RF evidence.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle import test_realtime_private_bank as private_bank
from tests.starlink_oracle.idle_mailbox_contract import (
    once,
    restore_guard,
    restore_service,
    tokens,
)

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "eb96c64738697c10b9c0abb379ab64f6a4a5c59c"


def frozen(name):
    return subprocess.run(["git", "-C", str(HDL), "show",
                           f"{BASE}:library/starlink_pss_acquisition/{name}.v"],
                          text=True, capture_output=True, check=True, timeout=10).stdout


@pytest.mark.parametrize("name,restore", [
    ("starlink_pss_realtime_result_guard", restore_guard),
    ("starlink_pss_shared_realtime_xfft_service", restore_service),
])
def test_whole_source_changes_only_idle_predicate_and_explicit_real_link_connection(name, restore):
    source = (ACQ / f"{name}.v").read_text()
    assert "USE_IDLE_MAILBOX_FAULT" in source
    assert restore(source) == tokens(frozen(name))


def simulate(tmp_path, top, files):
    executable = tmp_path / "probe.vvp"
    compiled = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
                               "-o", str(executable), *map(str, files)],
                              capture_output=True, text=True, check=False, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True,
                            text=True, check=False, timeout=60)
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("mode,predicate,passes", [
    (0, "1'b0", True), (0, "1'b1", True), (0, "1'bx", True), (0, "1'bz", True),
    (1, "mailbox_input_fault", True), (1, "1'b0", False),
    (-1, "1'b0", False), (2, "1'b0", False), ("32'bx", "1'b0", False),
])
def test_default_inertness_general_caller_adapter_and_missing_sticky_fault_witness(tmp_path, mode, predicate, passes):
    top = "tb_starlink_pss_realtime_occupancy"
    source = (ACQ / "tb" / f"{top}.sv").read_text()
    source = once(source, "wire idle_mailbox_fault_now = 1'bz;",
                  f"wire idle_mailbox_fault_now = {predicate};")
    source = once(source, "starlink_pss_realtime_result_guard dut (.*);",
                  f"starlink_pss_realtime_result_guard #(.USE_IDLE_MAILBOX_FAULT({mode})) dut (.*);")
    bench = tmp_path / "probe.sv"
    bench.write_text(source)
    result = simulate(tmp_path, top, [ACQ / "starlink_pss_realtime_result_guard.v",
                      ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v", bench])
    if passes:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OCCUPANCY_REACHABLE_PASS jobs=256 exact_words=131072 ack_fault_cases=254 " in result.stdout
    else:
        assert result.returncode != 0
        assert ("OCCUPANCY_PUBLIC_MISMATCH" if mode == 1 else
                "USE_IDLE_MAILBOX_FAULT must be zero or one") in result.stdout


@pytest.mark.parametrize("half,phase", [(5.0, 1.3), (3.1, 0.7), (6.7, 2.1)])
def test_real_private_mailbox_preserves_golden_outputs_and_idle_premise(tmp_path, monkeypatch, half, phase):
    source = private_bank.TB.read_text()
    source = once(source, "  wire commit_drive = probe.stimulus.guard_valid;",
                  "  wire commit_drive = probe.stimulus.dut.mailbox_commit_valid;\n"
                  "  defparam probe.stimulus.dut.USE_IDLE_MAILBOX_FAULT = 1;\n"
                  "  wire idle_fault_drive = probe.stimulus.mailbox_fault || probe.stimulus.inject_mailbox_fault;\n"
                  "  initial force probe.stimulus.dut.idle_mailbox_fault_now = idle_fault_drive;\n"
                  "  integer idle_checks = 0, ack_checks = 0;\n"
                  "  always @(posedge probe.stimulus.clk or negedge probe.stimulus.clk) begin\n"
                  "    #0.01;\n"
                  "    if (probe.stimulus.resetn && !probe.stimulus.dut.active) begin\n"
                  "      idle_checks = idle_checks + 1;\n"
                  "      if (probe.stimulus.mailbox.input_framing_fault_now !== 1'b0 ||\n"
                  "          probe.stimulus.dut.mailbox_input_fault !== idle_fault_drive)\n"
                  "        $fatal(1, \"IDLE_MAILBOX_PREMISE_FAIL\");\n"
                  "    end\n"
                  "    if (probe.stimulus.resetn && probe.stimulus.dut.awaiting_ack) begin\n"
                  "      ack_checks = ack_checks + 1;\n"
                  "      if (probe.stimulus.dut.active) $fatal(1, \"IDLE_MAILBOX_ACK_ACTIVE\");\n"
                  "    end\n"
                  "  end\n"
                  "  final begin\n"
                  "    if (idle_checks < 100 || ack_checks < 100) $fatal(1, \"IDLE_MAILBOX_COVERAGE_FAIL\");\n"
                  "    $display(\"IDLE_MAILBOX_PREMISE_PASS idle=%0d ack=%0d\", idle_checks, ack_checks);\n"
                  "  end")
    bench = tmp_path / "private_idle.sv"
    bench.write_text(source)
    monkeypatch.setattr(private_bank, "TB", bench)
    result = private_bank.run_probe(tmp_path, "tb_starlink_pss_realtime_private_bank",
                                   (("SLOW_HALF_NS", half), ("SLOW_PHASE_NS", phase)))
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PRIVATE_BANK_PASS healthy=23 rejected=37 independent_resets=12 " in result.stdout
    assert "IDLE_MAILBOX_PREMISE_PASS " in result.stdout


def late_ack_bench():
    source = private_bank.TB.read_text()
    old = re.search(r"  starlink_pss_realtime_result_guard guard \(.*?\n  \);", source, re.DOTALL)
    assert old is not None
    outputs = {"job_ready": (1, "job_ready"), "busy": (1, "busy"), "commit_pulse": (1, "commit"),
               "protocol_fault": (1, "protocol_fault"), "fault_reasons": (8, "reasons"),
               "mailbox_input_valid": (1, "valid"), "mailbox_private_valid": (1, "private_valid"),
               "mailbox_input_data": (36, "data"), "mailbox_input_position": (9, "position"),
               "mailbox_input_last": (1, "last"), "mailbox_input_metadata": (75, "metadata")}
    shadow = old.group().replace("starlink_pss_realtime_result_guard guard (", "frozen_guard shadow (")
    for port, (_, signal) in outputs.items():
        shadow = once(shadow, f".{port}({signal})", f".{port}(shadow_{signal})")
    declarations = "\n".join(f"  wire [{bits-1}:0] shadow_{signal};" for bits, signal in outputs.values())
    candidate = old.group().replace("starlink_pss_realtime_result_guard guard (",
                                    "starlink_pss_realtime_result_guard #(.USE_IDLE_MAILBOX_FAULT(1)) guard (\n"
                                    "    .idle_mailbox_fault_now(fault),")
    monitor = '''
  always @(posedge clk or negedge clk) begin
    #0.02;
    if ({job_ready,busy,commit,protocol_fault,reasons,valid,private_valid} !==
        {shadow_job_ready,shadow_busy,shadow_commit,shadow_protocol_fault,shadow_reasons,shadow_valid,shadow_private_valid})
      $fatal(1,"IDLE_MAILBOX_SHADOW_CONTROL");
    if (private_valid && {data,position,last,metadata} !==
        {shadow_data,shadow_position,shadow_last,shadow_metadata})
      $fatal(1,"IDLE_MAILBOX_SHADOW_PAYLOAD");
    if (resetn && !guard.active && (framing_fault_now !== 1'b0 ||
        guard.mailbox_input_fault !== fault)) $fatal(1,"IDLE_MAILBOX_PREMISE_FAIL");
    if (resetn && guard.awaiting_ack && guard.active) $fatal(1,"IDLE_MAILBOX_ACK_ACTIVE");
  end
'''
    source = once(source, old.group(), declarations + "\n" + shadow + "\n" + candidate + monitor)
    return once(source, ".input_commit_authorized(valid), .input_ready(ready), .input_fault(fault),",
                ".input_commit_authorized(guard.mailbox_commit_valid), .input_ready(ready), .input_fault(fault),")


@pytest.mark.parametrize("corrupt,mutation", [(0, None), (1, None), (1, "final"), (1, "reasons")])
def test_real_current_link_faults_and_ack_match_frozen_guard(tmp_path, corrupt, mutation):
    source = (ACQ / "starlink_pss_realtime_result_guard.v").read_text()
    if mutation == "final":
        source = once(source, "wire final_fault_now = phase_input_fault || mailbox_input_fault ||",
                      "wire final_fault_now = phase_input_fault || idle_mailbox_fault ||")
    elif mutation == "reasons":
        source = once(source, "external_fault_now || mailbox_input_fault};",
                      "external_fault_now || idle_mailbox_fault};")
    runtime = tmp_path / "candidate.v"
    runtime.write_text(source)
    golden = tmp_path / "golden.v"
    golden.write_text(frozen("starlink_pss_realtime_result_guard").replace(
        "module starlink_pss_realtime_result_guard #(", "module frozen_guard #(", 1))
    bench = tmp_path / "probe.sv"
    bench.write_text(late_ack_bench().replace("parameter integer CORRUPT_LINK = 0;",
                                            f"parameter integer CORRUPT_LINK = {corrupt};", 1))
    result = simulate(tmp_path, "tb_starlink_pss_private_bank_late_ack",
                      [runtime, golden, ACQ / "starlink_pss_block_mailbox.v", bench])
    if mutation:
        assert result.returncode != 0 and ("PRIVATE_LINK_" in result.stdout or "IDLE_MAILBOX_SHADOW" in result.stdout)
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert ("PRIVATE_LINK_FAULT_PASS nonfinal=3 held_final=3 " if corrupt else
                "PRIVATE_BANK_LATE_ACK_PASS cases=3 published_words=1536 ") in result.stdout
