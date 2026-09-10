"""Phase-exclusive certified retirement; frozen guard and real raw-mailbox faults."""
import itertools
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.exact_control_contract import restore_exact_control
from tests.starlink_oracle.forward_retirement_contract import (
    FORWARD_BODY,
    restore_forward_actual,
    restore_forward_guard,
    restore_forward_wrapper,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
TB = ACQ / "tb"
BASE = "ce6a885e60592a926c4c2d8b8c069ea45397b900"
TOP = "tb_starlink_pss_forward_retirement"


def frozen(name):
    return subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/{name}"], capture_output=True,
        text=True, check=True, timeout=10).stdout


def test_literal_whole_guard_wrapper_and_frozen_old_guard_inverse():
    guard = "starlink_pss_realtime_result_guard"
    assert restore_forward_guard((ACQ / f"{guard}.v").read_text()) == frozen(f"{guard}.v")
    assert (TB / f"{guard}_ce6a885e_golden.v").read_text().replace(
        f"module {guard}_ce6a885e_golden #(", f"module {guard} #(") == frozen(f"{guard}.v")
    wrapper = "starlink_pss_fft_bank_owned_slice.v"
    assert restore_forward_wrapper((ACQ / wrapper).read_text()) == frozen(wrapper)
    for name in ("block_mailbox", "realtime_input_guard", "forward_kernel_join", "kernel_rom", "spectrum_product"):
        name = f"starlink_pss_{name}.v"
        assert restore_exact_control((ACQ / name).read_text(),
            name.removeprefix("starlink_pss_").removesuffix(".v")) == frozen(name)


def test_actual_all_old_stimulus_shadow_assertions_and_csv_operations_literal():
    name = "tb/tb_starlink_pss_fft_bank_owned_slice.sv"
    assert restore_forward_actual((ACQ / name).read_text()) == frozen(name)
    source = (TB / "starlink_pss_forward_retirement_shadow.sv").read_text()
    assert "starlink_pss_realtime_result_guard_ce6a885e_golden" in source
    assert "old_valid && !inverse_phase" in source
    assert "forward_nonfinal_fault" not in source and "forward_final_fault" not in source
    assert "FORWARD_CALLER_PHASE_INVARIANT_BROKEN" in source


def test_legacy_bench_bindings_leave_all_stimulus_assertions_and_phase_mutant_literal():
    binding = "    .inverse_phase(1'b0), .forward_mailbox_fault(1'b0), .forward_retirement_valid(),"
    for kind in ("occupancy", "final_veto_equivalence"):
        name = f"tb/tb_starlink_pss_realtime_{kind}.sv"
        source = (ACQ / name).read_text()
        assert source.count(binding) == 1 and "USE_FORWARD_RETIREMENT" not in source
        if kind == "occupancy":
            source = source.replace("dut (\n" + binding + " .*);", "dut (.*);", 1)
        else:
            source = source.replace(binding + "\n", "", 1)
        assert source == frozen(name)
    path = Path(__file__).with_name("test_phase_input_contract.py")
    source = path.read_text()
    new = '''    bench_source = replace_once(bench_source, "starlink_pss_realtime_result_guard dut (\\n"
        "    .inverse_phase(1'b0), .forward_mailbox_fault(1'b0), .forward_retirement_valid(), .*);",
        f"starlink_pss_realtime_result_guard #(.USE_PHASE_INPUT_FAULT({mode})) dut (\\n"
        "    .inverse_phase(1'b0), .forward_mailbox_fault(1'b0), .forward_retirement_valid(), .*);")'''
    old = '''    bench_source = replace_once(bench_source, "starlink_pss_realtime_result_guard dut (.*);",
        f"starlink_pss_realtime_result_guard #(.USE_PHASE_INPUT_FAULT({mode})) dut (.*);")'''
    assert source.count(new) == 1
    baseline = subprocess.run(["git", "-C", str(HDL.parent), "show",
        "ce987ffe5ef3b7a1e8780cd99e37b64bba90ea99:tests/starlink_oracle/test_phase_input_contract.py"],
        capture_output=True, text=True, check=True, timeout=10).stdout
    assert source.replace(new, old, 1) == baseline


