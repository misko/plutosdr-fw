"""Bind the integrated candidate build route to its source and board topology."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_integrated_counter_utc_source_matches_released_gitlinks() -> None:
    manifest = dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/counter-utc-v054-source.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        entry = subprocess.check_output(
            ["git", "ls-tree", "0ffdfe964247c63945aa6d0e4a159ee09f241396", "--", component], cwd=ROOT, text=True
        ).split()
        assert entry[0] == "160000"
        assert manifest["submodule_" + component.replace("-", "_")] == entry[2]
    assert manifest["libiio_0_25_source"] == "e234d2d7fae19d47e4655068df69679c3b2f4427"
    assert manifest["libiio_0_25_archive_sha256"] == (
        "4505f1fcfbf4c5f066d35ca4e4af9d5cc734e86cf70e442eb17a84ff4321f752"
    )
    assert manifest["release_state"] == "candidate"


def test_integrated_counter_utc_identity_and_dual_rx_gate() -> None:
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    assert workflow.count("refs/heads/codex/counter-utc-release") == 4
    assert "'v0.54-plutoplus-spf-counter-utc-v1-rc1'" in workflow
    assert "'counter-utc-v054-source.yaml'" in workflow
    assert "counter-utc-v054-source.yaml:candidate)" in package
    assert "protected_version='v0.54-plutoplus-spf-counter-utc-v1-rc1'" in package
    topology_condition = package.split("scripts/issue108/check_dual_rx_topology.sh", 1)[0]
    assert '"$(basename "$MANIFEST")" == counter-utc-v054-source.yaml' in topology_condition
    offline = (ROOT / "scripts/check_tandem_release_offline.sh").read_text().splitlines()
    assert "    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/counter-utc-v054-source.yaml" in offline
    assert (
        "    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/adaptive-scan-v2-source.yaml"
        in offline
    )
