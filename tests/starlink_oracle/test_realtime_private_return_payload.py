"""Private fault-edge captures with a real mailbox; not FPGA/FFT qualification."""
from pathlib import Path
import re
import subprocess

import pytest


ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_private_return_payload"


def run_payload_probe(tmp_path, *, slow_half=5.0, phase=1.3, mutation=None):
    runtime = ACQ / "starlink_pss_realtime_result_guard.v"
    if mutation is not None:
        old, new = mutation
        source = runtime.read_text()
        assert source.count(old) == 1, "mutation must alter exactly one intended predicate"
        runtime = tmp_path / "mutated_guard.v"
        runtime.write_text(source.replace(old, new, 1))
    executable = tmp_path / "private_payload.vvp"
    compiled = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.SLOW_HALF_NS={slow_half}", f"-P{TOP}.SLOW_PHASE_NS={phase}",
        "-o", str(executable), str(runtime), str(ACQ / "starlink_pss_block_mailbox.v"),
        str(ACQ / "tb/tb_starlink_pss_realtime_result_guard.sv"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(["vvp", str(executable)], capture_output=True,
                          text=True, timeout=30)


@pytest.mark.parametrize("slow_half,phase", [(5.0, 1.3), (3.1, 0.7), (6.7, 2.1)])
def test_faulted_private_payload_never_becomes_valid_or_reusable(tmp_path, slow_half, phase):
    result = run_payload_probe(tmp_path, slow_half=slow_half, phase=phase)
    text = result.stdout + result.stderr
    assert result.returncode == 0, text
    assert not re.search(r"(?im)^\s*(fatal|error)(:|\s)", text)
    assert result.stdout.splitlines().count(
        "EFFECTIVE_INPUT_FULL_PASS rows=2048 binary_domain_only=1"
    ) == 1
    rows = re.findall(
        r"(?m)^PRIVATE_RETURN_PAYLOAD_PASS fault_captures=21 changed_fault_payloads=21 "
        r"reset_epochs=21 legacy_healthy=23 legacy_rejected=37 independent_resets=12 "
        r"real_mailbox=1 quarantine_edges=(\d+) capture_edges=(\d+)$", result.stdout,
    )
    assert len(rows) == 1, text
    assert tuple(map(int, rows[0])) == (504, 25882)
    assert "REALTIME_RESULT_GUARD_PASS healthy=23 rejected=37 independent_resets=12 " in text


@pytest.mark.parametrize("old,new,witness", [
    (
        "if (active && !protocol_fault && core_output_tvalid) begin",
        "if (active && !protocol_fault && core_output_tvalid && !fault_now) begin",
        "PRIVATE_RETURN_CAPTURE_MISMATCH",
    ),
    (
        "return_position <= core_output_tuser[8:0];",
        "return_position <= {1'b0, core_output_tuser[7:0]};",
        "PRIVATE_RETURN_CAPTURE_MISMATCH",
    ),
    (
        "if (protocol_fault || fault_now) begin\n        active <= 0;\n        return_valid <= 0;",
        "if (protocol_fault || fault_now) begin\n        active <= 0;\n        return_valid <= 1;",
        "PRIVATE_RETURN_FAULT_EDGE_ESCAPED",
    ),
    (
        "(input_count == 511 && certified_input_beat)",
        "(input_count == 510 && certified_input_beat)",
        "EFFECTIVE_INPUT_FULL_MISMATCH",
    ),
])
def test_probe_detects_private_capture_validity_and_count_mutations(tmp_path, old, new, witness):
    result = run_payload_probe(tmp_path, mutation=(old, new))
    text = result.stdout + result.stderr
    assert result.returncode != 0 and witness in text, text
    assert "PRIVATE_RETURN_PAYLOAD_PASS " not in text
