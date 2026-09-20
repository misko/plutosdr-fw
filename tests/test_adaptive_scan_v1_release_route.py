"""Keep the v0.52 adaptive-scan route and source locks consistent."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, str]:
    return dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/adaptive-scan-v1-source.yaml")
        .read_text()
        .splitlines()
        if ": " in line and not line.startswith("#")
    )


def test_adaptive_scan_v1_release_route_and_locks() -> None:
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    branch = "refs/heads/codex/feature-103"
    assert workflow.count(branch) == 4
    assert workflow.count("'v0.52-plutoplus-spf-adaptive-scan-v1'") == 1
    assert workflow.count("'adaptive-scan-v1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-adaptive-scan-v1'") == 1

    manifest = _manifest()
    assert manifest["submodule_buildroot"] == (
        "91b38f76f899fbd51bc1139e38c71695dda7bf1c"
    )
    assert manifest["submodule_linux"] == (
        "eeefe8c6228eede6206197e941aa7024d5ac60d2"
    )

    assert manifest["libiio_0_25_source"] == (
        "f353040efe92c54059d0c9168ce15ce89ec61730"
    )
    assert manifest["libiio_0_25_archive_sha256"] == (
        "5041aacd4e38d0d88f32ffe84f9bb6d4d6b79346fe18be188658a340f8174acb"
    )
    assert manifest["release_state"] == "candidate"
    assert "release_tag" not in manifest

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
