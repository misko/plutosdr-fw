"""Offline oracles for the protected tandem AGC v8 RC12 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC10_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc10-source.yaml"
RC11_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc11-source.yaml"
RC12_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc12-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"
RELEASING = ROOT / "RELEASING.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
RELEASE_PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN_RUNNER = ROOT / "KALMAN_GITHUB_RUNNER.md"
FLASHING = ROOT / "flashing.md"
TANDEM_CORE = ROOT / "hdl-tandem" / "tandem_agc_core.v"
DEPLOYER = ROOT / "tests" / "radio_hardware" / "tandem_ram_deploy.py"
CANDIDATE_BINDING = ROOT / "tests" / "radio_hardware" / "candidate_binding.py"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc12_reuses_only_the_reviewed_rc11_external_source_graph() -> None:
    rc10 = _manifest_values(RC10_MANIFEST)
    rc11 = _manifest_values(RC11_MANIFEST)
    rc12 = _manifest_values(RC12_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc12 == rc11 == rc10 == final
    assert rc12["schema"] == "plutosdr-fw.source-manifest"
    assert rc12["schema_version"] == "1"
    assert rc12["release_state"] == "candidate"
    assert "release_tag" not in rc12


def test_rc12_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc12"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc12-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc12'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc12'") == 1
    assert "Require the exact protected RC12 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc11-source.yaml")


def test_rc12_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc12-source.yaml"
    ) in checker


def test_rc12_keeps_the_two_reviewed_slice_relief_mappings() -> None:
    core = TANDEM_CORE.read_text(encoding="utf-8")

    assert '(* use_dsp = "yes" *) reg [19:0] pwr_div;' in core
    assert '(* use_dsp = "yes" *) reg [31:0] evt_seq;' in core
    assert core.count('(* use_dsp = "yes" *)') == 2


def test_rc12_uses_the_paired_dfu_suffix_and_runtime_selector_exactly() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    binding = CANDIDATE_BINDING.read_text(encoding="utf-8")
    flashing = FLASHING.read_text(encoding="utf-8")
    paired = "0456:b673,0456:b674"

    assert (
        'DFU_DEVICE_SELECTOR = f"{USB_VENDOR}:{RUNTIME_PRODUCT},'
        '{USB_VENDOR}:{DFU_PRODUCT}"'
    ) in deployer
    assert f'"{paired}"' in binding
    assert f"-d {paired}" in flashing
    assert "if device.serial and device.serial != serial:" in deployer
    assert "DFU USB serial differs from the pre-attested radio" in deployer


def test_rc12_bundle_upload_does_not_require_github_attestation() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")

    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow


def test_rc12_docs_preserve_exact_build_and_ram_without_receipt_history() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")
    sources = (releasing, notes, plan, runner)
    rc11_lock = "refs/tags/tandem-agc-v8-rc11-source/firmware-v1"
    rc12_lock = "refs/tags/tandem-agc-v8-rc12-source/firmware-v1"
    rc13_lock = "refs/tags/tandem-agc-v8-rc13-source/firmware-v1"

    assert "The active candidate is RC21" in releasing
    for source in sources:
        assert rc11_lock in source
        assert rc12_lock in source
        assert "4c332666ff054e21e10c1a8137fd5f1cbc73b568" in source
        assert "32970312166" in source
        assert (
            "ef8017c539f42d936bcde054e85864e331d4b383167201573c30419d98100831" in source
        )
        assert (
            "1dd94789dddefb7220caad75fb063ad0fdd2a8f3204f2f4fa48bd1cca2d31481" in source
        )
        assert "zero candidate deployments" in source
        assert "12261ed055d4488d64aa7ff5353b680a37c3f93d" in source
        assert "32978460325" in source
        assert "9611124509" in source
        assert (
            "a339c99eb7d16980b33249d5a8a5e8c0693a4d22cbf6333c5ce0b3aa2b0151cd" in source
        )
        assert (
            "789aa4d9e8fc672a2040abeee89a34de5f62dafd9e933628ac09d0aac21444c2" in source
        )
        assert (
            "6ffe6ddf898986b1fd6629db796b6b10422a4e5a00da268e0f63d1d258db52a0" in source
        )
        assert (
            "5db1c49f954e630e4d2a41860bc6bf3f1a6e58749c5c382398caa30887781957" in source
        )
        assert "one observed successful RC12 RAM deployment" in source
        assert "zero valid receipt-authorized deployments" in source
        assert "not hardware-qualified" in source
    for source in (releasing, notes, plan):
        assert rc13_lock in source

    assert "non-zero exit status 64 before transferring" in notes
    assert "File ID `0456:b673` does not match device" in notes
    assert "before transferring any candidate bytes" in notes
    assert "no retained selector-failure log" in notes
    assert "persistent RC1" in notes
    assert "postboot and cleanup SSH" in notes
    assert "/etc/init.d/S50dropbear" in notes
    assert "no persistent host key" in notes
    assert "no deployment receipt" in notes
    assert "no preboot QSPI digest" in notes
    assert "postboot QSPI equality is not claimed" in notes


def test_kalman_handoff_matches_the_current_bundle_checksum_contract() -> None:
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "The RC21 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner
