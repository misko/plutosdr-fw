"""Offline oracles for the protected tandem AGC v8 RC30 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC29_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc29-source.yaml"
RC30_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc30-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
CAMPAIGN = ROOT / "tests" / "radio_hardware" / "release_campaign.py"
RELEASE_CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
RELEASE_CLI_ORACLES = ROOT / "tests" / "radio_hardware" / "test_release_cli_oracles.py"
RELEASING = ROOT / "RELEASING.md"
NOTES = ROOT / "RELEASE_NOTES.md"
PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN = ROOT / "KALMAN_GITHUB_RUNNER.md"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc30_reuses_the_exact_rc29_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC30_MANIFEST)
        == _manifest_values(RC29_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc30_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc30"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc30-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc30'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc30'") == 1
    assert "Require the exact protected RC30 candidate identity" in workflow
    assert "Require the exact protected RC29 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc29"
    )


def test_rc30_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc30_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc30-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc30-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc30" in package


def test_rc30_qualification_policy_matches_non_authorizing_replays() -> None:
    campaign = CAMPAIGN.read_text(encoding="utf-8")
    release_cli = RELEASE_CLI.read_text(encoding="utf-8")
    oracles = RELEASE_CLI_ORACLES.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    assert 'BandCase("table3-sentinel-4200mhz", 4_200_000_000)' in campaign
    assert "COOLDOWN_ZERO_MINIMUM_KERNEL_BUFFERS = 48" in campaign
    assert "_STEADY_MATRIX_STABLE_FRAMES = 8" in release_cli
    assert "if run.policy.name == \"cooldown-0\"" in oracles
    assert '"name": "table3-sentinel-4200mhz"' in evidence
    assert '"center_frequency_hz": 4_200_000_000' in evidence


def test_rc30_docs_preserve_truthful_rc29_failure_and_active_identity() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33080376518" in notes
    assert "RC29" in notes and "not hardware-qualified" in notes
    assert "48-buffer" in notes
    assert "4.2-GHz" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC30" in text or "forward-only RC30" in text


def test_rc30_evidence_identity_and_attestation_policy_are_exact() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc30" in evidence
    assert "refs/tags/tandem-agc-v8-rc30-source/firmware-v1" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC30 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
