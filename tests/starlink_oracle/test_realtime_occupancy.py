"""Reachable public ACK/fault differential tests, independent of state encoding."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_occupancy"
MARKER = (
    "OCCUPANCY_REACHABLE_PASS jobs=256 exact_words=131072 ack_fault_cases=254 "
    "healthy_ack_cases=2 public_golden=1 no_internal_deposits=1"
)


def run_probe(tmp_path, mutation=None, netlist=None):
    runtime = netlist or ACQ / "starlink_pss_realtime_result_guard.v"
    if netlist:
        # Use the vendor's precompiled primitive models for actual synthesized
        # netlists. Icarus + source UNISIM models produced initialization Xs in
        # the unchanged baseline; retain those failed diagnostics separately.
        vendor = Path("/opt/Xilinx/Vivado/2022.2")
        environment = dict(os.environ, LD_LIBRARY_PATH=str(vendor / "lib/lnx64.o/SuSE"))
        commands = [
            [str(vendor / "bin/xvlog"), "--sv", str(netlist),
             str(ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"),
             str(ACQ / "tb" / f"{TOP}.sv"), str(vendor / "data/verilog/src/glbl.v")],
            [str(vendor / "bin/xelab"), "--debug", "typical", "--relax", "--mt", "2",
             "-L", "unisims_ver", TOP, "glbl", "-s", "occupancy_snapshot"],
            [str(vendor / "bin/xsim"), "occupancy_snapshot", "-runall"],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True,
                                    text=True, timeout=120, check=False)
            assert result.returncode == 0, result.stdout + result.stderr
        return result
    if mutation:
        old, new = mutation
        source = runtime.read_text()
        assert source.count(old) == 1
        runtime = tmp_path / "mutant.v"
        runtime.write_text(source.replace(old, new, 1))
    executable = tmp_path / "occupancy.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, "-o", str(executable), str(runtime),
        str(ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                          timeout=60, check=False)


def test_reachable_ack_wait_all_orphans_and_next_cycle_reason_accumulation(tmp_path):
    result = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count(MARKER) == 1


@pytest.mark.parametrize("old,new", [
    ("if (awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now)",
     "if (awaiting_ack && mailbox_input_ready)"),
    ("if (final_commit) awaiting_ack <= 1;", "if (final_commit) awaiting_ack <= 0;"),
])
def test_public_probe_rejects_faulted_ack_release_and_missing_ack_ownership(tmp_path, old, new):
    result = run_probe(tmp_path, (old, new))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and "OCCUPANCY_PUBLIC_MISMATCH" in text, text
    assert MARKER not in text


@pytest.mark.parametrize("variant", ["baseline", "candidate"])
def test_actual_synthesized_guard_preserves_reachable_public_contract(tmp_path, variant):
    measured = os.environ.get("STARLINK_PSS_OCCUPANCY_NETLIST_DIR")
    if not measured:
        pytest.skip("explicit actual Vivado guard measurement required")
    measured = Path(measured)
    scope = (measured / "scope.txt").read_text()
    assert "GUARD_OCCUPANCY_DEPENDENCY_MEASURED whole_receiver_and_timing_unqualified=1" in scope
    candidate_digest = hashlib.sha256((ACQ / "starlink_pss_realtime_result_guard.v").read_bytes()).hexdigest()
    assert f"candidate_sha256={candidate_digest}\n" in scope
    netlist = measured / f"{variant}_netlist.v"
    digest = hashlib.sha256(netlist.read_bytes()).hexdigest()
    assert f"{variant}_netlist_sha256={digest}\n" in scope
    result = run_probe(tmp_path, netlist=netlist)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines().count(MARKER) == 1
