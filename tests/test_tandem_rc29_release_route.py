"""Offline oracles for the protected tandem AGC v8 RC29 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC28_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc28-source.yaml"
RC29_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc29-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
MODULATED = ROOT / "tests" / "radio_hardware" / "modulated_hardware.py"
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


def test_rc29_reuses_the_exact_rc28_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC29_MANIFEST)
        == _manifest_values(RC28_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc29_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc29"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc29-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc29'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc29'") == 1
    assert "Require the exact protected RC29 candidate identity" in workflow
    assert "Require the exact protected RC28 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc28"
    )


def test_rc29_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc29_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc29-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc29-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc29" in package


def test_rc29_uses_the_proven_ad9361_modulated_configuration() -> None:
    modulated = MODULATED.read_text(encoding="utf-8")
    oracles = RELEASE_CLI_ORACLES.read_text(encoding="utf-8")
    assert "sample_rate_hz: int = 2_500_000" in modulated
    assert "samples_per_symbol: int = 8" in modulated
    assert "BlockerPoint(offset_hz=390_625.0" in modulated
    assert "kernel_buffers: int = 16" in modulated
    assert "options.sample_rate_hz < 2_500_000" in modulated
    assert "modulated.sample_rate_hz == 2_500_000" in oracles
    assert "modulated.samples_per_symbol == 8" in oracles
    assert "modulated.kernel_buffers == 16" in oracles
    assert "offset_hz=390_625.0" in oracles


def test_rc29_docs_preserve_truthful_rc28_result_and_active_identity() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33072902542" in notes
    assert "all 44 authorizing steady matrices" in notes
    assert "1,024,000-S/s" in notes
    assert "2,500,000 S/s" in notes
    assert "RC28" in notes and "not hardware-qualified" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC29" in text or "forward-only RC29" in text


def test_rc29_evidence_identity_and_attestation_policy_are_exact() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc29" in evidence
    assert "refs/tags/tandem-agc-v8-rc29-source/firmware-v1" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC29 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
