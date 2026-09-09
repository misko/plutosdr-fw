"""Reachable completed-input premise for a future publication-path experiment.

The production checker is unchanged. This is not final-publication equivalence,
whole-service reset/ACK qualification, synthesized timing, or radio evidence.
"""

import os
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_input_retirement"


def probe(tmp_path, identity, mutation):
    executable = tmp_path / "retirement.vvp"
    compilation = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.CHECK_IDENTITY={identity}", f"-P{TOP}.OMIT_DUPLICATE_MUTATION={int(mutation)}",
        "-o", str(executable), str(ACQ / "starlink_pss_realtime_input_guard.v"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert compilation.returncode == 0, compilation.stdout + compilation.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                            timeout=30, check=False)
    (tmp_path / "retirement.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("identity", [0, 1])
def test_completed_input_exact_reduced_fault_and_zero_new_certificates(tmp_path, identity):
    result = probe(tmp_path, identity, False)
    text = result.stdout + result.stderr
    assert result.returncode == 0 and "FATAL" not in text, text
    marker = (f"INPUT_RETIREMENT_PASS identity={identity} rows=32768 duplicate_rows=16384 "
              f"premature_witnesses={5 if identity else 4} reset_recovery=1 "
              "no_internal_deposits=1 no_publication_or_timing_claim=1")
    assert text.splitlines().count(marker) == 1


@pytest.mark.parametrize("identity", [0, 1])
def test_reachable_duplicate_after_completion_rejects_a_missing_veto(tmp_path, identity):
    result = probe(tmp_path, identity, True)
    assert result.returncode != 0 and "INPUT_RETIREMENT_PREDICATE_MISMATCH" in result.stdout
    assert "INPUT_RETIREMENT_PASS" not in result.stdout
