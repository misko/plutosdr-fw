"""Bind the v0.57 fixed-dwell build to its immutable source graph."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "fixed-dwell-v057-source.yaml"
VERSION = "v0.57-plutoplus-spf-fixed-dwell"


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests" / MANIFEST_NAME).read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_v057_branch_route_is_versioned_and_source_locked() -> None:
    manifest = _manifest()
    assert manifest["release_state"] == "final-release"
    assert manifest["libiio_0_25_source"] == (
        "0132fc62945f52d5c1fc0273c26b059d16bc42e1"
    )
    assert manifest["ppu_source"] == "036cf821997a0c1a8c60055de432a8021d662a5f"
    assert manifest["leo_source"] == "0608cc9bb9e941c46ba557f878598d69527dc711"
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", component], cwd=ROOT, text=True
        ).split()
        assert (entry[0], entry[3]) == ("160000", component)
        assert manifest["submodule_" + component.replace("-", "_")] == entry[1]

    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert "refs/heads/codex/issue-114-fixed-dwell" in workflow
    assert f"'{MANIFEST_NAME}'" in workflow
    assert "'plutoplus-spf-fixed-dwell'" in workflow
    assert f"'{VERSION}'" in workflow

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    assert f"{MANIFEST_NAME} |" in builder
    assert f"{MANIFEST_NAME} |" in package
    assert f"{MANIFEST_NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
    assert f"./scripts/check_source_graph.sh manifests/{MANIFEST_NAME}" in checker
