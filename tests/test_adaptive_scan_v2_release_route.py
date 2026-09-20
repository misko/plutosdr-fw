"""Keep the v0.53 adaptive-scan v2 route and source locks consistent."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/adaptive-scan-v2-source.yaml")
        .read_text()
        .splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_adaptive_scan_v2_release_route_and_locks() -> None:
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    branch = "refs/heads/codex/issue-108-manual-dual-rx-fw"
    assert workflow.count(branch) == 5
    assert workflow.count("'v0.53-plutoplus-spf-adaptive-scan-v2'") == 1
    assert workflow.count("'adaptive-scan-v2-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-adaptive-scan-v2'") == 1

    manifest = _manifest()
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        # This is a historical release. Later firmware may intentionally advance
        # its gitlinks while the published v0.53 source lock remains immutable.
        entry = subprocess.check_output(
            ["git", "ls-tree", "5cd4cf3e91f1cfd26dd7c75e9678c32e4c6f8090", "--", component],
            cwd=ROOT, text=True,
        ).split()
        assert (entry[0], entry[1], entry[3]) == ("160000", "commit", component)
        pin = entry[2]
        assert manifest["submodule_" + component.replace("-", "_")] == pin

    assert manifest["libiio_0_25_source"] == (
        "959cefb4b3cc9a13fffd02e3f7d0e5deabf3eca2"
    )
    assert manifest["libiio_0_25_archive_sha256"] == (
        "ce234ba0c8de0bf11d78424f6eb9b9c074046af8035e71faf516937717897aec"
    )
    assert manifest["release_state"] == "candidate"
    assert "release_tag" not in manifest

    build = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    offline = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    for source in (build, package):
        assert "adaptive-scan-v2-source.yaml |" in source
    assert "adaptive-scan-v2-source.yaml:candidate)" in package
    assert "adaptive-scan-v2-source.yaml:final-release)" in package
    assert "v0.53-plutoplus-spf-adaptive-scan-v2-rc1" in package
    assert "v0.53-plutoplus-spf-adaptive-scan-v2'" in package
    assert (
        "github.ref == 'refs/heads/codex/issue-108-manual-dual-rx-fw' &&\n"
        "          'final-release'"
        in workflow
    )
    assert "check_dual_rx_topology.sh" in package
    assert (
        "./scripts/check_source_graph.sh manifests/adaptive-scan-v2-source.yaml"
        in offline
    )


def test_adaptive_scan_v2_topology_checker_accepts_built_board_dtbs() -> None:
    dtbs = [
        ROOT / "build/zynq-pluto-sdr.dtb",
        ROOT / "build/zynq-pluto-sdr-revb.dtb",
        ROOT / "build/zynq-pluto-sdr-revc.dtb",
    ]
    if not all(path.is_file() for path in dtbs):
        return
    subprocess.run(
        [str(ROOT / "scripts/issue108/check_dual_rx_topology.sh"), *map(str, dtbs)],
        cwd=ROOT,
        check=True,
    )
