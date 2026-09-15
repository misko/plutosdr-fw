"""Keep the issue #99 prerelease route explicit and conservative."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/firmware-main.yml"
PACKAGER = ROOT / "scripts/ci/package_main_firmware.sh"


def test_issue99_rc1_release_route_is_pinned_and_stable_release_is_blocked():
    workflow = WORKFLOW.read_text()
    packager = PACKAGER.read_text()
    branch = "refs/heads/codex/issue-99-flash-safety"
    version = "v0.51-plutoplus-spf-counter-rx-v1-flash-safety-rc1"

    assert workflow.count(branch) == 4
    assert workflow.count("'flash-safety-v1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-counter-rx-v1-flash-safety'") == 1
    assert workflow.count(f"'{version}'") == 1
    assert "flash-safety stable is unqualified" in workflow
    assert "flash-safety-v1-source.yaml:candidate)" in packager
    assert f"protected_version='{version}'" in packager
    assert "16777216" in (ROOT / "buildroot/board/pluto/pluto-fw-update").read_text()
