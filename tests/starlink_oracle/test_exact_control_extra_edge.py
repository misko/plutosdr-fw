"""Offline added-stimulus scheduling only; original runtime/checkers stay exact."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "extra_edge", ACQ / "prepare_exact_control_extra_edge.py"
)
EDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EDGE)
ORIGINAL = ACQ / "evidence/status-qualified-observer-offline-v1/prepared"
TOP = "tb_starlink_pss_fft_bank_owned_slice"


def test_only_added_phase_boundary_check_inverse_and_full_pair_compile(tmp_path):
    prepared = tmp_path / "prepared"
    EDGE.prepare(ORIGINAL, prepared)
    source = prepared / "frozen_sources"
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=prepared, check=True
    )
    for name in json.loads((ORIGINAL / "preparation.json").read_text())[
        "source_sha256"
    ]:
        text = (source / name).read_text()
        if name == EDGE.EXTRA:
            assert text.count(EDGE.CORRECTION) == 1
            text = text.replace(EDGE.CORRECTION, "", 1)
        assert text.encode() == (ORIGINAL / "frozen_sources" / name).read_bytes(), name
    assert (prepared / "settings.tcl").read_bytes() == (
        ORIGINAL / "settings.tcl"
    ).read_bytes()
    # The full paired candidate/reference bench compiles; it is never run
    # against this quiescent stub, which would not prove numerical behavior.
    stub = tmp_path / "never_run_stub.v"
    stub.write_text(STUB)
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            TOP,
            f"-P{TOP}.FAST_MHZ=175",
            f"-P{TOP}.EXACT_EXTRA_EPOCHS=1",
            "-o",
            str(tmp_path / "full_pair_never_run.vvp"),
            *map(str, sorted(source.glob("*.v"))),
            *map(str, sorted(source.glob("*.sv"))),
            str(stub),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "full_pair_compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(FileExistsError):
        EDGE.prepare(ORIGINAL, prepared)


def fault_body():
    text = EDGE.align((ORIGINAL / "frozen_sources" / EDGE.EXTRA).read_text())
    # Execute literal prepared wait/hold/fault/current-veto/sticky/ownership
    # body for kinds0/1 only. Reset kinds2/3 remain literal via full inverse.
    start = text.index("    wait(!dut.next_inverse")
    end = text.index("    reset_epoch(0); send_words(0, 512); await_results(1);")
    return text[start:end]


def run(tmp_path, kind, mode, provider=0, mutation=None):
    body = fault_body()
    wait = "      if (exact_extra_kind == 1 || fft_clk === 1'b1)\n        @(negedge fft_clk);\n"
    assert body.count(EDGE.CORRECTION) == 1
    assert EDGE.CORRECTION.count(wait) == 1
    if mutation == "remove_high_phase_wait":
        body = body.replace(
            EDGE.CORRECTION,
            EDGE.CORRECTION.replace(wait, ""),
            1,
        )
    elif mutation == "unconditional_next_negedge":
        # The retained v1 error: a currently low final could commit before
        # an unconditional wait for the *next* falling edge returns.
        body = body.replace(
            EDGE.CORRECTION,
            EDGE.CORRECTION.replace(wait, "      @(negedge fft_clk);\n"),
            1,
        )
    elif mutation in {"two_held", "four_held"}:
        assert body.count("repeat (3) tick();") == 1
        body = body.replace(
            "repeat (3) tick();",
            f"repeat ({2 if mutation == 'two_held' else 4}) tick();",
        )
    elif mutation in {"unknown_x", "unknown_z"}:
        body = body.replace(
            EDGE.CORRECTION,
            f"      force fft_clk = 1'b{mutation[-1]};\n" + EDGE.CORRECTION,
            1,
        )
    elif mutation == "bad_owner":
        anchor = "      if (!dut.result_guard.active"
        assert EDGE.CORRECTION.count(anchor) == 1
        body = body.replace(
            EDGE.CORRECTION,
            EDGE.CORRECTION.replace(
                anchor, "      force dut.product_bank_valid=1;\n" + anchor
            ),
            1,
        )
    bench = (ACQ / "tb/tb_starlink_pss_extra_edge.sv").read_text()
    assert bench.count("// INSERT_EXACT_EXTRA_FAULT_BODY") == 1
    bench = bench.replace("// INSERT_EXACT_EXTRA_FAULT_BODY", body, 1)
    source = tmp_path / "fixture.sv"
    source.write_text(bench)
    executable = tmp_path / "fixture.vvp"
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-s",
            TOP,
            f"-P{TOP}.KIND={kind}",
            f"-P{TOP}.MODE={mode}",
            f"-P{TOP}.PROVIDER={provider}",
            "-o",
            str(executable),
            str(source),
            str(ACQ / "starlink_pss_realtime_result_guard.v"),
            str(
                ORIGINAL
                / "frozen_sources/starlink_pss_realtime_result_guard_ce6a885e_golden.v"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(
        ["vvp", str(executable)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("provider", [0, 1, 2])
@pytest.mark.parametrize("mode", [0, 1])
@pytest.mark.parametrize("kind", [0, 1])
def test_literal_fault_body_real_guard_three_held_edges_and_precommit_lead(
    tmp_path, kind, mode, provider
):
    rc, log = run(tmp_path, kind, mode, provider)
    assert rc == 0, log
    rows = re.findall(
        r"^EXTRA_EDGE_GUARD_PASS kind=(\d+) mode=(\d+) provider=(\d+) "
        r"held_posedges=(\d+) fault_edges=(\d+) lead_fs=(\d+) "
        r"exact_reasons=01 old_checks=(\d+) qualification_edges=(\d+) "
        r"qualification_clock=([01]) synthetic_core_minimal_banks_not_fft=1$",
        log,
        re.MULTILINE,
    )
    assert len(rows) == 1, log
    values = tuple(map(int, rows[0]))
    expected_lead = 1428572 if provider == 2 and kind == 0 else 2857143
    assert values[:6] == (kind, mode, provider, 3 if kind else 0, 1, expected_lead)
    assert values[6] > 1024
    assert values[7:] == (1, int(provider == 1))


@pytest.mark.parametrize(
    "kind,provider,mutation,marker",
    [
        (0, 1, "remove_high_phase_wait", "EXACT_EXTRA_ALIGNED_CLOCK_NOT_LOW"),
        (1, 0, "remove_high_phase_wait", "EXACT_EXTRA_ALIGNED_CLOCK_NOT_LOW"),
        (0, 0, "unconditional_next_negedge", "EDGE_EARLY_FINAL_PUBLICATION"),
        (0, 2, "unconditional_next_negedge", "EDGE_EARLY_FINAL_PUBLICATION"),
        (1, 0, "two_held", "EDGE_HELD_COUNT_WRONG count=2"),
        (1, 1, "four_held", "EDGE_HELD_COUNT_WRONG count=4"),
        (0, 0, "unknown_x", "EXACT_EXTRA_UNKNOWN_CLOCK_PHASE"),
        (1, 1, "unknown_z", "EXACT_EXTRA_UNKNOWN_CLOCK_PHASE"),
        (0, 0, "bad_owner", "EXACT_EXTRA_ALIGNED_FINAL_BOUNDARY_MISSING"),
        (1, 1, "bad_owner", "EXACT_EXTRA_ALIGNED_FINAL_BOUNDARY_MISSING"),
    ],
)
def test_phase_count_late_fault_and_ownership_mutants_rejected(
    tmp_path, kind, provider, mutation, marker
):
    rc, log = run(tmp_path, kind, 1, provider, mutation)
    assert rc != 0 and marker in log, log
    assert "EXTRA_EDGE_GUARD_PASS" not in log


def test_wrong_freeze_rejected_without_actual_launch(tmp_path):
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "SHA256SUMS").write_text("wrong\n")
    with pytest.raises(ValueError, match="reviewed qualified"):
        EDGE.prepare(wrong, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
    helper = (ACQ / "prepare_exact_control_extra_edge.py").read_text()
    assert "launch_simulation" not in helper and '"vivado"' not in helper
