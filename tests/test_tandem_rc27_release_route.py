"""Offline oracles for the protected tandem AGC v8 RC27 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC26_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc26-source.yaml"
RC27_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc27-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
EXPERIMENT = ROOT / "tests" / "radio_hardware" / "experiment.py"
FOLLOWUP_ORACLES = ROOT / "tests" / "radio_hardware" / "test_tandem_followup_oracles.py"
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


def test_rc27_reuses_the_exact_rc26_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC27_MANIFEST)
        == _manifest_values(RC26_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc27_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc27"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc27-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc27'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc27'") == 1
    assert "Require the exact protected RC27 candidate identity" in workflow
    assert "Require the exact protected RC26 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc26"
    )


def test_rc27_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc27_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc27-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc27-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc27" in package


def test_rc27_retries_only_metadata_buffer_enodata_with_the_existing_bound() -> None:
    experiment = EXPERIMENT.read_text(encoding="utf-8")
    oracles = FOLLOWUP_ORACLES.read_text(encoding="utf-8")
    assert "metadata and error.errno == errno.ENODATA" in experiment
    assert "attempt == 64" in experiment
    assert "test_metadata_refill_boundedly_discards_provider_omissions" in oracles
    assert "test_ordinary_refill_keeps_enodata_fatal" in oracles
    assert "test_metadata_refill_enodata_retry_is_strictly_bounded" in oracles


def test_rc27_keeps_continuity_quality_and_2450_policy_strict() -> None:
    experiment = EXPERIMENT.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    assert "next accepted frame's" in experiment
    assert "sequence exposes the gap to the continuity" in experiment
    assert '"release_claim": "none_at_2_4_ghz"' in evidence
    assert "rf_quality_only_failure_is_recorded_and_nonbinding" in evidence
    assert "1_050_000_000" in evidence
    assert "5_800_000_000" in evidence


def test_rc27_docs_preserve_truthful_rc26_results_and_active_identity() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33062658275" in notes
    assert "four exact-serial RAM deployments" in notes
    assert "ENODATA" in notes
    assert "RC26" in notes and "not hardware-qualified" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC27" in text or "forward-only RC27" in text


def test_rc27_evidence_identity_and_attestation_policy_are_exact() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc27" in evidence
    assert "refs/tags/tandem-agc-v8-rc27-source/firmware-v1" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC27 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
