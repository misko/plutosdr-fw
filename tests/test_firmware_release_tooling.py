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


def test_ddr_burst_v2_has_exact_candidate_and_main_routes() -> None:
    workflow = (ROOT / ".github" / "workflows" / "firmware-main.yml").read_text()
    builder = (ROOT / "scripts" / "build_gain_series_candidate.sh").read_text()
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    checker = (ROOT / "scripts" / "check_tandem_release_offline.sh").read_text()
    branch = "refs/heads/codex/ddr-burst-v2"

    assert workflow.count(branch) == 4
    assert workflow.count("'ddr-burst-v2-rc1-source.yaml'") == 2
    assert workflow.count("'plutoplus-spf-ddr-burst-v2'") == 1
    assert workflow.count("'plutoplus-spf-ddr-burst-v2-rc1'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-ddr-burst-v2'") == 1
    assert workflow.count("'v0.42-plutoplus-spf-ddr-burst-v2-rc1'") == 1
    assert "Require the exact DDR burst v2 RC1 candidate identity" in workflow
    assert "ddr-burst-v2-rc1-source.yaml:candidate" in package
    for source in (builder, package, checker):
        assert "ddr-burst-v2-rc1-source.yaml" in source


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
