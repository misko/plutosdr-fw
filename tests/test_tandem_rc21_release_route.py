"""Offline oracles for the protected tandem AGC v8 RC21 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC20_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc20-source.yaml"
RC21_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc21-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
CAMPAIGN = ROOT / "tests" / "radio_hardware" / "release_campaign.py"
CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
RELEASING = ROOT / "RELEASING.md"
NOTES = ROOT / "RELEASE_NOTES.md"
DEPLOY_PLAN = ROOT / "RC21_plus_deploy_plan.md"
KALMAN = ROOT / "KALMAN_GITHUB_RUNNER.md"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc21_reuses_the_exact_rc20_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC21_MANIFEST)
        == _manifest_values(RC20_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc21_owner_route_remains_an_exact_reproduction_mapping() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc21"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc21-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc21'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc21'") == 1
    assert "Require the exact protected RC21 reproduction identity" in workflow
    assert "Require the exact protected RC20 reproduction identity" in workflow
    assert workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc22"
    ) < workflow.index(branch)
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc20"
    )


def test_rc21_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc21_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc21-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc21-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc21" in package


def test_rc21_four_band_authorization_and_2450_diagnostic_are_exact() -> None:
    campaign = CAMPAIGN.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    cli = CLI.read_text(encoding="utf-8")
    exact_centers = ("1_050_000_000", "1_550_000_000", "2_050_000_000", "5_800_000_000")
    for center in exact_centers:
        assert center in campaign
        assert center in evidence
    assert 'AGGREGATE_SCHEMA = "plutosdr-fw.tandem-agc-release-hardware.v2"' in cli
    assert 'DIAGNOSTIC_PHASE = "diagnostic-2450"' in cli
    assert 'DIAGNOSTIC_FAIL = "diagnostic_failed"' in cli
    assert '"release_claim": "none_at_2_4_ghz"' in evidence
    assert "rf_quality_only_failure_is_recorded_and_nonbinding" in evidence


def test_rc21_hardware_failure_is_immutable_and_docs_name_rc25_active() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    releasing = RELEASING.read_text(encoding="utf-8")
    deploy_plan = DEPLOY_PLAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc21" in deploy_plan
    assert "16,400" in notes and "17,408" in notes
    assert "not hardware-qualified" in notes
    assert "The active candidate is RC25" in releasing


def test_rc21_reproduction_keeps_single_owner_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
