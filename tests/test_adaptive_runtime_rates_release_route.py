"""The runtime-rate image must bind its version and every component source."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_rate_source_and_route() -> None:
    manifest = dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/adaptive-runtime-rates-source.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", component], cwd=ROOT, text=True
        ).split()
        assert entry[0] == "160000"
        assert manifest["submodule_" + component.replace("-", "_")] == entry[1]
    assert manifest["libiio_0_25_source"] == "c93db89b27fd46faf5479ceb5bf08460226a88ce"
    assert manifest["libiio_0_25_archive_sha256"] == "be66825508f1c9b41bad219e2480be9d8b8c86b94d06cd38953b8d53630b8de5"
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    assert workflow.count("refs/heads/codex/issue-111-runtime-rates") == 5
    assert "'v0.55-plutoplus-spf-adaptive-runtime-rates'" in workflow
    assert "'adaptive-runtime-rates-source.yaml'" in workflow
    for name in ("scripts/build_gain_series_candidate.sh", "scripts/ci/package_main_firmware.sh"):
        assert "adaptive-runtime-rates-source.yaml |" in (ROOT / name).read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    assert "adaptive-runtime-rates-source.yaml:final-release)" in package
    assert '"$(basename "$MANIFEST")" == adaptive-runtime-rates-source.yaml ||' in package
    assert "protected_version='v0.55-plutoplus-spf-adaptive-runtime-rates'" in package
