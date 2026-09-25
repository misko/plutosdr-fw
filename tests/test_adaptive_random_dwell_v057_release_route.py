"""Bind the v0.57 main release route to its immutable source graph."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "adaptive-random-dwell-v057-source.yaml"
VERSION = "v0.57-plutoplus-spf-adaptive-random-dwell"


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests" / MANIFEST_NAME).read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_v057_main_route_is_versioned_and_source_locked() -> None:
    manifest = _manifest()
    assert manifest["release_state"] == "final-release"
    assert manifest["libiio_0_25_source"] == "9080b774f6ea086b4b9a5eb07743b313d297044f"
    assert "firmware_source" not in manifest
    assert "release_tag" not in manifest
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", component], cwd=ROOT, text=True
        ).split()
        assert (entry[0], entry[3]) == ("160000", component)
        assert manifest["submodule_" + component.replace("-", "_")] == entry[1]

    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert "'adaptive-random-dwell-v057-source.yaml'" in workflow
    assert "'plutoplus-spf-adaptive-random-dwell'" in workflow
    final_gate = re.search(
        r"- name: Require the exact final release identity\n"
        r"(?P<body>.*?)(?=\n      - name:)", workflow, re.DOTALL
    )
    assert final_gate is not None
    assert "github.ref == 'refs/heads/main'" in final_gate["body"]
    assert f"'{VERSION}'" in final_gate["body"]

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    assert MANIFEST_NAME in builder
    assert MANIFEST_NAME in package
    assert f"{MANIFEST_NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
    assert f"./scripts/check_source_graph.sh manifests/{MANIFEST_NAME}" in checker
