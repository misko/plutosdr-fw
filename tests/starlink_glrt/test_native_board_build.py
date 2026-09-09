"""Invalid native board selections fail before creating a build or using tools."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("rate,flag", [("2500000", "--native-refinement"),
    ("25000000", "--native-refinement"), ("60000000", "--native"), ("60000001", "--native-refinement")])
def test_invalid_native_build_selection_creates_no_evidence_directory(tmp_path, rate, flag):
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path/"board"
    result = subprocess.run(["bash", str(repo/"scripts/build_glrt_board.sh"), rate, str(output), flag],
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2
    assert not output.exists()
