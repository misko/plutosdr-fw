"""Offline oracles for the protected tandem AGC v8 RC31 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC30_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc30-source.yaml"
RC31_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc31-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
WRAPPER = ROOT / "scripts" / "deploy_tandem_agc_ram_hardware.sh"
BINDING = ROOT / "tests" / "radio_hardware" / "pluto_plus_candidate.py"
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


def test_rc31_reuses_the_exact_rc30_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC31_MANIFEST)
        == _manifest_values(RC30_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc31_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc31"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc31-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc31'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc31'") == 1
    assert "Require the exact protected RC31 reproduction identity" in workflow
    assert "Require the exact protected RC30 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc30"
    )


def test_rc31_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc31_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc31-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc31-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc31" in package


def test_rc31_preserves_its_tool_while_the_current_tool_advances() -> None:
    historical = "b2b3113c2e8724453179f09d357b4917c0f14c77"
    current = "4a9c761f3f974a96855589f7a3e867a790dce3f1"
    assert current in WRAPPER.read_text(encoding="utf-8")
    assert current in BINDING.read_text(encoding="utf-8")
    manifest = RC31_MANIFEST.read_text(encoding="utf-8")
    assert historical in manifest
    assert "exact serial from a mixed USB scan" in manifest
    assert "absence, duplicate serial, non-Plus selection" in manifest


def test_rc31_docs_preserve_truthful_rc30_result_and_rc32_active_identity() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33097467689" in notes
    assert "RC30" in notes and "zero candidate deployments" in notes
    assert "b2b3113c2e8724453179f09d357b4917c0f14c77" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC32" in text or "forward-only RC32" in text


def test_rc31_route_is_preserved_while_evidence_advances_to_rc32() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v2" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC32 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