def run(tmp_path, parameters, mutation=None):
    source = (ACQ / "starlink_pss_realtime_result_guard.v").read_text()
    if mutation:
        assert source.count(FORWARD_BODY) == 1
        changed = FORWARD_BODY
        if mutation == "phase_mask":
            changed = changed.replace("USE_FORWARD_RETIREMENT && !inverse_phase &&",
                                      "USE_FORWARD_RETIREMENT &&")
        elif mutation == "sticky_veto":
            assert changed.count("forward_mailbox_fault") == 3
            changed = changed.replace("forward_mailbox_fault", "1'b0")
        elif mutation in {"raw_private", "nonfinal_raw_private"}:
            start = changed.index("  assign forward_retirement_valid")
            end = changed.index("  // END FORWARD_RETIREMENT")
            payload = "mailbox_private_valid" if mutation == "raw_private" else (
                "(return_last ? mailbox_input_valid : mailbox_private_valid)")
            changed = changed[:start] + (
                "  assign forward_retirement_valid = USE_FORWARD_RETIREMENT && "
                f"!inverse_phase && {payload};\n") + changed[end:]
        else:
            raise AssertionError(mutation)
        assert changed != FORWARD_BODY
        source = source.replace(FORWARD_BODY, changed, 1)
    candidate = tmp_path / "starlink_pss_realtime_result_guard.v"
    candidate.write_text(source)
    sources = [candidate]
    for path in (ACQ / "starlink_pss_block_mailbox.v",
                 TB / "starlink_pss_realtime_result_guard_ce6a885e_golden.v",
                 TB / "starlink_pss_forward_retirement_shadow.sv", TB / f"{TOP}.sv"):
        copy = tmp_path / path.name
        shutil.copyfile(path, copy)
        sources.append(copy)
    executable = tmp_path / "simulation.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", TOP,
        *[f"-P{TOP}.{item}" for item in parameters], "-o", str(executable), *map(str, sources)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, capture_output=True,
                            text=True, timeout=45, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("enabled,completed,phase_input", list(itertools.product((0, 1), repeat=3)))
def test_all_modes_real_mailbox_75bits_phases_stalls_final_faults_unknown_and_reset(
        tmp_path, enabled, completed, phase_input):
    rc, log = run(tmp_path, [f"ENABLED={enabled}", f"COMPLETED={completed}", f"PHASE_INPUT={phase_input}"])
    assert rc == 0, log
    assert f"FORWARD_RETIREMENT_PASS enabled={enabled} completed={completed} phase_input={phase_input}" in log
    assert "bit_rows=900" in log and "position_rows=12288" in log and "snapshot_not_fft=1" in log


@pytest.mark.parametrize("mutation", ["phase_mask", "sticky_veto", "raw_private", "nonfinal_raw_private"])
def test_missing_phase_sticky_or_raw_private_retirement_mutants_rejected(tmp_path, mutation):
    rc, log = run(tmp_path, ["ENABLED=1"], mutation)
    assert rc != 0 and "FORWARD_RETIREMENT_MISMATCH" in log, log
    assert "FORWARD_RETIREMENT_PASS" not in log


def test_wrong_wrapper_phase_wiring_rejected(tmp_path):
    rc, log = run(tmp_path, ["ENABLED=1", "WRONG_PHASE_WIRING=1"])
    assert rc != 0 and "FORWARD_RETIREMENT_MISMATCH" in log, log
    assert "FORWARD_RETIREMENT_PASS" not in log


def test_deliberately_inconsistent_interface_is_rejected_not_called_equivalent(tmp_path):
    rc, log = run(tmp_path, ["BROKEN_CALLER=1"])
    assert rc != 0 and "FORWARD_CALLER_PHASE_INVARIANT_BROKEN" in log, log
    assert "FORWARD_RETIREMENT_PASS" not in log
