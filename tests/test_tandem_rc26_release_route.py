"""Offline oracles for the protected tandem AGC v8 RC26 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC25_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc25-source.yaml"
RC26_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc26-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
CAMPAIGN = ROOT / "tests" / "radio_hardware" / "release_campaign.py"
CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
CLI_ORACLES = ROOT / "tests" / "radio_hardware" / "test_release_cli_oracles.py"
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


def test_rc26_reuses_the_exact_rc25_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC26_MANIFEST)
        == _manifest_values(RC25_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc26_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc26"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc26-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc26'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc26'") == 1
    assert "Require the exact protected RC26 reproduction identity" in workflow
    assert "Require the exact protected RC25 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc25"
    )


def test_rc26_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc26_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc26-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc26-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc26" in package


def test_rc26_keeps_four_authorizing_bands_and_nonbinding_2450() -> None:
    campaign = CAMPAIGN.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    cli = CLI.read_text(encoding="utf-8")
    for center in (
        "1_050_000_000",
        "1_550_000_000",
        "2_050_000_000",
        "5_800_000_000",
    ):
        assert center in campaign
        assert center in evidence
    assert 'DIAGNOSTIC_PHASE = "diagnostic-2450"' in cli
    assert 'DIAGNOSTIC_FAIL = "diagnostic_failed"' in cli
    assert '"release_claim": "none_at_2_4_ghz"' in evidence
    assert "rf_quality_only_failure_is_recorded_and_nonbinding" in evidence


def test_rc26_replay_matches_the_frozen_transient_window_policy() -> None:
    cli = CLI.read_text(encoding="utf-8")
    oracles = CLI_ORACLES.read_text(encoding="utf-8")
    assert "initial_unrepresented < 0" in cli
    assert "initial_unrepresented != 0" not in cli
    assert "invalid quality outside a command bracket" not in cli
    assert "_tandem_batch_rf_quality_policy" in cli
    assert (
        "test_production_validator_accepts_startup_conditioning_and_diagnostic_rf"
        in oracles
    )
    assert "startup_hidden_transition=True" in oracles
    assert "diagnostic_overload_frame=17" in oracles


def test_rc26_docs_preserve_truthful_results_while_rc28_is_active() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33062658275" in notes
    assert "four exact-serial RAM deployments" in notes
    assert "ENODATA" in notes
    assert "RC26" in notes and "not hardware-qualified" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC28" in text or "forward-only RC28" in text


def test_rc26_route_remains_reproducible_while_rc28_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc28" in evidence
    assert "refs/tags/tandem-agc-v8-rc28-source/firmware-v1" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC26 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
