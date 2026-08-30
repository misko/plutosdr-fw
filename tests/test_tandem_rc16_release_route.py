"""Offline oracles for the protected tandem AGC v8 RC16 recovery route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC15_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc15-source.yaml"
RC16_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc16-source.yaml"
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


def test_rc16_reuses_the_exact_rc15_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC16_MANIFEST)
        == _manifest_values(RC15_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc16_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc16"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc16-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc16'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc16'") == 1
    assert "Require the exact protected RC16 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc15"
    )


def test_rc16_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc16_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc16-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc16-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc16" in package


def test_rc16_preserves_its_utility_while_the_current_tool_advances() -> None:
    historical = "2654f34eb909904ec65bc0526e0f8977cb30e2ed"
    assert historical in RC16_MANIFEST.read_text(encoding="utf-8")
    current = "4a9c761f3f974a96855589f7a3e867a790dce3f1"
    for path in (WRAPPER, BINDING):
        assert current in path.read_text(encoding="utf-8")
    assert 'pluto firmware candidate-ram "$@"' in WRAPPER.read_text(encoding="utf-8")


def test_rc16_history_is_retained_while_rc20_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v2" in evidence
    for source in sources:
        assert "RC16" in source
        assert "pluto-plus-utils" in source
    assert "2654f34eb909904ec65bc0526e0f8977cb30e2ed" in RC16_MANIFEST.read_text(
        encoding="utf-8"
    )
    assert "The active candidate is RC32" in sources[0]
    assert "RC15" in sources[1]


def test_rc16_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
