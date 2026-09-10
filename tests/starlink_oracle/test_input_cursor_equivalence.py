"""Private input cursor: immutable public checker comparison, not timing proof."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.input_identity_contract import restore_legacy_identity_guard

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "0a1af8933bb7d9bc4f0fa78b3350196e98045cda"


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def test_entire_cursor_delta_preserves_all_public_checks_and_frozen_reference():
    baseline = subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/starlink_pss_realtime_input_guard.v"],
        capture_output=True, text=True, timeout=10, check=True).stdout
    golden = (ACQ / "tb/starlink_pss_realtime_input_guard_0a1af893_golden.v").read_text()
    assert tokens(golden.replace("starlink_pss_realtime_input_guard_0a1af893_golden",
        "starlink_pss_realtime_input_guard")) == tokens(baseline)
    candidate = restore_legacy_identity_guard((ACQ / "starlink_pss_realtime_input_guard.v").read_text())
    # The completed-input experiment exports ONLY an alias of the existing
    # duplicate-start predicate. Prove that exact addition, then retain the
    # original whole-body comparison: no input check/reason may be removed.
    alias_port = "outputwireduplicate_start_fault_now,"
    alias_assign = "assignduplicate_start_fault_now=duplicate_start;"
    assert candidate.count(alias_port) == candidate.count(alias_assign) == 1
    candidate = candidate.replace(alias_port, "", 1).replace(alias_assign, "", 1)
    event_port = "outputwire[2:0]fault_events_now,"
    event_assign = "assignfault_events_now=errors_now;"
    assert candidate.count(event_port) == candidate.count(event_assign) == 1
    candidate = candidate.replace(event_port, "", 1).replace(event_assign, "", 1)
    private = ("if(slot_open&&input_enable&&input_valid&&core_input_tready&&expected_position!=511)"
               "expected_position<=expected_position+1'b1;")
    assert candidate.count(private) == 1
    candidate = candidate.replace(private, "", 1)
    completion = "if(certified_input_complete)input_complete<=1;"
    assert candidate.count(completion) == 1
    candidate = candidate.replace(completion,
        completion + "elseexpected_position<=expected_position+1'b1;", 1)
    assert candidate == tokens(baseline)


@pytest.mark.parametrize("identity", [0, 1])
def test_private_cursor_has_reachable_fault_witness_and_exact_public_outputs(tmp_path, identity):
    top = "tb_starlink_pss_input_cursor_equivalence"
    executable = tmp_path / "cursor.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.CHECK_IDENTITY={identity}", "-o", str(executable),
        str(ACQ / "starlink_pss_realtime_input_guard.v"),
        str(ACQ / "tb/starlink_pss_realtime_input_guard_0a1af893_golden.v"),
        str(ACQ / "tb/tb_starlink_pss_realtime_input_guard.sv"),
        str(ACQ / "tb" / f"{top}.sv")], capture_output=True, text=True,
        timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
        timeout=30, check=False)
    transcript = result.stdout + result.stderr
    (tmp_path / "input_cursor.log").write_text(transcript)
    assert result.returncode == 0, transcript
    rows = re.findall(rf"(?m)^INPUT_CURSOR_EQ_PASS identity={identity} "
        r"public_comparisons=(\d+) private_fault_rows=(\d+) no_internal_deposits=1$", transcript)
    assert len(rows) == 1 and int(rows[0][0]) >= 10000 and int(rows[0][1]) >= 10, transcript
    assert f"identity={identity} healthy={4 if identity else 5} rejected={26 if identity else 22}" in transcript


@pytest.mark.parametrize("identity", [0, 1])
@pytest.mark.parametrize("variant", ["baseline", "candidate"])
def test_actual_cursor_netlists_preserve_public_input_checker_contract(tmp_path, identity, variant):
    measured = os.environ.get("STARLINK_PSS_INPUT_CURSOR_NETLIST_DIR")
    if not measured:
        pytest.skip("explicit actual Vivado input-cursor measurement required")
    measured = Path(measured)
    scope = (measured / "scope.txt").read_text()
    assert "INPUT_CURSOR_DEPENDENCY_MEASURED whole_receiver_and_timing_unqualified=1" in scope
    candidate_hash = hashlib.sha256((ACQ / "starlink_pss_realtime_input_guard.v").read_bytes()).hexdigest()
    assert f"{candidate_hash}  {measured / 'candidate.v'}\n" in scope
    netlist = measured / f"{variant}_{identity}_netlist.v"
    digest = hashlib.sha256(netlist.read_bytes()).hexdigest()
    assert f"{variant}_{identity}_netlist_sha256={digest}\n" in scope
    stimulus = (ACQ / "tb/tb_starlink_pss_realtime_input_guard.sv").read_text()
    anchor = "starlink_pss_realtime_input_guard #(.CHECK_INPUT_BLOCK_IDENTITY(CHECK_IDENTITY)) dut ("
    assert stimulus.count(anchor) == 1
    stimulus = stimulus.replace(anchor, "starlink_pss_realtime_input_guard dut (", 1)
    # Vendor GSR and 100ps FDCE clock-to-Q need explicit simulator-only startup
    # and observation margins. Apply the same adapter to both measured designs.
    anchor = "  initial begin\n    healthy_job(0, 0);"
    assert stimulus.count(anchor) == 1
    stimulus = stimulus.replace(anchor,
        "  initial begin\n    #120; input_data = 1; input_enable = 1; input_valid = 1;\n"
        "    #1; healthy_job(0, 0);", 1).replace("#0.1;", "#0.3;")
    stimulus_path = tmp_path / "stimulus.sv"
    stimulus_path.write_text(stimulus)
    top = "tb_starlink_pss_input_cursor_equivalence"
    bench = (ACQ / "tb" / f"{top}.sv").read_text()
    bench = bench.replace("parameter integer CHECK_IDENTITY = 1",
        f"parameter integer CHECK_IDENTITY = {identity}", 1)
    bench = bench.replace("always @(posedge stimulus.clk or negedge stimulus.clk) begin",
        "always @(posedge stimulus.clk or negedge stimulus.clk) if ($time > 125) begin", 1)
    # Only the synthesized spelling changes; this is an observation, not a
    # deposit. Baseline is not expected to have candidate-only private changes.
    assert "wire [8:0]expected_position_reg;" in netlist.read_text()
    bench = bench.replace("stimulus.dut.expected_position", "stimulus.dut.expected_position_reg")
    if variant == "baseline":
        bench = bench.replace("private_fault_rows < 10", "private_fault_rows < 0", 1)
    bench_path = tmp_path / "comparison.sv"
    bench_path.write_text(bench)
    vendor = Path("/opt/Xilinx/Vivado/2022.2")
    environment = dict(os.environ, LD_LIBRARY_PATH=str(vendor / "lib/lnx64.o/SuSE"))
    commands = [
        [str(vendor / "bin/xvlog"), "--sv", str(netlist),
         str(ACQ / "tb/starlink_pss_realtime_input_guard_0a1af893_golden.v"),
         str(stimulus_path), str(bench_path), str(vendor / "data/verilog/src/glbl.v")],
        [str(vendor / "bin/xelab"), "--debug", "typical", "--relax", "--mt", "2",
         "-L", "unisims_ver", top, "glbl", "-s", "cursor_snapshot"],
        [str(vendor / "bin/xsim"), "cursor_snapshot", "-runall"],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True,
            text=True, timeout=120, check=False)
        (tmp_path / f"cursor_netlist_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    assert f"INPUT_CURSOR_EQ_PASS identity={identity} " in result.stdout
    assert f"identity={identity} healthy={4 if identity else 5} rejected={26 if identity else 22}" in result.stdout
