"""Offline oracles for the protected tandem AGC v8 RC15 utility route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC14_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc14-source.yaml"
RC15_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc15-source.yaml"
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


def test_rc15_reuses_the_exact_rc14_and_final_external_source_graph() -> None:
    rc14 = _manifest_values(RC14_MANIFEST)
    rc15 = _manifest_values(RC15_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc15 == rc14 == final
    assert rc15["release_state"] == "candidate"
    assert "release_tag" not in rc15


def test_rc15_owner_route_maps_branch_manifest_package_and_version_together() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc15"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc15-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc15'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc15'") == 1
    assert "Require the exact protected RC15 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc14"
    )


def test_rc15_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")

    assert "tests/test_tandem_rc15_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc15-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc15-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc15" in package


def test_rc15_preserves_its_burned_utility_while_rc16_advances() -> None:
    expected = "5ab8361211e747387c5dfa854f5ae65a6a4dac87"
    assert expected in RC15_MANIFEST.read_text(encoding="utf-8")
    advanced = "2654f34eb909904ec65bc0526e0f8977cb30e2ed"
    for path in (WRAPPER, BINDING):
        assert advanced in path.read_text(encoding="utf-8")
    source = BINDING.read_text(encoding="utf-8")
    assert "pluto-plus-utils.release-candidate-ram-receipt.v1" in source
    assert 'pluto firmware candidate-ram "$@"' in WRAPPER.read_text(encoding="utf-8")


def test_rc15_history_is_retained_while_rc16_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )

    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc17" in evidence
    assert "refs/tags/tandem-agc-v8-rc17-source/firmware-v1" in evidence
    for source in sources:
        assert "RC15" in source
        assert "pluto-plus-utils" in source
    assert "The active candidate is RC17" in sources[0]
    assert "zero RC14 RAM transitions" in sources[1]


def test_rc15_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")

    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC17 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
