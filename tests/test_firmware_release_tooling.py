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
    assert "iio-throughput-coverage-window-v6-rc1-source.yaml:candidate" in package
    assert "iio-throughput-coverage-window-v6-rc1-source.yaml:final-release" in package
    assert "iio-gain-timeline-v8-rc1-source.yaml:candidate" in package
    assert "iio-gain-timeline-v8-rc1-source.yaml:final-release" in package
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


def test_iio_throughput_coverage_window_v6_keeps_its_candidate_route() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/iio-throughput-coverage-window-v6-fw"
    manifest_name = "iio-throughput-coverage-window-v6-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 1
    assert (
        workflow.count("'plutoplus-spf-iio-throughput-coverage-window-v6'") == 0
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
        == 0
    )
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


def test_iio_gain_timeline_v8_has_candidate_and_main_routes() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    wrapper = (ROOT / "scripts" / "deploy_tandem_agc_ram_hardware.sh").read_text()
    planner = (ROOT / "scripts" / "tandem_release_device_plan.py").read_text()
    evidence = (ROOT / "scripts" / "tandem_release_evidence.py").read_text()
    ooc_launcher = (ROOT / "scripts" / "run_tandem_agc_ooc.sh").read_text()
    binding = (ROOT / "tests" / "radio_hardware" / "pluto_plus_candidate.py").read_text()
    branch = "refs/heads/codex/iio-gain-timeline-v8-fw"
    manifest_name = "iio-gain-timeline-v8-rc1-source.yaml"
    manifest = (ROOT / "manifests" / manifest_name).read_text()

    assert workflow.count(branch) == 4
    assert workflow.count(f"'{manifest_name}'") == 2
    assert workflow.count("'plutoplus-spf-iio-gain-timeline-v8'") == 1
    assert workflow.count("'plutoplus-spf-iio-gain-timeline-v8-rc1'") == 1
    assert (
        workflow.count("'v0.45-plutoplus-spf-iio-gain-timeline-v8-rc1'")
        == 1
    )
    assert workflow.count("'v0.45-plutoplus-spf-iio-gain-timeline-v8'") == 1
    assert "Require the exact IIO gain timeline v8 RC1 identity" in workflow
    assert "Require the exact final release identity" in workflow
    assert f"{manifest_name}:candidate" in package
    assert f"{manifest_name}:final-release" in package
    assert f"./scripts/check_source_graph.sh manifests/{manifest_name}" in checker
    for source in (builder, package, checker):
        assert manifest_name in source
    assert "release_state: candidate" in manifest
    assert "libiio_0_25_source: cd0901ccd0f521b956f58dd961943f099953ae71" in manifest
    assert "metadata_source: bbbf2f13e1a5aa7edab541e76f08afb384230d77" in manifest
    assert "submodule_buildroot: bdde66d448bd32b32e1a13ccf4278919e05e19ed" in manifest
    assert "submodule_hdl: ff17846a5d9b90c3294bdecb53eaa43617a519a7" in manifest
    assert "submodule_linux: 4b397a547f3ad35a29c9d07685be423db908f9bf" in manifest
    assert "no event at its first sample" in (ROOT / "IIO_GAIN_TIMELINE_V8_DESIGN.md").read_text()
    assert "preceding end endpoint is their input baseline" in (
        ROOT / "IIO_GAIN_TIMELINE_V8_DESIGN.md"
    ).read_text()
    tandem_axi = (ROOT / "hdl-tandem" / "tandem_agc_axi.v").read_text()
    tandem_cdc = (ROOT / "hdl-tandem" / "tandem_cdc_lib.v").read_text()
    tandem_core = (ROOT / "hdl-tandem" / "tandem_agc_core.v").read_text()
    assert "localparam integer CFGW = 135;" in tandem_axi
    assert "r_epoch, r_fault_clear, r_mode," in tandem_axi
    assert "r_epoch, 5'd0, r_fault_clear" not in tandem_axi
    assert "c_epoch       = cfg_held[134:103]" in tandem_axi
    assert "reg [28:0] r_thresholds;" in tandem_axi
    assert "wdata_q[31:16], wdata_q[13:8], wdata_q[6:0]" in tandem_axi
    assert "r_thresholds[28:13], 2'b00" in tandem_axi
    assert "r_thresholds[12:7], 1'b0, r_thresholds[6:0]" in tandem_axi
    assert "tandem_cdc_mailbox #(.W(STAW)) u_stat" in tandem_axi
    assert ".src_clk(l_clk), .src_resetn(l_resetn)" in tandem_axi
    assert ".dst_clk(s_axi_aclk), .dst_resetn(axi_resetn)" in tandem_axi
    assert "u_rst_status_l" not in tandem_axi
    assert "u_rst_status_axi" not in tandem_axi
    assert "module tandem_cdc_mailbox" in tandem_cdc
    assert '(* ram_style = "block" *)' in tandem_cdc
    assert "if (wr_resetn && wr_en && !full_r) mem[wbin[AW-1:0]] <= wr_data;" in tandem_cdc
    assert "always @(posedge wr_clk or negedge wr_resetn)" not in tandem_cdc
    assert "u_dst_ready_src" in tandem_cdc
    assert "u_src_ready_dst" in tandem_cdc
    assert "if (src_commit) mem[~src_request] <= din;" in tandem_cdc
    assert "evt_seq <= 32'd0;" in tandem_core
    assert "if (evt_push) evt_seq <= evt_seq + 32'd1;" in tandem_core
    assert "evt_seq <= 32'hFFFF_FFFF;" not in tandem_core
    utils_main = "4a9c761f3f974a96855589f7a3e867a790dce3f1"
    for source in (wrapper, binding):
        assert utils_main in source
        assert "b2b3113c2e8724453179f09d357b4917c0f14c77" not in source
    assert 'PLUTO_IIO_BUFFER_METADATA_ABI = "frame-metadata-v4"' in binding
    assert "selects authoritative buffer ABI 4" in planner
    assert "GAIN_TIMELINE_CANDIDATE_FIRMWARE_VERSION" in evidence
    assert "GAIN_TIMELINE_FINAL_FIRMWARE_VERSION" in evidence
    assert "refs/tags/iio-gain-timeline-v8-rc1-source/fw-v7" in evidence
    assert branch in evidence
    assert "git_exact rev-parse --path-format=absolute --git-common-dir" in ooc_launcher
    assert 'worktree_admin_prefix="$git_common_dir/worktrees/"' in ooc_launcher
    assert '== "$ROOT/.git"' not in ooc_launcher


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
