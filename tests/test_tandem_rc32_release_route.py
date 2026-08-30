"""Offline oracles for the protected tandem AGC v8 RC32 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC31_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc31-source.yaml"
RC32_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc32-source.yaml"
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


def test_rc32_reuses_the_exact_rc31_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC32_MANIFEST)
        == _manifest_values(RC31_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc32_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc32"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc32-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc32'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc32'") == 1
    assert "Require the exact protected RC32 candidate identity" in workflow
    assert "Require the exact protected RC31 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc31"
    )


def test_rc32_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc32_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc32-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc32-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in package


def test_rc32_preserves_its_tool_while_the_current_tool_advances() -> None:
    historical = "b2b3113c2e8724453179f09d357b4917c0f14c77"
    current = "97487a04810ea120e4071146d8a14ee95f0fcecd"
    assert current in WRAPPER.read_text(encoding="utf-8")
    assert current in BINDING.read_text(encoding="utf-8")
    assert historical in RC32_MANIFEST.read_text(encoding="utf-8")


def test_rc32_docs_preserve_rc31_result_and_active_identity() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33101253206" in notes
    assert "RC31" in notes and "4.2 GHz" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC32" in text or "forward-only RC32" in text


def test_rc32_evidence_identity_and_attestation_policy_are_exact() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v2" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC32 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
