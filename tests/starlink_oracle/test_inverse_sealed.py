"""Offline inverse-only composition; no vendor FFT or physical qualification."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FW = HERE.parents[1]
ACQ = FW / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "inverse_sealed_recipe", HERE / "inverse_sealed.py"
)
RECIPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECIPE)
TOP = "starlink_pss_fft_bank_owned_inverse_sealed_probe"
BENCH = "tb_starlink_inverse_sealed_ownership"
NAMES = [
    TOP,
    "starlink_pss_epoch_sealed_bank_cdc",
    "starlink_pss_inverse_sealed_issuer",
    "starlink_pss_spectrum_product_bank_arithmetic",
    "starlink_pss_spectrum_product_operand_register",
    "starlink_pss_realtime_input_guard_local_admission",
    "starlink_pss_realtime_result_guard",
    "starlink_pss_block_mailbox",
    "starlink_pss_forward_kernel_join",
    "starlink_pss_kernel_rom",
]
SOURCES = [ACQ / (name + ".v") for name in NAMES] + [
    ACQ / "tb" / (name + ".sv")
    for name in [
        BENCH,
        "starlink_pss_offline_xfft_interface",
        "starlink_pss_forward_retirement_shadow",
    ]
]
SOURCES += [ACQ / "tb/starlink_pss_realtime_result_guard_ce6a885e_golden.v"]
KERNEL = (
    ACQ
    / "evidence/forward-retirement-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem"
)


def env():
    return {
        key: value
        for key, value in os.environ.items()
        if key not in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")
    }


def test_literal_old_source_restoration():
    for old, new, derive, restore in [
        (
            "starlink_pss_epoch_sealed_bank.v",
            "starlink_pss_epoch_sealed_bank_cdc.v",
            RECIPE.derive_cdc,
            RECIPE.restore_cdc,
        ),
        (
            "starlink_pss_fft_bank_owned_local_admission_probe.v",
            TOP + ".v",
            RECIPE.derive_top,
            RECIPE.restore_top,
        ),
        (
            "tb/tb_starlink_bank_arithmetic_ownership.sv",
            "tb/" + BENCH + ".sv",
            RECIPE.derive_bench,
            RECIPE.restore_bench,
        ),
    ]:
        before, after = (ACQ / old).read_text(), (ACQ / new).read_text()
        assert derive(before) == after and restore(after) == before


def run_top(path, enabled, case, scheduling=1):
    path.mkdir()
    paths = SOURCES + [KERNEL, HERE / "inverse_sealed.py", Path(__file__)]
    for source in paths:
        shutil.copyfile(source, path / source.name)
    hashes = {
        source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in paths
    }
    (path / "sources.json").write_text(json.dumps(hashes, indent=2, sort_keys=True))
    commands = [
        [
            "iverilog",
            "-g2012",
            "-s",
            BENCH,
            f"-P{BENCH}.E={enabled}",
            f"-P{BENCH}.CASE={case}",
            f"-P{BENCH}.S={scheduling}",
            "-o",
            "top.simv",
            *[source.name for source in SOURCES],
        ],
        ["vvp", "top.simv"],
    ]
    receipts = []
    for index, command in enumerate(commands):
        result = subprocess.run(
            command,
            cwd=path,
            env=env(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        (path / f"phase{index}.log").write_text(result.stdout + result.stderr)
        receipts.append({"command": command, "exit": result.returncode})
        (path / "commands.json").write_text(json.dumps(receipts, indent=2))
        assert hashes == {
            name: hashlib.sha256((path / name).read_bytes()).hexdigest()
            for name in hashes
        }
        assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    assert not re.search(r"\b(?:FATAL|ERROR|FAIL)\b", result.stdout, re.IGNORECASE)
    assert result.stdout.count("BANK_ARITHMETIC_OWNERSHIP_PASS") == 1
    assert f"outputs={1024 if case == 0 else 512}" in result.stdout
    assert "synthetic_interface_not_fft=1 no_capacity_claim=1" in result.stdout


@pytest.mark.parametrize("enabled", [0, 1])
@pytest.mark.parametrize("scheduling", [0, 1])
def test_original_two_block_ownership_with_explicit_default_and_enabled(
    tmp_path, enabled, scheduling
):
    run_top(tmp_path / "run", enabled, 0, scheduling)


@pytest.mark.parametrize("case", range(1, 12))
def test_all_original_current_late_fault_and_reset_checks_preserved(tmp_path, case):
    run_top(tmp_path / "run", 1, case)


def run_compiled(path, bench, parameters, sources, mutant=None):
    path.mkdir()
    paths = sources + [HERE / "inverse_sealed.py", Path(__file__)]
    for source in paths:
        shutil.copyfile(source, path / source.name)
    if mutant:
        filename, old, new = mutant
        changed = path / filename
        original = changed.read_text()
        assert original.count(old) == 1
        changed.write_text(original.replace(old, new))
    hashes = {
        source.name: hashlib.sha256((path / source.name).read_bytes()).hexdigest()
        for source in paths
    }
    (path / "sources.json").write_text(json.dumps(hashes, indent=2, sort_keys=True))
    commands = [
        [
            "iverilog",
            "-g2012",
            "-s",
            bench,
            *[f"-P{bench}.{key}={value}" for key, value in parameters.items()],
            "-o",
            "guard.simv",
            *[source.name for source in sources if source.suffix in (".v", ".sv")],
        ],
        ["vvp", "guard.simv"],
    ]
    receipts = []
    try:
        for index, command in enumerate(commands):
            result = subprocess.run(
                command,
                cwd=path,
                env=env(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            (path / f"phase{index}.log").write_text(result.stdout + result.stderr)
            receipts.append({"command": command, "exit": result.returncode})
            (path / "commands.json").write_text(json.dumps(receipts, indent=2))
            if index == 0:
                assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    finally:
        assert hashes == {
            name: hashlib.sha256((path / name).read_bytes()).hexdigest()
            for name in hashes
        }
    return result


def run_guard(path, case, phase=0, bit=0, side=0, mutant=None):
    bench = "tb_starlink_inverse_sealed_guard"
    sources = [ACQ / "tb" / (bench + ".sv")] + [
        ACQ / (name + ".v")
        for name in [
            "starlink_pss_realtime_result_guard",
            "starlink_pss_block_mailbox",
            "starlink_pss_epoch_sealed_bank_cdc",
            "starlink_pss_inverse_sealed_issuer",
        ]
    ]
    result = run_compiled(
        path,
        bench,
        {"CASE": case, "PHASE_PS": phase, "BIT": bit, "SIDE": side},
        sources,
        mutant,
    )
    if mutant:
        return result
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr
    assert not re.search(r"\b(?:FATAL|ERROR|FAIL)\b", result.stdout, re.IGNORECASE)
    marker = (
        f"INVERSE_GUARD_OFFLINE_PASS case={case} phase_ps={phase} synthetic_not_fft=1"
    )
    assert result.stdout.splitlines()[-1:] == [marker]
    return result.stdout


@pytest.mark.parametrize("case", range(7))
def test_nonzero_real_guard_and_inverse_lifecycle(tmp_path, case):
    run_guard(tmp_path / "run", case)


@pytest.mark.parametrize("phase", [0, 1, 714, 1428, 2500, 4285, 5000, 5713, 7500, 9999])
@pytest.mark.parametrize("case", [0, 1, 4, 5, 6])
def test_ack_reuse_and_fault_visibility_clock_phase_sweep(tmp_path, case, phase):
    text = run_guard(tmp_path / "run", case, phase)
    if case < 2:
        timings = re.findall(
            r"publication_delta=(\d+) ack_to_release=(\d+) reuse_delta=(\d+)", text
        )
        assert len(timings) == 2
        assert all(
            int(pub) == 2 and int(ack) == 1 and int(reuse) <= 8
            for pub, ack, reuse in timings
        )


def run_purge(path, side, old_fault, fill_before_fast, mutant=None):
    bench = "tb_starlink_inverse_source_purge"
    sources = [source for source in SOURCES if source.name != BENCH + ".sv"]
    sources += [ACQ / "tb" / (bench + ".sv")]
    result = run_compiled(
        path,
        bench,
        {"SIDE": side, "OLD_FAULT": old_fault, "FILL_BEFORE_FAST": fill_before_fast},
        sources + [KERNEL],
        mutant,
    )
    if mutant:
        return result
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr
    assert result.stdout.splitlines()[-1:] == [
        f"INVERSE_SOURCE_PURGE_PASS side={side} old_fault={old_fault} fill_before_fast={fill_before_fast} source_words=512 output_words=512 synthetic_not_fft=1"
    ]
    assert (
        "FRESH_SOURCE_FAULT_QUARANTINE source=1 synchronized=1 fast=1" in result.stdout
    )
    assert len(re.findall(r"^FRESH_SOURCE pos=", result.stdout, re.MULTILINE)) == 512
    assert len(re.findall(r"^FRESH_OUTPUT pos=", result.stdout, re.MULTILINE)) == 512
    return result.stdout


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("old_fault", [0, 1])
@pytest.mark.parametrize("fill_before_fast", [0, 1])
def test_paused_remote_source_purge_and_separate_sticky_fault(
    tmp_path, side, old_fault, fill_before_fast
):
    run_purge(tmp_path / "run", side, old_fault, fill_before_fast)


@pytest.mark.parametrize("case", [7, 8, 9])
@pytest.mark.parametrize("bit", [0, 4, 5, 36, 69, 70, 71, 72, 73, 74])
def test_single_first_interior_final_full_metadata_fields(tmp_path, case, bit):
    run_guard(tmp_path / "run", case, bit=bit)


@pytest.mark.parametrize("stage", range(7))
@pytest.mark.parametrize("side", [0, 1])
def test_common_reset_at_each_owned_join_and_rearm(tmp_path, stage, side):
    run_guard(tmp_path / "run", 10, bit=stage, side=side)


def test_first_final_stalled_slow_valid_and_metadata(tmp_path):
    run_guard(tmp_path / "run", 11)


@pytest.mark.parametrize("old_fault", [0, 1])
@pytest.mark.parametrize("side", [0, 1])
def test_source_reset_and_old_fault_barrier_mutants(tmp_path, old_fault, side):
    mutant = (
        TOP + ".v",
        "if (!source_reader_running) source_fault_fast <= 0;"
        if old_fault
        else ".output_resetn(source_reader_running)",
        "if (!fast_running) source_fault_fast <= 0;"
        if old_fault
        else ".output_resetn(fast_running)",
    )
    result = run_purge(tmp_path / "run", side, old_fault, 0, mutant)
    assert result.returncode != 0
    assert "STALE_SOURCE_OR_FAULT_REOPENED_BEFORE_REMOTE_PURGE" in result.stdout


@pytest.mark.parametrize(
    "case,filename,old,new,reason",
    [
        (
            2,
            "starlink_pss_inverse_sealed_issuer.v",
            "guard_commit_valid !== 1'b1;",
            "1'b0;",
            "DEADLINE_PUBLICATION_NOT_VETOED",
        ),
        (
            0,
            "starlink_pss_epoch_sealed_bank_cdc.v",
            "acknowledge_sync[1] == request_toggle;",
            "1'b1;",
            "ACK_BEFORE_FINAL_SLOW_READ",
        ),
        (
            1,
            "starlink_pss_inverse_sealed_issuer.v",
            ".input_offer_new(!final_taken)",
            ".input_offer_new(1'b1)",
            "HELD_FINAL_REWRITE_OR_EARLY_CERTIFICATE",
        ),
        (
            0,
            "starlink_pss_inverse_sealed_issuer.v",
            "lease_reference <= bank_lease;",
            "lease_reference <= 0;",
            "INVERSE_GUARD_WATCHDOG",
        ),
        (
            0,
            "starlink_pss_inverse_sealed_issuer.v",
            "assign reservation = epoch_active && (reusable || producer_reference ||\n    certificate_reference || published_reference || reader_reference);",
            "assign reservation = reusable;",
            "ADMISSION_LOST_RESERVATION",
        ),
        (
            11,
            "starlink_pss_epoch_sealed_bank_cdc.v",
            "end else if (output_accept) read_valid <= 0;",
            "end else read_valid <= 0;",
            "SLOW_STALL_VALID_OR_TUPLE_WITHDRAWAL",
        ),
    ],
)
def test_targeted_guard_lifecycle_mutants(tmp_path, case, filename, old, new, reason):
    result = run_guard(tmp_path / "run", case, mutant=(filename, old, new))
    assert result.returncode != 0
    assert reason in result.stdout, result.stdout[-1000:]
