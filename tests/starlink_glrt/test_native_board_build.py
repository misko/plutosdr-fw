"""Invalid native board selections fail before creating a build or using tools."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("rate,flag", [("2500000", "--native-refinement"),
    ("25000000", "--native-refinement"), ("60000000", "--native"), ("60000001", "--native-refinement"),
    ("25000000", "--native-lean"), ("60000001", "--native-lean")])
def test_invalid_native_build_selection_creates_no_evidence_directory(tmp_path, rate, flag):
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path/"board"
    result = subprocess.run(["bash", str(repo/"scripts/build_glrt_board.sh"), rate, str(output), flag],
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2
    assert not output.exists()


@pytest.mark.parametrize("rate,native,legacy,accepted", [
    ("60000000", "1", "0", True), ("60000000", "1", "1", True),
    ("2500000", "0", "1", True), ("60000000", "0", "0", False),
    ("25000000", "1", "0", False), ("60000000", "1", "2", False),
])
def test_block_design_profile_selection(tmp_path, rate, native, legacy, accepted):
    # Execute the real selection/validation Tcl. Only Vivado's BD operations
    # are stubbed; the parameter values and rejected combinations are real.
    repo = Path(__file__).resolve().parents[2]
    bench = tmp_path / "selection.tcl"
    bench.write_text("\n".join([
        f"set ::env(STARLINK_GLRT_RATE_HZ) {rate}",
        f"set ::env(STARLINK_GLRT_NATIVE_REFINEMENT) {native}",
        f"set ::env(STARLINK_GLRT_LEGACY_SCORER) {legacy}",
        "proc unknown {args} { return {} }",
        'proc ad_ip_parameter {cell key value} { puts "$key=$value" }',
        f"source {{{repo / 'hdl/projects/pluto/system_glrt_bd.tcl'}}}",
    ]) + "\n")
    result = subprocess.run(["tclsh", str(bench)], capture_output=True, text=True, timeout=10, check=False)
    assert (result.returncode == 0) == accepted, result.stdout + result.stderr
    if accepted:
        assert f"CONFIG.ENABLE_LEGACY_SCORER={legacy}" in result.stdout
        assert ("CONFIG.ENABLE_NATIVE_REFINEMENT=1" in result.stdout) == (native == "1")
