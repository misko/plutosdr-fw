"""Offline oracles for the protected tandem AGC v8 RC13 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC11_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc11-source.yaml"
RC12_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc12-source.yaml"
RC13_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc13-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"
RELEASING = ROOT / "RELEASING.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
RELEASE_PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN_RUNNER = ROOT / "KALMAN_GITHUB_RUNNER.md"
FLASHING = ROOT / "flashing.md"
DEPLOY_WRAPPER = ROOT / "scripts" / "deploy_tandem_agc_ram_hardware.sh"
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


def test_rc13_reuses_only_the_reviewed_rc12_external_source_graph() -> None:
    rc11 = _manifest_values(RC11_MANIFEST)
    rc12 = _manifest_values(RC12_MANIFEST)
    rc13 = _manifest_values(RC13_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc13 == rc12 == rc11 == final
    assert rc13["schema"] == "plutosdr-fw.source-manifest"
    assert rc13["schema_version"] == "1"
    assert rc13["release_state"] == "candidate"
    assert "release_tag" not in rc13


def test_rc13_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc13"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc13-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc13'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc13'") == 1
    assert "Require the exact protected RC13 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc12"
    )
    assert workflow.index("tandem-agc-v8-rc13-source.yaml") < workflow.index(
        "tandem-agc-v8-rc12-source.yaml"
    )


def test_rc13_route_and_source_graph_are_required_offline_checks() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert "tests/test_tandem_rc13_release_route.py" in checker
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc13-source.yaml"
        in checker
    )


def test_rc13_keeps_paired_dfu_and_exact_receipt_v4_ssh_policy() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    binding = CANDIDATE_BINDING.read_text(encoding="utf-8")
    flashing = FLASHING.read_text(encoding="utf-8")
    wrapper = DEPLOY_WRAPPER.read_text(encoding="utf-8")
    paired = "0456:b673,0456:b674"
    ssh_policy = (
        "BatchMode=no",
        "NumberOfPasswordPrompts=1",
        "PreferredAuthentications=password",
        "PasswordAuthentication=yes",
        "PubkeyAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "StrictHostKeyChecking=no",
        "UserKnownHostsFile=/dev/null",
        "GlobalKnownHostsFile=/dev/null",
        "CheckHostIP=no",
        "UpdateHostKeys=no",
    )

    assert (
        'DFU_DEVICE_SELECTOR = f"{USB_VENDOR}:{RUNTIME_PRODUCT},'
        '{USB_VENDOR}:{DFU_PRODUCT}"'
    ) in deployer
    assert f'"{paired}"' in binding
    assert f"-d {paired}" in flashing
    assert "RAM_BOOT_RECEIPT_SCHEMA_VERSION = 4" in binding
    assert '"sshpass",\n        "-f",' in deployer
    assert '"sshpass",\n        "-f",' in binding
    assert '"-B",\n        interface,' in deployer
    assert '"-B",\n        network_interface,' in binding
    for option in ssh_policy:
        assert deployer.count(f'"{option}"') == 1
        assert binding.count(f'"{option}"') == 1
    assert "host-key checking is disabled" in wrapper


def test_rc13_removes_known_hosts_receipt_field_and_cli_inputs() -> None:
    deployer = DEPLOYER.read_text(encoding="utf-8")
    binding = CANDIDATE_BINDING.read_text(encoding="utf-8")
    wrapper = DEPLOY_WRAPPER.read_text(encoding="utf-8")

    for source in (deployer, binding):
        assert "known_hosts_sha256" not in source
        assert "known_hosts_path" not in source
    for source in (deployer, wrapper):
        assert "--known-hosts" not in source
        assert "--known-hosts-sha256" not in source
    assert "StrictHostKeyChecking=yes" not in deployer
    assert "StrictHostKeyChecking=yes" not in binding


def test_rc13_bundle_handoff_records_github_attestation_not_performed() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner


def test_rc13_docs_preserve_exact_rc12_build_and_ram_incident() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")
    sources = (releasing, notes, plan, runner)
    exact_history = (
        "refs/tags/tandem-agc-v8-rc12-source/firmware-v1",
        "12261ed055d4488d64aa7ff5353b680a37c3f93d",
        "32978460325",
        "9611124509",
        "a339c99eb7d16980b33249d5a8a5e8c0693a4d22cbf6333c5ce0b3aa2b0151cd",
        "789aa4d9e8fc672a2040abeee89a34de5f62dafd9e933628ac09d0aac21444c2",
        "6ffe6ddf898986b1fd6629db796b6b10422a4e5a00da268e0f63d1d258db52a0",
        "5db1c49f954e630e4d2a41860bc6bf3f1a6e58749c5c382398caa30887781957",
    )
    incident_terms = (
        "winbond-db6968136727402c",
        "one observed successful RC12 RAM deployment",
        "zero valid receipt-authorized deployments",
        "not hardware-qualified",
        "/etc/init.d/S50dropbear",
        "no persistent host key",
        "postboot and cleanup SSH",
        "no deployment receipt",
        "no preboot QSPI digest",
        "postboot QSPI equality is not claimed",
    )

    assert "The active candidate is RC29" in releasing
    for source in sources:
        for exact_value in exact_history:
            assert exact_value in source
        for wording in incident_terms[:4]:
            assert wording in source
    for wording in incident_terms[4:]:
        assert wording in notes

    assert "first attempt" in notes
    assert "before reboot or DFU" in notes
    assert "paired-selector `-D` and `-e`" in notes
    assert "returned exact `0456:b673`" in notes
    assert "exited 255" in notes
    assert "The active candidate is RC29" in plan
    assert "refs/tags/tandem-agc-v8-rc22-source/firmware-v1" in releasing
    assert "refs/tags/tandem-agc-v8-rc22-source/firmware-v1" in notes
    assert "refs/tags/tandem-agc-v8-rc22-source/firmware-v1" in plan
