"""Offline oracles for the protected tandem AGC v8 RC11 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC9_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc9-source.yaml"
RC10_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc10-source.yaml"
RC11_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc11-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"
RELEASING = ROOT / "RELEASING.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
RELEASE_PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN_RUNNER = ROOT / "KALMAN_GITHUB_RUNNER.md"
TANDEM_CORE = ROOT / "hdl-tandem" / "tandem_agc_core.v"
DEPLOYER = ROOT / "tests" / "radio_hardware" / "tandem_ram_deploy.py"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc11_reuses_only_the_reviewed_rc10_external_source_graph() -> None:
    rc9 = _manifest_values(RC9_MANIFEST)
    rc10 = _manifest_values(RC10_MANIFEST)
    rc11 = _manifest_values(RC11_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc11 == rc10 == rc9 == final
    assert rc11["schema"] == "plutosdr-fw.source-manifest"
    assert rc11["schema_version"] == "1"
    assert rc11["release_state"] == "candidate"
    assert "release_tag" not in rc11


def test_rc11_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc11"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc11-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc11'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc11'") == 1
    assert "Require the exact protected RC11 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc10-source.yaml")


def test_rc11_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc11-source.yaml"
    ) in checker


def test_rc11_keeps_the_two_reviewed_slice_relief_mappings() -> None:
    core = TANDEM_CORE.read_text(encoding="utf-8")

    assert '(* use_dsp = "yes" *) reg [19:0] pwr_div;' in core
    assert '(* use_dsp = "yes" *) reg [31:0] evt_seq;' in core
    assert core.count('(* use_dsp = "yes" *)') == 2


def test_rc11_dfu_exception_is_exactly_prebound_b674_only() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")

    assert "def resolve_dfu_device(" in deployer
    assert "device.vendor_id == USB_VENDOR" in deployer
    assert "device.product_id == DFU_PRODUCT" in deployer
    assert "device.topology == topology" in deployer
    assert "if device.serial and device.serial != serial:" in deployer
    assert "DFU USB serial differs from the pre-attested radio" in deployer
    assert "if product_id == DFU_PRODUCT:" in deployer


def test_rc11_bundle_upload_does_not_require_github_attestation() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")

    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow


def test_kalman_handoff_keeps_the_shared_bundle_checksum_contract() -> None:
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner


def test_rc11_docs_preserve_rc10_incident_and_the_burned_rc11_lock() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    rc10_lock = "refs/tags/tandem-agc-v8-rc10-source/firmware-v1"
    rc11_lock = "refs/tags/tandem-agc-v8-rc11-source/firmware-v1"
    rc12_lock = "refs/tags/tandem-agc-v8-rc12-source/firmware-v1"
    rc13_lock = "refs/tags/tandem-agc-v8-rc13-source/firmware-v1"
    final_lock = "refs/tags/tandem-agc-v8-source/firmware-v1"

    assert "The active candidate is RC31" in releasing
    for source in (releasing, notes, plan):
        assert rc10_lock in source
        assert rc11_lock in source
        assert rc12_lock in source
        assert rc13_lock in source
    assert final_lock in releasing
    assert "repeat the full four-radio campaign" in releasing
    assert 'gh attestation verify "$release_work"' not in releasing

    assert "32964460396" in notes
    assert "before any `dfu-util -D`" in notes
    assert "zero candidate deployments" in notes
    assert "persistent RC1" in notes

    assert "exact_main_commit='<40-character-exact-main-commit>'" in plan
    assert 'git tag tandem-agc-v8-source/firmware-v1 "$exact_main_commit"' in plan
    assert "The v8 policy always\nselects `full-campaign`." in plan
