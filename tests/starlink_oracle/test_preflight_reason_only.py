"""Reason-only preflight input: exact structural delta and adversarial traces."""
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.completed_input_contract import (
    restore_preflight_reason_only_guard,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_preflight_reason"


def test_preflight_input_only_reaches_reason_register():
    name = "starlink_pss_realtime_result_guard.v"
    baseline = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"ba000e4805e5d61f50f136cba59cc1e9646f0aa8:library/starlink_pss_acquisition/{name}",
    ], text=True, capture_output=True, check=True, timeout=10).stdout
    baseline = re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", baseline))
    assert restore_preflight_reason_only_guard((ACQ / name).read_text()) == baseline


@pytest.mark.parametrize("mutation", [0, 1])
def test_preflight_reason_edge_and_omission_mutation(tmp_path, mutation):
    executable = tmp_path / "preflight.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, f"-P{TOP}.MUTATE_REASON={mutation}",
        "-o", str(executable), str(ACQ / "starlink_pss_realtime_result_guard.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], text=True, capture_output=True, check=False, timeout=30)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], text=True, capture_output=True, check=False, timeout=30)
    transcript = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(transcript)
    if mutation:
        assert result.returncode != 0 and "PREFLIGHT_REASON_MISMATCH phase=0 first=0 next=0" in transcript
        assert "PREFLIGHT_REASON_ONLY_PASS" not in transcript
    else:
        assert result.returncode == 0, transcript
        assert "PREFLIGHT_REASON_ONLY_PASS rows=108 phases=3 event_kinds=6 exact_reasons=1" in transcript
