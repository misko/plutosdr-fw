"""Offline oracles for the protected tandem AGC v8 RC22 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC21_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc21-source.yaml"
RC22_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc22-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
CAMPAIGN = ROOT / "tests" / "radio_hardware" / "release_campaign.py"
CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
RTL = ROOT / "hdl-tandem" / "tandem_agc_core.v"
STRESS = ROOT / "hdl-tandem" / "tb_tandem_agc_stress.v"
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


def test_rc22_reuses_the_exact_rc21_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC22_MANIFEST)
        == _manifest_values(RC21_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc22_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc22"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc22-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc22'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc22'") == 1
    assert "Require the exact protected RC24 candidate identity" in workflow
    assert "Require the exact protected RC22 reproduction identity" in workflow
    assert "Require the exact protected RC21 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc21"
    )


def test_rc22_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc22_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc22-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc22-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc22" in package


def test_rc22_keeps_four_authorizing_bands_and_nonbinding_2450() -> None:
    campaign = CAMPAIGN.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    cli = CLI.read_text(encoding="utf-8")
    for center in ("1_050_000_000", "1_550_000_000", "2_050_000_000", "5_800_000_000"):
        assert center in campaign
        assert center in evidence
    assert 'DIAGNOSTIC_PHASE = "diagnostic-2450"' in cli
    assert 'DIAGNOSTIC_FAIL = "diagnostic_failed"' in cli
    assert '"release_claim": "none_at_2_4_ghz"' in evidence
    assert "rf_quality_only_failure_is_recorded_and_nonbinding" in evidence


def test_rc22_fixes_and_regresses_the_exact_power_period_contract() -> None:
    rtl = RTL.read_text(encoding="utf-8")
    stress = STRESS.read_text(encoding="utf-8")
    assert "pwr_div >= (cfg_pwr_period - 20'd1)" in rtl
    assert "wire may_decide = decision_eligible && pwr_tick;" in rtl
    assert "minimum event spacing is (N+1)*cfg_pwr_period samples" in rtl
    assert "power-measurement tick period equals cfg_pwr_period exactly" in stress
    assert "cooldown decisions obey exact (cooldown+1)*power-period spacing" in stress
    assert "(event_sample1 - event_sample0) == 64'd204" in stress


def test_rc22_docs_preserve_truthful_rc21_hardware_failure() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "16,400" in notes
    assert "17,408" in notes
    assert "RC21" in notes and "not hardware-qualified" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC24" in text or "forward-only RC24" in text


def test_rc22_reproduction_identity_and_attestation_policy_are_exact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    manifest = RC22_MANIFEST.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc22" in workflow
    assert "RC22 is RAM-only" in manifest
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
