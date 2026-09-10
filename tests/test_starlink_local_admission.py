"""Offline exact first-admission CE equivalence; no FFT or physical execution."""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "local_recipe", ROOT / "tests/starlink_oracle/local_admission.py"
)
RECIPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECIPE)
BENCH = ACQ / "tb/tb_starlink_pss_local_admission.sv"


def original(name):
    return subprocess.run(
        [
            "git",
            "-C",
            str(ROOT / "hdl"),
            "show",
            f"{RECIPE.BASE}:library/starlink_pss_acquisition/{name}.v",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout


def clean_env():
    env = os.environ.copy()
    for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    return env


def simulate(directory, source=None, check=1, balanced=1):
    directory.mkdir()
    legacy = original(RECIPE.OLD_GUARD).replace(
        f"module {RECIPE.OLD_GUARD} #(\n",
        "module local_admission_original_guard #(\n",
        1,
    )
    (directory / "original.v").write_text(legacy)
    (directory / "candidate.v").write_text(
        source if source is not None else (ACQ / f"{RECIPE.GUARD}.v").read_text()
    )
    (directory / "bench.sv").write_bytes(BENCH.read_bytes())
    command = [
        "iverilog",
        "-g2012",
        "-s",
        "tb_starlink_pss_local_admission",
        f"-Ptb_starlink_pss_local_admission.CHECK_IDENTITY={check}",
        f"-Ptb_starlink_pss_local_admission.BALANCED={balanced}",
        "-o",
        "simulation",
        "original.v",
        "candidate.v",
        "bench.sv",
    ]
    compiled = subprocess.run(
        command,
        check=False,
        cwd=directory,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    (directory / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(
        ["vvp", "simulation"],
        check=False,
        cwd=directory,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    (directory / "simulate.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("kind", ["guard", "top"])
def test_whole_source_inverse_and_literal_prior_callers(kind):
    old, new, edits = (
        (RECIPE.OLD_GUARD, RECIPE.GUARD, RECIPE.guard_edits())
        if kind == "guard"
        else (RECIPE.OLD_TOP, RECIPE.TOP, RECIPE.top_edits())
    )
    source = (ACQ / f"{new}.v").read_text()
    assert RECIPE.apply(source, edits, inverse=True) == original(old)
    assert (ACQ / f"{old}.v").read_text() == original(old)
    assert source == RECIPE.apply(original(old), edits)


@pytest.mark.parametrize("kind,count", [("guard", 5), ("top", 3)])
def test_every_strict_anchor_rejects_missing_and_duplicate(kind, count):
    old, edits = (
        (RECIPE.OLD_GUARD, RECIPE.guard_edits())
        if kind == "guard"
        else (RECIPE.OLD_TOP, RECIPE.top_edits())
    )
    source = original(old)
    assert len(edits) == count
    for before, _ in edits:
        for mutation in (source.replace(before, "", 1), source + before):
            with pytest.raises(ValueError, match="nonunique"):
                RECIPE.apply(mutation, edits)


@pytest.mark.parametrize("check,balanced", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_literal_outputs_private_state_cycles_reachable_and_arbitrary_snapshots(
    tmp_path, check, balanced
):
    result = simulate(tmp_path / "run", check=check, balanced=balanced)
    log = result.stdout + result.stderr
    assert result.returncode == 0, log
    assert not re.search(r"FAIL|FATAL|ERROR|MISMATCH", log, re.IGNORECASE)
    rows = re.findall(r"^LOCAL_ADMISSION_OFFLINE_PASS (.*)$", log, re.MULTILINE)
    assert len(rows) == 1
    counts = {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", rows[0])}
    assert {
        key: counts[key]
        for key in (
            "check_identity",
            "balanced",
            "healthy_blocks",
            "metadata_bits",
            "position_bits",
            "duplicates",
            "data_xz",
            "arbitrary_snapshots",
        )
    } == {
        "check_identity": check,
        "balanced": balanced,
        "healthy_blocks": 3,
        "metadata_bits": 420,
        "position_bits": 54,
        "duplicates": 5,
        "data_xz": 4,
        "arbitrary_snapshots": 16384,
    }
    assert (
        counts["reachable_checks"] > 0
        and counts["arbitrary_checks"] > 0
        and counts["cycles"] > 16384
    )
    assert counts["descriptor_capture_bits"] == 70


@pytest.mark.parametrize(
    "mutation",
    [
        "omit_job_start",
        "omit_job_started",
        "omit_protocol_fault",
        "capture_zero",
        "capture_direction",
        "capture_start",
        "capture_exponent",
        "wrong_enable",
        "drop_identity_check",
        "drop_current_duplicate_veto",
        "drop_sticky_fault",
    ],
)
def test_independent_original_shadow_rejects_semantic_mutations(tmp_path, mutation):
    source = (ACQ / f"{RECIPE.GUARD}.v").read_text()
    block = RECIPE.LOCAL
    if mutation == "omit_job_start":
        changed = block.replace(" && job_start", "")
    elif mutation == "omit_job_started":
        changed = block.replace(" && !job_started", "")
    elif mutation == "omit_protocol_fault":
        changed = block.replace(" && !protocol_fault", "")
    elif mutation == "wrong_enable":
        changed = block.replace("!job_started", "!input_complete")
    elif mutation.startswith("capture_"):
        value = {
            "capture_zero": "70'b0",
            "capture_direction": "job_descriptor ^ (70'b1 << 69)",
            "capture_start": "job_descriptor ^ (70'b1 << 5)",
            "capture_exponent": "job_descriptor ^ 70'b1",
        }[mutation]
        changed = block.replace(
            "descriptor <= job_descriptor;", "descriptor <= " + value + ";"
        )
    else:
        changed = block
    assert source.count(block) == 1
    source = source.replace(block, changed, 1)
    if mutation == "drop_identity_check":
        source = source.replace(
            "(!CHECK_INPUT_BLOCK_IDENTITY || identity_matches);", "1'b1;", 1
        )
    elif mutation == "drop_current_duplicate_veto":
        source = source.replace(
            "core_input_tvalid && core_input_tready && !fault_now;",
            "core_input_tvalid && core_input_tready;",
            1,
        )
    elif mutation == "drop_sticky_fault":
        source = source.replace(
            "fault_reasons <= fault_reasons | errors_now;",
            "fault_reasons <= fault_reasons;",
            1,
        )
    result = simulate(tmp_path / "mutant", source=source)
    log = result.stdout + result.stderr
    assert result.returncode != 0 and "LOCAL_ADMISSION_MISMATCH" in log, log
    assert "LOCAL_ADMISSION_OFFLINE_PASS" not in log
    if mutation == "omit_protocol_fault":
        assert (
            "phase=1" in log
        )  # Explicit arbitrary-state witness, not claimed reachable.


def parameter_probe(tmp_path, top, value=None, positional=False, omit_forward=False):
    name = RECIPE.TOP if top else RECIPE.GUARD
    source = (ACQ / f"{name}.v").read_text()
    if omit_forward:
        source = source.replace(
            ".LOCAL_FIRST_ADMISSION(LOCAL_FIRST_ADMISSION)", ".LOCAL_FIRST_ADMISSION(0)"
        )
    (tmp_path / "probe_source.v").write_text(source)
    kernel = (
        ACQ
        / "build/bank-arithmetic-actual-candidate175-monitor-prepared-v3/frozen_sources/upper_edge_pss_kernel_q17.mem"
    )
    if top:
        args = (
            f'("{kernel}",0,0,0)' if positional else f'(.KERNEL_ROM_FILE("{kernel}"))'
        )
    else:
        args = "(1,1)" if positional else "()"
    if value is not None:
        if top:
            args = f'(.KERNEL_ROM_FILE("{kernel}"),.LOCAL_FIRST_ADMISSION({value}))'
        else:
            args = f"(.LOCAL_FIRST_ADMISSION({value}))"
    observed = (
        "dut.input_guard.LOCAL_FIRST_ADMISSION" if top else "dut.LOCAL_FIRST_ADMISSION"
    )
    expected = "0" if value is None else value
    # Ignore the absent vendor module ONLY for this syntax/parameter receipt;
    # there is no input traffic, no FFT transactor and no numerical claim.
    bench = f"""module parameter_probe;
      {name} #{args} dut ();
      initial begin #1;
        if ({observed} !== {expected}) $fatal(1,"wrong actual local-admission binding");
        $display("LOCAL_ADMISSION_SYNTAX_PARAMETER_ONLY value=%b",{observed}); $finish(0);
      end
    endmodule
    """
    (tmp_path / "probe.sv").write_text(bench)
    sources = ["probe_source.v", "probe.sv"]
    if top:
        sources += [
            str(ACQ / f"{part}.v")
            for part in (
                RECIPE.GUARD,
                "starlink_pss_realtime_result_guard",
                "starlink_pss_block_mailbox",
                "starlink_pss_forward_kernel_join",
                "starlink_pss_kernel_rom",
                "starlink_pss_spectrum_product_operand_register",
                "starlink_pss_spectrum_product_bank_arithmetic",
            )
        ]
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-i", "-s", "parameter_probe", "-o", "probe", *sources],
        check=False,
        cwd=tmp_path,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(
        ["vvp", "probe"],
        check=False,
        cwd=tmp_path,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("positional", [False, True])
def test_default_zero_and_unchanged_positional_parameter_prefix(
    tmp_path, top, positional
):
    result = parameter_probe(tmp_path, top, positional=positional)
    assert (
        result.returncode == 0
        and result.stdout.count(
            "LOCAL_ADMISSION_SYNTAX_PARAMETER_ONLY value=00000000000000000000000000000000"
        )
        == 1
    )


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("value", ["-1", "2", "1'bx", "1'bz"])
def test_invalid_and_unknown_new_parameter_rejected(tmp_path, top, value):
    result = parameter_probe(tmp_path, top, value=value)
    assert (
        result.returncode != 0
        and "LOCAL_FIRST_ADMISSION must be zero or one" in result.stdout
    )
    assert "LOCAL_ADMISSION_SYNTAX_PARAMETER_ONLY" not in result.stdout


def test_actual_top_forwarding_and_omission_mutant(tmp_path):
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    result = parameter_probe(healthy, True, value="1")
    assert result.returncode == 0
    mutant = tmp_path / "mutant"
    mutant.mkdir()
    result = parameter_probe(mutant, True, value="1", omit_forward=True)
    assert (
        result.returncode != 0
        and "wrong actual local-admission binding" in result.stdout
    )


def test_no_new_storage_or_changed_remaining_state_and_combinational_contract():
    source = (ACQ / f"{RECIPE.GUARD}.v").read_text()
    legacy = original(RECIPE.OLD_GUARD)
    assert re.findall(r"^  reg .*", source, re.MULTILINE) == re.findall(
        r"^  reg .*", legacy, re.MULTILINE
    )
    assert (
        source[source.index("  reg job_started") : source.index("  always @(posedge")]
        == legacy[
            legacy.index("  reg job_started") : legacy.index("  always @(posedge")
        ]
    )
    assert (
        source[source.index("        if (certified_input_beat)") :]
        == legacy[legacy.index("        if (certified_input_beat)") :]
    )
    assert "input_guard" in (ACQ / f"{RECIPE.TOP}.v").read_text()
