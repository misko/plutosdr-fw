"""Keep the superseded v0.56 source graph immutable and reproducible."""
from pathlib import Path

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
    assert manifest["libiio_0_25_source"] == "c93db89b27fd46faf5479ceb5bf08460226a88ce"
    assert manifest["submodule_buildroot"] == "a6ee97729ee2494c759a942ae8b26239bb840833"

    builder = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    assert MANIFEST_NAME in builder
    assert MANIFEST_NAME in package
    assert f"{MANIFEST_NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
    assert f"check_source_graph.sh manifests/{MANIFEST_NAME}" in checker
