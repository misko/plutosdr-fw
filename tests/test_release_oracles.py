"""Offline release-process regressions that need no firmware toolchain."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_LIB = ROOT / "scripts" / "ci" / "source_manifest_lib.sh"
RC2_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc2-source.yaml"
RC3_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc3-source.yaml"
RC4_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc4-source.yaml"
RC5_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc5-source.yaml"
RC6_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc6-source.yaml"
RC7_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc7-source.yaml"
RC8_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc8-source.yaml"
RC9_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc9-source.yaml"
RC10_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc10-source.yaml"
RC11_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc11-source.yaml"
RC12_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc12-source.yaml"
RC13_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc13-source.yaml"
RC14_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc14-source.yaml"
RC15_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc15-source.yaml"
RC16_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc16-source.yaml"
RC17_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc17-source.yaml"
RC18_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc18-source.yaml"
RC19_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc19-source.yaml"
RC20_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc20-source.yaml"
RC21_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc21-source.yaml"
RC22_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc22-source.yaml"
RC23_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc23-source.yaml"
RC24_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc24-source.yaml"
RC25_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc25-source.yaml"
RC26_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc26-source.yaml"
RC27_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc27-source.yaml"
RC28_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc28-source.yaml"
RC29_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc29-source.yaml"
RC30_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc30-source.yaml"
RC31_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc31-source.yaml"
RC32_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc32-source.yaml"
FINAL_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
DDR_BURST_RC5_SOURCE_MANIFEST = (
    ROOT / "manifests" / "ddr-burst-v1-rc5-source.yaml"
)
DDR_BURST_V2_RC1_SOURCE_MANIFEST = (
    ROOT / "manifests" / "ddr-burst-v2-rc1-source.yaml"
)
DDR_BURST_V2_RC2_SOURCE_MANIFEST = (
    ROOT / "manifests" / "ddr-burst-v2-rc2-source.yaml"
)
TANDEM_V2_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v2-source.yaml"
FIRMWARE_MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
FIRMWARE_PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
QUALITY_HARDWARE_LAUNCHER = ROOT / "scripts" / "run_tandem_agc_quality_hardware.sh"
TANDEM_OOC_LAUNCHER = ROOT / "scripts" / "run_tandem_agc_ooc.sh"
TANDEM_OOC_TCL = ROOT / "hdl-tandem" / "axi_ooc.tcl"
TANDEM_OOC_VALIDATOR = ROOT / "scripts" / "validate_tandem_agc_ooc.py"
TANDEM_OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"

RC3_LIBIIO_SOURCE = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
RC3_LIBIIO_REF = "refs/tags/tandem-agc-v8-rc3-source/libiio-v1"
RC3_BUILDROOT_SOURCE = "f89eb67b2c0131640ae9c9e0f0be46da000f3e37"
RC3_BUILDROOT_REF = "refs/tags/tandem-agc-v8-rc3-source/buildroot-v1"
RC3_BUILDROOT_IDENTITY = "tandem-agc-v8-rc3-source/buildroot-v1"
RC3_LINUX_SOURCE = "77a1f2352162097bb983402f47c9cb4a28a2f055"
RC3_LINUX_REF = "refs/tags/tandem-agc-v2-source/linux-v11"
RC3_LINUX_IDENTITY = "tandem-agc-v2-source/linux-v11"
TANDEM_V2_LIBIIO_SOURCE = "015e4924113d4996667f80b880c34cbf7d1147de"
TANDEM_V2_LIBIIO_REF = "refs/tags/tandem-agc-v2-source/libiio-v9"
TANDEM_V2_BUILDROOT_SOURCE = "4401fe4cd17a7e02cd41e4a20c78318f389a4deb"
TANDEM_V2_BUILDROOT_REF = "refs/tags/tandem-agc-v2-source/buildroot-v7"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def _resolve(repo: Path, ref: str) -> str:
    script = f'source {SOURCE_LIB!s}; source_manifest_ref_commit "$1" "$2"'
    return subprocess.check_output(
        ["bash", "-c", script, "bash", str(repo), ref], text=True
    ).strip()


def _tag_identity(ref: str) -> str:
    script = f'source {SOURCE_LIB!s}; source_manifest_tag_identity "$1"'
    return subprocess.check_output(
        ["bash", "-c", script, "bash", ref], text=True
    ).strip()


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_source_manifest_ref_commit_peels_annotated_tag(tmp_path: Path) -> None:
    work = tmp_path / "work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.name", "release oracle", cwd=work)
    _git("config", "user.email", "oracle@example.invalid", cwd=work)
    (work / "payload").write_text("qualified\n", encoding="utf-8")
    _git("add", "payload", cwd=work)
    _git("commit", "-m", "qualified source", cwd=work)
    commit = _git("rev-parse", "HEAD", cwd=work)
    _git("tag", "-a", "v8", "-m", "annotated v8", cwd=work)
    _git("init", "--bare", str(bare), cwd=work)
    _git("remote", "add", "origin", str(bare), cwd=work)
    _git("push", "origin", "HEAD", "refs/tags/v8", cwd=work)

    assert _resolve(bare, "refs/tags/v8") == commit


def test_source_manifest_ref_commit_accepts_lightweight_tag(tmp_path: Path) -> None:
    work = tmp_path / "work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.name", "release oracle", cwd=work)
    _git("config", "user.email", "oracle@example.invalid", cwd=work)
    (work / "payload").write_text("candidate\n", encoding="utf-8")
    _git("add", "payload", cwd=work)
    _git("commit", "-m", "candidate source", cwd=work)
    commit = _git("rev-parse", "HEAD", cwd=work)
    _git("tag", "source-lock", cwd=work)
    _git("init", "--bare", str(bare), cwd=work)
    _git("remote", "add", "origin", str(bare), cwd=work)
    _git("push", "origin", "HEAD", "refs/tags/source-lock", cwd=work)

    assert _resolve(bare, "refs/tags/source-lock") == commit


def test_source_manifest_tag_identity_preserves_namespace() -> None:
    assert (
        _tag_identity("refs/tags/tandem-agc-v8-rc2-source/buildroot-v1")
        == "tandem-agc-v8-rc2-source/buildroot-v1"
    )


def test_final_packed_identities_match_declared_source_lock_tags() -> None:
    values = _manifest_values(FINAL_SOURCE_MANIFEST)
    mappings = {
        "versions_hdl": "submodule_hdl_ref",
        "versions_buildroot": "submodule_buildroot_ref",
        "versions_linux": "submodule_linux_ref",
        "versions_u_boot_xlnx": "submodule_u_boot_xlnx_ref",
    }

    for identity_key, ref_key in mappings.items():
        assert values[identity_key] == _tag_identity(values[ref_key])


def test_rc3_advances_dependencies_and_rc4_reuses_them_for_top_rtl_fix() -> None:
    rc2 = _manifest_values(RC2_SOURCE_MANIFEST)
    rc3 = _manifest_values(RC3_SOURCE_MANIFEST)
    rc4 = _manifest_values(RC4_SOURCE_MANIFEST)
    rc5 = _manifest_values(RC5_SOURCE_MANIFEST)
    rc6 = _manifest_values(RC6_SOURCE_MANIFEST)
    rc7 = _manifest_values(RC7_SOURCE_MANIFEST)
    rc8 = _manifest_values(RC8_SOURCE_MANIFEST)
    rc9 = _manifest_values(RC9_SOURCE_MANIFEST)
    rc10 = _manifest_values(RC10_SOURCE_MANIFEST)
    rc11 = _manifest_values(RC11_SOURCE_MANIFEST)
    rc12 = _manifest_values(RC12_SOURCE_MANIFEST)
    rc13 = _manifest_values(RC13_SOURCE_MANIFEST)
    rc14 = _manifest_values(RC14_SOURCE_MANIFEST)
    rc15 = _manifest_values(RC15_SOURCE_MANIFEST)
    rc16 = _manifest_values(RC16_SOURCE_MANIFEST)
    rc17 = _manifest_values(RC17_SOURCE_MANIFEST)
    rc18 = _manifest_values(RC18_SOURCE_MANIFEST)
    rc19 = _manifest_values(RC19_SOURCE_MANIFEST)
    rc20 = _manifest_values(RC20_SOURCE_MANIFEST)
    rc21 = _manifest_values(RC21_SOURCE_MANIFEST)
    rc22 = _manifest_values(RC22_SOURCE_MANIFEST)
    rc23 = _manifest_values(RC23_SOURCE_MANIFEST)
    rc24 = _manifest_values(RC24_SOURCE_MANIFEST)
    rc25 = _manifest_values(RC25_SOURCE_MANIFEST)
    rc26 = _manifest_values(RC26_SOURCE_MANIFEST)
    rc27 = _manifest_values(RC27_SOURCE_MANIFEST)
    rc28 = _manifest_values(RC28_SOURCE_MANIFEST)
    rc29 = _manifest_values(RC29_SOURCE_MANIFEST)
    rc30 = _manifest_values(RC30_SOURCE_MANIFEST)
    rc31 = _manifest_values(RC31_SOURCE_MANIFEST)
    rc32 = _manifest_values(RC32_SOURCE_MANIFEST)
    final = _manifest_values(FINAL_SOURCE_MANIFEST)
    tandem_v2 = _manifest_values(TANDEM_V2_SOURCE_MANIFEST)
    changed_component_keys = {
        "libiio_0_25_source",
        "libiio_0_25_ref",
        "submodule_buildroot",
        "submodule_buildroot_ref",
        "submodule_linux",
        "submodule_linux_ref",
    }
    packed_identity_keys = {
        "versions_hdl",
        "versions_buildroot",
        "versions_linux",
        "versions_u_boot_xlnx",
    }

    assert set(rc3) - set(rc2) == packed_identity_keys
    assert set(rc2) - set(rc3) == set()
    assert {
        key for key, value in rc2.items() if rc3[key] != value
    } == changed_component_keys

    assert (
        rc3
        == rc4
        == rc5
        == rc6
        == rc7
        == rc8
        == rc9
        == rc10
        == rc11
        == rc12
        == rc13
        == rc14
        == rc15
        == rc16
        == rc17
        == rc18
        == rc19
        == rc20
        == rc21
        == rc22
        == rc23
        == rc24
        == rc25
        == rc26
        == rc27
        == rc28
        == rc29
        == rc30
        == rc31
        == rc32
        == final
    )
    for values in (
        rc3,
        rc4,
        rc5,
        rc6,
        rc7,
        rc8,
        rc9,
        rc10,
        rc11,
        rc12,
        rc13,
        rc14,
        rc15,
        rc16,
        rc17,
        rc18,
        rc19,
        rc20,
        rc21,
        rc22,
        rc23,
        rc24,
        rc25,
        rc26,
        rc27,
        rc28,
        rc29,
        rc30,
        rc31,
        final,
    ):
        assert "release_tag" not in values
        assert values["libiio_0_25_source"] == RC3_LIBIIO_SOURCE
        assert values["libiio_0_25_ref"] == RC3_LIBIIO_REF
        assert values["submodule_buildroot"] == RC3_BUILDROOT_SOURCE
        assert values["submodule_buildroot_ref"] == RC3_BUILDROOT_REF
        assert values["versions_buildroot"] == RC3_BUILDROOT_IDENTITY
    for values in (
        rc3,
        rc4,
        rc5,
        rc6,
        rc7,
        rc8,
        rc9,
        rc10,
        rc11,
        rc12,
        rc13,
        rc14,
        rc15,
        rc16,
        rc17,
        rc18,
        rc19,
        rc20,
        rc21,
        rc22,
        rc23,
        rc24,
        rc25,
        rc26,
        rc27,
        rc28,
        rc29,
        rc30,
        rc31,
        final,
        tandem_v2,
    ):
        assert values["submodule_linux"] == RC3_LINUX_SOURCE
        assert values["submodule_linux_ref"] == RC3_LINUX_REF
    assert rc3["versions_linux"] == RC3_LINUX_IDENTITY
    assert final["versions_linux"] == RC3_LINUX_IDENTITY


def test_tandem_v2_preserves_historical_transport_but_prevents_linux_rollback() -> None:
    tandem_v2 = _manifest_values(TANDEM_V2_SOURCE_MANIFEST)

    assert tandem_v2["libiio_0_25_source"] == TANDEM_V2_LIBIIO_SOURCE
    assert tandem_v2["libiio_0_25_ref"] == TANDEM_V2_LIBIIO_REF
    assert tandem_v2["submodule_buildroot"] == TANDEM_V2_BUILDROOT_SOURCE
    assert tandem_v2["submodule_buildroot_ref"] == TANDEM_V2_BUILDROOT_REF
    assert tandem_v2["submodule_linux"] == RC3_LINUX_SOURCE
    assert tandem_v2["submodule_linux_ref"] == RC3_LINUX_REF


def test_ddr_burst_v2_advances_only_libiio_and_buildroot() -> None:
    previous = _manifest_values(DDR_BURST_RC5_SOURCE_MANIFEST)
    current = _manifest_values(DDR_BURST_V2_RC1_SOURCE_MANIFEST)
    changed = {key for key, value in previous.items() if current[key] != value}

    assert changed == {
        "libiio_0_25_source",
        "libiio_0_25_ref",
        "submodule_buildroot",
        "submodule_buildroot_ref",
        "versions_buildroot",
    }
    assert current["libiio_0_25_source"] == (
        "45a760d4000a044fc3709b5d89bceec5d0883be5"
    )
    assert current["submodule_buildroot"] == (
        "707a0fd23ad6551db5a91a79c4e61de55bec798f"
    )
    assert "release_tag" not in current


def test_ddr_burst_v2_rc2_advances_only_libiio_and_buildroot() -> None:
    previous = _manifest_values(DDR_BURST_V2_RC1_SOURCE_MANIFEST)
    current = _manifest_values(DDR_BURST_V2_RC2_SOURCE_MANIFEST)
    changed = {key for key, value in previous.items() if current[key] != value}

    assert changed == {
        "libiio_0_25_source",
        "libiio_0_25_ref",
        "submodule_buildroot",
        "submodule_buildroot_ref",
        "versions_buildroot",
    }
    assert current["libiio_0_25_source"] == (
        "79419a85f5fa239dc1cb54a5122292d9876b1b1a"
    )
    assert current["submodule_buildroot"] == (
        "9211a3a642df608b2556eebb2e7a63b1d7e71cab"
    )
    assert "release_tag" not in current


def test_historical_routes_and_all_v8_source_graphs_are_explicit() -> None:
    main_workflow = FIRMWARE_MAIN_WORKFLOW.read_text(encoding="utf-8")
    pr_workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    offline_check = TANDEM_OFFLINE_CHECK.read_text(encoding="utf-8")
    launcher = QUALITY_HARDWARE_LAUNCHER.read_text(encoding="utf-8")

    for candidate in ("rc3", "rc4"):
        branch = f"refs/heads/codex/firmware-tandem-agc-v8-{candidate}"
        assert main_workflow.count(f"{branch}'") == 3
        assert f"tandem-agc-v8-{candidate}-source.yaml" in main_workflow
        assert f"plutoplus-spf-tandem-agc-v8-{candidate}" in main_workflow
    for manifest in (
        "manifests/tandem-agc-v8-rc3-source.yaml",
        "manifests/tandem-agc-v8-rc4-source.yaml",
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
        "manifests/tandem-agc-v8-source.yaml",
    ):
        assert f"./scripts/check_source_graph.sh {manifest}" in offline_check
    assert "./scripts/check_tandem_release_offline.sh source-graph" in pr_workflow
    assert "manifests/tandem-agc-v8-rc4-source.yaml" in launcher


def test_required_hdl_simulation_uses_final_timestamp_source() -> None:
    values = _manifest_values(FINAL_SOURCE_MANIFEST)
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    checkout = re.search(
        r"repository:\s*misko/plutosdr-hdl-quantulum\s*\n\s*"
        r"ref:\s*([0-9a-f]{40})",
        workflow,
    )

    assert checkout is not None
    assert checkout.group(1) == values["submodule_hdl_quantulum"]
    assert "cd hdl-quantulum-final/util_upack2_timestamp/test" in workflow
    assert "./run_timestamp_check_pipeline.sh" in workflow


def test_required_hdl_simulation_uses_ddr_burst_rc5_timestamp_source() -> None:
    values = _manifest_values(DDR_BURST_RC5_SOURCE_MANIFEST)
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    checkouts = re.findall(
        r"repository:\s*misko/plutosdr-hdl-quantulum\s*\n\s*"
        r"ref:\s*([0-9a-f]{40})",
        workflow,
    )

    assert values["submodule_hdl_quantulum"] in checkouts
    assert "cd hdl-quantulum/util_cpack2_timestamp/src" in workflow
    assert "rx_fifo_reset.v rx_fifo_reset_tb.v" in workflow
    assert "grep -F 'srl_style = \"srl\"' rx_fifo_reset.v" in workflow


def test_required_pr_gate_runs_root_tandem_rtl_suite() -> None:
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    offline_check = TANDEM_OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "iverilog python3-numpy python3-pytest" in workflow
    assert "git submodule update --init --depth 1 hdl hdl-quantulum linux" in workflow
    assert "./scripts/check_tandem_release_offline.sh oracles" in workflow
    assert "tests/test_tandem_agc_ooc_validator.py" in offline_check
    assert "./hdl-tandem/run_tests.sh" in offline_check


def test_tandem_ooc_gate_is_exact_routed_and_fail_closed() -> None:
    launcher = TANDEM_OOC_LAUNCHER.read_text(encoding="utf-8")
    tcl = TANDEM_OOC_TCL.read_text(encoding="utf-8")
    validator = TANDEM_OOC_VALIDATOR.read_text(encoding="utf-8")

    assert launcher.splitlines()[0] == "#!/bin/bash -p"
    assert TANDEM_OOC_LAUNCHER.stat().st_mode & 0o111
    assert not (ROOT / "hdl-tandem" / "core_ooc.tcl").exists()
    assert not (ROOT / "hdl-tandem" / "cdc_ooc.tcl").exists()
    assert "plutosdr-fw-tandem-agc-v1" not in tcl
    assert "/tmp/" not in tcl
    assert "/home/" not in tcl
    assert "synth_design -top $top -part $part -mode out_of_context" in tcl
    assert "production event parameter is not exact" in tcl
    for default in (
        "EVT_AW[ \\t]*=[ \\t]*6,",
        "EVT_DW[ \\t]*=[ \\t]*128,",
        "EVENTS[ \\t]*=[ \\t]*1[ \\t]*$",
    ):
        assert default in tcl
    for command in (
        "place_design",
        "route_design",
        "report_timing_summary -delay_type min_max",
        "report_cdc -no_waiver",
        "report_cdc -details -no_waiver",
        "report_route_status",
        "report_drc -ruledeck default -no_waivers",
        "report_methodology -no_waivers",
        "get_msg_config -count -severity {CRITICAL WARNING}",
        "get_msg_config -count -severity ERROR",
        "=== TANDEM AXI ROUTE COMPLETE ===",
    ):
        assert command in tcl
    assert "get_msg_config -count -severity FATAL" not in tcl
    assert "=== TANDEM AXI ROUTED OOC PASS ===" not in tcl

    for binding in (
        "SW Build 3671981",
        "IP Build 3669848",
        "EXPECTED_SETTINGS_SHA256=",
        "EXPECTED_VIVADO_SHA256=",
        "EXPECTED_SETUP_ENV_SHA256=",
        "EXPECTED_VIVADO_BINARY_SHA256=",
        "EXPECTED_LOADER_SHA256=",
        "EXPECTED_RDI_ARGS_SHA256=",
        "EXPECTED_LDLIBPATH_SHA256=",
        "EXPECTED_LIBEDIT_SHA256=",
        "EXPECTED_LIBTINFO_SHA256=",
        "git_exact show",
        "validate_tandem_agc_ooc.py",
        "/usr/bin/python3 -I -B",
        "evidence_manifest_sha256=",
        "verdict=PASS",
        "firmware_release_eligible=false",
        "integrated_route_required=true",
        "routed checkpoint size is outside the bounded 512 KiB..16 MiB range",
        'dcp_magic" == "50 4b 03 04"',
    ):
        assert binding in launcher
    assert launcher.index("=== TANDEM AXI ROUTE COMPLETE ===") < launcher.index(
        "verdict=PASS"
    )
    assert launcher.index("validate_tandem_agc_ooc.py") < launcher.index(
        "evidence-sha256.txt"
    )
    final_status_claim = (
        'ln -- "$run_ref/status.txt" "/proc/$$/fd/$output_fd/status.txt"'
    )
    assert launcher.count(final_status_claim) == 1
    assert '"$output_ref/status.txt"' not in launcher
    assert '"$output_dir/status.txt"' not in launcher
    assert launcher.count("$run_ref/status.txt") == 3
    assert launcher.count('"/proc/$$/fd/$output_fd/status.txt"') == 1
    assert launcher.count("status.txt") == 5
    assert launcher.count("/usr/bin/python3 -I -B") == 2
    assert launcher.count('"$output_ref/input/validate_tandem_agc_ooc.py"') == 2
    assert launcher.count('--directory-fd "$output_fd"') == 2
    for final_gate in (
        "output directory identity changed during final promotion",
        "output parent identity changed during final promotion",
        "firmware HEAD changed during final promotion",
        "firmware source tree changed during final promotion",
        "OOC input changed during final promotion",
        "final staged OOC input hash inventory is not exact",
        "final OOC evidence inventory is not exact",
        "final strict routed OOC report validation failed",
        "sha256sum -c evidence-sha256.txt",
        "output directory identity changed immediately before status claim",
    ):
        assert final_gate in launcher
    commands = [
        line.strip()
        for line in launcher.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert commands[-1] == final_status_claim

    for exact_inventory in (
        '"CDC-3": ("Info", 5,',
        '"CDC-6": ("Warning", 2,',
        '"CDC-15": ("Warning", 133,',
        '"REQP-1839": ("Warning", "RAMB36 async control check", 18)',
        '"ZPS7-1": ("Warning", "PS7 block required", 1)',
        '"LUTAR-1": ("Warning", "LUT drives async reset alert", 1)',
        '"TIMING-18": ("Warning", "Missing input or output delay", 182)',
        '"no_input_delay": 137',
        '"no_output_delay": 45',
        '"Slice LUTs": (17600, 1, 17600)',
        '"Slice Registers": (35200, 1, 35200)',
        '"Block RAM Tile": (60, 2, 2)',
        '"DSPs": (80, 0, 80)',
    ):
        assert exact_inventory in validator


def test_tandem_ooc_launcher_ignores_exported_shell_functions() -> None:
    environment = {
        "PATH": "/usr/bin:/bin",
        "BASH_FUNC_stat%%": '() { printf "%s\\n" FORGED-STAT; }',
    }
    result = subprocess.run(
        ["/bin/bash", "-p", "-c", "type stat"],
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    )

    assert "stat is /usr/bin/stat" in result.stdout
    assert "function" not in result.stdout


def test_tandem_ooc_default_check_ignores_verilog_comment_decoys(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "hdl-tandem"
    staged.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    for name in (
        "axi_ooc.tcl",
        "tandem_cdc_lib.v",
        "tandem_agc_core.v",
        "tandem_agc_axi.v",
        "tandem_agc_axi.xdc",
    ):
        (staged / name).write_bytes((ROOT / "hdl-tandem" / name).read_bytes())

    def early_tcl_result() -> str:
        wrapper = f"""
