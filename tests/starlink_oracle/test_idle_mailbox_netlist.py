"""Fresh synthesized idle-mode guards, not receiver timing or RF qualification."""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_idle_mailbox_contract import (
    ACQ,
    frozen,
    late_ack_bench,
    once,
)


def measured_netlist(mode):
    directory = os.environ.get("STARLINK_PSS_IDLE_MAILBOX_NETLIST_DIR")
    if not directory:
        pytest.skip("explicit actual Vivado idle-mailbox mode measurement required")
    directory = Path(directory)
    scope = (directory / "scope.txt").read_text()
    marker = ("IDLE_MAILBOX_DEPENDENCY_MEASURED active_final_faults_retained=1 "
              "whole_receiver_and_timing_unqualified=1")
    assert scope.splitlines().count(marker) == 1
    assert "USE_PHASE_INPUT_FAULT=1 both_modes=true\n" in scope
    source = (ACQ / "starlink_pss_realtime_result_guard.v").read_bytes()
    assert f"source_sha256={hashlib.sha256(source).hexdigest()}\n" in scope
    assert (directory / "guard.v").read_bytes() == source
    netlist = directory / f"mode{mode}_netlist.v"
    assert f"mode{mode}_netlist_sha256={hashlib.sha256(netlist.read_bytes()).hexdigest()}\n" in scope
    return netlist


def run_netlist(tmp_path, top, sources, marker):
    vendor = Path("/opt/Xilinx/Vivado/2022.2")
    environment = dict(os.environ, LD_LIBRARY_PATH=str(vendor / "lib/lnx64.o/SuSE"))
    commands = [
        [str(vendor / "bin/xvlog"), "--sv", *map(str, sources),
         str(vendor / "data/verilog/src/glbl.v")],
        [str(vendor / "bin/xelab"), "--debug", "typical", "--relax", "--mt", "2",
         "-L", "unisims_ver", top, "glbl", "-s", "idle_snapshot"],
        [str(vendor / "bin/xsim"), "idle_snapshot", "-runall"],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=tmp_path, env=environment, text=True,
                                capture_output=True, check=False, timeout=120)
        (tmp_path / f"netlist_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count(marker) == 1, result.stdout + result.stderr


@pytest.mark.parametrize("mode", [0, 1])
def test_actual_netlists_preserve_general_caller_public_tuple(tmp_path, mode):
    netlist = measured_netlist(mode)
    top = "tb_starlink_pss_realtime_occupancy"
    source = (ACQ / "tb" / f"{top}.sv").read_text()
    source = once(source, "wire phase_input_fault_now = 1'bz;",
                  "wire phase_input_fault_now = external_fault_now || certified_input_beat || certified_input_complete;")
    if mode:
        source = once(source, "wire idle_mailbox_fault_now = 1'bz;",
                      "wire idle_mailbox_fault_now;")
        source = once(source, "starlink_pss_realtime_result_guard dut (.*);",
                      "assign idle_mailbox_fault_now = mailbox_input_fault;\n"
                      "  starlink_pss_realtime_result_guard dut (.*);")
    bench = tmp_path / "probe.sv"
    bench.write_text(source)
    run_netlist(tmp_path, top,
                [netlist, ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v", bench],
                "OCCUPANCY_REACHABLE_PASS jobs=256 exact_words=131072 ack_fault_cases=254 "
                "healthy_ack_cases=2 public_golden=1 no_internal_deposits=1")


@pytest.mark.parametrize("corrupt", [0, 1])
def test_actual_enabled_netlist_real_link_faults_and_ack_against_frozen_guard(tmp_path, corrupt):
    netlist = measured_netlist(1)
    source = late_ack_bench()
    # Select this complete bench only; the source file also contains unrelated
    # mailbox benches with their own sampling delays and helper tasks.
    source = source[source.index("module tb_starlink_pss_private_bank_late_ack;"):]
    source = source[:source.index("\nendmodule") + len("\nendmodule")]
    source = "`timescale 1ns/1ps\n" + source
    source = once(source, "starlink_pss_realtime_result_guard #(.USE_IDLE_MAILBOX_FAULT(1)) guard (",
                  "starlink_pss_realtime_result_guard guard (\n"
                  "    .phase_input_fault_now(external_fault || beat || complete),")
    # Phase observations use the independent frozen RTL reference, not an
    # assumed internal synthesized net name. All public candidate controls and
    # valid payloads still compare against that reference every half-cycle.
    assert source.count("guard.active") == 2 and source.count("guard.awaiting_ack") == 1
    source = source.replace("guard.active", "shadow.active").replace("guard.awaiting_ack", "shadow.awaiting_ack")
    source = once(source, "parameter integer CORRUPT_LINK = 0;",
                  f"parameter integer CORRUPT_LINK = {corrupt};")
    # UNISIM FDCE has a 100 ps Q update delay. Observe after 200 ps on the
    # SAME edge, rather than comparing RTL immediately with not-yet-updated
    # primitive outputs. No stimulus edge, fault expectation or cycle changes.
    source = once(source, "    #0.02;", "    #0.2;")
    source = once(source, "task tick; @(posedge clk); #0.1; endtask",
                  "task tick; @(posedge clk); #0.2; endtask")
    bench = tmp_path / "probe.sv"
    bench.write_text(source)
    golden = tmp_path / "golden.v"
    golden.write_text(once(frozen("starlink_pss_realtime_result_guard"),
                          "module starlink_pss_realtime_result_guard #(", "module frozen_guard #("))
    marker = ("PRIVATE_LINK_FAULT_PASS nonfinal=3 held_final=3 exact_same_edge_reason=01 no_false_commit=1"
              if corrupt else "PRIVATE_BANK_LATE_ACK_PASS cases=3 published_words=1536 reset_recovery=2 same_edge_sync_ack=1")
    run_netlist(tmp_path, "tb_starlink_pss_private_bank_late_ack",
                [netlist, golden, ACQ / "starlink_pss_block_mailbox.v", bench], marker)
