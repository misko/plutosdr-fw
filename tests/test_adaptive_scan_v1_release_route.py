"""Keep the v0.52 adaptive-scan route and source locks consistent."""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/adaptive-scan-v1-source.yaml")
        .read_text()
        .splitlines()
        if ": " in line and not line.startswith("#")
    )


def _historical_source_commit(manifest: dict[str, str]) -> str:
    """Return the immutable firmware source commit, fetching its release tag if needed."""
    source_commit = manifest["firmware_source"]
    assert re.fullmatch(r"[0-9a-f]{40}", source_commit)

    available = subprocess.run(
        ["git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if available.returncode != 0:
        # CI checkouts may be shallow. Fetch only the manifest's immutable
        # release tag, then verify that it resolves to the pinned source commit.
        tag = manifest["release_tag"]
        assert re.fullmatch(r"[A-Za-z0-9._/-]+", tag)
        subprocess.run(
            ["git", "fetch", "--no-tags", "origin", f"refs/tags/{tag}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        fetched_commit = subprocess.check_output(
            ["git", "rev-parse", "FETCH_HEAD^{commit}"], cwd=ROOT, text=True
        ).strip()
        assert fetched_commit == source_commit

    return source_commit


def _historical_submodule_pin(source_commit: str, component: str) -> str:
    entry = subprocess.check_output(
        ["git", "ls-tree", source_commit, "--", component], cwd=ROOT, text=True
    ).split()
    assert len(entry) == 4
    mode, object_type, object_id, path = entry
    assert (mode, object_type, path) == ("160000", "commit", component)
    return object_id


def test_adaptive_scan_v1_release_route_and_locks() -> None:
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    branch = "refs/heads/codex/feature-103"
    assert workflow.count(branch) == 4
    assert workflow.count("'v0.52-plutoplus-spf-adaptive-scan-v1'") == 1
    assert workflow.count("'adaptive-scan-v1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-adaptive-scan-v1'") == 1

    manifest = _manifest()
    source_commit = _historical_source_commit(manifest)
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        pin = _historical_submodule_pin(source_commit, component)
        assert manifest["submodule_" + component.replace("-", "_")] == pin

    assert manifest["libiio_0_25_source"] == (
        "5518228d9181b95de7b7f3e2fdfe1fee438fbbf0"
    )
    assert manifest["libiio_0_25_archive_sha256"] == (
        "3fca3c443626736716907baee722a462b5fc20587707a6b5deaa4e085624454a"
    )
    assert manifest["release_state"] == "hardware-qualified-release"
    assert manifest["release_tag"] == "v0.52-plutoplus-spf-adaptive-scan-v1"
    assert manifest["firmware_source"] == (
        "2da11edf69bba3e193b816da037da13e41c51a4d"
    )

    protected = (
        ROOT / "scripts/build_gain_series_candidate.sh"
    ).read_text(), (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    for source in protected:
        assert "adaptive-scan-v1-source.yaml |" in source
    assert (
        "adaptive-scan-v1-source.yaml:*)"
        in (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    )
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/adaptive-scan-v1-source.yaml"
        in (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    )


def test_adaptive_scan_v1_build_applies_qualified_topology_to_every_fit_slot() -> None:
    build = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    makefile = (ROOT / "Makefile").read_text()
    topology = (ROOT / "scripts/feature103/apply_rx0_tx2_topology.sh").read_text()

    assert "candidate_make_args+=(FEATURE103_RX0_TX2_TOPOLOGY=1)" in build
    assert "$(FEATURE103_TOPOLOGY_STAMP)" in makefile
    assert "apply_rx0_tx2_topology.sh $(TARGET_DTS_FILES)" in makefile
    assert "apply_rx0_tx2_topology.sh --check" in (
        ROOT / "scripts/ci/package_main_firmware.sh"
    ).read_text()
    assert "adi,2rx-2tx-mode-enable" in topology
    assert "adi,1rx-1tx-mode-use-rx-num 1" in topology
    assert "adi,1rx-1tx-mode-use-tx-num 2" in topology
    assert "adi,axi-ad9364-dds-6.00.a" in topology
