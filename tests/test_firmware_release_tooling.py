"""Static oracles for release-only package and verification entry points."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_final_release_verifier_cannot_skip_dfu_suffix() -> None:
    verifier = (ROOT / "scripts" / "verify_release.sh").read_text()
    assert "grep dfu-suffix" in verifier
    assert 'dfu-suffix -c "$IMAGE"' in verifier
    assert "dfu suffix SKIPPED" not in verifier
    assert "if command -v dfu-suffix" not in verifier


def test_trusted_build_packages_the_exact_persistent_frm() -> None:
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()

    assert "build/pluto.dfu build/pluto.frm" in builder
    assert package.count("build/pluto.frm") == 2
    assert 'cp build/pluto.frm "$frm"' in package
    assert 'cmp -n "$dfu_fit_bytes" "$dfu" "$frm"' in package
    assert '"$frm_trailer_md5" == "$frm_body_md5"' in package
    assert '"$(basename "$frm")"' in package
    assert "--untracked-files=all" in builder
    assert package.count("--untracked-files=all") == 2
    assert (
        "release-authorizing package requires a completely clean source tree" in package
    )


def test_trusted_build_retains_and_gates_routed_utilization() -> None:
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    assert "report_utilization -file" in package
    assert package.count("system_top_utilization_routed.rpt") >= 4
    assert (
        '--utilization-report "$ARTIFACT_ROOT/system_top_utilization_routed.rpt"'
        in package
    )


def test_packaged_dfu_fpga_payload_matches_the_qualified_xsa() -> None:
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    assert 'fpga_index="$(awk' in package
    assert '-o "$ARTIFACT_ROOT/packed-fpga.bit" "$dfu"' in package
    assert 'unzip -p "$xsa" system_top.bit' in package
    assert (
        'cmp "$ARTIFACT_ROOT/system_top.bit" "$ARTIFACT_ROOT/packed-fpga.bit"'
        in package
    )
    assert "sha256sum system_top.bit > system-top-bit.sha256" in package


def test_bundle_and_checksum_inventories_use_one_bytewise_order() -> None:
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()

    # Python's evidence verifier compares canonical ASCII member names in
    # bytewise order.  The producer must not inherit a runner locale or retain
    # the hand-authored payload array order.
    assert package.count("LC_ALL=C sort") == 3
    assert "mapfile -t payload_files < <(" in package
    assert "printf '%s\\n' \"${payload_files[@]}\" | LC_ALL=C sort" in package
    assert "tar --sort=name" in package


def test_protected_package_routes_require_exact_declared_identities() -> None:
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    assert "tandem-agc-v8-rc5-source.yaml:*" in package
    assert "tandem-agc-v8-rc6-source.yaml:*" in package
    assert "tandem-agc-v8-rc7-source.yaml:*" in package
    assert "tandem-agc-v8-rc8-source.yaml:*" in package
    assert "tandem-agc-v8-rc9-source.yaml:*" in package
    assert "tandem-agc-v8-rc10-source.yaml:*" in package
    assert "tandem-agc-v8-rc11-source.yaml:*" in package
    assert "tandem-agc-v8-rc12-source.yaml:*" in package
    assert "tandem-agc-v8-rc13-source.yaml:*" in package
    assert "tandem-agc-v8-rc14-source.yaml:*" in package
    assert "tandem-agc-v8-rc15-source.yaml:*" in package
    assert "tandem-agc-v8-rc16-source.yaml:*" in package
    assert "tandem-agc-v8-rc17-source.yaml:*" in package
    assert "tandem-agc-v8-rc18-source.yaml:*" in package
    assert "tandem-agc-v8-rc19-source.yaml:*" in package
    assert "tandem-agc-v8-rc20-source.yaml:*" in package
    assert "tandem-agc-v8-rc21-source.yaml:*" in package
    assert "tandem-agc-v8-rc22-source.yaml:*" in package
    assert "tandem-agc-v8-rc23-source.yaml:*" in package
    assert "tandem-agc-v8-rc24-source.yaml:*" in package
    assert "tandem-agc-v8-rc25-source.yaml:*" in package
    assert "tandem-agc-v8-rc26-source.yaml:*" in package
    assert "tandem-agc-v8-rc27-source.yaml:*" in package
    assert "tandem-agc-v8-rc28-source.yaml:*" in package
    assert "tandem-agc-v8-rc29-source.yaml:*" in package
    assert "tandem-agc-v8-rc30-source.yaml:*" in package
    assert "tandem-agc-v8-rc31-source.yaml:*" in package
    assert "tandem-agc-v8-rc32-source.yaml:*" in package
    assert "ddr-burst-v1-rc2-source.yaml:candidate" in package
    assert "ddr-burst-v1-rc3-source.yaml:candidate" in package
    assert "ddr-burst-v1-rc4-source.yaml:candidate" in package
    assert "ddr-burst-v1-rc5-source.yaml:candidate" in package
    assert "ddr-burst-v2-rc1-source.yaml:candidate" in package
    assert "ddr-burst-v2-rc2-source.yaml:candidate" in package
    assert "ddr-burst-v2-rc3-source.yaml:candidate" in package
    assert "ddr-capacity-test-rc1-source.yaml:candidate" in package
    assert "ddr-ring-v1-rc1-source.yaml:candidate" in package
    assert "ddr-ring-v1-rc2-source.yaml:candidate" in package
    assert "ddr-ring-v1-rc2-source.yaml:final-release" in package
    assert "ddr-ring-prefill-v1-rc1-source.yaml:candidate" in package
    assert "ddr-ring-prefill-v1-rc1-source.yaml:final-release" in package
    assert "iq-direct-async-ring-v1-rc1-source.yaml:candidate" in package
    assert "iio-throughput-coverage-window-v6-rc1-source.yaml:candidate" in package
    assert "iio-throughput-coverage-window-v6-rc1-source.yaml:final-release" in package
    assert "tandem-agc-v8-source.yaml:final-release" in package
    assert "protected route requires RELEASE_VERSION=" in package
    for source in (package, builder):
        assert "protected manifest must use the canonical repository path" in source
        assert "protected manifest differs from its committed HEAD blob" in source


def test_single_rx_metadata_candidate_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/issue-50-single-rx-metadata"

    assert workflow.count(f"{branch}'") == 4
    assert workflow.count("'single-rx-metadata-rc1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-single-rx-metadata-rc1'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-single-rx-metadata-rc1'") == 1
    assert "Require the exact single-RX metadata candidate identity" in workflow
    for source in (builder, package):
        assert "single-rx-metadata-rc1-source.yaml" in source


def test_ddr_burst_rc5_keeps_its_exact_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/ddr-burst"

    assert workflow.count(f"{branch}'") == 4
    assert workflow.count("'ddr-burst-v1-rc5-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-ddr-burst-v1-rc5'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-ddr-burst-v1-rc5'") == 1
    assert "Require the exact DDR burst RC5 RAM candidate identity" in workflow
    assert "ddr-burst-v1-rc5-source.yaml:candidate" in package
    assert "v0.42-plutoplus-spf-ddr-burst-v1-rc5" in package
    for source in (builder, package):
        assert "ddr-burst-v1-rc5-source.yaml" in source


def test_ddr_burst_v2_keeps_its_exact_rc3_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/ddr-burst-v2"

    assert workflow.count(branch) == 4
    assert workflow.count("'ddr-burst-v2-rc1-source.yaml'") == 0
    assert workflow.count("'ddr-burst-v2-rc3-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-ddr-burst-v2'") == 0
    assert workflow.count("'plutoplus-spf-ddr-burst-v2-rc3'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-ddr-burst-v2'") == 0
    assert workflow.count("'v0.42-plutoplus-spf-ddr-burst-v2-rc3'") == 1
    assert "Require the exact DDR burst v2 RC3 candidate identity" in workflow
    assert "ddr-burst-v2-rc1-source.yaml:candidate" in package
    assert "ddr-burst-v2-rc2-source.yaml:candidate" in package
    assert "ddr-burst-v2-rc3-source.yaml:candidate" in package
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-burst-v1-rc5-source.yaml"
    ) in checker
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-burst-v2-rc1-source.yaml"
    ) in checker
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-burst-v2-rc2-source.yaml"
    ) in checker
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-burst-v2-rc3-source.yaml"
    ) in checker
    for source in (builder, package, checker):
        assert "ddr-burst-v2-rc1-source.yaml" in source
        assert "ddr-burst-v2-rc2-source.yaml" in source
        assert "ddr-burst-v2-rc3-source.yaml" in source


def test_ddr_capacity_candidate_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/ddr-capacity-test"

    assert workflow.count(branch) == 4
    assert workflow.count("'ddr-capacity-test-rc1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-ddr-capacity-test-rc1'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-ddr-capacity-test-rc1'") == 1
    assert "Require the exact DDR capacity test RC1 identity" in workflow
    assert "ddr-capacity-test-rc1-source.yaml:candidate" in package
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-capacity-test-rc1-source.yaml"
        in checker
    )
    for source in (builder, package, checker):
        assert "ddr-capacity-test-rc1-source.yaml" in source


def test_ddr_ring_v1_keeps_its_exact_historical_rc2_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/ddr-ring-v1"

    assert workflow.count(branch) == 4
    assert workflow.count("'ddr-ring-v1-rc1-source.yaml'") == 0
    assert workflow.count("'ddr-ring-v1-rc2-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-ddr-ring-v1'") == 0
    assert workflow.count("'plutoplus-spf-ddr-ring-v1-rc2'") == 1
    assert workflow.count("'v0.43-plutoplus-spf-ddr-ring-v1'") == 0
    assert workflow.count("'v0.43-plutoplus-spf-ddr-ring-v1-rc2'") == 1
    assert "Require the exact DDR ring v1 RC2 candidate identity" in workflow
    assert "ddr-ring-v1-rc1-source.yaml:candidate" in package
    assert "ddr-ring-v1-rc2-source.yaml:candidate" in package
    assert "ddr-ring-v1-rc2-source.yaml:final-release" in package
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-ring-v1-rc1-source.yaml"
    ) in checker
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-ring-v1-rc2-source.yaml"
    ) in checker
    for source in (builder, package, checker):
        assert "ddr-ring-v1-rc1-source.yaml" in source
        assert "ddr-ring-v1-rc2-source.yaml" in source


def test_ddr_ring_prefill_v1_keeps_its_exact_historical_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/issue-63-ddr-prefill"

    assert workflow.count(branch) == 4
    assert workflow.count("'ddr-ring-prefill-v1-rc1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-ddr-ring-prefill-v1'") == 0
    assert workflow.count("'plutoplus-spf-ddr-ring-prefill-v1-rc1'") == 1
    assert workflow.count("'v0.44-plutoplus-spf-ddr-ring-prefill-v1'") == 0
    assert workflow.count("'v0.44-plutoplus-spf-ddr-ring-prefill-v1-rc1'") == 1
    assert "Require the exact DDR ring prefill v1 RC1 candidate identity" in workflow
    assert "Require the exact final release identity" in workflow
    assert "ddr-ring-prefill-v1-rc1-source.yaml:candidate" in package
    assert "ddr-ring-prefill-v1-rc1-source.yaml:final-release" in package
    assert (
        "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh "
        "manifests/ddr-ring-prefill-v1-rc1-source.yaml"
    ) in checker
    for source in (builder, package, checker):
        assert "ddr-ring-prefill-v1-rc1-source.yaml" in source


def test_direct_async_ring_v1_has_an_exact_protected_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    source_graph = (ROOT / "scripts" / "check_source_graph.sh").read_text()
    branch = "refs/heads/codex/iq-direct-async-main-refresh"
    manifest_name = "iq-direct-async-ring-v1-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert workflow.count("'plutoplus-spf-iq-direct-async-ring-v1-rc1'") == 1
    assert (
        workflow.count("'v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1'")
        == 1
    )
    assert "Require the exact direct-async IQ ring v1 RC1 identity" in workflow
    assert f"{manifest_name}:candidate" in package
    assert f"./scripts/check_source_graph.sh manifests/{manifest_name}" in checker
    for source in (builder, package, checker):
        assert manifest_name in source
    assert "libiio_0_25_archive_sha256" in source_graph
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: b7303fded264e10473bbbb084afade8f1b1373d1" in manifest
    assert "metadata_source: 3294365ff44da26b261be4a2ccb241b7896d23ad" in manifest
    assert "submodule_buildroot: a929267288a80a31407a3af06345c088979bcc2e" in manifest
    assert (
        "libiio_0_25_archive_sha256: "
        "67364f519619afb1c7f12d35ea35e605e00d01d23fc470f16dc903c5b5cdd49a"
        in manifest
    )


def test_iio_throughput_affinity_candidate_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    manifest_name = "iio-throughput-affinity-v1-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count("refs/heads/codex/iio-throughput-stage-timing-fw") == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert workflow.count("'plutoplus-spf-iio-throughput-affinity-v1-rc1'") == 1
    assert workflow.count("'v0.45-plutoplus-spf-iio-throughput-affinity-v1-rc1'") == 1
    assert f"{manifest_name}:candidate" in package
    for source in (builder, package):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: 69ba17e53198d1f1db68b1f9c186e99da30f04aa" in manifest
    assert "submodule_buildroot: e560f6df5e8cd1aecc49cd43900a4ef6574bc0d1" in manifest


def test_iio_throughput_rw_affinity_v2_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-rw-affinity-v2-fw"
    manifest_name = "iio-throughput-rw-affinity-v2-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-rw-affinity-v2-rc1'")
        == 1
    )
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-throughput-rw-affinity-v2-rc1'")
        == 1
    )
    assert f"{manifest_name}:candidate" in package
    for source in (builder, package):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: c1a7be84982fa4449bd7070084fa0389f9f90cfa" in manifest
    assert "submodule_buildroot: b5026fc3f23227afd9cf9fbffcb0b971d9d47859" in manifest


def test_iio_throughput_sampler_poll_v3_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-sampler-poll-v3-fw"
    manifest_name = "iio-throughput-sampler-poll-v3-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-sampler-poll-v3-rc1'")
        == 1
    )
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-throughput-sampler-poll-v3-rc1'")
        == 1
    )
    assert f"{manifest_name}:candidate" in package
    for source in (builder, package):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "metadata_source: 195d4c4f140009e93c282522a686bfad6b8718b6" in manifest
    assert "submodule_buildroot: 3674741f33623c32e6d29f05f219185af28285a6" in manifest


def test_iio_throughput_refill_sampler_v4_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-refill-sampler-v4-fw"
    manifest_name = "iio-throughput-refill-sampler-v4-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-refill-sampler-v4-rc1'")
        == 1
    )
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-throughput-refill-sampler-v4-rc1'")
        == 1
    )
    assert f"{manifest_name}:candidate" in package
    for source in (builder, package):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: d8e8688eaf6be16da9a0c9d92b7e8f49e0a3b334" in manifest
    assert "metadata_source: 195d4c4f140009e93c282522a686bfad6b8718b6" in manifest
    assert "submodule_buildroot: 8da0894c88e5a618b0bf9191c1fc0f2102a5d115" in manifest


def test_iio_throughput_sampler_wake_v5_has_an_exact_protected_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-sampler-wake-v5-fw"
    manifest_name = "iio-throughput-sampler-wake-v5-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-sampler-wake-v5-rc1'")
        == 1
    )
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-throughput-sampler-wake-v5-rc1'")
        == 1
    )
    assert f"{manifest_name}:candidate" in package
    for source in (builder, package):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: d8e8688eaf6be16da9a0c9d92b7e8f49e0a3b334" in manifest
    assert "metadata_source: 3294365ff44da26b261be4a2ccb241b7896d23ad" in manifest
    assert "submodule_buildroot: 9222c97347334ba1eadf5580faeb3a1093246f46" in manifest


def test_iio_throughput_coverage_window_v6_has_candidate_and_main_routes() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-coverage-window-v6-fw"
    manifest_name = "iio-throughput-coverage-window-v6-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 2
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-coverage-window-v6'") == 1
    )
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-coverage-window-v6-rc1'")
        == 1
    )
    assert (
        workflow.count(
            "'v0.45-plutoplus-spf-iio-throughput-coverage-window-v6-rc1'"
        )
        == 1
    )
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-throughput-coverage-window-v6'")
        == 1
    )
    assert "Require the exact final release identity" in workflow
    assert f"{manifest_name}:candidate" in package
    assert f"{manifest_name}:final-release" in package
    assert f"./scripts/check_source_graph.sh manifests/{manifest_name}" in checker
    for source in (builder, package, checker):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: 6ba402481fc5a17464460cef79628cb42019fb12" in manifest
    assert "metadata_source: 3294365ff44da26b261be4a2ccb241b7896d23ad" in manifest
    assert (
        "submodule_buildroot: b3b02cb8cd505972333a65be3962b131de2bc270"
        in manifest
    )


def test_wide_metadata_dma_uses_the_qualified_fit_strategy() -> None:
    block_design = (ROOT / "hdl" / "projects" / "pluto" / "system_bd.tcl").read_text()
    project = (ROOT / "hdl" / "projects" / "pluto" / "system_project.tcl").read_text()

    assert "CONFIG.DMA_LENGTH_WIDTH 26" in block_design
    assert "Flow_AreaOptimized_high" in project
    assert "STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD 4" in project


def test_rx_timestamp_fifo_resets_with_the_reconfigurable_adc_clock() -> None:
    block_design = (ROOT / "hdl" / "projects" / "pluto" / "system_bd.tcl").read_text()
    timestamp = (
        ROOT
        / "hdl-quantulum"
        / "util_cpack2_timestamp"
        / "src"
        / "util_cpack2_timestamp.v"
    ).read_text()

    assert "ad_connect axi_ad9361/rst cpack_timestamp/reset" in block_design
    assert ".rst(fifo_reset)" in timestamp
    assert ".rst('b0)" not in timestamp
    assert "if (!timestamp_en || fifo_rd_rst_busy)" in timestamp
    reset_hold = (
        ROOT / "hdl-quantulum" / "util_cpack2_timestamp" / "src" / "rx_fifo_reset.v"
    ).read_text()
    assert 'shreg_extract = "yes", srl_style = "srl"' in reset_hold
    assert "reset_delay <= {reset_delay[3:0], reset}" in reset_hold


def test_release_authorizing_entry_points_require_owner_review() -> None:
    owners = (ROOT / ".github" / "CODEOWNERS").read_text().splitlines()
    required = {
        "/scripts/check_tandem_release_offline.sh @misko",
        "/scripts/run_tandem_agc_ooc.sh @misko",
        "/scripts/validate_tandem_agc_ooc.py @misko",
        "/scripts/validate_integrated_release.py @misko",
        "/scripts/tandem_release_evidence.py @misko",
        "/scripts/tandem_release_device_plan.py @misko",
        "/scripts/deploy_tandem_agc_ram_hardware.sh @misko",
        "/scripts/run_tandem_agc_release_hardware.sh @misko",
        "/scripts/run_muted_metadata_batch_lifecycle_hardware.sh @misko",
        "/scripts/run_stale_small_adc_hardware.sh @misko",
        "/tests/radio_hardware/candidate_binding.py @misko",
        "/tests/radio_hardware/pluto_plus_candidate.py @misko",
        "/tests/radio_hardware/tandem_ram_deploy.py @misko",
        "/tests/radio_hardware/release_cli.py @misko",
        "/tests/radio_hardware/muted_metadata_batch_lifecycle.py @misko",
        "/tests/radio_hardware/stale_small_adc_hardware.py @misko",
    }
    assert required <= set(owners)


def test_pr_workflow_uses_the_shared_offline_entry_point() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware.yml").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()

    assert "check_tandem_release_offline.sh oracles" in workflow
    assert "check_tandem_release_offline.sh source-graph" in workflow
    for required in (
        "tests/test_release_oracles.py",
        "tests/test_tandem_release_evidence.py",
        "tests/test_validate_integrated_release.py",
        "tests/radio_hardware",
        "./hdl-tandem/run_tests.sh",
        "manifests/tandem-agc-v8-rc5-source.yaml",
        "manifests/tandem-agc-v8-rc6-source.yaml",
        "manifests/tandem-agc-v8-rc7-source.yaml",
        "manifests/tandem-agc-v8-rc8-source.yaml",
        "manifests/tandem-agc-v8-rc9-source.yaml",
        "manifests/tandem-agc-v8-rc10-source.yaml",
        "manifests/tandem-agc-v8-rc11-source.yaml",
        "manifests/tandem-agc-v8-rc12-source.yaml",
        "manifests/tandem-agc-v8-rc13-source.yaml",
        "manifests/tandem-agc-v8-rc14-source.yaml",
        "manifests/tandem-agc-v8-rc15-source.yaml",
        "manifests/tandem-agc-v8-rc16-source.yaml",
        "manifests/tandem-agc-v8-rc17-source.yaml",
        "manifests/tandem-agc-v8-rc18-source.yaml",
        "manifests/tandem-agc-v8-rc19-source.yaml",
        "manifests/tandem-agc-v8-rc20-source.yaml",
        "manifests/tandem-agc-v8-rc21-source.yaml",
        "manifests/tandem-agc-v8-rc22-source.yaml",
        "manifests/tandem-agc-v8-rc23-source.yaml",
        "manifests/tandem-agc-v8-rc24-source.yaml",
        "manifests/tandem-agc-v8-rc25-source.yaml",
        "manifests/tandem-agc-v8-rc26-source.yaml",
        "manifests/tandem-agc-v8-rc27-source.yaml",
        "manifests/tandem-agc-v8-rc28-source.yaml",
        "manifests/tandem-agc-v8-rc29-source.yaml",
        "manifests/tandem-agc-v8-rc30-source.yaml",
        "manifests/tandem-agc-v8-rc31-source.yaml",
        "manifests/tandem-agc-v8-rc32-source.yaml",
        "./scripts/test_legal_info_network.sh",
    ):
        assert required in checker
