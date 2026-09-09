"""Real Tcl terminal-evidence gate, including xsim's exit-zero-on-fatal hazard."""
from pathlib import Path
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
VERIFIER = ACQ / "verify_realtime_probe_result.tcl"
PASS = "PROBE_PASS exact_words=1024 UNQUALIFIED"
GOOD = f"JOB id=0\nJOB id=1\n{PASS}\n"


def verify(path, *, rows="2", prefix="JOB", markers=None):
    # System tclsh is newer than Vivado; exercise the verifier without try.
    script = "if {[llength [info commands try]]} {rename try {}}\n"
    script += f"source {{{VERIFIER}}}\n"
    script += "if {[catch {require_realtime_probe_pass [lindex $argv 0] "
    script += "[lrange $argv 3 end] [lindex $argv 1] [lindex $argv 2]} message]} "
    script += "{puts stderr $message; exit 2}\nputs VERIFIED\n"
    return subprocess.run(["tclsh", "/dev/stdin", str(path), prefix, rows,
                           *(markers if markers is not None else [PASS])],
                          input=script, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("text", [GOOD, GOOD.replace("\n", "\r\n")])
def test_exact_terminal_pass_and_inventory(tmp_path, text):
    log = tmp_path / "simulate.log"
    log.write_text(text)
    result = verify(log)
    assert result.returncode == 0 and "VERIFIED" in result.stdout


@pytest.mark.parametrize("text,reason", [
    ("", "terminal bench pass"),
    ("JOB id=0\nJOB id=1\nrun complete\n", "terminal bench pass"),
    (GOOD.replace("1024", "512"), "terminal bench pass"),
    (GOOD + PASS + "\n", "terminal bench pass"),
    (GOOD.replace("JOB id=1\n", ""), "inventory"),
    (GOOD + "JOB id=2\n", "inventory"),
    (GOOD + "Fatal: simulation stopped\n", "fatal/error"),
    ("  ERROR: assertion failed\n" + GOOD, "fatal/error"),
    (GOOD + "error test did not finish\n", "fatal/error"),
])
def test_bad_or_incomplete_terminal_evidence_is_failure(tmp_path, text, reason):
    log = tmp_path / "simulate.log"
    log.write_text(text)
    result = verify(log)
    assert result.returncode == 2 and reason in result.stderr


def test_missing_log_and_independent_required_markers(tmp_path):
    log = tmp_path / "simulate.log"
    assert "missing realtime simulation log" in verify(log).stderr
    log.write_text(GOOD)
    assert verify(log, markers=[PASS, "SECOND_PASS"]).returncode == 2
    log.write_text(GOOD + "SECOND_PASS\n")
    assert verify(log, markers=[PASS, "SECOND_PASS"]).returncode == 0


@pytest.mark.parametrize("rows,prefix,markers", [
    ("0", "JOB", [PASS]), ("4097", "JOB", [PASS]), ("2.0", "JOB", [PASS]),
    ("2", "JOB.*", [PASS]), ("2", "JOB", []), ("2", "JOB", [PASS] * 5),
])
def test_invalid_contract_fails_closed(tmp_path, rows, prefix, markers):
    log = tmp_path / "simulate.log"
    log.write_text(GOOD)
    result = verify(log, rows=rows, prefix=prefix, markers=markers)
    assert result.returncode == 2 and "invalid realtime bench verification contract" in result.stderr


@pytest.mark.parametrize("runner", ["simulate_realtime_xfft_protocol_probe.tcl",
                                    "simulate_realtime_guarded_mailbox_probe.tcl"])
def test_both_runners_snapshot_verifier_and_check_after_simulator_closes(runner):
    source = (ACQ / runner).read_text()
    assert "file copy $verifier_path $source_dir" in source
    assert source.index("close_sim") < source.index("require_realtime_probe_pass")
    assert source.index("require_realtime_probe_pass") < source.index("close_project")
    assert "SIMULATION_VERIFIED" in source
