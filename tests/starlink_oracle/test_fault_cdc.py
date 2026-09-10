"""Offline CDC stage recurrence, not vendor FFT or analog CDC qualification."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.fault_cdc_contract import BASE, restore_fault_cdc
from tests.starlink_oracle.test_exact_control import KINDS, STUB

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"


def frozen(name):
    return subprocess.run(
        [
            "git",
            "-C",
            str(HDL),
            "show",
            f"{BASE}:library/starlink_pss_acquisition/{name}",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout


def test_entire_runtime_inverse_and_original_actual_bench_unchanged():
    for kind in KINDS:
        name = f"starlink_pss_{kind}.v"
        current = (ACQ / name).read_text()
        if kind == "fft_bank_owned_slice":
            current = restore_fault_cdc(current)
        assert current == frozen(name)
    name = "tb/tb_starlink_pss_fft_bank_owned_slice.sv"
    assert (ACQ / name).read_text() == frozen(name)
    text = (ACQ / "starlink_pss_fft_bank_owned_slice.v").read_text()
    assert '(* ASYNC_REG = "TRUE" *) reg [1:0] cause_sync;' in text
    assert "cause_index < 12" in text
    assert (
        "else cause_sync <= {cause_sync[0], distributed_fast_fault.cause_sticky[cause_index]};"
        in text
    )
    assert "assign first_stage[cause_index] = cause_sync[0];" in text
    assert "assign second_stage[cause_index] = cause_sync[1];" in text


def test_compatibility_composition_preserves_entire_old_inverse_helper():
    path = Path(__file__).with_name("exact_control_contract.py")
    current = path.read_text()
    additions = (
        "from tests.starlink_oracle.fault_cdc_contract import restore_fault_cdc\n\n",
        (
            '        if "parameter integer PER_CAUSE_FAULT_CDC" in source:\n'
            "            source = restore_fault_cdc(source)\n"
        ),
    )
    for addition in additions:
        assert current.count(addition) == 1
        current = current.replace(addition, "", 1)
    original = subprocess.run(
        [
            "git",
            "-C",
            str(HDL.parent),
            "show",
            "bdd2fd5e3e6da0da1831dca8db5793cbf9a1ddba:tests/starlink_oracle/exact_control_contract.py",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    assert current == original


@pytest.mark.parametrize(
    "old,new",
    [
        ("cause_sync[1];", "cause_sync[0];"),
        ("if (!slow_running) cause_sync <= 0;", "if (!core_aresetn) cause_sync <= 0;"),
        ("cause_index < 12", "cause_index < 11"),
        (
            "PER_CAUSE_FAULT_CDC && DISTRIBUTED_FAST_FAULT",
            "PER_CAUSE_FAULT_CDC || DISTRIBUTED_FAST_FAULT",
        ),
        (
            "parameter integer PER_CAUSE_FAULT_CDC = 0",
            "parameter integer PER_CAUSE_FAULT_CDC = 1",
        ),
        (
            "fast_fault_slow <= {fast_fault_slow[0], fast_fault};",
            "fast_fault_slow <= 0;",
        ),
    ],
)
def test_malformed_cdc_addition_is_not_silently_stripped(old, new):
    source = (ACQ / "starlink_pss_fft_bank_owned_slice.v").read_text()
    assert old in source
    with pytest.raises(ValueError, match="CDC body|CDC inverse addition"):
        restore_fault_cdc(source.replace(old, new))


def run(tmp_path, parameters=(), mutation=None, bench=None):
    sources = []
    for kind in KINDS:
        name = f"starlink_pss_{kind}"
        candidate = (ACQ / f"{name}.v").read_text()
        if kind == "fft_bank_owned_slice" and mutation:
            for old, new in mutation:
                assert candidate.count(old) == 1, old
                candidate = candidate.replace(old, new, 1)
        path = tmp_path / f"{name}.v"
        path.write_text(candidate)
        sources.append(path)
        golden = frozen(f"{name}.v")
        for rename in KINDS:
            golden = golden.replace(
                f"starlink_pss_{rename}", f"starlink_pss_{rename}_cdc_golden"
            )
        path = tmp_path / f"{name}_cdc_golden.v"
        path.write_text(golden)
        sources.append(path)
    path = tmp_path / "quiescent_fft_stub.v"
    path.write_text(STUB)
    sources.append(path)
    path = tmp_path / "tb_starlink_pss_fault_cdc.sv"
    path.write_text(
        bench if bench is not None else (ACQ / "tb" / path.name).read_text()
    )
    sources.append(path)
    shutil.copyfile(
        ACQ
        / "evidence/exact-control-combined-route-v1/frozen_sources/upper_edge_pss_kernel_q17.mem",
        tmp_path / "upper_edge_pss_kernel_q17.mem",
    )
    executable = tmp_path / "simulation.vvp"
    compiled = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-s",
            "tb_starlink_pss_fault_cdc",
            *[f"-Ptb_starlink_pss_fault_cdc.{p}" for p in parameters],
            "-o",
            str(executable),
            *map(str, sources),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(
        ["vvp", str(executable)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("registered", [0, 1])
@pytest.mark.parametrize("phase", [0, 713, 2857])
def test_per_cause_matches_frozen_aggregate_all_subsets_and_reset_phases(
    tmp_path, registered, phase
):
    rc, log = run(tmp_path, [f"REGISTERED={registered}", f"SLOW_PHASE_PS={phase}"])
    assert rc == 0, log
    marker = re.findall(r"^FAULT_CDC_PASS (.*)$", log, re.MULTILINE)
    assert len(marker) == 1
    fields = dict(item.split("=") for item in marker[0].split())
    assert fields == {
        "enabled": "1",
        "registered": str(registered),
        "phase_ps": str(phase),
        "masks": "4096",
        "x_rows": "48",
        "reset_rows": "3",
        "private_reset_rows": "1",
        "slow_checks": fields["slow_checks"],
        "fast_checks": fields["fast_checks"],
        "quiescent_stub_not_fft": "1",
    }
    assert int(fields["slow_checks"]) > 16000 and int(fields["fast_checks"]) > 16000


@pytest.mark.parametrize("registered", [0, 1])
def test_default_aggregate_mode_is_unchanged(tmp_path, registered):
    rc, log = run(tmp_path, ["ENABLED=0", f"REGISTERED={registered}"])
    assert rc == 0 and f"FAULT_CDC_PASS enabled=0 registered={registered}" in log, log


@pytest.mark.parametrize("cause", range(12))
def test_each_missing_cause_is_rejected(tmp_path, cause):
    rc, log = run(
        tmp_path,
        mutation=[
            (
                "assign second_stage[cause_index] = cause_sync[1];",
                f"assign second_stage[cause_index] = cause_index == {cause} ? 1'b0 : cause_sync[1];",
            )
        ],
    )
    assert rc != 0 and "CDC_STAGE_OR_PUBLIC_MISMATCH" in log, log
    assert "FAULT_CDC_PASS" not in log


@pytest.mark.parametrize(
    "kind", ["missing_stage", "private_reset", "wrong_epoch_reset", "added_latency"]
)
def test_latency_and_wrong_reset_mutants_are_rejected(tmp_path, kind):
    changes = {
        "missing_stage": [
            (
                "assign second_stage[cause_index] = cause_sync[1];",
                "assign second_stage[cause_index] = cause_sync[0];",
            )
        ],
        "private_reset": [
            (
                "if (!slow_running) cause_sync <= 0;",
                "if (!slow_running || !core_aresetn) cause_sync <= 0;",
            )
        ],
        "wrong_epoch_reset": [
            ("if (!slow_running) cause_sync <= 0;", "if (!resetn) cause_sync <= 0;")
        ],
        "added_latency": [
            ("reg [1:0] cause_sync;", "reg [2:0] cause_sync;"),
            (
                "{cause_sync[0], distributed_fast_fault.cause_sticky[cause_index]}",
                "{cause_sync[1:0], distributed_fast_fault.cause_sticky[cause_index]}",
            ),
            (
                "assign first_stage[cause_index] = cause_sync[0];",
                "assign first_stage[cause_index] = cause_sync[1];",
            ),
            (
                "assign second_stage[cause_index] = cause_sync[1];",
                "assign second_stage[cause_index] = cause_sync[2];",
            ),
        ],
    }[kind]
    rc, log = run(tmp_path, mutation=changes)
    assert rc != 0 and "CDC_STAGE_OR_PUBLIC_MISMATCH" in log, log
    assert "FAULT_CDC_PASS" not in log


@pytest.mark.parametrize(
    "invalid", ["-1", "2", "32'bx", "32'bz", "disabled_distributed"]
)
def test_new_option_fails_closed(tmp_path, invalid):
    value = "1" if invalid == "disabled_distributed" else invalid
    distributed = "0" if invalid == "disabled_distributed" else "1"
    bench = f"""module tb_starlink_pss_fault_cdc;
starlink_pss_fft_bank_owned_slice #(.DISTRIBUTED_FAST_FAULT({distributed}),
  .PER_CAUSE_FAULT_CDC({value})) candidate ();
initial begin #10; $fatal(1,"CDC_BAD_OPTION_ACCEPTED"); end
endmodule
"""
    rc, log = run(tmp_path, bench=bench)
    reason = (
        "requires DISTRIBUTED_FAST_FAULT"
        if invalid == "disabled_distributed"
        else "must be zero or one"
    )
    assert rc != 0 and "PER_CAUSE_FAULT_CDC " + reason in log, log
    assert "CDC_BAD_OPTION_ACCEPTED" not in log
