"""Offline oracles for the protected tandem AGC v8 RC25 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC24_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc24-source.yaml"
RC25_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc25-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
CAMPAIGN = ROOT / "tests" / "radio_hardware" / "release_campaign.py"
CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
EXPERIMENT = ROOT / "tests" / "radio_hardware" / "experiment.py"
TRANSIENT = ROOT / "tests" / "radio_hardware" / "transient_hardware.py"
TRANSIENT_ORACLES = (
    ROOT / "tests" / "radio_hardware" / "test_transient_hardware_oracles.py"
)
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


def test_rc25_reuses_the_exact_rc24_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC25_MANIFEST)
        == _manifest_values(RC24_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc25_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc25"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc25-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc25'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc25'") == 1
    assert "Require the exact protected RC25 reproduction identity" in workflow
    assert "Require the exact protected RC24 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc24"
    )


def test_rc25_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc25_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc25-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc25-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc25" in package


def test_rc25_keeps_four_authorizing_bands_and_nonbinding_2450() -> None:
    campaign = CAMPAIGN.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    cli = CLI.read_text(encoding="utf-8")
    for center in (
        "1_050_000_000",
        "1_550_000_000",
        "2_050_000_000",
        "4_200_000_000",
    ):
        assert center in campaign
        assert center in evidence
    assert 'DIAGNOSTIC_PHASE = "diagnostic-2450"' in cli
    assert 'DIAGNOSTIC_FAIL = "diagnostic_failed"' in cli
    assert '"release_claim": "none_at_2_4_ghz"' in evidence
    assert "rf_quality_only_failure_is_recorded_and_nonbinding" in evidence


def test_rc25_rejects_torn_status_and_retains_close_failure_metadata() -> None:
    experiment = EXPERIMENT.read_text(encoding="utf-8")
    transient = TRANSIENT.read_text(encoding="utf-8")
    oracles = TRANSIENT_ORACLES.read_text(encoding="utf-8")
    assert "TANDEM_STATUS_SNAPSHOT_ATTEMPTS = 16" in experiment
    assert "transition_before == transition_after" in experiment
    assert "rx1_gain_index == rx2_gain_index" in experiment
    assert "did not produce a coherent snapshot" in experiment
    assert "if frames:" in transient
    assert "test_live_tandem_status_retries_a_cross_attribute_transition" in oracles
    assert "test_live_tandem_status_rejects_permanent_cross_attribute_churn" in oracles
    assert 'persisted["failure_evidence"]["batch_frames"][-1]' in oracles


def test_rc25_docs_preserve_truthful_rc24_and_rc25_hardware_results() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33053594379" in notes
    assert "manual, native-slow, and native-fast" in notes
    assert "RC24" in notes and "not hardware-qualified" in notes
    assert "33058150539" in notes
    assert "all four comparison modes" in notes
    assert "outer release replay" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC32" in text or "forward-only RC32" in text


def test_rc25_route_remains_reproducible_while_rc31_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v2" in evidence
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc25" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC25 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
