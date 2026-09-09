"""Public pilot snapshot comparison; physical replication is measured separately."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl")))
CONTROL = "library/axi_starlink_pilot_capture/axi_starlink_pilot_capture.v"
BASE = "84a1a3589a08f5af72323755d38b9d7ef9153846"


def baseline():
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{CONTROL}"],
                          check=True, capture_output=True, text=True, timeout=10).stdout


def simulate(directory, candidate):
    for name, source in [("baseline", baseline()), ("replicated", candidate)]:
        marker = "module axi_starlink_pilot_capture #("
        assert source.count(marker) == 1
        (directory / f"{name}.v").write_text(source.replace(
            marker, f"module pilot_snapshot_{name} #(", 1))
    for name in ["pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"]:
        shutil.copyfile(HDL / "library/starlink_pss_acquisition" / name, directory / name)
    sources = [directory / "baseline.v", directory / "replicated.v"]
    sources += [HDL / "library" / path for path in [
        "axi_starlink_pilot_capture/tb/tb_pilot_snapshot_replication.sv",
        "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
        "starlink_pss_acquisition/starlink_pilot_ddc.v",
        "starlink_pss_acquisition/starlink_pilot_halfband2.v",
        "starlink_pss_acquisition/starlink_pilot_fir3.v",
    ]]
    executable = directory / "snapshot.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "tb_pilot_snapshot_replication",
                    "-o", str(executable), *map(str, sources)],
                   check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=directory, check=False,
                            capture_output=True, text=True, timeout=30)
    (directory / "simulation.log").write_text(result.stdout + result.stderr)
    return result


def test_snapshot_changes_are_only_local_synthesis_attributes():
    def tokens(text):
        return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", text))

    old, new = tokens(baseline()), tokens((HDL / CONTROL).read_text())
    fragment = "regarm_request,stop_request,clear_request;(*max_fanout=32*)regsnapshot_request;"
    assert new.count(fragment) == 1
    remap = '(*extract_enable="no"*)reg[31:0]snapshot[0:25];'
    assert new.count(remap) == 1
    new = new.replace(remap, "reg[31:0]snapshot[0:25];")
    assert new.replace(fragment, "regarm_request,stop_request,clear_request,snapshot_request;") == old


def test_real_pilot_public_snapshot_behavior_matches_frozen_baseline(tmp_path):
    result = simulate(tmp_path, (HDL / CONTROL).read_text())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PILOT_SNAPSHOT_EQ_PASS") == 1
    assert "snapshots=12" in result.stdout
    assert "PILOT_SNAPSHOT_EQ_FAIL" not in result.stdout


@pytest.mark.parametrize("before,after", [
    ("else if (snapshot_request)", "else if (snapshot_request || arm_request)"),
    ("snapshot_generation + 1'b1", "snapshot_generation + 2'd2"),
])
def test_public_bench_rejects_changed_snapshot_semantics(tmp_path, before, after):
    candidate = (HDL / CONTROL).read_text()
    assert candidate.count(before) == 1
    result = simulate(tmp_path, candidate.replace(before, after, 1))
    assert result.returncode != 0 and "PILOT_SNAPSHOT_EQ_FAIL" in result.stdout
    assert "PILOT_SNAPSHOT_EQ_PASS" not in result.stdout
