"""Exercise the complete built candidate through the synthetic MTD transaction."""
import hashlib
import json

import pytest

from .test_flash_safety import ROOT, run_updater, updater  # noqa: F401


@pytest.fixture
def fit():
    directory = ROOT / "build/issue99/candidate"
    if not (directory / "candidate.json").exists():
        pytest.skip("build the issue99 recovery candidate first")
    manifest = json.loads((directory / "candidate.json").read_text())
    for name, record in manifest["files"].items():
        data = (directory / name).read_bytes()
        assert len(data) == record["bytes"]
        assert hashlib.sha256(data).hexdigest() == record["sha256"]
    assert manifest["qualification"] is None
    assert manifest["persistent_range"]["fit_bytes"] <= 0xE00000
    return directory / "pluto.itb"


def test_built_candidate_completes_checked_transaction(updater):
    root, _, _ = updater
    result = run_updater(updater)
    assert result.returncode == 0, result.stderr
    assert (root / "mutations").read_text() == "flashcp\nfw_setenv\n"
    assert "Done" in result.stdout
