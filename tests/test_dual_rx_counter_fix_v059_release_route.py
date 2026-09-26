"""Bind the v0.59 dual-RX counter-fix candidate to its source graph."""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "dual-rx-counter-fix-v059-source.yaml"
VERSION = "v0.59-plutoplus-spf-dual-rx-counter-fix"
BRANCH = "refs/heads/codex/v059-dual-rx-counter-fix"


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests" / MANIFEST_NAME).read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_v059_route_is_versioned_and_source_locked() -> None:
    manifest = _manifest()
    assert manifest["release_state"] == "final-release"
    assert manifest["submodule_linux"] == "a008394055c72ad88e45b30e0979d0e5f09642ec"
    assert manifest["submodule_linux_ref"] == (
        "refs/tags/adaptive-multirate-agc-v059-source/linux-v2"
    )
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", component], cwd=ROOT, text=True
        ).split()
        assert (entry[0], entry[3]) == ("160000", component)
        assert manifest["submodule_" + component.replace("-", "_")] == entry[1]

    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert f"github.ref == '{BRANCH}'" in workflow
    assert f"'{MANIFEST_NAME}'" in workflow
    assert "'plutoplus-spf-dual-rx-counter-fix'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    gate = re.search(
        r"- name: Require the exact dual-RX counter-fix candidate identity\n"
        r"(?P<body>.*?)(?=\n      - name:)", workflow, re.DOTALL
    )
    assert gate is not None
    assert f"github.ref == '{BRANCH}'" in gate["body"]
    assert f"'{VERSION}'" in gate["body"]

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    assert MANIFEST_NAME in builder
    assert MANIFEST_NAME in package
    assert f"protected_version='{VERSION}'" in package
