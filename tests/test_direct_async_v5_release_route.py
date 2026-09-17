"""Keep the v0.51 direct-async route and source locks consistent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_async_v5_release_route_and_locks():
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    branch = "refs/heads/codex/issue-102-fw-release"
    assert workflow.count(branch) == 4
    assert workflow.count("'v0.51-plutoplus-spf-iq-direct-async-v5'") == 1
    assert workflow.count("'iq-direct-async-v5-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-iq-direct-async-v5'") == 1
    manifest = dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/iq-direct-async-v5-source.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )
    assert manifest["submodule_buildroot"] == (
        "2864a10b0ddd04d355b180152cd02d32909d6376"
    )
    assert manifest["submodule_linux"] == (
        "4683cd2e3556448295e03a216a3a7fc6e8bbc474"
    )
    assert manifest["libiio_0_25_source"] == "a8c4809c2cfe77ac5bd6fe95f8ead0559fbbe6ff"
    assert manifest["libiio_0_25_archive_sha256"] == "e7034fc9b5cb945150ed46c922f22434a7d95cc6ff4773deb9a476ac6b3f78fa"
    for script in ("scripts/build_gain_series_candidate.sh", "scripts/ci/package_main_firmware.sh"):
        assert "iq-direct-async-v5-source.yaml |" in (ROOT / script).read_text()
