"""Offline release-process regressions that need no firmware toolchain."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_LIB = ROOT / "scripts" / "ci" / "source_manifest_lib.sh"
RC2_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc2-source.yaml"
RC3_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc3-source.yaml"
FINAL_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
TANDEM_V2_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v2-source.yaml"
FIRMWARE_MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
FIRMWARE_PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
QUALITY_HARDWARE_LAUNCHER = ROOT / "scripts" / "run_tandem_agc_quality_hardware.sh"

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


def test_rc3_advances_only_libiio_buildroot_and_linux_and_is_final() -> None:
    rc2 = _manifest_values(RC2_SOURCE_MANIFEST)
    rc3 = _manifest_values(RC3_SOURCE_MANIFEST)
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

    assert rc3 == final
    assert "release_tag" not in rc3
    for values in (rc3, final):
        assert values["libiio_0_25_source"] == RC3_LIBIIO_SOURCE
        assert values["libiio_0_25_ref"] == RC3_LIBIIO_REF
        assert values["submodule_buildroot"] == RC3_BUILDROOT_SOURCE
        assert values["submodule_buildroot_ref"] == RC3_BUILDROOT_REF
        assert values["versions_buildroot"] == RC3_BUILDROOT_IDENTITY
    for values in (rc3, final, tandem_v2):
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


def test_rc3_has_explicit_trusted_build_and_pr_source_graph_routes() -> None:
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc3"
    main_workflow = FIRMWARE_MAIN_WORKFLOW.read_text(encoding="utf-8")
    pr_workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    launcher = QUALITY_HARDWARE_LAUNCHER.read_text(encoding="utf-8")

    assert main_workflow.count(branch) == 3
    assert "tandem-agc-v8-rc3-source.yaml" in main_workflow
    assert "plutoplus-spf-tandem-agc-v8-rc3" in main_workflow
    for manifest in (
        "manifests/tandem-agc-v8-rc3-source.yaml",
        "manifests/tandem-agc-v8-source.yaml",
    ):
        assert f"./scripts/check_source_graph.sh {manifest}" in pr_workflow
    assert "manifests/tandem-agc-v8-rc3-source.yaml" in launcher


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
    assert "./run_timestamp_check_pipeline.sh" in workflow


def test_required_pr_gate_runs_root_tandem_rtl_suite() -> None:
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")

    assert "iverilog python3-numpy python3-pytest" in workflow
    assert "./hdl-tandem/run_tests.sh" in workflow


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
