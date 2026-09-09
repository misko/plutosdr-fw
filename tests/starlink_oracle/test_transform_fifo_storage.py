"""Pinned public equivalence and mutation witnesses for LUTRAM -> BRAM."""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "ced8a17d21e5ea00a134eb075a095d5ecf435955"
BASE_SHA = "21740ca5d282ee1aea6b302692ffe3d4d96df1bfacd805d570fec4cea65f6db5"
TOP = "tb_starlink_pss_transform_fifo_storage"


def baseline():
    result = subprocess.run(
        ["git", "-C", str(HDL), "show",
         f"{BASE}:library/starlink_pss_acquisition/starlink_pss_transform_fifo.v"],
        capture_output=True, check=True, timeout=10,
    )
    assert hashlib.sha256(result.stdout).hexdigest() == BASE_SHA
    return result.stdout.decode()


def test_storage_change_does_not_change_behavioral_tokens():
    def tokens(source):
        source = re.sub(r"//[^\n]*", "", source)
        source = re.sub(r'/\*.*?\*/', "", source, flags=re.DOTALL)
        source = re.sub(r'\(\* ram_style = "(?:distributed|block)" \*\)', "", source)
        return re.sub(r"\s+", "", source)

    candidate = (ACQ / "starlink_pss_transform_fifo.v").read_text()
    assert 'ram_style = "block"' in candidate
    assert tokens(candidate) == tokens(baseline())


@pytest.mark.parametrize("depth", [2, 4, 8, 16])
@pytest.mark.parametrize("mutation", [None, "wrong_address", "no_reset_payload"])
def test_cycle_exact_public_outputs_and_reachable_mutations(tmp_path, depth, mutation):
    golden = tmp_path / "golden.v"
    golden.write_text(baseline().replace(
        "module starlink_pss_transform_fifo #(",
        "module starlink_pss_transform_fifo_golden #(", 1))
    source = (ACQ / "starlink_pss_transform_fifo.v").read_text()
    if mutation == "wrong_address":
        before, after = "payload_memory[read_pointer]", "payload_memory[write_pointer]"
    elif mutation == "no_reset_payload":
        before, after = "output_payload <= 0;", "output_payload <= 1;"
    if mutation:
        assert source.count(before) == 1
        source = source.replace(before, after, 1)
    candidate = tmp_path / "candidate.v"
    candidate.write_text(source)
    executable = tmp_path / "test.vvp"
    (tmp_path / "build").mkdir()
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.FIFO_DEPTH={depth}", "-o", str(executable),
        str(candidate), str(golden), str(ACQ / "tb/tb_starlink_pss_transform_fifo.sv"),
        str(ACQ / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30, check=False)
    output = result.stdout + result.stderr
    if mutation:
        assert result.returncode != 0 and "FIFO_STORAGE_EQUIVALENCE_FAIL" in output, output
    else:
        assert result.returncode == 0 and "FAIL" not in output and "ERROR" not in output, output
        assert output.count("FIFO_STORAGE_EQUIVALENCE_WITNESS checked_cycles=512") == 1
        assert f"TRANSFORM_FIFO_PASS words=512 depth={depth}" in output
