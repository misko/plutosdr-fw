"""Bind the v0.56 main release route to its immutable source graph."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "adaptive-runtime-rates-v056-source.yaml"
VERSION = "v0.56-plutoplus-spf-adaptive-runtime-rates"


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests" / MANIFEST_NAME).read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_v056_main_route_is_versioned_and_source_locked() -> None:
    manifest = _manifest()
    assert manifest["release_state"] == "final-release"
    assert "firmware_source" not in manifest
    assert "release_tag" not in manifest
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            [
                "git",
                "ls-tree",
                "e39162c7cee17136b2575aadfa4c6802d7cdebed",
                "--",
                component,
            ],
            cwd=ROOT,
            text=True,
        ).split()
        assert (entry[0], entry[3]) == ("160000", component)
        assert manifest["submodule_" + component.replace("-", "_")] == entry[2]

    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert (
        "github.ref == 'refs/heads/main' &&\n"
        "          'adaptive-runtime-rates-v056-source.yaml'"
    ) in workflow
    assert (
        "github.ref == 'refs/heads/main' &&\n"
        "          'plutoplus-spf-adaptive-runtime-rates'"
    ) in workflow
    final_gate = re.search(
        r"- name: Require the exact final release identity\n"
        r"(?P<body>.*?)(?=\n      - name:)",
        workflow,
        re.DOTALL,
    )
    assert final_gate is not None
    assert "github.ref == 'refs/heads/main'" in final_gate["body"]
    assert f"'{VERSION}'" in final_gate["body"]

    counter_rx_gate = re.search(
        r"- name: Require the exact counter RX v1 candidate identity\n"
        r"(?P<body>.*?)(?=\n      - name:)",
        workflow,
        re.DOTALL,
    )
    assert counter_rx_gate is not None
    assert "'v0.50-plutoplus-spf-counter-rx-v1'" in counter_rx_gate["body"]

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    assert f"{MANIFEST_NAME} |" in builder
    assert f"{MANIFEST_NAME} |" in package
    assert f"{MANIFEST_NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
    assert f"./scripts/check_source_graph.sh manifests/{MANIFEST_NAME}" in checker
