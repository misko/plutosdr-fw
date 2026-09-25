"""Bind the v0.58 release branch to its immutable source graph."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "adaptive-multirate-agc-v058-source.yaml"
VERSION = "v0.58-plutoplus-spf-adaptive-multirate-agc"
BRANCH = "refs/heads/codex/issues-111-116-next-fw"


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests" / MANIFEST_NAME).read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_v058_route_is_versioned_and_source_locked() -> None:
    manifest = _manifest()
    assert manifest["release_state"] == "final-release"
    assert manifest["libiio_0_25_source"] == "7639fc9b6c01336e1451f4f58ccf66e30a22388d"
    assert manifest["libiio_0_25_archive_sha256"] == (
        "6da6c6c4fb94148c6fdde184c77c3a62d77424c73bc52b6427f5d0353e253410"
    )
    assert "firmware_source" not in manifest
    assert "release_tag" not in manifest
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", component], cwd=ROOT, text=True
        ).split()
        assert (entry[0], entry[3]) == ("160000", component)
        assert manifest["submodule_" + component.replace("-", "_")] == entry[1]

    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert f"github.ref == '{BRANCH}'" in workflow
    assert f"'{MANIFEST_NAME}'" in workflow
    assert "'plutoplus-spf-adaptive-multirate-agc'" in workflow
    gate = re.search(
        r"- name: Require the exact adaptive multirate AGC identity\n"
        r"(?P<body>.*?)(?=\n      - name:)", workflow, re.DOTALL
    )
    assert gate is not None
    assert f"github.ref == '{BRANCH}'" in gate["body"]
    assert f"'{VERSION}'" in gate["body"]

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    assert MANIFEST_NAME in builder
    assert MANIFEST_NAME in package
    assert f"{MANIFEST_NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
