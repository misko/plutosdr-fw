"""Same-workload public AXI/core traces for old and integrated health control.

This is RTL evidence under the tested producer contract, not formal proof,
synthesized timing, physical qualification, or live stop/drain evidence.
STARLINK_PSS_TEST_HDL selects an isolated candidate without editing a live
implementation build's sources. Default is this firmware's HDL submodule.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl")))
CONTROL_PATH = "library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"
WRAPPER_PATH = "library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v"
BASE = "653a3205bc7bd158a7267a9288beba63aebe12cf"


def frozen(path):
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{path}"],
                          check=True, capture_output=True, text=True, timeout=10).stdout


def trace(tmp_path, controller, summary):
    tmp_path.mkdir()
    source = tmp_path / "controller.v"
    source.write_text(controller)
    executable = tmp_path / "controller.vvp"
    sources = [
        "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_map_stop.sv",
        "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        "starlink_pss_acquisition/starlink_pss_phase_map.v",
        "starlink_pss_acquisition/starlink_pss_phase_map_bank.v",
        "starlink_pss_acquisition/starlink_pss_acquisition_health.v",
    ]
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-DPSMA_STOP_PUBLIC_TRACE",
        "-s", "tb_axi_starlink_pss_map_stop",
        f"-Ptb_axi_starlink_pss_map_stop.HEALTH_COUNTERS_FROM_FLAGS={summary}",
        "-o", str(executable), str(source), *[str(HDL / "library" / p) for p in sources],
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "simulation.log").write_text(result.stdout + result.stderr)
    return result, tmp_path / "psma-public-trace.txt"


@pytest.mark.parametrize("summary", [0, 1])
def test_old_and_candidate_public_stop_traces_are_cycle_identical(tmp_path, summary):
    baseline = frozen(CONTROL_PATH)
    # Test adapter only: the old controller accepts an unused bench parameter.
    # Its legacy counter/flag expression and all executable behavior stay intact.
    marker = "module axi_starlink_pss_phase_map_sync #("
    assert baseline.count(marker) == 1
    baseline = baseline.replace(marker, marker + "\n  parameter integer HEALTH_COUNTERS_FROM_FLAGS = 0,", 1)
    old, old_trace = trace(tmp_path / "old", baseline, summary)
    new, new_trace = trace(tmp_path / "candidate", (HDL / CONTROL_PATH).read_text(), summary)
    for result in [old, new]:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("PSMA_STOP_PASS") == 1
        assert f"PSMA_STOP_HEALTH_PASS summary={summary} real_causes=5" in result.stdout
    assert len(old_trace.read_text().splitlines()) > 1000
    assert new_trace.read_bytes() == old_trace.read_bytes()


@pytest.mark.parametrize("mutation", ["default_bypass", "denominator_fatal"])
def test_controller_changes_cannot_silently_weaken_or_strengthen_fault_policy(tmp_path, mutation):
    candidate = (HDL / CONTROL_PATH).read_text()
    before, after = {
        "default_bypass": ("!HEALTH_COUNTERS_FROM_FLAGS &&", "1'b0 &&"),
        "denominator_fatal": ("32'h0000_57ff", "32'h0000_5fff"),
    }[mutation]
    assert candidate.count(before) == 1
    result, _ = trace(tmp_path / "mutant", candidate.replace(before, after, 1), 0)
    assert result.returncode != 0 and "PSMA_STOP_FAIL" in result.stdout
    assert "PSMA_STOP_PASS" not in result.stdout


def test_controller_rejects_invalid_summary_selection(tmp_path):
    result, _ = trace(tmp_path / "invalid", (HDL / CONTROL_PATH).read_text(), 2)
    assert result.returncode != 0
    assert "HEALTH_COUNTERS_FROM_FLAGS must be zero or one" in result.stdout
    assert "PSMA_STOP_PASS" not in result.stdout


def test_runtime_change_is_only_the_explicit_summary_selection():
    def tokens(text):
        return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", text))

    baseline = tokens(frozen(CONTROL_PATH))
    candidate = tokens((HDL / CONTROL_PATH).read_text())
    parameter = "parameterintegerHEALTH_COUNTERS_FROM_FLAGS=0,"
    guard = (
        'if(HEALTH_COUNTERS_FROM_FLAGS!=0&&HEALTH_COUNTERS_FROM_FLAGS!=1)'
        '$fatal(1,"HEALTH_COUNTERS_FROM_FLAGSmustbezeroorone");'
    )
    for fragment in [parameter, guard]:
        assert candidate.count(fragment) == 1
        candidate = candidate.replace(fragment, "", 1)
    counter_wire = re.search(r"wirestop_detector_counter_fault=.*?;", candidate)
    assert counter_wire
    assert counter_wire.group() == (
        "wirestop_detector_counter_fault=!HEALTH_COUNTERS_FROM_FLAGS&&"
        "(|scheduler_gap_count|||scheduler_index_error_count|||scheduler_overflow_count||"
        "|detector_fault_count|||score_phase_index_discontinuity_count);"
    )
    candidate = candidate.replace(counter_wire.group(), "", 1)
    old_expression = re.search(r"wirestop_upstream_fault_now=.*?;", baseline)
    new_expression = re.search(r"wirestop_upstream_fault_now=.*?;", candidate)
    assert old_expression and new_expression
    assert new_expression.group() == (
        "wirestop_upstream_fault_now=|(snapshot_health_flags&32'h0000_57ff)||"
        "|ingress_dropped_sample_count||stop_detector_counter_fault;"
    )
    assert candidate.replace(new_expression.group(), old_expression.group(), 1) == baseline
    wrapper = tokens((HDL / WRAPPER_PATH).read_text())
    selection = ".HEALTH_COUNTERS_FROM_FLAGS(ENABLE_BOUNDARY_STOP),"
    assert wrapper.count(selection) == 1
    assert wrapper.replace(selection, "", 1) == tokens(frozen(WRAPPER_PATH))
