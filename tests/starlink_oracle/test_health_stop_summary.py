"""Test a proposed stop-control simplification under its real producer contract.

Not formal proof or a receiver implementation. The generic controller must keep
checking independently supplied counters unless its stronger producer contract
is explicitly established. No delay, mask or ingress-loss omission is allowed.
"""

import re
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
HEALTH = HDL / "library/starlink_pss_acquisition/starlink_pss_acquisition_health.v"
BENCH = HEALTH.parent / "tb/tb_starlink_pss_health_stop_summary.sv"
BASE = "653a3205bc7bd158a7267a9288beba63aebe12cf"


def run_summary(tmp_path, width, shared, mutation=None):
    old_controller = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"{BASE}:library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v",
    ], check=True, capture_output=True, text=True, timeout=10).stdout
    expression = re.search(r"wire stop_upstream_fault_now = (.*?);", old_controller, re.DOTALL)
    assert expression
    proposed = "|(snapshot_health_flags & 32'h0000_57ff) || |ingress_dropped_sample_count"
    producer = HEALTH.read_text()
    if mutation == "phase_flag":
        old = "detector_health_flags[HEALTH_PHASE_INDEX_DISCONTINUITY] <= 1'b1;"
        assert producer.count(old) == 1
        producer = producer.replace(old, old.replace("1'b1", "1'b0"))
    elif mutation == "epoch":
        old = "detector_health_flags <= 32'd0;"
        assert producer.count(old) == 1
        producer = producer.replace(old, "detector_health_flags <= 32'h400;")
    elif mutation == "denominator":
        proposed = proposed.replace("57ff", "5fff")
    elif mutation == "ingress":
        proposed = proposed.replace(" || |ingress_dropped_sample_count", "")
    (tmp_path / "health.v").write_text(producer)
    (tmp_path / "health_stop_expressions.vh").write_text(
        f"wire legacy_stop = {expression.group(1)};\nwire proposed_stop = {proposed};\n")
    executable = tmp_path / "summary.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pss_health_stop_summary",
        f"-Ptb_starlink_pss_health_stop_summary.COUNTER_WIDTH={width}",
        f"-Ptb_starlink_pss_health_stop_summary.USE_SHARED_XFFT={shared}",
        "-I", str(tmp_path), "-o", str(executable), str(tmp_path / "health.v"), str(BENCH),
    ], check=True, capture_output=True, text=True, timeout=30)
    return subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                          check=False, timeout=30)


@pytest.mark.parametrize("width", [1, 3, 32])
@pytest.mark.parametrize("shared", [0, 1])
def test_real_producer_sticky_summary_matches_legacy_stop_decision(tmp_path, width, shared):
    result = run_summary(tmp_path, width, shared)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("HEALTH_SUMMARY_PASS") == 1
    assert f"width={width} shared={shared} input_combinations=8192 checks=32814" in result.stdout
    assert "receiver_implemented=0" in result.stdout


@pytest.mark.parametrize("mutation", ["phase_flag", "epoch", "denominator", "ingress"])
def test_invalid_summary_assumptions_have_reachable_witnesses(tmp_path, mutation):
    result = run_summary(tmp_path, 3, 1, mutation)
    assert result.returncode != 0, result.stdout
    assert "HEALTH_SUMMARY_" in result.stdout
    assert "HEALTH_SUMMARY_PASS" not in result.stdout
