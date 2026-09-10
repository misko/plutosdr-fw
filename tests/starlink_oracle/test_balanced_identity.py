"""Default-preserving LUT equality, immutable checker and omission witnesses."""
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.input_identity_contract import (
    restore_legacy_identity_guard,
    tokens,
)
from tests.starlink_oracle.preflight_identity_contract import (
    restore_held_preflight_wrapper,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "d99c251ee16215a1152be3b4ceac65391bc0e073"


def frozen(name):
    return subprocess.run([
        "git", "-C", str(HDL), "show", f"{BASE}:library/starlink_pss_acquisition/{name}",
    ], capture_output=True, text=True, check=True, timeout=10).stdout


def execute(tmp_path, top, sources, parameters=()):
    executable = tmp_path / "simulation.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        *[f"-P{top}.{parameter}" for parameter in parameters], "-o", str(executable),
        *map(str, sources)], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                            timeout=60, check=False)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    return result.returncode, result.stdout + result.stderr


def test_balanced_entire_guard_delta_and_immutable_reference():
    name = "starlink_pss_realtime_input_guard.v"
    baseline = frozen(name)
    golden = (ACQ / "tb/starlink_pss_input_guard_d99c251e_golden.v").read_text()
    assert golden.replace("starlink_pss_input_guard_d99c251e_golden",
        "starlink_pss_realtime_input_guard") == baseline
    assert restore_legacy_identity_guard((ACQ / name).read_text()) == tokens(baseline)
    wrapper = "starlink_pss_fft_bank_owned_slice.v"
    candidate = restore_held_preflight_wrapper((ACQ / wrapper).read_text())
    opt_in = ",\n    .BALANCED_IDENTITY_EQ(REGISTERED_SCHEDULING)"
    assert candidate.count(opt_in) == 1
    assert candidate.replace(opt_in, "", 1) == frozen(wrapper)


@pytest.mark.parametrize("mode,mutation", [(0, False), (1, False), (1, True), (2, False)])
def test_every_identity_bit_and_omitted_bit69(tmp_path, mode, mutation):
    candidate = (ACQ / "starlink_pss_realtime_input_guard.v").read_text()
    if mutation:
        old = "assign leaf_equal[leaf] = input_metadata[3*leaf +: BITS] == descriptor[3*leaf +: BITS];"
        assert candidate.count(old) == 1
        candidate = candidate.replace(old, "assign leaf_equal[leaf] = leaf == 23 ? 1'b1 : "
            "input_metadata[3*leaf +: BITS] == descriptor[3*leaf +: BITS];", 1)
    source = tmp_path / "candidate.v"
    source.write_text(candidate)
    top = "tb_starlink_pss_balanced_identity"
    rc, log = execute(tmp_path, top, [source, ACQ / "tb/starlink_pss_input_guard_d99c251e_golden.v",
        ACQ / "tb" / f"{top}.sv"], [f"BALANCED_MODE={mode}"])
    if mutation:
        assert rc != 0 and "BALANCED_IDENTITY_MISMATCH bit=69 slot=0 ready=0" in log, log
        assert "BALANCED_IDENTITY_PASS" not in log
    elif mode == 2:
        assert rc != 0 and "BALANCED_IDENTITY_EQ must be zero or one" in log, log
    else:
        assert rc == 0 and f"BALANCED_IDENTITY_PASS mode={mode} bits=70 rows=420" in log, log


@pytest.mark.parametrize("identity", [0, 1])
def test_balanced_existing_full_cursor_fault_stall_reset_witness(tmp_path, identity):
    name = "tb_starlink_pss_realtime_input_guard.sv"
    bench = (ACQ / "tb" / name).read_text()
    anchor = "#(.CHECK_INPUT_BLOCK_IDENTITY(CHECK_IDENTITY)) dut ("
    assert bench.count(anchor) == 1
    bench = bench.replace(anchor,
        "#(.CHECK_INPUT_BLOCK_IDENTITY(CHECK_IDENTITY), .BALANCED_IDENTITY_EQ(1)) dut (", 1)
    stimulus = tmp_path / name
    stimulus.write_text(bench)
    top = "tb_starlink_pss_input_cursor_equivalence"
    rc, log = execute(tmp_path, top, [ACQ / "starlink_pss_realtime_input_guard.v",
        ACQ / "tb/starlink_pss_realtime_input_guard_0a1af893_golden.v", stimulus,
        ACQ / "tb" / f"{top}.sv"], [f"CHECK_IDENTITY={identity}"])
    assert rc == 0 and f"INPUT_CURSOR_EQ_PASS identity={identity}" in log, log
    assert f"identity={identity} healthy={4 if identity else 5} rejected={26 if identity else 22}" in log


@pytest.mark.parametrize("mutation", [0, 1])
def test_balanced_simultaneous_final_input_output_and_duplicate_veto(tmp_path, mutation):
    top = "tb_starlink_pss_completed_input_fence"
    bench = (ACQ / "tb" / f"{top}.sv").read_text()
    anchor = "starlink_pss_realtime_input_guard input_guard ("
    assert bench.count(anchor) == 1
    bench = bench.replace(anchor,
        "starlink_pss_realtime_input_guard #(.BALANCED_IDENTITY_EQ(1)) input_guard (", 1)
    stimulus = tmp_path / f"{top}.sv"
    stimulus.write_text(bench)
    rc, log = execute(tmp_path, top, [ACQ / "starlink_pss_realtime_input_guard.v",
        ACQ / "starlink_pss_realtime_result_guard.v", stimulus], [f"MUTATE_DUPLICATE={mutation}"])
    if mutation:
        assert rc != 0 and "COMPLETED_INPUT_EQ_MISMATCH phase=2 kind=0" in log, log
        assert "COMPLETED_INPUT_FENCE_PASS" not in log
    else:
        assert rc == 0 and "COMPLETED_INPUT_FENCE_PASS healthy=4 rejected=26 simultaneous_edges=1" in log, log
        assert "commits=3" in log