set argc 1
set argv [list {{{output}}}]
proc create_project {{args}} {{error STOP_AFTER_DEFAULT_CHECK}}
if {{[catch {{source {{{staged / "axi_ooc.tcl"}}}}} message]}} {{
  puts $message
  exit 0
}}
exit 3
"""
        return subprocess.check_output(
            ["tclsh"], input=wrapper, text=True, stderr=subprocess.STDOUT
        ).strip()

    assert early_tcl_result() == "STOP_AFTER_DEFAULT_CHECK"
    axi = staged / "tandem_agc_axi.v"
    source = axi.read_text(encoding="utf-8")
    live = "parameter integer EVT_AW = 6,"
    assert source.count(live) == 1
    axi.write_text(
        "/* parameter integer EVT_AW = 6, */\n"
        + source.replace(live, "parameter integer EVT_AW = 64,"),
        encoding="utf-8",
    )
    assert early_tcl_result() == "production event parameter is not exact: EVT_AW"


def test_required_usb_gadget_job_uses_final_source_and_complete_suite() -> None:
    values = _manifest_values(FINAL_SOURCE_MANIFEST)
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    usb_job = re.search(
        r"- name: Check out pinned USB gadget source(?P<body>.*?)"
        r"- name: Build and test the direct-IP implementation",
        workflow,
        flags=re.DOTALL,
    )

    assert usb_job is not None
    body = usb_job.group("body")
    checkout = re.search(
        r"repository:\s*misko/plutosdr-fw\s*\n\s*"
        r"ref:\s*([0-9a-f]{40})",
        body,
    )
    asserted_count = re.search(
        r'test "\$\{count:-0\}" -eq ([0-9]+)',
        body,
    )

    assert checkout is not None
    assert checkout.group(1) == values["gadget_source"]
    assert "ctest --test-dir usb-gadget/build-tests --output-on-failure" in body
    assert asserted_count is not None

    cmake = _git("show", f"{values['gadget_source']}:CMakeLists.txt", cwd=ROOT)
    suite_count = len(re.findall(r"(?m)^\s*add_test\s*\(", cmake))
    assert suite_count > 0
    assert int(asserted_count.group(1)) == suite_count
