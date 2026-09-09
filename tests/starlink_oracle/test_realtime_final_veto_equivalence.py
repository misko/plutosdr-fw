"""Conditional final-veto RTL algebra only; not service/timing qualification."""
from pathlib import Path
import re
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_final_veto_equivalence"


def _run(tmp_path, *, watchdog=5, omit=-1):
    executable = tmp_path / f"final_veto_{watchdog}_{omit}.vvp"
    compiled = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.WATCHDOG_CYCLES={watchdog}", f"-P{TOP}.OMIT_VETO={omit}",
        "-o", str(executable), str(ACQ / "starlink_pss_realtime_result_guard.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return subprocess.run(
        ["vvp", str(executable)], capture_output=True, text=True, timeout=60
    )


@pytest.mark.parametrize("watchdog", [2, 5, 17])
def test_final_veto_equivalence_all_events_exponents_gates_and_actual_edges(tmp_path, watchdog):
    result = _run(tmp_path, watchdog=watchdog)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert not re.search(r"(?im)^\s*(fatal|error)(:|\s)", transcript)
    assert result.stdout.splitlines().count(
        f"FINAL_VETO_EQ_PASS watchdog={watchdog} rows=262656 edges=512 "
        "mutation_witnesses=9 boundaries=10 reset=1"
    ) == 1


@pytest.mark.parametrize("omit", range(9))
def test_omitting_each_final_veto_is_detected_on_its_single_event_witness(tmp_path, omit):
    result = _run(tmp_path, omit=omit)
    transcript = result.stdout + result.stderr
    assert result.returncode != 0, transcript
    assert "FINAL_VETO_EQ_PASS" not in transcript
    assert (
        f"FINAL_VETO_EQ_MISMATCH omit={omit} events={1 << omit:03x} actual=1 proposed=0"
    ) in transcript
