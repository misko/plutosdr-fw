"""Old-vs-factored actual RTL behavior; no physical timing or FFT qualification."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_realtime_result_guard_equivalence"
GOLDEN_NAME = "starlink_pss_realtime_result_guard_ff4229_golden"
GOLDEN = ACQ / "tb" / f"{GOLDEN_NAME}.v"


def test_golden_is_exact_ff4229_guard_with_only_module_name_changed():
    text = GOLDEN.read_text()
    assert "ff4229bb230437fcd975413390a34c00ffcc226f" in text.splitlines()[0]
    body = text.split("// SPDX-License-Identifier: GPL-2.0\n", 1)[1]
    restored = "// SPDX-License-Identifier: GPL-2.0\n" + body.replace(
        f"module {GOLDEN_NAME} #(", "module starlink_pss_realtime_result_guard #(", 1)
    assert hashlib.sha256(restored.encode()).hexdigest() == (
        "a3637871ad72551987006b5d5c1e0de716f28a07e706c0decf036e072cd7f35c"
    )


def test_factored_guard_public_equivalence_and_exact_watchdog_boundaries(tmp_path):
    executable = tmp_path / "guard_equivalence.vvp"
    compiled = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP, "-o", str(executable),
        str(ACQ / "starlink_pss_realtime_result_guard.v"), str(GOLDEN),
        str(ACQ / "starlink_pss_block_mailbox.v"),
        str(ACQ / "tb/tb_starlink_pss_realtime_result_guard.sv"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not re.search(r"(?im)^\s*(fatal|error)(:|\s)", result.stdout + result.stderr)
    expected = (
        "GUARD_FACTORED_EQ_PASS legacy_healthy=23 legacy_rejected=37 independent_resets=12 "
        "idle_combinations=12288 watchdog_configurations=6 watchdog_epochs=12"
    )
    assert result.stdout.splitlines().count(expected) == 1
    assert "REALTIME_RESULT_GUARD_PASS healthy=23 rejected=37 independent_resets=12 " in result.stdout
    assert "GUARD_IDLE_TRUTH_PASS combinations=12288 reset_clean_and_sticky=1" in result.stdout
    for cycles in (2, 3, 5, 17, 2048, 2049):
        assert result.stdout.splitlines().count(
            f"GUARD_WATCHDOG_EQ_PASS cycles={cycles} epochs=2"
        ) == 1
